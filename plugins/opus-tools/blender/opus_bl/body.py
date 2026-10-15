"""Body blockouts from proportion canons: humanoids, quadrupeds and dragons.

Proportions come from data, not guesswork. A canon places joints in head units
(humanoids) or in meters for a reference animal. Explicit primitives (ellipsoids for the
ribcage, pelvis and head, tapered capsules for limbs and necks) are placed on that
skeleton with exact sizes and orientations, fused by a voxel remesh into one watertight
body, smoothed, and decimated to a budget. An armature with UE-mannequin-style bone
names (pelvis, spine_01, upperarm_l, thigh_l, ...) is bound to it with heat weights.
That rig retargets in Unreal's IK Retargeter and maps onto Godot's humanoid profile.

Convention: the creature faces -Y (Blender front), its left side is +X, feet at z = 0.
"""

from __future__ import annotations

import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- canons

# Humanoid landmarks in head units (HU) above the floor; widths and radii in HU.
# Two-value radii are half-sizes (side to side, front to back).
HUMANOID = {
    "realistic": dict(
        heads=7.5, chin=6.5, shoulder=6.1, chest=5.45, waist=4.6, hip=3.95, crotch=3.65, knee=2.05, ankle=0.3,
        shoulder_x=0.92, hip_x=0.4, upper_arm=1.45, forearm=1.2, hand=0.75, foot=1.0,
        head_r=(0.33, 0.42), neck_r=0.25, chest_r=(0.72, 0.5), waist_r=(0.6, 0.42), hips_r=(0.74, 0.46), shoulder_r=0.3,
        upper_arm_r=0.22, elbow_r=0.17, wrist_r=0.12, hand_r=(0.15, 0.06), thigh_r=0.37, knee_r=0.22,
        calf_r=0.25, ankle_r=0.12, foot_r=(0.16, 0.1),
    ),
    "heroic": dict(
        heads=8.0, chin=7.0, shoulder=6.58, chest=5.85, waist=4.95, hip=4.25, crotch=3.95, knee=2.2, ankle=0.32,
        shoulder_x=1.1, hip_x=0.43, upper_arm=1.55, forearm=1.3, hand=0.8, foot=1.05,
        head_r=(0.33, 0.41), neck_r=0.28, chest_r=(0.86, 0.56), waist_r=(0.62, 0.43), hips_r=(0.72, 0.45), shoulder_r=0.36,
        upper_arm_r=0.26, elbow_r=0.19, wrist_r=0.13, hand_r=(0.16, 0.06), thigh_r=0.4, knee_r=0.23,
        calf_r=0.27, ankle_r=0.13, foot_r=(0.16, 0.1),
    ),
    "stylized": dict(
        heads=6.0, chin=5.0, shoulder=4.72, chest=4.2, waist=3.55, hip=3.05, crotch=2.85, knee=1.55, ankle=0.28,
        shoulder_x=0.82, hip_x=0.38, upper_arm=1.15, forearm=0.95, hand=0.6, foot=0.85,
        head_r=(0.4, 0.45), neck_r=0.22, chest_r=(0.7, 0.5), waist_r=(0.58, 0.42), hips_r=(0.68, 0.45), shoulder_r=0.28,
        upper_arm_r=0.21, elbow_r=0.17, wrist_r=0.13, hand_r=(0.15, 0.07), thigh_r=0.34, knee_r=0.22,
        calf_r=0.25, ankle_r=0.13, foot_r=(0.16, 0.1),
    ),
    "chibi": dict(
        heads=3.0, chin=2.0, shoulder=1.88, chest=1.68, waist=1.42, hip=1.18, crotch=1.08, knee=0.6, ankle=0.12,
        shoulder_x=0.42, hip_x=0.2, upper_arm=0.45, forearm=0.38, hand=0.28, foot=0.42,
        head_r=(0.52, 0.5), neck_r=0.13, chest_r=(0.42, 0.33), waist_r=(0.4, 0.31), hips_r=(0.42, 0.32), shoulder_r=0.14,
        upper_arm_r=0.11, elbow_r=0.1, wrist_r=0.09, hand_r=(0.11, 0.06), thigh_r=0.17, knee_r=0.14,
        calf_r=0.14, ankle_r=0.1, foot_r=(0.13, 0.09),
    ),
}

# Animals: joint coordinates for a reference animal, (x, y, z) in meters with the
# creature facing -Y, plus (side to side, vertical) radius. Left limbs only; mirrored.
QUADRUPED = {
    "dog": dict(
        height=0.55,
        nodes={
            "rump": ((0, 0.26, 0.45), (0.11, 0.1)), "back": ((0, 0.02, 0.46), (0.1, 0.11)),
            "chest": ((0, -0.22, 0.44), (0.12, 0.13)), "neck_base": ((0, -0.3, 0.52), (0.08, 0.08)),
            "neck_top": ((0, -0.37, 0.62), (0.065, 0.065)), "skull": ((0, -0.43, 0.65), (0.07, 0.07)),
            "snout": ((0, -0.58, 0.6), (0.035, 0.035)), "ear_l": ((0.05, -0.41, 0.74), (0.02, 0.012)),
            "tail_1": ((0, 0.34, 0.48), (0.035, 0.035)), "tail_2": ((0, 0.45, 0.53), (0.025, 0.025)),
            "tail_3": ((0, 0.55, 0.52), (0.014, 0.014)),
            "fshoulder_l": ((0.07, -0.2, 0.4), (0.06, 0.06)), "felbow_l": ((0.075, -0.18, 0.26), (0.04, 0.04)),
            "fwrist_l": ((0.075, -0.2, 0.08), (0.028, 0.028)), "fpaw_l": ((0.075, -0.25, 0.025), (0.035, 0.03)),
            "hip_l": ((0.075, 0.23, 0.4), (0.07, 0.07)), "knee_l": ((0.08, 0.15, 0.25), (0.05, 0.05)),
            "hock_l": ((0.075, 0.3, 0.13), (0.03, 0.03)), "hpaw_l": ((0.075, 0.27, 0.025), (0.035, 0.03)),
        },
    ),
    "horse": dict(
        height=1.6,
        nodes={
            "rump": ((0, 0.62, 1.48), (0.27, 0.27)), "back": ((0, 0.05, 1.42), (0.28, 0.3)),
            "chest": ((0, -0.5, 1.32), (0.3, 0.33)), "neck_base": ((0, -0.72, 1.5), (0.2, 0.22)),
            "neck_top": ((0, -0.95, 1.88), (0.13, 0.14)), "skull": ((0, -1.05, 1.98), (0.12, 0.13)),
            "snout": ((0, -1.22, 1.62), (0.08, 0.08)), "ear_l": ((0.07, -0.98, 2.13), (0.03, 0.015)),
            "tail_1": ((0, 0.86, 1.48), (0.06, 0.06)), "tail_2": ((0, 0.95, 1.2), (0.07, 0.05)),
            "tail_3": ((0, 0.98, 0.85), (0.05, 0.03)),
            "fshoulder_l": ((0.17, -0.52, 1.12), (0.13, 0.13)), "felbow_l": ((0.16, -0.45, 0.92), (0.08, 0.08)),
            "fwrist_l": ((0.15, -0.5, 0.45), (0.05, 0.05)), "fpaw_l": ((0.15, -0.55, 0.06), (0.06, 0.06)),
            "hip_l": ((0.2, 0.55, 1.25), (0.16, 0.16)), "knee_l": ((0.18, 0.42, 0.9), (0.1, 0.1)),
            "hock_l": ((0.16, 0.7, 0.55), (0.06, 0.06)), "hpaw_l": ((0.15, 0.66, 0.06), (0.06, 0.06)),
        },
    ),
    "cat": dict(
        height=0.25,
        nodes={
            "rump": ((0, 0.14, 0.22), (0.055, 0.05)), "back": ((0, 0.0, 0.215), (0.05, 0.055)),
            "chest": ((0, -0.12, 0.2), (0.055, 0.06)), "neck_base": ((0, -0.16, 0.23), (0.04, 0.04)),
            "neck_top": ((0, -0.19, 0.27), (0.035, 0.035)), "skull": ((0, -0.22, 0.29), (0.045, 0.042)),
            "snout": ((0, -0.27, 0.28), (0.022, 0.02)), "ear_l": ((0.03, -0.21, 0.34), (0.014, 0.006)),
            "tail_1": ((0, 0.19, 0.24), (0.014, 0.014)), "tail_2": ((0, 0.3, 0.3), (0.012, 0.012)),
            "tail_3": ((0, 0.36, 0.4), (0.01, 0.01)),
            "fshoulder_l": ((0.035, -0.11, 0.18), (0.03, 0.03)), "felbow_l": ((0.037, -0.1, 0.11), (0.02, 0.02)),
            "fwrist_l": ((0.037, -0.11, 0.035), (0.013, 0.013)), "fpaw_l": ((0.037, -0.135, 0.012), (0.017, 0.014)),
            "hip_l": ((0.037, 0.12, 0.18), (0.035, 0.035)), "knee_l": ((0.04, 0.08, 0.1), (0.025, 0.025)),
            "hock_l": ((0.037, 0.15, 0.055), (0.014, 0.014)), "hpaw_l": ((0.037, 0.13, 0.012), (0.017, 0.014)),
        },
    ),
}

QUAD_EDGES = [
    ("rump", "back"), ("back", "chest"), ("chest", "neck_base"), ("neck_base", "neck_top"),
    ("neck_top", "skull"), ("skull", "snout"), ("skull", "ear_l"),
    ("rump", "tail_1"), ("tail_1", "tail_2"), ("tail_2", "tail_3"),
    ("chest", "fshoulder_l"), ("fshoulder_l", "felbow_l"), ("felbow_l", "fwrist_l"), ("fwrist_l", "fpaw_l"),
    ("rump", "hip_l"), ("hip_l", "knee_l"), ("knee_l", "hock_l"), ("hock_l", "hpaw_l"),
]
QUAD_BONES = [
    ("pelvis", "rump", "back", "root"), ("spine_01", "back", "chest", "pelvis"),
    ("neck_01", "chest", "neck_base", "spine_01"), ("neck_02", "neck_base", "neck_top", "neck_01"),
    ("head", "neck_top", "skull", "neck_02"), ("jaw", "skull", "snout", "head"),
    ("tail_01", "rump", "tail_1", "pelvis"), ("tail_02", "tail_1", "tail_2", "tail_01"),
    ("tail_03", "tail_2", "tail_3", "tail_02"),
    ("upperarm_l", "fshoulder_l", "felbow_l", "spine_01"), ("lowerarm_l", "felbow_l", "fwrist_l", "upperarm_l"),
    ("hand_l", "fwrist_l", "fpaw_l", "lowerarm_l"),
    ("thigh_l", "hip_l", "knee_l", "pelvis"), ("calf_l", "knee_l", "hock_l", "thigh_l"),
    ("foot_l", "hock_l", "hpaw_l", "calf_l"),
]

# A western dragon: long neck and tail, horned wedge head, bat wings with finger spars.
DRAGON = dict(
    height=2.2,
    nodes={
        "rump": ((0, 0.9, 1.2), (0.42, 0.4)), "back": ((0, 0.1, 1.35), (0.5, 0.52)),
        "chest": ((0, -0.7, 1.3), (0.48, 0.55)), "neck_base": ((0, -1.15, 1.6), (0.3, 0.32)),
        "neck_mid": ((0, -1.4, 2.2), (0.22, 0.24)), "neck_top": ((0, -1.45, 2.75), (0.18, 0.2)),
        "skull": ((0, -1.7, 2.95), (0.2, 0.2)), "snout": ((0, -2.25, 2.85), (0.09, 0.1)),
        "tail_1": ((0, 1.55, 1.05), (0.3, 0.3)), "tail_2": ((0, 2.35, 0.8), (0.2, 0.2)),
        "tail_3": ((0, 3.2, 0.55), (0.11, 0.11)), "tail_4": ((0, 4.0, 0.4), (0.04, 0.04)),
        "fshoulder_l": ((0.38, -0.7, 1.05), (0.22, 0.22)), "felbow_l": ((0.5, -0.5, 0.62), (0.15, 0.15)),
        "fwrist_l": ((0.5, -0.75, 0.18), (0.11, 0.11)), "fpaw_l": ((0.5, -0.95, 0.07), (0.13, 0.08)),
        "hip_l": ((0.42, 0.85, 1.0), (0.3, 0.3)), "knee_l": ((0.52, 0.45, 0.6), (0.2, 0.2)),
        "hock_l": ((0.5, 1.05, 0.35), (0.12, 0.12)), "hpaw_l": ((0.5, 0.85, 0.07), (0.14, 0.08)),
        "wing_root_l": ((0.3, -0.55, 1.72), (0.14, 0.14)), "wing_elbow_l": ((1.25, -0.25, 2.85), (0.09, 0.09)),
        "wing_wrist_l": ((2.3, 0.1, 3.35), (0.06, 0.06)),
    },
    # finger spars of each wing (from the wrist), and membrane anchor points on the body
    fingers=[(3.9, 0.35, 3.75), (3.7, 1.35, 2.7), (2.8, 1.95, 1.95), (1.7, 2.05, 1.5)],
    membrane_body=[(0.3, -0.5, 1.6), (0.35, 0.9, 1.35)],
    horns=[((0.12, -1.6, 3.12), (0.16, 0.25, 3.42), 0.06), ((0.17, -1.55, 3.05), (0.3, 0.05, 3.15), 0.045)],
    spines=["neck_base", "neck_mid", "back", "rump", "tail_1", "tail_2", "tail_3"],
)
DRAGON_EDGES = [
    ("rump", "back"), ("back", "chest"), ("chest", "neck_base"), ("neck_base", "neck_mid"),
    ("neck_mid", "neck_top"), ("neck_top", "skull"), ("skull", "snout"),
    ("rump", "tail_1"), ("tail_1", "tail_2"), ("tail_2", "tail_3"), ("tail_3", "tail_4"),
    ("chest", "fshoulder_l"), ("fshoulder_l", "felbow_l"), ("felbow_l", "fwrist_l"), ("fwrist_l", "fpaw_l"),
    ("rump", "hip_l"), ("hip_l", "knee_l"), ("knee_l", "hock_l"), ("hock_l", "hpaw_l"),
    ("chest", "wing_root_l"), ("wing_root_l", "wing_elbow_l"), ("wing_elbow_l", "wing_wrist_l"),
]
DRAGON_BONES = [
    ("pelvis", "rump", "back", "root"), ("spine_01", "back", "chest", "pelvis"),
    ("neck_01", "chest", "neck_base", "spine_01"), ("neck_02", "neck_base", "neck_mid", "neck_01"),
    ("neck_03", "neck_mid", "neck_top", "neck_02"), ("head", "neck_top", "skull", "neck_03"),
    ("jaw", "skull", "snout", "head"),
    ("tail_01", "rump", "tail_1", "pelvis"), ("tail_02", "tail_1", "tail_2", "tail_01"),
    ("tail_03", "tail_2", "tail_3", "tail_02"), ("tail_04", "tail_3", "tail_4", "tail_03"),
    ("upperarm_l", "fshoulder_l", "felbow_l", "spine_01"), ("lowerarm_l", "felbow_l", "fwrist_l", "upperarm_l"),
    ("hand_l", "fwrist_l", "fpaw_l", "lowerarm_l"),
    ("thigh_l", "hip_l", "knee_l", "pelvis"), ("calf_l", "knee_l", "hock_l", "thigh_l"),
    ("foot_l", "hock_l", "hpaw_l", "calf_l"),
    ("wing_upperarm_l", "wing_root_l", "wing_elbow_l", "spine_01"),
    ("wing_forearm_l", "wing_elbow_l", "wing_wrist_l", "wing_upperarm_l"),
]

ARCHETYPES = {
    "humanoid": sorted(HUMANOID),
    "quadruped": sorted(QUADRUPED),
    "dragon": ["western"],
}


# ---------------------------------------------------------------- spec helpers

def _mirror_name(n: str) -> str:
    return n[:-2] + "_r" if n.endswith("_l") else n


def _mirror(nodes: dict, edges: list, bones: list):
    """Add the right side (x -> -x) for every node, edge and bone ending in _l."""
    nodes = dict(nodes)
    for n, (co, r) in list(nodes.items()):
        if n.endswith("_l"):
            nodes[_mirror_name(n)] = (Vector((-co[0], co[1], co[2])), r)
    edges = list(edges) + [(_mirror_name(a), _mirror_name(b)) for a, b in edges if a.endswith("_l") or b.endswith("_l")]
    bones = list(bones) + [
        (_mirror_name(n), _mirror_name(h), _mirror_name(t), _mirror_name(p)) for n, h, t, p in bones if n.endswith("_l")
    ]
    return nodes, edges, bones


def _humanoid(c: dict, pose: str):
    """Primitives, joints and bones for a humanoid canon, in head units."""
    a = math.radians(0 if pose == "T" else 45)
    arm = Vector((math.cos(a), 0, -math.sin(a)))
    sh = Vector((c["shoulder_x"], 0.0, c["shoulder"]))
    elbow = sh + arm * c["upper_arm"]
    wrist = elbow + arm * c["forearm"]
    hand = wrist + arm * c["hand"]
    hip_l = Vector((c["hip_x"], 0.0, c["hip"] - 0.15))
    knee = Vector((c["hip_x"] * 0.85, -0.03, c["knee"]))
    ankle = Vector((c["hip_x"] * 0.8, 0.04, c["ankle"]))
    toe = Vector((c["hip_x"] * 0.8, 0.04 - c["foot"] * 0.85, 0.05))
    chin, top = c["chin"], c["heads"]
    hr, cr, wr, pr = c["head_r"], c["chest_r"], c["waist_r"], c["hips_r"]
    torso_h = c["shoulder"] - c["crotch"]
    P = []  # primitives
    # head, jaw, nose and ears: a face needs a front
    P.append(("ellipsoid", (0, -0.03, chin + 0.52), (hr[0], hr[1], 0.53), None))
    P.append(("ellipsoid", (0, -0.1, chin + 0.24), (hr[0] * 0.72, hr[1] * 0.72, 0.26), None))
    P.append(("ellipsoid", (0, -hr[1] * 0.98, chin + 0.42), (0.065, 0.08, 0.12), None))
    P.append(("ellipsoid", (hr[0] * 0.97, 0.03, chin + 0.5), (0.05, 0.1, 0.15), None))
    P.append(("capsule", (0, 0.04, c["shoulder"] + 0.05), (0, 0.02, chin + 0.25), c["neck_r"], c["neck_r"] * 0.95))
    # torso: one lofted tube through elliptical sections (chest forward, seat back), plus glutes
    def lerp2(r1, r2, t):
        return (r1[0] + (r2[0] - r1[0]) * t, r1[1] + (r2[1] - r1[1]) * t)

    sections = [
        (c["crotch"] - 0.05, (pr[0] * 0.8, pr[1] * 0.85), 0.03),
        (c["crotch"] + 0.1, (pr[0] * 0.93, pr[1] * 0.95), 0.04),
        (c["hip"], pr, 0.04),
        ((c["hip"] + c["waist"]) / 2, lerp2(pr, wr, 0.6), 0.02),
        (c["waist"], wr, 0.0),
        ((c["waist"] + c["chest"]) / 2, lerp2(wr, cr, 0.55), -0.03),
        (c["chest"], cr, -0.05),
        ((c["chest"] + c["shoulder"]) / 2, (cr[0] * 1.02, cr[1] * 0.95), -0.03),
        (c["shoulder"], (cr[0] * 0.82, cr[1] * 0.8), 0.0),
        (c["shoulder"] + 0.14, (c["neck_r"] * 1.6, c["neck_r"] * 1.4), 0.03),
    ]
    P.append(("loft", [((0.0, dy, z), r) for z, r, dy in sections], "xy"))
    P.append(("ellipsoid", (pr[0] * 0.42, pr[1] * 0.45, c["crotch"] + 0.22), (pr[0] * 0.48, pr[1] * 0.6, 0.32), None))
    # shoulders: trapezius slope and deltoid mass
    P.append(("capsule", (0.12, 0.06, c["shoulder"] + 0.14), (c["shoulder_x"] * 0.82, 0.05, c["shoulder"] + 0.02),
              c["shoulder_r"] * 0.75, c["shoulder_r"] * 0.7))
    P.append(("ellipsoid", tuple(sh + Vector((-0.06, 0.02, -0.06))), (c["shoulder_r"] * 0.95, c["shoulder_r"] * 0.95, c["shoulder_r"] * 1.1), None))
    # arms
    P.append(("capsule", tuple(sh), tuple(elbow), c["upper_arm_r"], c["elbow_r"]))
    P.append(("capsule", tuple(elbow), tuple(wrist), c["elbow_r"] * 1.08, c["wrist_r"]))
    P.append(("ellipsoid", tuple(elbow + arm * c["forearm"] * 0.3), (c["elbow_r"] * 1.15, c["elbow_r"] * 1.05, c["forearm"] * 0.3), tuple(arm)))
    P.append(("ellipsoid", tuple(wrist + arm * c["hand"] * 0.45), (c["hand_r"][0], c["hand_r"][1], c["hand"] * 0.5), tuple(arm)))
    # legs: thigh, quad bulge, knee, calf muscle, foot and heel
    leg_up = (knee - hip_l).normalized()
    P.append(("capsule", tuple(hip_l), tuple(knee), c["thigh_r"], c["knee_r"]))
    P.append(("ellipsoid", tuple(hip_l.lerp(knee, 0.35) + Vector((0, -0.04, 0))), (c["thigh_r"] * 1.02, c["thigh_r"] * 1.02, (knee - hip_l).length * 0.36), tuple(leg_up)))
    P.append(("capsule", tuple(knee), tuple(ankle), c["knee_r"], c["ankle_r"]))
    leg_lo = (ankle - knee).normalized()
    P.append(("ellipsoid", tuple(knee.lerp(ankle, 0.3) + Vector((0, 0.05, 0))), (c["calf_r"], c["calf_r"] * 1.05, (ankle - knee).length * 0.3), tuple(leg_lo)))
    foot_c = Vector((ankle.x, ankle.y - c["foot"] * 0.3, c["foot_r"][1] * 0.95))
    P.append(("ellipsoid", tuple(foot_c), (c["foot_r"][0], c["foot_r"][1], c["foot"] * 0.52), (0, -1, 0)))
    P.append(("ellipsoid", (ankle.x, ankle.y + 0.04, c["ankle_r"] * 1.05), (c["ankle_r"] * 1.1, c["ankle_r"] * 1.2, c["ankle_r"] * 1.1), None))
    # mirror the left-side primitives (x > 0) to the right
    mirrored = []
    for prim in P:
        if prim[0] == "loft":
            continue  # centered on the body
        pts = [Vector(v) for v in prim[1:3]] if prim[0] == "capsule" else [Vector(prim[1])]
        if all(v.x > 1e-6 for v in pts):
            if prim[0] == "capsule":
                mirrored.append(("capsule", (-prim[1][0], prim[1][1], prim[1][2]), (-prim[2][0], prim[2][1], prim[2][2]), prim[3], prim[4]))
            else:
                axis = prim[3] and (-prim[3][0], prim[3][1], prim[3][2])
                mirrored.append(("ellipsoid", (-prim[1][0], prim[1][1], prim[1][2]), prim[2], axis))
    P += mirrored
    joints = {
        "hips": Vector((0, 0, c["hip"])), "pelvis_top": Vector((0, 0, c["hip"] + 0.25)),
        "waist": Vector((0, 0, c["waist"])), "chest": Vector((0, 0, c["chest"])),
        "neck_base": Vector((0, 0.02, c["shoulder"] + 0.12)), "neck_top": Vector((0, 0.02, chin + 0.1)),
        "top": Vector((0, 0, top)), "clav_l": Vector((0.15, 0.02, c["shoulder"] + 0.02)),
        "shoulder_l": sh, "elbow_l": elbow, "wrist_l": wrist, "hand_l": hand,
        "hip_l": hip_l, "knee_l": knee, "ankle_l": ankle, "ball_l": ankle.lerp(toe, 0.7), "toe_l": toe,
    }
    for n in list(joints):
        if n.endswith("_l"):
            v = joints[n]
            joints[n[:-2] + "_r"] = Vector((-v.x, v.y, v.z))
    bones = [
        ("pelvis", "hips", "pelvis_top", "root"), ("spine_01", "pelvis_top", "waist", "pelvis"),
        ("spine_02", "waist", "chest", "spine_01"), ("spine_03", "chest", "neck_base", "spine_02"),
        ("neck_01", "neck_base", "neck_top", "spine_03"), ("head", "neck_top", "top", "neck_01"),
    ]
    for s in ("l", "r"):
        bones += [
            (f"clavicle_{s}", f"clav_{s}", f"shoulder_{s}", "spine_03"),
            (f"upperarm_{s}", f"shoulder_{s}", f"elbow_{s}", f"clavicle_{s}"),
            (f"lowerarm_{s}", f"elbow_{s}", f"wrist_{s}", f"upperarm_{s}"),
            (f"hand_{s}", f"wrist_{s}", f"hand_{s}", f"lowerarm_{s}"),
            (f"thigh_{s}", f"hip_{s}", f"knee_{s}", "pelvis"),
            (f"calf_{s}", f"knee_{s}", f"ankle_{s}", f"thigh_{s}"),
            (f"foot_{s}", f"ankle_{s}", f"ball_{s}", f"calf_{s}"),
            (f"ball_{s}", f"ball_{s}", f"toe_{s}", f"foot_{s}"),
        ]
    return P, joints, bones


TORSO_NODES = ("rump", "back", "chest")


def _animal(data: dict, edges: list, bones: list):
    """Primitives, joints and bones for an animal: capsules along every edge, plus torso ellipsoids."""
    nodes = {n: (Vector(co), r) for n, (co, r) in data["nodes"].items()}
    nodes, edges, bones = _mirror(nodes, edges, bones)
    P = []
    for a, b in edges:
        (pa, ra), (pb, rb) = nodes[a], nodes[b]
        P.append(("capsule", tuple(pa), tuple(pb), (ra[0] + ra[1]) / 2, (rb[0] + rb[1]) / 2))
    # torso: lofted sections from behind the rump to in front of the chest (vertical rings in XZ)
    rump, back, chest = (nodes[n] for n in TORSO_NODES)
    ext = (rump[0] - chest[0]).normalized() * rump[1][0] * 0.6
    sections = [
        (rump[0] + ext, (rump[1][0] * 0.55, rump[1][1] * 0.6)), (rump[0], rump[1]),
        (rump[0].lerp(back[0], 0.5), tuple((a + b) / 2 * 1.04 for a, b in zip(rump[1], back[1]))),
        (back[0], back[1]), (back[0].lerp(chest[0], 0.5), tuple((a + b) / 2 * 1.04 for a, b in zip(back[1], chest[1]))),
        (chest[0], chest[1]), (chest[0] - ext, (chest[1][0] * 0.6, chest[1][1] * 0.65)),
    ]
    P.append(("loft", [(tuple(co), r) for co, r in sections], "xz"))
    skull, snout = nodes["skull"][0], nodes["snout"][0]
    sr = nodes["skull"][1]
    P.append(("ellipsoid", tuple(skull.lerp(snout, 0.2)), (sr[0] * 1.05, sr[1] * 1.0, (snout - skull).length * 0.45), tuple(snout - skull)))
    joints = {n: co for n, (co, _) in nodes.items()}
    return P, joints, bones, nodes


def _add_capsule(bm, a, b, ra: float, rb: float, segments: int = 16):
    a, b = Vector(a), Vector(b)
    d = b - a
    if d.length > 1e-6:
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=ra, radius2=rb, depth=d.length,
                              matrix=Matrix.Translation((a + b) / 2) @ rot)
    for p, r in ((a, ra), (b, rb)):
        bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=segments // 2, radius=r, matrix=Matrix.Translation(p))


def _add_ellipsoid(bm, center, radii, axis=None):
    rot = Vector(axis).to_track_quat("Z", "Y").to_matrix().to_4x4() if axis else Matrix.Identity(4)
    scale = Matrix.Diagonal((radii[0], radii[1], radii[2], 1.0))
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0, matrix=Matrix.Translation(center) @ rot @ scale)


def _add_loft(bm, sections, plane: str = "xy", segments: int = 24):
    """A closed tube through elliptical sections. plane "xy": horizontal rings (upright
    torsos); "xz": vertical rings (horizontal bodies). Each section is (center, (r1, r2))."""
    u, v = (Vector((1, 0, 0)), Vector((0, 1, 0))) if plane == "xy" else (Vector((1, 0, 0)), Vector((0, 0, 1)))
    rings = []
    for center, (r1, r2) in sections:
        c = Vector(center)
        rings.append([bm.verts.new(c + u * (r1 * math.cos(t)) + v * (r2 * math.sin(t)))
                      for t in (2 * math.pi * i / segments for i in range(segments))])
    for a, b in zip(rings, rings[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((a[i], a[j], b[j], b[i]))
    for ring, center in ((rings[0], sections[0][0]), (rings[-1], sections[-1][0])):
        hub = bm.verts.new(Vector(center))
        for i in range(segments):
            bm.faces.new((hub, ring[(i + 1) % segments], ring[i]))


def _add_cone(bm, base, tip, radius: float, segments: int = 8):
    base, tip = Vector(base), Vector(tip)
    axis = tip - base
    rot = axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=0.0, depth=axis.length,
                          matrix=Matrix.Translation(base + axis / 2) @ rot)


def _dragon_parts(nodes: dict, data: dict):
    """Extra solids (finger spars, horns, back spines), the open wing membranes, and the
    finger joints and bones that let the wings fold."""
    P, membranes, joints, bones = [], [], {}, []
    for side in (1, -1):
        sx = Vector((side, 1, 1))  # element-wise: mirrors x for the right side
        s = "l" if side == 1 else "r"
        wrist = Vector(nodes["wing_wrist_l"][0]) * sx
        tips = [Vector(f) * sx for f in data["fingers"]]
        for i, tip in enumerate(tips, 1):
            P.append(("capsule", tuple(wrist), tuple(tip), 0.07, 0.035))
            joints[f"wing_tip_{i}_{s}"] = tip
            bones.append((f"wing_finger_0{i}_{s}", f"wing_wrist_{s}", f"wing_tip_{i}_{s}", f"wing_forearm_{s}"))
        for base, tip, r in data["horns"]:
            P.append(("cone", tuple(Vector(base) * sx), tuple(Vector(tip) * sx), r))
        root = Vector(nodes["wing_root_l"][0]) * sx
        elbow = Vector(nodes["wing_elbow_l"][0]) * sx
        body = [Vector(p) * sx for p in data["membrane_body"]]
        # scalloped trailing edge: between finger tips the membrane sags toward the wrist
        edge = []
        for i, tip in enumerate(tips):
            edge.append(tip)
            nxt = tips[i + 1] if i + 1 < len(tips) else body[1]
            edge.append(tip.lerp(nxt, 0.5).lerp(wrist, 0.22))
        ring = [root, elbow, wrist] + edge + [body[1], body[0]]
        membranes.append(ring if side == 1 else list(reversed(ring)))
    for n in data["spines"]:
        co, rad = nodes[n]
        top = Vector(co) + Vector((0, 0, rad[1] * 0.85))
        P.append(("cone", tuple(top - Vector((0, 0, rad[1] * 0.3))), tuple(top + Vector((0, 0.06, rad[1] * 0.55 + 0.06))), rad[0] * 0.28))
    return P, membranes, joints, bones


def _fuse(name: str, prims: list, voxel: float, target_tris: int):
    """Union the primitives with a voxel remesh, smooth, and decimate to the triangle budget."""
    bm = bmesh.new()
    for prim in prims:
        kind = prim[0]
        if kind == "capsule":
            _add_capsule(bm, *prim[1:])
        elif kind == "ellipsoid":
            _add_ellipsoid(bm, *prim[1:])
        elif kind == "cone":
            _add_cone(bm, *prim[1:])
        elif kind == "loft":
            _add_loft(bm, *prim[1:])
    me = bpy.data.meshes.new(name + "_parts")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name + "_parts", me)
    bpy.context.scene.collection.objects.link(obj)
    rm = obj.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    sm = obj.modifiers.new("smooth", "SMOOTH")
    sm.factor, sm.iterations = 0.5, 6
    dg = bpy.context.evaluated_depsgraph_get()
    fused = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(me)
    _drop_debris(fused)
    tris = sum(len(p.vertices) - 2 for p in fused.polygons)
    if target_tris and tris > target_tris:
        tmp = bpy.data.objects.new(name + "_tmp", fused)
        bpy.context.scene.collection.objects.link(tmp)
        dec = tmp.modifiers.new("decimate", "DECIMATE")
        dec.ratio = target_tris / tris
        dg = bpy.context.evaluated_depsgraph_get()
        reduced = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(fused)
        fused = reduced
    return fused


def _drop_debris(mesh, keep: float = 0.01):
    """Delete loose islands under ``keep`` of the vertex count: the voxel remesh can
    leave crumbs where a part is thinner than a voxel, and they break heat weighting."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    seen, islands = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        island, stack = [], [v]
        while stack:
            x = stack.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            island.append(x)
            stack.extend(e.other_vert(x) for e in x.link_edges)
        islands.append(island)
    crumbs = [v for isl in islands if len(isl) < keep * len(bm.verts) for v in isl]
    if crumbs:
        bmesh.ops.delete(bm, geom=crumbs, context="VERTS")
        bm.to_mesh(mesh)
    bm.free()
    return len(islands)


def _add_membranes(mesh, membranes, thickness: float) -> range:
    """Append wing membranes as thin closed solids (so they read from both sides).
    Existing vertices and their weights are kept; returns the new vertex indices."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    first = len(bm.verts)
    faces = []
    for ring in membranes:
        verts = [bm.verts.new(p) for p in ring]
        center = bm.verts.new(sum(ring[2:], Vector()) / len(ring[2:]))
        for a, b in zip(verts, verts[1:] + verts[:1]):
            faces.append(bm.faces.new((center, a, b)))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    bmesh.ops.solidify(bm, geom=faces, thickness=thickness)
    count = len(bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    return range(first, count)


def _deselect_all():
    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        if o is not None:
            o.select_set(False)


def _armature(name: str, joints: dict, bones: list, root_height: float):
    arm_data = bpy.data.armatures.new(name + "_rig")
    arm = bpy.data.objects.new(name + "_rig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    _deselect_all()
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    root = eb.new("root")
    root.head, root.tail = (0, 0, 0), (0, 0, max(root_height * 0.15, 0.05))
    for bname, head, tail, parent in bones:
        b = eb.new(bname)
        b.head = joints[head]
        b.tail = joints[tail]
        if (b.tail - b.head).length < 1e-4:
            b.tail = b.head + Vector((0, 0, 0.05))
        b.parent = eb[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def _segment_distance(p, a, b) -> float:
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (a + ab * t - p).length


def _nearest_bone_weights(mesh_obj, arm, indices, only=None, k: int = 2) -> int:
    """Weight vertices by inverse squared distance to their k nearest bone segments.
    Covers what heat weighting can't reach (thin membranes, unweighted islands)."""
    segs = [(b.name, b.head_local, b.tail_local) for b in arm.data.bones
            if b.name != "root" and (only is None or b.name in only)]
    groups = {n: mesh_obj.vertex_groups.get(n) or mesh_obj.vertex_groups.new(name=n) for n, _, _ in segs}
    verts = mesh_obj.data.vertices
    for i in indices:
        p = verts[i].co
        near = sorted((_segment_distance(p, h, t), n) for n, h, t in segs)[:k]
        w = [1.0 / max(d, 1e-4) ** 2 for d, _ in near]
        for (_, n), wi in zip(near, w):
            groups[n].add([i], wi / sum(w), "REPLACE")
    return len(indices)


def _bind(mesh_obj, arm) -> tuple[str, int]:
    """Bind with automatic (heat) weights and fill any vertex heat missed from the nearest
    bones. Falls back to envelope weights when heat weighting fails for most of the mesh.
    Returns (method, vertices filled by nearest-bone weights)."""
    _deselect_all()
    mesh_obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        missing = [v.index for v in mesh_obj.data.vertices if not any(g.weight > 1e-4 for g in v.groups)]
        if len(missing) <= len(mesh_obj.data.vertices) * 0.25:
            return "automatic", _nearest_bone_weights(mesh_obj, arm, missing)
    except RuntimeError:
        pass
    mesh_obj.vertex_groups.clear()
    bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
    missing = [v.index for v in mesh_obj.data.vertices if not any(g.weight > 1e-4 for g in v.groups)]
    return "envelope", _nearest_bone_weights(mesh_obj, arm, missing)


def build(
    archetype: str = "humanoid",
    preset: str = "realistic",
    height: float = 0.0,
    pose: str = "A",
    target_tris: int = 10000,
    rig: bool = True,
    out_blend: str = "",
    out_glb: str = "",
    name: str = "",
) -> dict:
    """Build a rigged blockout. ``height`` is total height in meters (default: the canon's)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    membranes = []
    if archetype == "humanoid":
        if preset not in HUMANOID:
            raise ValueError(f"humanoid presets: {sorted(HUMANOID)}")
        c = HUMANOID[preset]
        prims, joints, bones = _humanoid(c, pose.upper())
        default_height = 1.0 if preset == "chibi" else 1.8
        span = c["heads"]
    elif archetype in ("quadruped", "dragon"):
        if archetype == "quadruped" and preset not in QUADRUPED:
            raise ValueError(f"quadruped presets: {sorted(QUADRUPED)}")
        data = QUADRUPED[preset] if archetype == "quadruped" else DRAGON
        edges = QUAD_EDGES if archetype == "quadruped" else DRAGON_EDGES
        bone_spec = QUAD_BONES if archetype == "quadruped" else DRAGON_BONES
        prims, joints, bones, nodes = _animal(data, edges, bone_spec)
        if archetype == "dragon":
            extra, membranes, finger_joints, finger_bones = _dragon_parts(nodes, data)
            prims += extra
            joints.update(finger_joints)
            bones += finger_bones
        default_height = data["height"]
        pts = [Vector(p) for p in joints.values()]
        span = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
    else:
        raise ValueError(f"archetype must be one of {sorted(ARCHETYPES)}")
    label = name or f"{archetype}_{preset}"

    # dragons have thin wing spars: a finer voxel keeps them in one piece
    mesh = _fuse(label, prims, voxel=span / (240.0 if archetype == "dragon" else 170.0), target_tris=target_tris)
    body = bpy.data.objects.new(label, mesh)
    bpy.context.scene.collection.objects.link(body)
    for p in mesh.polygons:
        p.use_smooth = True

    # feet on the floor, then scale everything to the requested height
    zs = [v.co.z for v in mesh.vertices]
    z0, z1 = min(zs), max(zs)
    target = height or default_height
    s = target / max(z1 - z0, 1e-6)
    to_floor = Matrix.Scale(s, 4) @ Matrix.Translation((0, 0, -z0))
    mesh.transform(to_floor)
    joints = {n: to_floor @ Vector(v) for n, v in joints.items()}
    landmarks = None
    if archetype == "humanoid":
        # the canon in meters, for modeling to and for checking against
        landmarks = {k: (to_floor @ Vector((0, 0, c[k]))).z for k in
                     ("chin", "shoulder", "chest", "waist", "hip", "crotch", "knee", "ankle")}
        landmarks.update(
            head_height=s, shoulder_width=2 * (c["shoulder_x"] + c["shoulder_r"]) * s, hip_width=2 * c["hips_r"][0] * s,
            chest_depth=2 * c["chest_r"][1] * s, upper_arm=c["upper_arm"] * s, forearm=c["forearm"] * s,
            hand=c["hand"] * s, foot=c["foot"] * s, leg=(c["hip"] - 0.15 - c["ankle"]) * s,
        )
        landmarks = {k: round(v, 4) for k, v in landmarks.items()}

    mat = bpy.data.materials.new("blockout")
    mat.diffuse_color = (0.72, 0.62, 0.55, 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.72, 0.62, 0.55, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.6
    mesh.materials.append(mat)

    binding, filled = None, 0
    if rig:
        arm = _armature(label, joints, bones, target)
        binding, filled = _bind(body, arm)
    if membranes:
        # added after binding: heat weighting can't solve paper-thin sheets, so the
        # membranes take their weights from the nearest wing, finger and spine bones
        rings = [[to_floor @ p for p in ring] for ring in membranes]
        new_verts = _add_membranes(mesh, rings, thickness=span / 150.0 * s)
        for p in mesh.polygons:
            p.use_smooth = True
        if rig:
            wing = {b.name for b in arm.data.bones if b.name.startswith("wing_") or b.name in ("spine_01", "pelvis")}
            filled += _nearest_bone_weights(body, arm, new_verts, only=wing)
    tris = sum(len(p.vertices) - 2 for p in mesh.polygons)
    if out_blend:
        os.makedirs(os.path.dirname(os.path.abspath(out_blend)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    if out_glb:
        os.makedirs(os.path.dirname(os.path.abspath(out_glb)), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB")
    return {
        "archetype": archetype,
        "preset": preset,
        "height_m": round(target, 4),
        "pose": pose.upper() if archetype == "humanoid" else None,
        "heads_tall": HUMANOID[preset]["heads"] if archetype == "humanoid" else None,
        "tris": tris,
        "bones": (["root"] + [b[0] for b in bones]) if rig else [],
        "binding": binding,
        "weights_filled_nearest": filled,
        "landmarks_m": landmarks,
        "joints_m": {n: [round(x, 4) for x in v] for n, v in joints.items()},
        "blend": out_blend or None,
        "glb": out_glb or None,
    }
