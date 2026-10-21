"""Signed distance near edges and corners: opus_bl.geom against the exact answer, and the old
closest-face-normal sign for comparison.

    blender -b --factory-startup --python sdf_probe.py -- modules out.json
"""

import json
import math
import sys
import time

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

modules, out = sys.argv[sys.argv.index("--") + 1 :][:2]
sys.path.insert(0, modules)
from opus_bl import geom  # noqa: E402

rng = np.random.default_rng(7)


def old_sign(bvh, p) -> float:
    """The v0.3 method: the sign of (p - closest) . normal of whichever face the BVH returns."""
    loc, normal, _, dist = bvh.find_nearest(Vector(p))
    return dist if (Vector(p) - loc).dot(normal) >= 0 else -dist


def box_mesh(half, m):
    q = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], float) * half
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
    M = np.array(m)
    return q @ M[:3, :3].T + M[:3, 3], np.array(tris)


def box_sdf(q, half):
    d = np.abs(q) - half
    return np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(axis=1), 0)


def score(name, solid, pts, truth, extra=None, old_bvh=None):
    t = time.time()
    new = solid.signed(pts)
    dt = time.time() - t
    one = np.array([solid.signed1(p) for p in pts])
    old = np.array([old_sign(old_bvh or solid.bvh, p) for p in pts])
    sgn = np.sign(truth)
    return {"case": name, "points": int(len(pts)), "outside": int((truth > 0).sum()), "inside": int((truth < 0).sum()),
            "new_wrong": int((np.sign(new) != sgn).sum()), "one_wrong": int((np.sign(one) != sgn).sum()),
            "old_wrong": int((np.sign(old) != sgn).sum()),
            "max_err": float(np.abs(new - truth).max()), "one_vs_batch": float(np.abs(one - new).max()),
            "us_per_point": round(dt / len(pts) * 1e6, 1), **(extra or {})}


results = []

# 1. a cube (2 m), turned off the axes, sampled near its edges and corners; a third of the
#    outside points lie in the plane of a face beyond its edge, where the old sign is a coin toss
half = np.array([1.0, 1.0, 1.0])
M = Matrix.Translation((0.3, -0.2, 0.5)) @ Euler((0.4, 0.7, 1.1)).to_matrix().to_4x4()
co, tris = box_mesh(half, M)
cube = geom.Solid(co, tris)
q = []
for _ in range(3000):
    corner = rng.choice([-1.0, 1.0], 3)
    k = rng.integers(3)
    p = corner * half
    if rng.random() < 0.5:  # along an edge
        p[k] = rng.uniform(-0.9, 0.9)
    p = p + rng.normal(0, 0.15, 3)
    if rng.random() < 0.33:  # in a face's plane, beyond its edge
        j = rng.integers(3)
        p[j] = corner[j] * half[j]
    q.append(p)
q = np.array(q)
truth = box_sdf(q, half)
keep = np.abs(truth) > 1e-6
q, truth = q[keep], truth[keep]
Mn = np.array(M)
pts = q @ Mn[:3, :3].T + Mn[:3, 3]
results.append(score("cube, rotated, near edges and corners", cube, pts, truth, {"closed": not cube.open.any()}))

# the same cube on the axes: the old sign only breaks at exact ties here
co, tris = box_mesh(half, Matrix())
results.append(score("cube, axis-aligned", geom.Solid(co, tris), q, truth))

# 2. a blade-like wedge with a 30 degree edge: outside points all around the sharp edge
h = math.tan(math.radians(15))
co = np.array([(0, -1, -h), (1, -1, 0), (0, -1, h), (0, 1, -h), (1, 1, 0), (0, 1, h)], float)
tris = np.array([(0, 2, 1), (3, 4, 5), (0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5)])[:, ::-1]
wedge = geom.Solid(co, tris)
pts, truth = [], []
for ang in np.linspace(-82, 82, 41):
    for y in np.linspace(-0.8, 0.8, 9):
        for r in (0.002, 0.05):
            d = np.array([math.cos(math.radians(ang)), 0, math.sin(math.radians(ang))])
            pts.append(np.array([1, y, 0]) + d * r)
            truth.append(r)  # within the edge's outside wedge (|ang| < 75 deg) the edge is closest
        pts.append(np.array([0.9, y, 0.0]))  # inside, near the edge
        truth.append(-math.sin(math.radians(15)) * 0.1)
pts, truth = np.array(pts), np.array(truth)
far = np.abs(np.linspace(-82, 82, 41)) > 75  # beyond 75 deg a face is closest; keep only the sign
results.append(score("wedge, 30 degree edge", wedge, pts, truth, {"closed": not wedge.open.any()}))
results[-1]["max_err"] = float(np.abs(np.abs(wedge.signed(pts)) - np.abs(truth))[np.repeat(~far, 9 * 3)].max())

# 3. an open box (one face missing): the winding number decides inside
co, tris = box_mesh(half, Matrix())
open_box = geom.Solid(co, tris[2:])
q = rng.uniform(-1.4, 1.4, (600, 3))
q = q[np.abs(box_sdf(q, half)) > 0.02]
results.append(score("open box, winding number", open_box, q, box_sdf(q, half), {"closed": not open_box.open.any()}))
results[-1].pop("max_err")  # the missing face changes distances, not the side

# 4. two overlapping cubes as loose parts of one mesh: inside one while the other's buried
#    face is nearer still counts as inside
co1, t1 = box_mesh(half, Matrix())
co2, t2 = box_mesh(half, Matrix.Translation((1.5, 0, 0)))
union = geom.Solid(np.concatenate([co1, co2]), np.concatenate([t1, t2 + 8]))
q = np.array([[0.45, 0.0, 0.0], [0.55, 0.3, 0.2], [0.9, -0.5, 0.1], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [-1.2, 0.0, 0.0]])
truth = np.minimum(box_sdf(q, half), box_sdf(q - [1.5, 0, 0], half))
results.append(score("two overlapping cubes", union, q, truth, {"parts": union.ncomp}))
results[-1].pop("max_err")  # inside the union the depth is to the deeper part, not the union

# 5. faces turned inward, and an object mirrored by a negative scale: still outward (the old
#    sign read both inside out)
co, tris = box_mesh(half, Matrix())
q = rng.uniform(-1.5, 1.5, (400, 3))
q = q[np.abs(box_sdf(q, half)) > 1e-3]
raw = BVHTree.FromPolygons(co.tolist(), tris[:, ::-1].tolist())
results.append(score("cube, faces turned inward", geom.Solid(co, tris[:, ::-1]), q, box_sdf(q, half), old_bvh=raw))
me = bpy.data.meshes.new("mirrored")
me.from_pydata(co.tolist(), [], tris.tolist())
obj = bpy.data.objects.new("mirrored", me)
bpy.context.scene.collection.objects.link(obj)
obj.scale = (-1.0, 1.0, 1.0)
bpy.context.view_layer.update()
raw = BVHTree.FromPolygons((co * [-1, 1, 1]).tolist(), tris.tolist())
results.append(score("cube, mirrored object", geom.Solid.from_objects([obj]), q, box_sdf(q, half), old_bvh=raw))

# 6. a 4 cm box pushed right through a 2 mm plate: no vertex of either is inside the other,
#    so a closest-point test (old or new sign) sees nothing; triangle overlap does
plate = geom.Solid(*box_mesh(np.array([0.05, 0.05, 0.001]), Matrix()))
box = geom.Solid(*box_mesh(np.array([0.02, 0.02, 0.02]), Matrix.Translation((0.01, 0.005, -0.01))))
pen = geom.penetration(plate, box)
results.append({"case": "box through plate",
                "box_verts_inside": int((plate.signed(box.V) < 0).sum()), "plate_verts_inside": int((box.signed(plate.V) < 0).sum()),
                "old_box_verts_inside": sum(old_sign(plate.bvh, p) < 0 for p in box.V),
                "old_plate_verts_inside": sum(old_sign(box.bvh, p) < 0 for p in plate.V),
                "kind": pen["kind"], "triangles": pen["triangles"], "depth_mm": round(pen["depth"] * 1000, 3),
                "sheet_mm": round(pen["sheet"] * 1000, 3), "thickness_mm": round(pen["thickness"] * 1000, 3)})

with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
