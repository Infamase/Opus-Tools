"""On-demand 3D understanding: views from any angle, part maps, a structure report, and
calibrated silhouettes for proportion and reference checks.

Parts are the asset's mesh objects, or, for a single skinned mesh, the regions each bone
dominates (so a fused character body still splits into head, upperarm_l, thigh_r, ...).
"""

from __future__ import annotations

import math
import os

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from opus_bl import assets, body
from opus_bl.lookdev import BG, CLAY, _camera, _cycles, _diagnostic_material, _render_settings, _wire_copies, _workbench, _world

# distinct, colorblind-aware part colors (Okabe-Ito first, then extras)
PALETTE = [
    (0.90, 0.62, 0.00), (0.34, 0.71, 0.91), (0.00, 0.62, 0.45), (0.94, 0.89, 0.26), (0.00, 0.45, 0.70),
    (0.84, 0.37, 0.00), (0.80, 0.47, 0.65), (0.55, 0.85, 0.40), (0.60, 0.40, 0.85), (0.95, 0.45, 0.45),
    (0.45, 0.80, 0.80), (0.75, 0.60, 0.35), (0.40, 0.55, 0.30), (0.95, 0.70, 0.80), (0.50, 0.50, 0.95),
    (0.70, 0.85, 0.95), (0.85, 0.85, 0.55), (0.65, 0.30, 0.30), (0.30, 0.65, 0.55), (0.90, 0.55, 0.25),
]
HIGHLIGHT = (1.0, 0.45, 0.05)
DIM = (0.55, 0.55, 0.58)
NAMED_VIEWS = {
    "front": (0.0, 0.0), "right": (90.0, 0.0), "back": (180.0, 0.0), "left": (270.0, 0.0),
    "top": (0.0, 90.0), "bottom": (0.0, -90.0), "three_quarter": (38.66, 26.6), "three_quarter_back": (218.66, 26.6),
}


# ---------------------------------------------------------------- geometry access

def _world_mesh(obj):
    """Evaluated world-space vertices (N x 3) and polygons of a mesh object."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(obj.matrix_world)
    co = co @ m[:3, :3].T + m[:3, 3]
    polys = [tuple(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    return co, polys


def _armature_of(obj):
    arm = obj.find_armature()
    if arm is None and obj.parent is not None and obj.parent.type == "ARMATURE":
        arm = obj.parent
    return arm


def parts_of(targets) -> tuple[str, list[dict]]:
    """Parts to label and measure: the regions each bone dominates on skinned meshes, and
    every other mesh object whole. Mode is "bones", "objects" or "bones+objects"."""
    meshes = [o for o in targets if o.type == "MESH"]
    skinned = [o for o in meshes if o.vertex_groups and _armature_of(o) is not None]
    parts = []
    for obj in skinned:
        arm = _armature_of(obj)
        deform = {b.name for b in arm.data.bones if b.use_deform}
        names = {g.index: g.name for g in obj.vertex_groups if g.name in deform}
        dominant = np.full(len(obj.data.vertices), -1)
        for v in obj.data.vertices:
            best = max((g for g in v.groups if g.group in names), key=lambda g: g.weight, default=None)
            if best is not None and best.weight > 0.05:
                dominant[v.index] = best.group
        co, _ = _world_mesh(obj)  # posed
        if len(co) != len(dominant):
            co = np.array([obj.matrix_world @ v.co for v in obj.data.vertices])
        for gi, name in sorted(names.items()):
            idx = np.nonzero(dominant == gi)[0]
            if len(idx):
                parts.append({"name": name, "kind": "bone", "object": obj, "indices": idx, "co": co[idx]})
    for o in meshes:
        if o in skinned:
            continue
        co, _ = _world_mesh(o)
        if len(co):
            parts.append({"name": o.name, "kind": "object", "object": o, "indices": None, "co": co})
    mode = "objects" if not skinned else ("bones" if len(skinned) == len(meshes) else "bones+objects")
    return mode, parts


def _bounds(points: np.ndarray) -> tuple[Vector, Vector]:
    return Vector(points.min(axis=0)), Vector(points.max(axis=0))


def _all_points(targets) -> np.ndarray:
    pts = [_world_mesh(o)[0] for o in targets if o.type == "MESH"]
    pts = [p for p in pts if len(p)]
    if not pts:
        lo, hi = assets.world_bounds(targets)
        return np.array([tuple(lo), tuple(hi)])
    return np.concatenate(pts)


# ---------------------------------------------------------------- camera

def view_angles(view) -> tuple[float, float]:
    if isinstance(view, str):
        if view not in NAMED_VIEWS:
            raise ValueError(f"unknown view {view!r}; named views: {sorted(NAMED_VIEWS)}")
        return NAMED_VIEWS[view]
    return float(view[0]), float(view[1])


def aim(cam, azimuth: float, elevation: float, points: np.ndarray, zoom: float = 1.0, ortho: bool = False, margin: float = 1.12):
    """Point the camera at ``points`` from (azimuth, elevation) in degrees. Azimuth 0 looks at
    the front (camera on -Y), 90 from the +X side (Blender's Right view), 180 the back."""
    az, el = math.radians(azimuth), math.radians(elevation)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    return aim_direction(cam, d, points, zoom, ortho, margin)


def aim_direction(cam, d: Vector, points: np.ndarray, zoom: float = 1.0, ortho: bool = False, margin: float = 1.12):
    """Point the camera at ``points`` from direction ``d`` (from the points toward the camera)."""
    d = Vector(d).normalized()
    lo, hi = _bounds(points)
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-4)
    vertical = abs(d.z) > 0.999
    up = Vector((0, 1, 0)) if vertical else Vector((0, 0, 1))
    right = (-d).cross(up).normalized()
    up_v = right.cross(-d).normalized()
    rel = points - np.array(center)
    span = max(np.ptp(rel @ np.array(right)), np.ptp(rel @ np.array(up_v)), 1e-4)
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = span * margin / max(zoom, 1e-3)
        dist = radius * 4 + 1.0
    else:
        cam.data.type = "PERSP"
        cam.data.sensor_fit = "AUTO"
        cam.data.sensor_width = 36.0
        cam.data.lens = 50.0
        half_fov = math.atan(18.0 / 50.0)
        depth = float(np.ptp(rel @ np.array(d))) / 2  # how far the asset reaches toward the camera
        dist = (span / 2 * margin) / math.tan(half_fov) / max(zoom, 1e-3) + depth
    cam.location = center + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler() if not vertical else (
        (0.0, 0.0, 0.0) if d.z > 0 else (math.pi, 0.0, 0.0))
    cam.data.clip_start = max(dist * 0.001, 1e-5)
    cam.data.clip_end = dist + radius * 4 + 10
    bpy.context.view_layer.update()
    return d


# ---------------------------------------------------------------- coloring

def _paint_parts(mode: str, parts: list[dict], highlight: set | None = None):
    """Color parts for a Workbench render; returns the color per part name."""
    colors = {}
    for i, p in enumerate(parts):
        if highlight is None:
            colors[p["name"]] = PALETTE[i % len(PALETTE)]
        else:
            colors[p["name"]] = HIGHLIGHT if p["name"] in highlight else DIM
    # one flat color per face (face corners); skinned meshes by the bone most of its vertices follow
    table = np.array([(*colors[p["name"]], 1.0) for p in parts] + [(*DIM, 1.0)])
    by_object = {}
    for i, p in enumerate(parts):
        by_object.setdefault(p["object"], []).append((i, p))
    for obj, plist in by_object.items():
        me = obj.data
        vpart = np.full(len(me.vertices), -1)
        for i, p in plist:
            vpart[slice(None) if p["indices"] is None else p["indices"]] = i
        loop_vert = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", loop_vert)
        starts = np.empty(len(me.polygons), dtype=np.int64)
        counts = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", starts)
        me.polygons.foreach_get("loop_total", counts)
        data = np.empty((len(me.loops), 4))
        for st, n in zip(starts, counts):
            ids = vpart[loop_vert[st : st + n]]
            ids = ids[ids >= 0]
            data[st : st + n] = table[np.bincount(ids).argmax() if len(ids) else -1]
        attr = me.color_attributes.get("opus_parts") or me.color_attributes.new("opus_parts", "FLOAT_COLOR", "CORNER")
        attr.data.foreach_set("color", data.ravel())
        me.color_attributes.active_color = attr
    return colors, "VERTEX"


def _label_anchor(scene, cam, part: dict, size: float):
    """A visible surface point of the part, in normalized image coordinates (x right, y down)."""
    co = part["co"]
    if len(co) > 1500:
        co = co[np.linspace(0, len(co) - 1, 1500).astype(int)]
    proj = np.array([tuple(world_to_camera_view(scene, cam, Vector(c))) for c in co])
    inside = (proj[:, 0] > 0.02) & (proj[:, 0] < 0.98) & (proj[:, 1] > 0.02) & (proj[:, 1] < 0.98) & (proj[:, 2] > 0)
    if not inside.any():
        return None
    co, proj = co[inside], proj[inside]
    c2 = proj[:, :2].mean(axis=0)
    order = np.argsort(np.linalg.norm(proj[:, :2] - c2, axis=1) + 0.002 * proj[:, 2] / max(size, 1e-6))
    dg = bpy.context.evaluated_depsgraph_get()
    cam_loc = cam.matrix_world.translation
    forward = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
    tol = size * 0.01
    for k in order[:40]:
        v = Vector(co[k])
        if cam.data.type == "ORTHO":
            origin = v - forward * (size * 10 + 1)
            direction = forward
        else:
            origin = cam_loc
            direction = (v - cam_loc).normalized()
        hit, loc, *_ = scene.ray_cast(dg, origin, direction)
        if hit and (loc - v).length < tol:
            return {"x": float(proj[k, 0]), "y": float(1 - proj[k, 1]), "visible": True}
    k = order[0]
    return {"x": float(proj[k, 0]), "y": float(1 - proj[k, 1]), "visible": False}


# ---------------------------------------------------------------- task: views

def views(
    path: str,
    out_dir: str,
    shots: list,
    objects: list[str] | None = None,
    target: str = "",
    isolate: bool = False,
    size: int = 640,
) -> dict:
    """Render ``shots`` (dicts with view or azimuth/elevation, pass, zoom, ortho).

    ``target`` (an object, collection or bone name) frames the camera on that part; the rest
    stays visible for context unless ``isolate``. Passes: shaded, clay, wire, silhouette,
    normals, parts (labeled part map), focus (the target highlighted, the rest gray).
    """
    targets = assets.load(path, objects)
    scene = bpy.context.scene
    names = {o.name for o in targets}
    for o in scene.objects:
        if o.name not in names and (o.type in assets.GEOMETRY_TYPES or o.type == "LIGHT"):
            o.hide_render = True
            o.hide_set(True)
    mode, parts = parts_of(targets)
    all_pts = _all_points(targets)
    frame_pts, focus = all_pts, None
    if target:
        focus = {p["name"] for p in parts if p["name"] == target}
        if not focus:  # a collection or object name in bone mode
            focus = {p["name"] for p in parts if p["object"].name == target or target in
                     {c.name for c in p["object"].users_collection}}
        if not focus:
            raise ValueError(f"no part named {target!r}; parts: {[p['name'] for p in parts][:60]}")
        frame_pts = np.concatenate([p["co"] for p in parts if p["name"] in focus])
        if isolate:
            for p in parts:
                if p["kind"] == "object" and p["name"] not in focus:
                    p["object"].hide_render = True
                    p["object"].hide_set(True)
    lo, hi = _bounds(all_pts)
    size_m = max((hi - lo).length, 1e-6)
    _render_settings(size)
    cam = _camera()
    os.makedirs(out_dir, exist_ok=True)
    wires = []
    tiles = []
    for i, shot in enumerate(shots):
        shot = dict(shot)
        pass_name = shot.get("pass", "clay")
        view = shot.get("view")
        az, el = view_angles(view) if view else (float(shot.get("azimuth", 0)), float(shot.get("elevation", 0)))
        bpy.context.view_layer.material_override = None
        for w in wires:
            w.hide_render = True
            w.hide_set(True)  # hidden from label ray casts too
        labels = None
        if pass_name == "shaded":
            _workbench(light="STUDIO", color_type="TEXTURE", cavity=True, outline=True)
        elif pass_name in ("clay", "wire"):
            for o in targets:
                o.color = CLAY
            _workbench(light="STUDIO", color_type="OBJECT", cavity=True, outline=True)
            if pass_name == "wire":
                if not wires:
                    wires = _wire_copies(list({p["object"] for p in parts if not (isolate and focus and p["kind"] == "object" and p["name"] not in focus)}), size_m * 0.6)
                for w in wires:
                    w.hide_render = False
                    w.hide_set(False)
        elif pass_name == "silhouette":
            _workbench(light="FLAT", color_type="SINGLE", single=(0, 0, 0), cavity=False, outline=False, bg=(1, 1, 1))
        elif pass_name == "normals":
            _cycles(2, denoise=False)
            scene.view_settings.view_transform = "Standard"
            _world(BG)
            bpy.context.view_layer.material_override = _diagnostic_material("normals")
        elif pass_name in ("parts", "focus"):
            colors, ctype = _paint_parts(mode, parts, focus if pass_name == "focus" else None)
            _workbench(light="STUDIO", color_type=ctype, cavity=True, outline=True)
        else:
            raise ValueError("pass must be shaded, clay, wire, silhouette, normals, parts or focus")
        aim(cam, az, el, frame_pts, zoom=float(shot.get("zoom", 1.0)), ortho=bool(shot.get("ortho", False)))
        if pass_name == "parts":
            labels = []
            for p in parts:
                a = _label_anchor(scene, cam, p, size_m)
                if a:
                    labels.append({"name": p["name"], "color": colors[p["name"]], **a})
        fp = os.path.join(out_dir, f"shot{i:02d}_{pass_name}.png")
        scene.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        tiles.append({"path": fp, "pass": pass_name, "azimuth": az, "elevation": el,
                      "view": view if isinstance(view, str) else None, "labels": labels})
    return {"tiles": tiles, "mode": mode, "parts": [p["name"] for p in parts], "target": target or None,
            "stats": assets.stats(targets)}


# ---------------------------------------------------------------- task: structure report

def _direction_label(v) -> str:
    v = np.abs(np.asarray(v))
    axis = int(np.argmax(v))
    if v[axis] < 0.8:
        return "diagonal"
    return ("side to side (X)", "front to back (Y)", "vertical (Z)")[axis]


def _shape(lengths, fill) -> str:
    l1, l2, l3 = sorted(lengths, reverse=True)
    l3 = max(l3, 1e-6)
    l2 = max(l2, 1e-6)
    if l1 / l3 < 1.5:
        if fill is None:
            return "compact"
        return "box-like" if fill > 0.8 else ("rounded block / cylinder-like" if fill > 0.62 else "sphere-like")
    if l1 / l2 > 2.5 and l2 / l3 < 1.8:
        return "rod / limb-like"
    if l2 / l3 > 3.0:
        return "plate / slab"
    if l1 / l2 > 1.6:
        return "elongated block"
    return "flattened block"


def _segment_distances(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((pts - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(a + t[:, None] * ab - pts, axis=1)


def _volume(co: np.ndarray, polys) -> float | None:
    """Signed-tetrahedron volume; None when the mesh is open."""
    edges = {}
    for poly in polys:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            k = (min(a, b), max(a, b))
            edges[k] = edges.get(k, 0) + 1
    if not edges or any(n != 2 for n in edges.values()):
        return None
    vol = 0.0
    for poly in polys:
        p0 = co[poly[0]]
        for i in range(1, len(poly) - 1):
            vol += float(np.dot(p0, np.cross(co[poly[i]], co[poly[i + 1]]))) / 6.0
    return abs(vol)


def _bone_style(names) -> str:
    joined = " ".join(names).lower()
    if "mixamorig" in joined:
        return "mixamo"
    if "upperarm_l" in joined or "spine_01" in joined:
        return "unreal (UE mannequin)"
    if "def-" in joined or ".l" in joined:
        return "rigify / blender (.L/.R)"
    if "leftupperarm" in joined or "leftupperleg" in joined:
        return "humanoid profile (Godot/Unity)"
    return "custom"


def report(path: str, objects: list[str] | None = None) -> dict:
    targets = assets.load(path, objects)
    mode, parts = parts_of(targets)
    all_pts = _all_points(targets)
    lo, hi = _bounds(all_pts)
    dims = hi - lo
    size = max(dims.length, 1e-6)
    out_parts = []
    meshes = {}
    for p in parts:
        co = p["co"]
        c = co.mean(axis=0)
        info = {"name": p["name"], "verts": int(len(co)), "center_m": [round(float(x), 4) for x in c],
                "size_m": [round(float(x), 4) for x in np.ptp(co, axis=0)]}
        if len(co) >= 4:
            evals, evecs = np.linalg.eigh(np.cov((co - c).T))
            order = np.argsort(evals)[::-1]
            axes = evecs[:, order].T
            lengths = [float(np.ptp((co - c) @ ax)) for ax in axes]
            info["extents_m"] = [round(x, 4) for x in lengths]
            info["main_axis"] = _direction_label(axes[0])
            fill = None
            if p["kind"] == "object":
                wco, polys = _world_mesh(p["object"])
                meshes[p["name"]] = (wco, polys)
                vol = _volume(wco, polys)
                if vol is not None:
                    info["volume_m3"] = round(vol, 6)
                    fill = vol / max(lengths[0] * lengths[1] * lengths[2], 1e-12)
            info["shape"] = _shape(lengths, fill)
        if p["kind"] == "bone":
            arm = _armature_of(p["object"])
            b = arm.data.bones[p["name"]]
            mw = arm.matrix_world
            h, t = np.array(mw @ b.head_local), np.array(mw @ b.tail_local)
            info["bone_length_m"] = round(float(np.linalg.norm(t - h)), 4)
            info["girth_radius_m"] = round(float(np.median(_segment_distances(co, h, t))), 4)
        out_parts.append(info)

    # contacts and floating parts between objects
    contacts, gaps = [], []
    if 1 < len(meshes) <= 60:
        trees = {n: BVHTree.FromPolygons([tuple(v) for v in co], polys) for n, (co, polys) in meshes.items() if polys}
        names = list(trees)
        tol = size * 0.004
        dist = {}
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                if trees[a].overlap(trees[b]):
                    dist[a, b] = dist[b, a] = 0.0
                    contacts.append({"a": a, "b": b, "kind": "intersecting"})
                    continue
                d = min(_sampled_gap(meshes[a][0], trees[b]), _sampled_gap(meshes[b][0], trees[a]))
                dist[a, b] = dist[b, a] = d
                if d <= tol:
                    contacts.append({"a": a, "b": b, "kind": "touching"})
        for a in names:
            gap, nearest = min((dist[a, b], b) for b in names if b != a)
            if gap > tol:
                gaps.append({"part": a, "nearest": nearest, "gap_m": round(gap, 4)})

    # mirror symmetry across the asset's center plane (X)
    pts = all_pts[:: max(1, len(all_pts) // 6000)]
    kd = KDTree(len(pts))
    for i, v in enumerate(pts):
        kd.insert(Vector(v), i)
    kd.balance()
    cx = (lo.x + hi.x) / 2
    off = np.array([kd.find(Vector((2 * cx - v[0], v[1], v[2])))[2] for v in pts])
    asym_parts = []
    for p in parts:
        sub = p["co"][:: max(1, len(p["co"]) // 300)]
        d = np.array([kd.find(Vector((2 * cx - v[0], v[1], v[2])))[2] for v in sub])
        if len(d) and float(np.median(d)) > size * 0.01:
            asym_parts.append({"part": p["name"], "median_offset_m": round(float(np.median(d)), 4)})
    symmetry = {
        "plane_x_m": round(cx, 4),
        "median_offset_m": round(float(np.median(off)), 5),
        "offset_pct_of_size": round(float(np.median(off)) / size * 100, 2),
        "symmetric": bool(np.median(off) < size * 0.005),
        "asymmetric_parts": sorted(asym_parts, key=lambda x: -x["median_offset_m"])[:8],
    }

    # balance: surface centroid vs footprint on the floor
    floor = all_pts[all_pts[:, 2] <= lo.z + max(dims.z * 0.02, 1e-4)]
    com = all_pts.mean(axis=0)
    balance = {"center_of_mass_m": [round(float(x), 4) for x in com], "lowest_z_m": round(lo.z, 4)}
    if len(floor) >= 3:
        hull_idx = geometry.convex_hull_2d([tuple(v[:2]) for v in floor])
        hull = [floor[i][:2] for i in hull_idx]
        inside = _point_in_polygon(com[:2], hull)
        balance["footprint_xy_m"] = [[round(float(a), 3) for a in h] for h in hull][:24]
        balance["com_over_footprint"] = inside
        if not inside:
            cxy = np.mean(hull, axis=0)
            v = com[:2] - cxy
            balance["leans_toward"] = ("+X (its left)" if v[0] > 0 else "-X (its right)") if abs(v[0]) > abs(v[1]) else (
                "+Y (back)" if v[1] > 0 else "-Y (front)")

    rig = None
    arms = {_armature_of(o) for o in targets if o.type == "MESH"} - {None}
    if arms:
        arm = next(iter(arms))
        mw = arm.matrix_world
        bones = {b.name: round(float((mw @ b.tail_local - mw @ b.head_local).length), 4) for b in arm.data.bones}
        rig = {"armature": arm.name, "bones": len(bones), "style": _bone_style(bones), "bone_lengths_m": bones}

    return {
        "mode": mode,
        "bounds_m": {"min": [round(x, 4) for x in lo], "max": [round(x, 4) for x in hi], "size": [round(x, 4) for x in dims]},
        "on_floor": abs(lo.z) < max(size * 0.005, 1e-3),
        "centered_x": abs(cx) < max(size * 0.01, 1e-3),
        "parts": out_parts,
        "contacts": contacts,
        "gaps": sorted(gaps, key=lambda g: -g["gap_m"]),
        "symmetry": symmetry,
        "balance": balance,
        "rig": rig,
        "stats": assets.stats(targets),
    }


def _sampled_gap(co: np.ndarray, tree) -> float:
    sample = co[:: max(1, len(co) // 400)]
    return min((tree.find_nearest(Vector(v))[3] or float("inf")) for v in sample)


def _point_in_polygon(p, poly) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


# ---------------------------------------------------------------- task: silhouettes

def _render_silhouettes(out_dir: str, prefix: str, targets, views_: list[str], size: int) -> dict:
    """Orthographic silhouettes with a known pixel scale (meters per pixel)."""
    scene = bpy.context.scene
    _render_settings(size)
    _workbench(light="FLAT", color_type="SINGLE", single=(0, 0, 0), cavity=False, outline=False, bg=(1, 1, 1))
    cam = _camera()
    pts = _all_points(targets)
    out = {}
    for v in views_:
        az, el = view_angles(v)
        aim(cam, az, el, pts, ortho=True, margin=1.08)
        fp = os.path.join(out_dir, f"{prefix}_{v}.png")
        scene.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        out[v] = {"path": fp, "m_per_px": cam.data.ortho_scale / size}
    return out


def _bone_positions(targets) -> dict | None:
    arms = {_armature_of(o) for o in targets if o.type == "MESH"} - {None}
    if not arms:
        return None
    arm = next(iter(arms))
    mw = arm.matrix_world
    return {b.name: [list(mw @ b.head_local), list(mw @ b.tail_local)] for b in arm.data.bones}


def silhouettes(
    path: str,
    out_dir: str,
    objects: list[str] | None = None,
    views: list[str] | None = None,
    size: int = 768,
    canon: str = "",
    presets: list[str] | None = None,
    pose: str = "auto",
) -> dict:
    """Silhouettes of the asset, plus the same silhouettes of canon blockouts built at the
    asset's height (``canon`` = humanoid, quadruped or dragon) for side-by-side comparison."""
    views = views or ["front", "right"]
    os.makedirs(out_dir, exist_ok=True)
    targets = assets.load(path, objects)
    names = {o.name for o in targets}
    for o in bpy.context.scene.objects:
        if o.name not in names and o.type in assets.GEOMETRY_TYPES:
            o.hide_render = True
    pts = _all_points(targets)
    lo, hi = _bounds(pts)
    dims = hi - lo
    result = {
        "model": {"views": _render_silhouettes(out_dir, "model", targets, views, size),
                  "size_m": [round(x, 4) for x in dims], "bones": _bone_positions(targets)},
        "canons": {},
    }
    if canon:
        if canon != "humanoid":
            poses = ["A"]
        elif pose == "auto":
            detected = _detect_arm_pose(result["model"]["bones"], pts, lo, hi)
            poses = ["A", "T"] if detected == "either" else [detected]
        else:
            poses = [pose.upper()]
        result["pose"] = poses[0] if len(poses) == 1 else "A or T"
        for preset in presets or body.ARCHETYPES[canon]:
            for p in poses:
                built = body.build(archetype=canon, preset=preset, height=dims.z, pose=p, target_tris=6000, rig=False)
                objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
                key = preset if len(poses) == 1 else f"{preset} ({p}-pose)"
                result["canons"][key] = {
                    "preset": preset, "pose": p,
                    "views": _render_silhouettes(out_dir, f"canon_{preset}_{p}", objs, views, size),
                    "landmarks_m": built["landmarks_m"], "joints_m": built["joints_m"], "heads_tall": built["heads_tall"],
                }
    return result


def _detect_arm_pose(bones: dict | None, pts: np.ndarray, lo: Vector, hi: Vector) -> str:
    """"T", "A" or "either": from the upper arm bone's angle when rigged, otherwise from how
    high the outermost point of the silhouette (the hand) sits."""
    for name, (h, t) in (bones or {}).items():
        n = "".join(ch for ch in name.lower() if ch.isalnum())
        if n.endswith(("upperarml", "leftarm", "leftupperarm")):
            dx = abs(t[0] - h[0]) + 1e-9
            return "T" if math.degrees(math.atan2(abs(t[2] - h[2]), dx)) < 25 else "A"
    cx = (lo.x + hi.x) / 2
    tip = pts[np.argmax(np.abs(pts[:, 0] - cx))]
    r = (tip[2] - lo.z) / max(hi.z - lo.z, 1e-6)
    return "T" if r > 0.7 else ("A" if r < 0.56 else "either")
