"""Mesh Lint: game-readiness checks on the evaluated, world-space geometry of an asset."""

from __future__ import annotations

import math
import os
import re

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from opus_bl import assets

DEFAULT_NAME = re.compile(r"^(Cube|Cylinder|Sphere|Plane|Cone|Torus|Icosphere|Circle|Mesh|Object|Suzanne)(\.\d+)?$")
UV_RASTER = 256
MAX_UV_FACES = 60000
GAP_SAMPLES = 2000  # vertices per piece tested for the gap to another piece
IMPORTED = (".glb", ".gltf", ".fbx", ".obj", ".stl")  # importers split vertices at hard edges and seams


def _finding(out, severity, check, obj, count, message, sample=None, extra=None):
    if count:
        f = {"severity": severity, "check": check, "object": obj, "count": int(count), "message": message}
        if sample:
            f["sample_locations"] = [[round(c, 4) for c in p] for p in sample[:5]]
        f.update(extra or {})
        out.append(f)


def _rigid_bone(obj) -> str | None:
    """The bone ``obj`` hangs on rigidly: it (or an object it is parented to) is parented to a
    bone and no Armature modifier deforms it, the form grip_hold gives a held prop."""
    if any(m.type == "ARMATURE" for m in obj.modifiers):
        return None
    o = obj
    while o is not None:
        if o.parent is not None and o.parent_type == "BONE" and o.parent_bone:
            return o.parent_bone
        o = o.parent
    return None


def _islands(bm) -> list[list[int]]:
    """Vertex indices of each connected piece."""
    parent = list(range(len(bm.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in bm.edges:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b
    groups: dict[int, list[int]] = {}
    for v in bm.verts:
        if v.link_edges:
            groups.setdefault(find(v.index), []).append(v.index)
    return list(groups.values())


def _pieces(bm, name: str) -> list[dict]:
    """Each connected piece of ``bm``: its object, vertices (N x 3), box and BVH (None when it
    has no faces)."""
    islands = _islands(bm)
    label = {}
    for k, island in enumerate(islands):
        for i in island:
            label[i] = k
    faces = [[] for _ in islands]
    for f in bm.faces:
        faces[label[f.verts[0].index]].append(f)
    out = []
    for island, fs in zip(islands, faces):
        local = {i: j for j, i in enumerate(island)}
        co = np.array([bm.verts[i].co[:] for i in island], dtype=float)
        bvh = BVHTree.FromPolygons(co.tolist(), [[local[v.index] for v in f.verts] for f in fs]) if fs else None
        out.append({"object": name, "co": co, "lo": co.min(axis=0), "hi": co.max(axis=0), "bvh": bvh})
    return out


def _gap(p: dict, q: dict, limit: float = math.inf) -> float:
    """How far apart two pieces are: 0 when their surfaces cross or one lies inside the other,
    else the nearest a vertex of either comes to the other's faces. Distances past ``limit``
    are not looked for (inf when nothing is that close)."""
    if p["bvh"] is not None and q["bvh"] is not None and p["bvh"].overlap(q["bvh"]):
        return 0.0
    best = limit
    for a, b in ((p, q), (q, p)):
        if b["bvh"] is None:
            continue
        near = a["co"][np.all((a["co"] >= b["lo"] - best) & (a["co"] <= b["hi"] + best), axis=1)]
        near = near[:: len(near) // GAP_SAMPLES + 1]
        inside = len(near) > 0 and bool(np.all((a["lo"] >= b["lo"]) & (a["hi"] <= b["hi"])))
        for v in near.tolist():
            loc, normal, _, d = b["bvh"].find_nearest(v)
            if loc is None:
                inside = False
                continue
            inside &= (Vector(v) - loc).dot(normal) < 0
            best = min(best, d)
        if inside:  # every vertex is behind the other's faces: embedded in it
            return 0.0
    if p["bvh"] is None and q["bvh"] is None:  # loose edges only: their boxes will do
        best = min(best, float(np.linalg.norm(np.maximum(0, np.maximum(p["lo"] - q["hi"], q["lo"] - p["hi"])))))
    return best if best < limit else math.inf


def _floating(pieces: list[dict], tol: float) -> tuple[list[tuple[int, int, float]], int]:
    """Pieces that float: no chain of pieces touching within ``tol`` joins them to one that
    reaches the asset's lowest point. Returns [(piece, nearest piece it isn't joined to, gap)]
    and the number of pairs of pieces whose surfaces cross."""
    n = len(pieces)
    lo = np.array([p["lo"] for p in pieces])
    hi = np.array([p["hi"] for p in pieces])
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    crossing = 0
    for i in range(n - 1):  # only pieces whose boxes come within tol can touch
        near = np.nonzero(np.all((lo[i + 1 :] <= hi[i] + tol) & (hi[i + 1 :] + tol >= lo[i]), axis=1))[0] + i + 1
        for j in near.tolist():
            a, b = pieces[i]["bvh"], pieces[j]["bvh"]
            if a is not None and b is not None and a.overlap(b):
                crossing += 1
                parent[find(i)] = find(j)
            elif find(i) != find(j) and _gap(pieces[i], pieces[j], tol * 1.0001) <= tol:
                parent[find(i)] = find(j)
    if n < 2:
        return [], crossing
    grounded = {find(i) for i in np.nonzero(lo[:, 2] - lo[:, 2].min() <= tol)[0].tolist()}
    out = []
    for i in range(n):
        if find(i) in grounded:
            continue
        # the nearest piece it isn't joined to, closest boxes first
        box = np.linalg.norm(np.maximum(0, np.maximum(lo - hi[i], lo[i] - hi)), axis=1)
        best, nearest = math.inf, -1
        for j in np.argsort(box, kind="stable").tolist():
            if box[j] > best:
                break
            if find(j) != find(i):
                g = _gap(pieces[i], pieces[j], best)
                if g < best:
                    best, nearest = g, j
        out.append((i, nearest, best))
    return out, crossing


def _uv_checks(bm, uv_layer, out, name):
    areas, uv_areas, oob = [], [], 0
    tris = []
    for f in bm.faces:
        pts = [l[uv_layer].uv.copy() for l in f.loops]
        a3 = f.calc_area()
        a2 = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            a2 += x1 * y2 - x2 * y1
        areas.append(a3)
        uv_areas.append(abs(a2) / 2)
        if any(p.x < -0.001 or p.x > 1.001 or p.y < -0.001 or p.y > 1.001 for p in pts):
            oob += 1
        if len(tris) < MAX_UV_FACES * 2:
            for i in range(1, len(pts) - 1):
                tris.append((pts[0], pts[i], pts[i + 1]))
    areas = np.array(areas)
    uv_areas = np.array(uv_areas)
    real = areas > (areas.max() * 1e-6 if len(areas) else 0)
    collapsed = int(np.sum(real & (uv_areas < 1e-10)))
    _finding(out, "warning", "uv_collapsed", name, collapsed, f"{collapsed} faces have no UV space (collapsed UVs)")
    _finding(out, "info", "uv_out_of_bounds", name, oob, f"{oob} faces reach outside 0-1 UV space (fine for tiling textures)")
    ok = real & (uv_areas > 1e-10)
    density = None
    if ok.sum() >= 4:
        dens = np.sqrt(uv_areas[ok] / areas[ok])
        p10, p50, p90 = np.percentile(dens, [10, 50, 90])
        density = {"median_uv_per_m": round(float(p50), 4), "spread_p90_over_p10": round(float(p90 / max(p10, 1e-9)), 2)}
        if p90 / max(p10, 1e-9) > 3.0:
            _finding(out, "warning", "texel_density", name, 1,
                     f"texel density varies {p90 / max(p10, 1e-9):.1f}x between faces (aim for under 2x)")
    # overlap: rasterize UV triangles and count cells covered more than once
    cover = np.zeros((UV_RASTER, UV_RASTER), np.int16)
    for a, b, c in tris:
        xs = np.array([a.x, b.x, c.x]) * UV_RASTER
        ys = np.array([a.y, b.y, c.y]) * UV_RASTER
        x0, x1 = int(max(0, math.floor(xs.min()))), int(min(UV_RASTER - 1, math.ceil(xs.max())))
        y0, y1 = int(max(0, math.floor(ys.min()))), int(min(UV_RASTER - 1, math.ceil(ys.max())))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-12:
            continue
        l1 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        l2 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        inside = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
        cover[y0 : y1 + 1, x0 : x1 + 1] += inside
    used = (cover > 0).sum()
    overlap = float((cover > 1).sum() / used) if used else 0.0
    if overlap > 0.05:
        _finding(out, "warning", "uv_overlap", name, 1,
                 f"{overlap:.0%} of used UV space is covered twice or more (fine for mirrored parts, "
                 "wrong for baking unique textures)")
    return {"uv_overlap_fraction": round(overlap, 3), "texel_density": density, "uv_space_used": round(float(used) / UV_RASTER**2, 3)}


def _weight_checks(obj, out):
    me = obj.data
    deform = {g.index for g in obj.vertex_groups}
    if not deform:
        _finding(out, "error", "weights_missing", obj.name, 1, "deforming mesh has no vertex groups")
        return
    too_many, unweighted, unnormalized = 0, 0, 0
    for v in me.vertices:
        ws = [g.weight for g in v.groups if g.group in deform and g.weight > 1e-4]
        if not ws:
            unweighted += 1
        if len(ws) > 4:
            too_many += 1
        if ws and abs(sum(ws) - 1.0) > 0.01:
            unnormalized += 1
    _finding(out, "error", "weights_unweighted", obj.name, unweighted, f"{unweighted} vertices have no bone weights (they won't move)")
    _finding(out, "warning", "weights_over_4", obj.name, too_many, f"{too_many} vertices have more than 4 bone influences")
    _finding(out, "info", "weights_unnormalized", obj.name, unnormalized, f"{unnormalized} vertices' weights don't sum to 1")


def run(
    path: str,
    objects: list[str] | None = None,
    budget_tris: int = 0,
    deforming: bool | None = None,
) -> dict:
    targets = assets.load(path, objects)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lo, hi = assets.world_bounds(targets)
    asset_size = max((hi - lo).length, 1e-6)
    findings: list[dict] = []
    per_object = []
    all_islands = []  # every connected piece of every object (_pieces)
    imported = os.path.splitext(path)[1].lower() in IMPORTED
    total_tris = 0
    for obj in targets:
        eo = obj.evaluated_get(depsgraph)
        me = eo.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(me)
        eo.to_mesh_clear()
        bm.transform(obj.matrix_world)
        bm.normal_update()  # transform() leaves normals in object space; flips compare world ones
        notes = []
        if imported:  # weld what the importer split, so faces have neighbours again
            n_verts = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=asset_size * 1e-6)
            if len(bm.verts) < n_verts:
                notes.append(f"welded for import: {n_verts - len(bm.verts)} split vertices merged")
        for seq in (bm.verts, bm.edges, bm.faces):
            seq.ensure_lookup_table()
            seq.index_update()
        name = obj.name
        tris = sum(len(f.verts) - 2 for f in bm.faces)
        total_tris += tris

        nonmanifold = [e for e in bm.edges if len(e.link_faces) > 2]
        boundary = [e for e in bm.edges if len(e.link_faces) == 1]
        wire = [e for e in bm.edges if not e.link_faces]
        loose = [v for v in bm.verts if not v.link_edges]
        zero = [f for f in bm.faces if f.calc_area() < (asset_size * 1e-5) ** 2]
        short = [e for e in bm.edges if e.calc_length() < asset_size * 1e-6]
        ngons = [f for f in bm.faces if len(f.verts) > 4]
        _finding(findings, "error", "non_manifold", name, len(nonmanifold),
                 f"{len(nonmanifold)} edges shared by 3+ faces", [e.verts[0].co for e in nonmanifold])
        _finding(findings, "info", "open_edges", name, len(boundary),
                 f"{len(boundary)} open (boundary) edges: holes, unless the mesh is meant to be open")
        _finding(findings, "warning", "loose_geometry", name, len(loose) + len(wire),
                 f"{len(loose)} loose vertices and {len(wire)} loose edges", [v.co for v in loose])
        _finding(findings, "warning", "degenerate", name, len(zero) + len(short),
                 f"{len(zero)} zero-area faces and {len(short)} zero-length edges", [f.calc_center_median() for f in zero])

        is_deforming = deforming if deforming is not None else any(m.type == "ARMATURE" for m in obj.modifiers)
        rigid = _rigid_bone(obj)
        if rigid:  # a prop on a bone moves with it whole: nothing deforms
            is_deforming = False
        _finding(findings, "error" if is_deforming else "info", "ngons", name, len(ngons),
                 f"{len(ngons)} n-gons (5+ sides)" + (": these deform badly, use quads/tris" if is_deforming else ""))

        # flipped faces: compare against consistently recalculated normals
        flipped = 0
        if bm.faces:
            bm2 = bm.copy()
            bmesh.ops.recalc_face_normals(bm2, faces=bm2.faces)
            bm2.faces.ensure_lookup_table()
            flips = [i for i in range(len(bm.faces)) if bm.faces[i].normal.dot(bm2.faces[i].normal) < 0]
            bm2.free()
            flipped = len(flips)
            if flipped > len(bm.faces) / 2:
                _finding(findings, "error", "inside_out", name, 1, "the whole mesh is inside out (normals point inward)")
            else:
                _finding(findings, "error", "flipped_normals", name, flipped,
                         f"{flipped} faces point inward", [bm.faces[i].calc_center_median() for i in flips])

        uv_layer = bm.loops.layers.uv.active
        uv_info = None
        if uv_layer is None:
            _finding(findings, "error", "no_uvs", name, 1, "no UV map: textures and baking need one")
        else:
            uv_info = _uv_checks(bm, uv_layer, findings, name)

        pieces = _pieces(bm, name)
        all_islands += pieces

        sx, sy, sz = obj.scale
        if min(sx, sy, sz) < 0:
            _finding(findings, "error", "negative_scale", name, 1, f"negative scale {tuple(round(s, 3) for s in obj.scale)} flips normals on export")
        elif max(abs(sx - 1), abs(sy - 1), abs(sz - 1)) > 1e-4:
            _finding(findings, "warning", "unapplied_scale", name, 1,
                     f"unapplied scale {tuple(round(s, 3) for s in obj.scale)}: apply it before export")
        if any(abs(r) > 1e-4 for r in obj.rotation_euler) and obj.type == "MESH":
            _finding(findings, "info", "unapplied_rotation", name, 1, "object has rotation; fine if intended")
        if DEFAULT_NAME.match(name):
            _finding(findings, "info", "default_name", name, 1, f"default name '{name}' becomes the Godot node name")

        mats = [s.material for s in obj.material_slots]
        empty_slots = sum(1 for m in mats if m is None)
        _finding(findings, "warning", "empty_material_slot", name, empty_slots, f"{empty_slots} empty material slot(s)")
        if not mats:
            _finding(findings, "info", "no_material", name, 1, "no material assigned")
        for m in mats:
            for t in assets._images_of(m):
                if t["missing"]:
                    _finding(findings, "error", "missing_texture", name, 1, f"texture '{t['name']}' file is missing")
                w, h = t["size"]
                if w and h and (w & (w - 1) or h & (h - 1)):
                    _finding(findings, "info", "npot_texture", name, 1, f"texture '{t['name']}' is {w}x{h} (not power of two)")
                if max(w, h) > 4096:
                    _finding(findings, "warning", "huge_texture", name, 1, f"texture '{t['name']}' is {w}x{h}")
        if is_deforming and obj.type == "MESH":
            _weight_checks(obj, findings)

        info = {
            "name": name,
            "tris": tris,
            "faces": len(bm.faces),
            "ngons": len(ngons),
            "flipped_faces": flipped,
            "islands": len(pieces),
            "uv": uv_info,
            "deforming": bool(is_deforming),
        }
        if rigid:
            info["rigid_attachment"] = rigid
        if notes:
            info["notes"] = notes
        per_object.append(info)
        bm.free()

    # floating parts: pieces that no chain of touching pieces joins to the ground. Touching is
    # surface distance (BVH), not boxes: a tusk 7 mm off the face has a box inside the head's
    tol = min(asset_size * 0.002, 0.002)
    floating, intersecting = _floating(all_islands, tol)
    for i, j, gap in floating:  # a grounded piece is always in reach, so j >= 0
        p, near = all_islands[i], all_islands[j]["object"]
        other = f"another piece of {near}" if near == p["object"] else near
        _finding(findings, "warning", "floating_part", p["object"], 1,
                 f"a piece floats {gap * 1000:.1f} mm off {other}: nothing it touches reaches the ground",
                 [(p["lo"] + p["hi"]) / 2], {"gap_mm": round(gap * 1000, 1), "nearest": near})

    # intersecting pieces (common and fine for static props; bad for deforming characters)
    _finding(findings, "info", "intersecting_parts", "(asset)", intersecting,
             f"{intersecting} pair(s) of pieces intersect (fine for static props, avoid on deforming meshes)")

    if budget_tris and total_tris > budget_tris:
        _finding(findings, "error", "over_budget", "(asset)", 1, f"{total_tris:,} tris, over the budget of {budget_tris:,}")

    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["object"], f["check"]))
    summary = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    return {
        "file": path,
        "total_tris": total_tris,
        "budget_tris": budget_tris or None,
        "bounds_m": [round(v, 4) for v in (hi - lo)],
        "objects": per_object,
        "findings": findings,
        "summary": summary,
        "game_ready": summary["error"] == 0,
    }
