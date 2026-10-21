"""Render an asset at TRUE game pixel size, for readability checks and game-size blind reads.

A camera with the profile's FOV and resolution stands at distance d from the subject's
center; the render border crops the frame to the subject, so every pixel is a game pixel.
Part maps use mask mode (one exact color per part, background alpha 0); the host measures
them (``opus.threed.understand``).
"""

from __future__ import annotations

import colorsys
import math
import os

import bpy
import numpy as np
from mathutils import Vector, geometry

from opus_bl import assets
from opus_bl.inspect3d import PALETTE, _all_points, _armature_of, _paint_parts, parts_of, view_angles
from opus_bl.lookdev import BG, CLAY, _camera, _render_settings, _workbench, mask_mode, srgb8

MARGIN_PX = 2


def _select(path: str, objects: list[str] | None):
    """The geometry to check: everything visible, or the named objects, collections or rigs
    (a rig selects the meshes it deforms)."""
    targets = assets.load(path, None)
    if objects:
        wanted = set(objects)
        in_coll = {o.name for c in bpy.data.collections if c.name in wanted for o in c.all_objects}

        def by_rig(o):
            arm = _armature_of(o) if o.type == "MESH" else None
            return arm is not None and arm.name in wanted

        targets = [o for o in targets if o.name in wanted or o.name in in_coll or by_rig(o)]
        if not targets:
            raise ValueError(f"no visible geometry in objects, collections or rigs named {sorted(wanted)}")
    names = {o.name for o in targets}
    for o in bpy.context.scene.objects:
        if o.name not in names and (o.type in assets.GEOMETRY_TYPES or o.type == "LIGHT"):
            o.hide_render = True
    return targets


def id_colors(n: int) -> list[tuple]:
    """``n`` linear colors whose 8-bit renders are all distinct (PALETTE first, then
    golden-ratio hues), so a part map decodes back to part IDs exactly."""
    out, seen = [], []

    def accept(lin):
        s8 = srgb8(lin)
        if all(max(abs(a - b) for a, b in zip(s8, t)) >= 10 for t in seen):
            out.append(tuple(lin[:3]))
            seen.append(s8)

    for c in PALETTE:
        accept(c)
    i = 0
    while len(out) < n:
        rgb = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, (0.85, 0.55, 0.7)[(i // 7) % 3], (0.95, 0.75, 0.55)[(i // 3) % 3])
        accept([c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb])
        i += 1
        if i > 20000:
            raise ValueError(f"{n} parts are too many for distinct ID colors; check fewer objects")
    return out[:n]


def _direction(azimuth: float, elevation: float) -> Vector:
    az, el = math.radians(azimuth), math.radians(elevation)
    return Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))


def _place(cam, camera: dict, center: Vector, d: Vector, dist: float, radius: float):
    data = cam.data
    data.sensor_fit = "VERTICAL"
    data.shift_x = data.shift_y = 0.0
    if camera["projection"] == "ortho":
        data.type = "ORTHO"
        data.ortho_scale = float(camera["ortho_h"])  # the vertical view height with a vertical fit
    else:
        data.type = "PERSP"
        data.angle_y = math.radians(float(camera["vfov_deg"]))
    cam.location = center + d * dist
    if abs(d.z) > 0.999:
        cam.rotation_euler = (0.0, 0.0, 0.0) if d.z > 0 else (math.pi, 0.0, 0.0)
    else:
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    near = float(camera.get("near_m") or 0.0) / max(float(camera.get("scale") or 1.0), 1e-6)
    data.clip_start = near or max(1e-4, 0.005 * dist)
    data.clip_end = dist + radius * 4 + 10
    bpy.context.view_layer.update()


def _project(cam, pts: np.ndarray, res_w: int, res_h: int):
    """Pixel coordinates (x right, y down) of world points, and whether each is in front."""
    dg = bpy.context.evaluated_depsgraph_get()
    m = np.array(cam.calc_matrix_camera(dg, x=res_w, y=res_h)) @ np.array(cam.matrix_world.inverted())
    h = np.c_[pts, np.ones(len(pts))] @ m.T
    w = h[:, 3]
    safe = np.where(np.abs(w) < 1e-12, 1e-12, w)
    x = (h[:, 0] / safe + 1) / 2 * res_w
    y = (1 - (h[:, 1] / safe + 1) / 2) * res_h
    return x, y, w > 0


def _projected_size(cam, co: np.ndarray, res_w: int, res_h: int) -> list[float]:
    """A part's projected extent (px) and convex-hull area (px²), ignoring occlusion."""
    x, y, _ = _project(cam, co, res_w, res_h)
    pts = np.c_[x, y]
    area = 0.0
    if len(pts) >= 3:
        hull = pts[geometry.convex_hull_2d([tuple(v) for v in pts])]
        area = 0.5 * abs(float(hull[:, 0] @ np.roll(hull[:, 1], 1) - hull[:, 1] @ np.roll(hull[:, 0], 1)))
    return [round(float(max(np.ptp(x), np.ptp(y))), 2), round(area, 2)]


def _border(scene, x0: int, y0: int, x1: int, y1: int, res_w: int, res_h: int):
    """Crop the render to pixels [x0, x1) x [y0, y1) (y down); Blender's border runs bottom-up."""
    r = scene.render
    r.use_border = r.use_crop_to_border = True
    r.border_min_x, r.border_max_x = (x0 + 0.25) / res_w, (x1 + 0.25) / res_w
    r.border_min_y, r.border_max_y = (res_h - y1 + 0.25) / res_h, (res_h - y0 + 0.25) / res_h


def _set_pass(pass_name: str, mode: str, parts: list, colors: list):
    if pass_name == "parts":
        _paint_parts(mode, parts, palette=colors)
        mask_mode(color_type="VERTEX", transparent=True)
    elif pass_name == "silhouette":
        mask_mode(single=(0, 0, 0), bg=(1, 1, 1))
    elif pass_name == "shaded":  # as the game would show it: anti-aliased, no outline
        _workbench(light="STUDIO", color_type="TEXTURE", cavity=False, outline=False, bg=BG)
    elif pass_name == "clay":
        _workbench(light="STUDIO", color_type="OBJECT", cavity=True, outline=True, bg=BG)
    else:
        raise ValueError("passes are parts, silhouette, shaded and clay")


def render(
    path: str,
    out_dir: str,
    camera: dict,
    levels: list,
    objects: list[str] | None = None,
    shots: list[dict] | None = None,
) -> dict:
    """Render each shot ({key, view | azimuth/elevation, passes}) at each level ([name,
    distance_m]; None for an orthographic camera). Passes: parts, silhouette, shaded, clay.
    ``camera`` = {projection, vfov_deg | ortho_h, res_w, res_h, near_m, scale}."""
    shots = shots or [{"key": "front", "view": "front", "passes": ["parts", "shaded"]}]
    os.makedirs(out_dir, exist_ok=True)
    targets = _select(path, objects)
    scene = bpy.context.scene
    mode, parts = parts_of(targets)
    pts = _all_points(targets)
    lo, hi = Vector(pts.min(axis=0)), Vector(pts.max(axis=0))
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-4)
    res_w, res_h = int(camera["res_w"]), int(camera["res_h"])
    _render_settings(res_h)
    scene.render.resolution_x = res_w
    cam = _camera()
    colors = id_colors(len(parts))
    for o in targets:
        o.color = CLAY

    renders = []
    for shot in shots:
        az, el = view_angles(shot["view"]) if shot.get("view") else (float(shot.get("azimuth", 0)), float(shot.get("elevation", 0)))
        d = _direction(az, el)
        for name, dist in levels:
            dist = float(dist) if dist else radius * 4 + 1.0  # an ortho camera's distance doesn't scale it
            _place(cam, camera, center, d, dist, radius)
            x, y, front = _project(cam, pts, res_w, res_h)
            clipped = bool(x.min() < 0 or y.min() < 0 or x.max() > res_w or y.max() > res_h or not front.all())
            x0, y0 = max(0, math.floor(x.min()) - MARGIN_PX), max(0, math.floor(y.min()) - MARGIN_PX)
            x1, y1 = min(res_w, math.ceil(x.max()) + MARGIN_PX), min(res_h, math.ceil(y.max()) + MARGIN_PX)
            if x1 - x0 < 1 or y1 - y0 < 1:
                raise ValueError(f"the subject is outside the frame at {name}")
            _border(scene, x0, y0, x1, y1, res_w, res_h)
            item = {"shot": shot.get("key", ""), "azimuth": az, "elevation": el, "level": name, "distance_m": dist,
                    "crop": [x0, y0, x1, y1], "clipped": clipped, "files": {},
                    "projected_height_px": round(float(np.ptp(y[front])), 2) if front.any() else 0.0}
            if "parts" in shot["passes"]:  # how big each part would be if nothing hid it: [extent, hull area]
                item["parts_projected"] = {p["name"]: _projected_size(cam, p["co"], res_w, res_h) for p in parts}
            for pass_name in shot["passes"]:
                _set_pass(pass_name, mode, parts, colors)
                fp = os.path.join(out_dir, f"{shot.get('key', 'shot')}_{name}_{pass_name}.png")
                scene.render.filepath = fp
                bpy.ops.render.render(write_still=True)
                item["files"][pass_name] = fp
            renders.append(item)
    return {
        "mode": mode,
        "parts": [{"name": p["name"], "object": p["object"].name, "color8": list(srgb8(c))} for p, c in zip(parts, colors)],
        "size_m": [round(float(v), 4) for v in (hi - lo)],
        "renders": renders,
    }
