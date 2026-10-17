"""Count skin vertices weighted to two different fingers (finger bleed).

    blender -b body.blend --python weight_probe.py -- out.json
"""

import json
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH")
names = {g.index: g.name for g in mesh.vertex_groups}
fingers = ("thumb", "index", "middle", "ring", "pinky")
shared, finger_verts = 0, 0
for v in mesh.data.vertices:
    owners = {names[g.group].split("_")[0] for g in v.groups if g.weight > 0.01} & set(fingers)
    finger_verts += bool(owners)
    shared += len(owners) > 1
with open(out, "w") as f:
    json.dump({"shared": shared, "finger_verts": finger_verts}, f)
