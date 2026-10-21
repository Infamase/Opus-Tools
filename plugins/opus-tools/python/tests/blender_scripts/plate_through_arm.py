"""Cut a 2 mm plate across the right forearm, between two rings of skin vertices, so no
vertex is inside the plate: only a surface test can see it.

    blender -b rig.blend --python plate_through_arm.py -- out.blend
"""

import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

out = sys.argv[sys.argv.index("--") + 1]
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
body = next(o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == arm)
bone = arm.data.bones["lowerarm_r"]
head, tail = arm.matrix_world @ bone.head_local, arm.matrix_world @ bone.tail_local
axis = (tail - head).normalized()
# skin vertices of the forearm, by their position along the bone
g = body.vertex_groups["lowerarm_r"].index
co = np.array([tuple(body.matrix_world @ v.co) for v in body.data.vertices
               if any(x.group == g and x.weight > 0.5 for x in v.groups)])
t = np.sort((co - np.array(head)) @ np.array(axis))
length = (tail - head).length
mid = t[(t > 0.3 * length) & (t < 0.7 * length)]
gaps = np.diff(mid)
k = int(np.argmax(gaps))
at = head + axis * float((mid[k] + mid[k + 1]) / 2)  # halfway between two rings

bm = bmesh.new()
rot = axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(at) @ rot @ Matrix.Diagonal((0.14, 0.14, 0.002, 1.0)))
me = bpy.data.meshes.new("Plate")
bm.to_mesh(me)
bm.free()
plate = bpy.data.objects.new("Plate", me)
bpy.context.scene.collection.objects.link(plate)
plate["ring_gap_mm"] = float(gaps[k] * 1000)
bpy.ops.wm.save_as_mainfile(filepath=out)
