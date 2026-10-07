"""Load an asset file and measure it: bounds, triangle counts, materials, textures, transforms."""

from __future__ import annotations

import os

import bpy
import numpy as np
from mathutils import Vector

GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT"}


def load(path: str, objects: list[str] | None = None) -> list[bpy.types.Object]:
    """Open a .blend or import .glb/.gltf/.fbx/.obj/.stl into an empty scene.

    Returns the visible geometry objects, optionally filtered by object or collection name.
    """
    path = os.path.abspath(path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=path)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=path)
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=path)
        elif ext == ".stl":
            bpy.ops.wm.stl_import(filepath=path)
        else:
            raise ValueError(f"unsupported file type: {ext}")
    scene = bpy.context.scene
    objs = [o for o in scene.objects if o.type in GEOMETRY_TYPES and not o.hide_render and o.visible_get()]
    if objects:
        wanted = set(objects)
        in_coll = {
            o.name
            for c in bpy.data.collections
            if c.name in wanted
            for o in c.all_objects
        }
        objs = [o for o in objs if o.name in wanted or o.name in in_coll]
        if not objs:
            raise ValueError(f"no visible geometry objects named {sorted(wanted)}")
    if not objs:
        raise ValueError("the file has no visible geometry objects")
    return objs


def world_bounds(objs) -> tuple[Vector, Vector]:
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def _images_of(mat) -> list[dict]:
    out = []
    if mat is None or mat.node_tree is None:
        return out
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image is not None:
            img = n.image
            path = bpy.path.abspath(img.filepath) if img.filepath else ""
            out.append(
                {
                    "name": img.name,
                    "size": list(img.size),
                    "packed": img.packed_file is not None,
                    "missing": bool(path) and img.packed_file is None and not os.path.exists(path),
                }
            )
    return out


def object_stats(obj, depsgraph) -> dict:
    eo = obj.evaluated_get(depsgraph)
    me = eo.to_mesh()
    try:
        n_poly = len(me.polygons)
        totals = np.empty(n_poly, dtype=np.int64)
        me.polygons.foreach_get("loop_total", totals)
        info = {
            "name": obj.name,
            "type": obj.type,
            "verts": len(me.vertices),
            "faces": n_poly,
            "tris": int((totals - 2).sum()) if n_poly else 0,
            "ngons": int((totals > 4).sum()),
            "uv_maps": [uv.name for uv in me.uv_layers],
        }
    finally:
        eo.to_mesh_clear()
    mats = [s.material for s in obj.material_slots]
    info.update(
        {
            "materials": [m.name if m else None for m in mats],
            "textures": [t for m in mats for t in _images_of(m)],
            "modifiers": [f"{m.type}:{m.name}" for m in obj.modifiers],
            "armature": next((m.object.name for m in obj.modifiers if m.type == "ARMATURE" and m.object), None),
            "location": [round(v, 4) for v in obj.matrix_world.translation],
            "scale": [round(v, 4) for v in obj.scale],
            "rotation_deg": [round(np.degrees(v), 2) for v in obj.rotation_euler],
            "dimensions": [round(v, 4) for v in obj.dimensions],
        }
    )
    return info


def stats(objs) -> dict:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    per = [object_stats(o, depsgraph) for o in objs]
    lo, hi = world_bounds(objs)
    size = hi - lo
    return {
        "objects": per,
        "totals": {
            "objects": len(per),
            "tris": sum(p["tris"] for p in per),
            "verts": sum(p["verts"] for p in per),
            "materials": len({m for p in per for m in p["materials"] if m}),
        },
        "bounds": {
            "min": [round(v, 4) for v in lo],
            "max": [round(v, 4) for v in hi],
            "size_m": [round(v, 4) for v in size],
        },
    }


def stats_task(path: str, objects: list[str] | None = None) -> dict:
    return stats(load(path, objects))
