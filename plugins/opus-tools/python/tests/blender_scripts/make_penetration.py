"""Parts that pass through, sit inside and only touch each other, for penetration tests.

    blender -b --factory-startup --python make_penetration.py -- out_dir

through.blend: a 4 cm box pushed right through a 2 mm plate (no vertex of either is inside
the other), and a pin buried inside the box. touching.blend: a block resting on the plate
and a second block against the first, faces flush but offset.
"""

import os
import sys

import bmesh
import bpy
from mathutils import Matrix

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)


def box(name, size, center):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1.0)))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


bpy.ops.wm.read_factory_settings(use_empty=True)
box("Plate", (0.1, 0.1, 0.002), (0, 0, 0))
box("Box", (0.04, 0.04, 0.04), (0.01, 0.005, -0.01))  # z from -3 to +1 cm through the plate
box("Pin", (0.01, 0.01, 0.01), (0.01, 0.005, -0.02))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "through.blend"))

bpy.ops.wm.read_factory_settings(use_empty=True)
box("Plate", (0.1, 0.1, 0.002), (0, 0, 0))
box("Block", (0.04, 0.04, 0.04), (0, 0, 0.021))  # bottom face on the plate's top face
box("Side", (0.04, 0.04, 0.04), (0.04, 0.01, 0.029))  # flush against Block, shifted
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "touching.blend"))
