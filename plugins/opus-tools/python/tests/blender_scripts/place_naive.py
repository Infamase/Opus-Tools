"""Place a prop the naive way, by eye: its grip center at the middle of the palm (so the
handle runs through the hand) or a few centimeters off it.

    blender -b --factory-startup --python place_naive.py -- modules rig.blend prop.blend out.blend inside|floating
"""

import sys

import bpy
from mathutils import Matrix

modules, rig, prop, out, mode = sys.argv[sys.argv.index("--") + 1 :][:5]
sys.path.insert(0, modules)
from opus_bl import grip  # noqa: E402

bpy.ops.wm.open_mainfile(filepath=rig)
objs = grip._append_objects(prop)
empty = grip._grip_empties(objs)[0]
root = grip._top(empty)
arm = grip._armature(bpy.context.scene.objects)
info = grip.find_hand(arm, "r")
f = grip.hand_frame(arm, info)
center = f["wrist"] + f["a"] * (f["palm_len"] * 0.6)
if mode == "floating":
    center -= f["n"] * 0.15  # well off the back of the hand
offset = center - empty.matrix_world.translation
root.matrix_world = Matrix.Translation(offset) @ root.matrix_world
bpy.ops.wm.save_as_mainfile(filepath=out)
