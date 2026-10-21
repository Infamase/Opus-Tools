"""Measure a body blockout as built: bone lengths, and the left foot and hand on the skin.

    blender -b body.blend --python body_probe.py -- out.json

Foot length is heel to toe tip along Y (the foot axis) over the skin below the ankle joint;
hand length is wrist joint to the farthest hand vertex along the hand bone (ANSUR II
measures both this way: heel to longest toe, wrist crease to middle fingertip).
"""

import json
import sys

import bpy
import numpy as np

out = sys.argv[sys.argv.index("--") + 1]
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH")
mw = mesh.matrix_world
co = np.array([tuple(mw @ v.co) for v in mesh.data.vertices])
bones = {b.name: (np.array(arm.matrix_world @ b.head_local), np.array(arm.matrix_world @ b.tail_local))
         for b in arm.data.bones}
groups = {g.index: g.name for g in mesh.vertex_groups}
used = {groups[g.group] for v in mesh.data.vertices for g in v.groups if g.weight > 0.05}
rep = {
    "height": float(co[:, 2].max() - co[:, 2].min()),
    "lengths": {n: float(np.linalg.norm(t - h)) for n, (h, t) in bones.items()},
    "weighted_bones": sorted(used),
}
if "hand_l" in bones and "clavicle_l" not in bones:  # a quadruped: each foot's lowest skin, left side
    mid = (bones["thigh_l"][0][1] + bones["upperarm_l"][0][1]) / 2
    left = co[:, 0] > 0
    rep["feet_min_z"] = {"front": float(co[left & (co[:, 1] < mid), 2].min()),
                         "hind": float(co[left & (co[:, 1] > mid), 2].min())}
if "middle_01_l" in bones:
    left = co[:, 0] > 0
    ankle = bones["foot_l"][0]
    foot = co[left & (co[:, 2] < ankle[2])]
    rep["foot_length"] = float(foot[:, 1].max() - foot[:, 1].min())
    rep["foot_breadth"] = float(foot[:, 0].max() - foot[:, 0].min())
    hand_groups = {i for i, n in groups.items() if n.endswith("_l") and n.split("_")[0] in
                   ("hand", "thumb", "index", "middle", "ring", "pinky")}
    in_hand = np.array([any(g.group in hand_groups and g.weight > 0.5 for g in v.groups) for v in mesh.data.vertices])
    wrist, knuckles = bones["hand_l"]
    palm = np.linalg.norm(knuckles - wrist)
    axis = (knuckles - wrist) / palm
    along = (co - wrist) @ axis
    rep["hand_length"] = float(along[in_hand].max())
    rep["hand_verts"] = int(in_hand.sum())
    # breadth across the metacarpal heads, thumb excluded: hand skin just short of the knuckles
    thumb = {i for i, n in groups.items() if n.startswith("thumb_") and n.endswith("_l")}
    on_thumb = np.array([any(g.group in thumb and g.weight > 0.2 for g in v.groups) for v in mesh.data.vertices])
    ring = co[in_hand & ~on_thumb & (along > 0.85 * palm) & (along < palm)]
    across = np.cross(axis, np.array(arm.matrix_world.to_3x3() @ arm.data.bones["hand_l"].z_axis))
    rep["hand_breadth"] = float(np.ptp((ring - wrist) @ across)) if len(ring) else 0.0
with open(out, "w", encoding="utf-8") as f:
    json.dump(rep, f)
