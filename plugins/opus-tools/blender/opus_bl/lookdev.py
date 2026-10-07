"""Render the Look Dev Sheet tiles.

Passes: shaded (Workbench/EEVEE/Cycles), clay + wireframe, silhouette, face orientation
(blue = outward, red = flipped), UV checker, and a scale view with a 1.8 m mannequin (or a
10 cm cube for small props) in front of a measured backdrop grid.
"""

from __future__ import annotations

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

from opus_bl import assets

BG = (0.16, 0.16, 0.18)
CLAY = (0.78, 0.78, 0.80, 1.0)
WIRE = (0.03, 0.10, 0.45, 1.0)
REF = (0.42, 0.52, 0.68, 1.0)
GRID = (0.30, 0.30, 0.34, 1.0)

ORTHO = {
    "front": (Vector((0, -1, 0)), (math.radians(90), 0.0, 0.0), ("x", "z")),
    "back": (Vector((0, 1, 0)), (math.radians(90), 0.0, math.radians(180)), ("x", "z")),
    "right": (Vector((1, 0, 0)), (math.radians(90), 0.0, math.radians(90)), ("y", "z")),
    "left": (Vector((-1, 0, 0)), (math.radians(90), 0.0, math.radians(-90)), ("y", "z")),
    "top": (Vector((0, 0, 1)), (0.0, 0.0, 0.0), ("x", "y")),
}
THREE_QUARTER = Vector((1.0, -1.25, 0.8))
THREE_QUARTER_BACK = Vector((-1.0, 1.25, 0.8))

DEFAULT_PLAN = [
    ("shaded", ["front", "right", "back", "top", "three_quarter"]),
    ("clay_wire", ["front", "right", "three_quarter"]),
    ("silhouette", ["front", "right"]),
    ("normals", ["three_quarter", "three_quarter_back"]),
    ("uv", ["three_quarter"]),
    ("scale", ["front"]),
]


# ---------------------------------------------------------------- scene helpers

def _link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _camera():
    scene = bpy.context.scene
    cam = bpy.data.objects.get("opus_cam")
    if cam is None:
        cam = _link(bpy.data.objects.new("opus_cam", bpy.data.cameras.new("opus_cam")))
    scene.camera = cam
    return cam


def _aim(cam, view, lo, hi, margin=1.15):
    center = (lo + hi) / 2
    size = hi - lo
    radius = max(size.length / 2, 1e-4)
    if view in ("three_quarter", "three_quarter_back"):
        cam.data.type = "PERSP"
        cam.data.sensor_width = 36.0
        cam.data.lens = 50.0
        half_fov = math.atan(18.0 / 50.0)
        direction = THREE_QUARTER if view == "three_quarter" else THREE_QUARTER_BACK
        loc = center + direction.normalized() * (radius / math.sin(half_fov) * 1.08)
        cam.location = loc
        cam.rotation_euler = (center - loc).to_track_quat("-Z", "Y").to_euler()
        dist = (loc - center).length
    else:
        direction, rot, axes = ORTHO[view]
        cam.data.type = "ORTHO"
        ext = max(getattr(size, axes[0]), getattr(size, axes[1]))
        cam.data.ortho_scale = max(ext * margin, 1e-4)
        dist = radius * 4 + 1.0
        cam.location = center + direction * dist
        cam.rotation_euler = rot
    cam.data.clip_start = max(dist * 0.001, 1e-5)
    cam.data.clip_end = dist + radius * 4 + 10


def _world(color, hdri: str | None = None):
    scene = bpy.context.scene
    w = bpy.data.worlds.get("opus_world") or bpy.data.worlds.new("opus_world")
    scene.world = w
    w.color = color[:3]
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    cam_bg = nt.nodes.new("ShaderNodeBackground")
    cam_bg.inputs["Color"].default_value = (*color[:3], 1.0)
    if not hdri:
        nt.links.new(cam_bg.outputs["Background"], out.inputs["Surface"])
        return
    # light the asset with a bundled studio HDRI, but show a flat background to the camera
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(
        bpy.utils.system_resource("DATAFILES", path=f"studiolights/world/{hdri}"), check_existing=True
    )
    light_bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(env.outputs["Color"], light_bg.inputs["Color"])
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(light_bg.outputs["Background"], mix.inputs[1])
    nt.links.new(cam_bg.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def _render_settings(size: int):
    r = bpy.context.scene.render
    r.resolution_x = r.resolution_y = int(size)
    r.resolution_percentage = 100
    r.film_transparent = False
    if hasattr(r.image_settings, "media_type"):  # Blender 5.0+: set before file_format
        r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"


def _workbench(light="STUDIO", color_type="OBJECT", single=(0.8, 0.8, 0.8), cavity=True, outline=True, bg=BG):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = light
    if light == "MATCAP":
        sh.studio_light = "clay_studio.exr"
    sh.color_type = color_type
    sh.single_color = single
    sh.show_cavity = cavity
    if cavity:
        sh.cavity_type = "BOTH"
    sh.show_object_outline = outline
    sh.object_outline_color = (0.04, 0.04, 0.05)
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "Standard"
    _world(bg)


def _cycles(samples: int, denoise: bool):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = denoise
    scene.cycles.use_adaptive_sampling = False


def _emission(nt, color):
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1.0)
    return e


def _diagnostic_material(kind: str):
    mat = bpy.data.materials.new(f"opus_{kind}")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if kind == "normals":
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
        nt.links.new(_emission(nt, (0.18, 0.38, 1.0)).outputs[0], mix.inputs[1])
        nt.links.new(_emission(nt, (1.0, 0.12, 0.12)).outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    else:  # uv checker
        img = bpy.data.images.get("opus_uvgrid") or bpy.data.images.new("opus_uvgrid", 1024, 1024)
        img.generated_type = "COLOR_GRID"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Closest"
        uv = nt.nodes.new("ShaderNodeUVMap")
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        em = _emission(nt, (1, 1, 1))
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def _wire_copies(objs, size: float):
    wires = []
    for o in objs:
        if o.type != "MESH":
            continue
        d = _link(o.copy())
        m = d.modifiers.new("opus_wire", "WIREFRAME")
        m.thickness = max(size * 0.0045, 1e-5)
        m.use_replace = True
        m.use_even_offset = True
        d.color = WIRE
        wires.append(d)
    return wires


def _mannequin(height: float = 1.8):
    """A simple 1.8 m figure built from primitives."""
    bm = bmesh.new()
    s = height / 1.8

    def cyl(x, z, r, depth):
        bmesh.ops.create_cone(
            bm, cap_ends=True, segments=16, radius1=r * s, radius2=r * s, depth=depth * s,
            matrix=Matrix.Translation((x * s, 0, z * s)),
        )

    for x in (-0.1, 0.1):
        cyl(x, 0.43, 0.075, 0.86)  # legs
    for x in (-0.25, 0.25):
        cyl(x, 1.13, 0.05, 0.64)  # arms
    cyl(0, 1.52, 0.05, 0.1)  # neck
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 1.17 * s)) @ Matrix.Diagonal((0.38 * s, 0.2 * s, 0.62 * s, 1)))
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.12 * s, matrix=Matrix.Translation((0, 0, 1.68 * s)))
    me = bpy.data.meshes.new("opus_ref")
    bm.to_mesh(me)
    bm.free()
    obj = _link(bpy.data.objects.new("opus_ref", me))
    obj.color = REF
    return obj


def _ref_cube(edge: float = 0.1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=edge, matrix=Matrix.Translation((0, 0, edge / 2)))
    me = bpy.data.meshes.new("opus_ref")
    bm.to_mesh(me)
    bm.free()
    obj = _link(bpy.data.objects.new("opus_ref", me))
    obj.color = REF
    return obj


def _backdrop(lo: Vector, hi: Vector, cell: float, y: float):
    """Vertical grid of lines in the XZ plane at depth ``y``: ``cell`` meters per square."""
    bm = bmesh.new()
    t = cell * 0.025
    x0 = math.floor(lo.x / cell) * cell
    x1 = math.ceil(hi.x / cell) * cell
    z0 = math.floor(lo.z / cell) * cell
    z1 = math.ceil(hi.z / cell) * cell
    for i in range(int(round((x1 - x0) / cell)) + 1):
        x = x0 + i * cell
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((x, y, (z0 + z1) / 2)) @ Matrix.Diagonal((t, t, z1 - z0 + t, 1)))
    for j in range(int(round((z1 - z0) / cell)) + 1):
        z = z0 + j * cell
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, y, z)) @ Matrix.Diagonal((x1 - x0 + t, t, t, 1)))
    me = bpy.data.meshes.new("opus_grid")
    bm.to_mesh(me)
    bm.free()
    obj = _link(bpy.data.objects.new("opus_grid", me))
    obj.color = GRID
    return obj


def _show(objs, visible: bool):
    for o in objs:
        o.hide_render = not visible


# ---------------------------------------------------------------- main

def run(
    path: str,
    out_dir: str,
    objects: list[str] | None = None,
    engine: str = "workbench",
    size: int = 300,
    plan: list | None = None,
) -> dict:
    targets = assets.load(path, objects)
    scene = bpy.context.scene
    target_names = {o.name for o in targets}
    # isolate the asset: hide other geometry and scene lights (lookdev uses its own lighting)
    for o in scene.objects:
        if o.name not in target_names and (o.type in assets.GEOMETRY_TYPES or o.type == "LIGHT"):
            o.hide_render = True
    info = assets.stats(targets)
    lo, hi = assets.world_bounds(targets)
    size_vec = hi - lo
    max_dim = max(size_vec.x, size_vec.y, size_vec.z, 1e-6)

    _render_settings(size)
    cam = _camera()
    os.makedirs(out_dir, exist_ok=True)

    # helpers that only some passes show
    wires = _wire_copies(targets, max_dim)
    small = max_dim < 0.5
    ref = _ref_cube(0.1) if small else _mannequin(1.8)
    gap = max(0.05, 0.25 * size_vec.x) if small else max(0.25, 0.2 * size_vec.x)
    ref_half = 0.05 if small else 0.3
    ref.location = (lo.x - gap - ref_half, (lo.y + hi.y) / 2, lo.z)
    ref_lo = Vector((min(lo.x, lo.x - gap - 2 * ref_half), lo.y, lo.z))
    ref_hi = Vector((hi.x, hi.y, max(hi.z, lo.z + (0.1 if small else 1.8))))
    cell = 0.1 if small else (1.0 if max(ref_hi.z - ref_lo.z, size_vec.x) < 20 else 5.0)
    grid = _backdrop(ref_lo, ref_hi, cell, hi.y + max(0.02, 0.05 * size_vec.y))
    for o in targets:
        o.color = CLAY
    _show(wires + [ref, grid], False)

    tiles = []
    for pass_name, views in plan or DEFAULT_PLAN:
        override = None
        if pass_name == "shaded":
            if engine == "workbench":
                _workbench(light="STUDIO", color_type="TEXTURE", cavity=True, outline=True)
            else:
                if engine == "eevee":
                    scene.render.engine = "BLENDER_EEVEE"
                    scene.eevee.taa_render_samples = 32
                else:
                    _cycles(48, denoise=True)
                scene.view_settings.view_transform = "AgX"
                _world(BG, hdri="studio.exr")
        elif pass_name == "clay_wire":
            _workbench(light="STUDIO", color_type="OBJECT", cavity=True, outline=True)
            _show(wires, True)
        elif pass_name == "silhouette":
            _workbench(light="FLAT", color_type="SINGLE", single=(0.0, 0.0, 0.0), cavity=False, outline=False, bg=(1, 1, 1))
        elif pass_name in ("normals", "uv"):
            _cycles(2, denoise=False)
            scene.view_settings.view_transform = "Standard"
            _world(BG)
            override = _diagnostic_material(pass_name)
            bpy.context.view_layer.material_override = override
        elif pass_name == "scale":
            _workbench(light="STUDIO", color_type="OBJECT", cavity=False, outline=True)
            _show([ref, grid], True)
        for view in views:
            if pass_name == "scale":
                _aim(cam, view, ref_lo, ref_hi, margin=1.1)
            else:
                _aim(cam, view, lo, hi)
            fp = os.path.join(out_dir, f"{pass_name}_{view}.png")
            scene.render.filepath = fp
            bpy.ops.render.render(write_still=True)
            tiles.append({"pass": pass_name, "view": view, "path": fp})
        bpy.context.view_layer.material_override = None
        _show(wires + [ref, grid], False)

    return {
        "tiles": tiles,
        "stats": info,
        "engine": engine,
        "reference": "cube_10cm" if small else "human_1.8m",
        "grid_cell_m": cell,
    }
