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


def pen_case(name, plate, other, **extra):
    pen = geom.penetration(plate, other)
    return {"case": name, "kind": pen["kind"] if pen else None, "depth_mm": round(pen["depth"] * 1000, 3) if pen else 0.0,
            "sheet_mm": round(pen.get("sheet", 0.0) * 1000, 3) if pen else 0.0, **extra}


def obj_from(name, co, tris):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(co).tolist(), [], np.asarray(tris).tolist())
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


# 7. a cube with one face (2 triangles) reversed, as mesh_lint's flipped_normals finds in
#    user assets: the faces are turned to agree, so the part stays closed and the sign exact
co, tris = box_mesh(half, Matrix())
flipped = tris.copy()
flipped[:2] = flipped[:2, ::-1]
side = geom.Solid(co, flipped)
x0 = co[tris[0]][:, 0].mean()  # the reversed face's plane
q = np.column_stack([x0 * rng.uniform(0.6, 0.99, 500), rng.uniform(-0.8, 0.8, 500), rng.uniform(-0.8, 0.8, 500)])
results.append(score("cube, one face reversed", side, q, box_sdf(q, half), {"closed": not side.open.any()}))

# 8. a curved 3 mm plate (a 120 degree cylinder section, Solidify) and a box whose front face
#    pokes 0.5 mm past the plate's concave side at its middle: a crossing, not "through"
n, R, L = 41, 0.15, 0.3
ring = [(R * math.sin(math.radians(-60 + 120 * i / (n - 1))), -R * math.cos(math.radians(-60 + 120 * i / (n - 1)))) for i in range(n)]
sheet_co = [(x, y, z) for z in (-L / 2, L / 2) for x, y in ring]
sheet_quads = [(k, k + 1, n + k + 1, n + k) for k in range(n - 1)]
me = bpy.data.meshes.new("curved")
me.from_pydata(sheet_co, [], sheet_quads)
curved = bpy.data.objects.new("curved", me)
bpy.context.scene.collection.objects.link(curved)
mod = curved.modifiers.new("solid", "SOLIDIFY")
mod.thickness, mod.offset = 0.003, 1.0
bpy.context.view_layer.update()
shell = geom.Solid.from_objects([curved])
mid = shell.V[np.abs(shell.V[:, 0]) < 1e-9]
inner = float(mid[:, 1].max())  # the concave side faces +Y, toward the axis
sh = shell.shell()
normals = [s_.FN.mean(axis=0) for s_ in sh["sides"]]
torso = geom.Solid(*box_mesh(np.array([0.005, 0.025, 0.005]), Matrix.Translation((0, inner - 0.0005 + 0.025, 0))))
results.append(pen_case("curved plate, box 0.5 mm past its concave side", shell, torso,
                        thickness_mm=round(sh["thickness"] * 1000, 3), sides=len(sh["sides"]),
                        sides_face_apart=bool(len(normals) == 2 and np.dot(normals[0], normals[1]) < -0.5)))

# 9. a 2 mm plate turned 40 random ways, a box sunk 0.05 mm into its top face each time
kinds, deepest, apart = {}, 0.0, 0
for k in range(40):
    M = Matrix.Translation(tuple(rng.uniform(-1, 1, 3))) @ Euler(tuple(rng.uniform(0, 2 * math.pi, 3))).to_matrix().to_4x4()
    plate = geom.Solid(*box_mesh(np.array([0.05, 0.05, 0.001]), M))
    box = geom.Solid(*box_mesh(np.array([0.01, 0.01, 0.01]), M @ Matrix.Translation((0, 0, 0.011 - 0.00005))))
    sh = plate.shell()
    apart += int(np.dot(sh["sides"][0].FN.mean(axis=0), sh["sides"][1].FN.mean(axis=0)) < -0.5)
    pen = geom.penetration(plate, box)
    kinds[pen["kind"]] = kinds.get(pen["kind"], 0) + 1
    deepest = max(deepest, pen["depth"], pen.get("sheet", 0.0))
results.append({"case": "rotated plates, box sunk 0.05 mm", "kinds": kinds, "deepest_mm": round(deepest * 1000, 3),
                "sides_face_apart": apart})

# 10. a C-clamp (one object: two 3 mm jaws and a spine past the rim) whose jaws press 0.05 mm
#     into either face of a 2 mm plate: each jaw sits behind the far sheet without crossing it
e, t = 0.00005, 0.003
plate = geom.Solid(*box_mesh(np.array([0.05, 0.05, 0.001]), Matrix()))
parts = [box_mesh(np.array([0.01, 0.01, t / 2]), Matrix.Translation((0.045, 0, 0.001 - e + t / 2))),
         box_mesh(np.array([0.01, 0.01, t / 2]), Matrix.Translation((0.045, 0, -0.001 + e - t / 2))),
         box_mesh(np.array([0.002, 0.01, 0.001 + t]), Matrix.Translation((0.057, 0, 0)))]
clamp = geom.Solid(np.concatenate([p[0] for p in parts]), np.concatenate([p[1] + 8 * i for i, p in enumerate(parts)]))
results.append(pen_case("clamp, both jaws 0.05 mm into a 2 mm plate", plate, clamp))

# 11. an object scaled to 0 (a common way to hide a part) has no faces: no solid, no crash
good = obj_from("good", *box_mesh(half, Matrix()))
zero = obj_from("zero", *box_mesh(half, Matrix()))
zero.scale = (0.0, 0.0, 0.0)
bpy.context.view_layer.update()
both = geom.Solid.from_objects([good, zero])
#     flattened on one axis instead, its faces weld into a closed sheet with no volume: nothing
#     is inside it, so a box it rests on is not "penetrated"
base = geom.Solid(*box_mesh(np.array([0.5, 0.5, 0.5]), Matrix()))
flat = np.array([(-0.5, 0, 0.5), (0.5, 0, 0.5), (0.5, 0, 0.7), (-0.5, 0, 0.7)])  # front and back on other diagonals
lid = geom.Solid(np.concatenate([flat, flat]), np.array([(0, 1, 2), (0, 2, 3), (7, 6, 5), (7, 5, 4)]))
pen = geom.penetration(base, lid)
results.append({"case": "object scaled to 0", "alone_is_none": geom.Solid.from_objects([zero]) is None,
                "with_another_tris": len(both.T) if both is not None else 0,
                "flat_lid_open": bool(lid.open.all()), "flat_lid_depth_mm": round(pen["depth"] * 1000, 3) if pen else 0.0,
                "flat_lid_inside": int((lid.signed(flat.mean(axis=0) + rng.uniform(-0.05, 0.05, (300, 3))) < 0).sum())})

# 12. a 28,800-triangle handle tube with no end caps: the winding number with distant clusters
#     as dipoles against the exact sum, and what a solver query costs
segs, rings_n, r_t, h_t = 96, 151, 0.016, 0.6
ang = np.linspace(0, 2 * np.pi, segs, endpoint=False)
tube_co = np.array([(r_t * math.cos(a), r_t * math.sin(a), z) for z in np.linspace(-h_t / 2, h_t / 2, rings_n) for a in ang])
tube_tris = []
for i in range(rings_n - 1):
    for j in range(segs):
        a0, a1, b0, b1 = i * segs + j, i * segs + (j + 1) % segs, (i + 1) * segs + j, (i + 1) * segs + (j + 1) % segs
        tube_tris += [(a0, a1, b1), (a0, b1, b0)]
tube = geom.Solid(tube_co, np.array(tube_tris))
q = np.column_stack([rng.uniform(-0.03, 0.03, 600), rng.uniform(-0.03, 0.03, 600), rng.uniform(-0.33, 0.33, 600)])
t0 = time.time()
exact = tube.winding(q)  # all parts: the exact sum
t_exact = (time.time() - t0) / len(q)
fast = tube.winding(q, 0)
clear = np.abs(exact - 0.5) > 0.02
near = q[:200] * [0.55, 0.55, 1.0]  # near the wall, where fingers press
t0 = time.time()
for p in near:
    tube.signed1(p)
t_one = (time.time() - t0) / len(near)
results.append({"case": "open tube, clustered winding", "open": bool(tube.open.all()), "tris": len(tube.T),
                "max_err": float(np.abs(fast - exact).max()), "side_wrong": int(((fast > 0.5) != (exact > 0.5))[clear].sum()),
                "inside": int((exact > 0.5).sum()), "us_exact": round(t_exact * 1e6, 1), "us_signed1": round(t_one * 1e6, 1)})

with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
