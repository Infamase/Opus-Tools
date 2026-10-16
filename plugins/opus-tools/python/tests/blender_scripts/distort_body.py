"""Make a badly proportioned humanoid from a good one: shorter legs and a bigger head.

    blender -b in.blend --python distort_body.py -- out.blend crotch_m chin_m
"""

import sys

import bpy
from mathutils import Vector

out, crotch, chin = sys.argv[sys.argv.index("--") + 1 :][:3]
crotch, chin = float(crotch), float(chin)
mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH")
for o in list(bpy.context.scene.objects):
    if o.type == "ARMATURE":
        bpy.data.objects.remove(o)
mesh.modifiers.clear()
top = max(v.co.z for v in mesh.data.vertices)
head_c = Vector((0, 0, (chin + top) / 2))
for v in mesh.data.vertices:
    z = v.co.z
    if z < crotch:
        v.co.z = z * 0.75  # legs 25% shorter
    else:
        v.co.z = z - crotch * 0.25
    if z > chin:
        v.co = head_c + (v.co - head_c) * 1.35 + Vector((0, 0, (top - chin) * 0.17))
bpy.ops.wm.save_as_mainfile(filepath=out)
