"""Pose one bone of a rigged body and report how far the skinned vertices moved.

    blender -b file.blend --python pose_probe.py -- bone out.json
"""

import json
import math
import sys

import bpy
import numpy as np

bone, out = sys.argv[sys.argv.index("--") + 1 :][:2]
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH")


def coords():
    dg = bpy.context.evaluated_depsgraph_get()
    me = mesh.evaluated_get(dg).to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    mesh.evaluated_get(dg).to_mesh_clear()
    return co.reshape(-1, 3)


rest = coords()
pb = arm.pose.bones[bone]
pb.rotation_mode = "XYZ"
pb.rotation_euler = (math.radians(40), 0, 0)
bpy.context.view_layer.update()
moved = np.linalg.norm(coords() - rest, axis=1)
side = np.sign(rest[:, 0])
with open(out, "w") as f:
    json.dump(
        {
            "max_move": float(moved.max()),
            "moved_left": int(((moved > 0.01) & (side > 0)).sum()),
            "moved_right": int(((moved > 0.01) & (side < 0)).sum()),
            "verts": len(rest),
        },
        f,
    )
