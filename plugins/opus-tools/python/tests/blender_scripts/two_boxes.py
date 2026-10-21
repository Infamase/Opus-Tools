"""Two touching boxes, one part each, for the mask-mode and readability tests.

    blender -b --factory-startup --python two_boxes.py -- out.blend
"""

import sys

import bmesh
import bpy
from mathutils import Matrix

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
for name, x in (("BoxA", -0.25), ("BoxB", 0.25)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((x, 0, 0.9)) @ Matrix.Diagonal((0.5, 0.3, 1.8, 1)))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, me))
bpy.ops.wm.save_as_mainfile(filepath=out)
