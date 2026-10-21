"""Part-map and floating-part cases built on a humanoid blockout, for test_parts.py.

    blender -b human.blend --python parts_cases.py -- out_dir

Writes, each from the unchanged blockout:

float.blend   a 4 cm-radius sphere, 15 cm above the head, as an island of the skinned body
              weighted to ``head`` (a floater only the island check can see)
tusk.blend    a 1 cm tusk island 7.5 mm in front of the face, weighted to ``head``
touch.blend   islands that don't float: one sunk 3 mm into the face, one 1 mm off the side of
              the head, one wholly inside the head
crate.blend   a 40 cm crate on the floor 1.5 m beside the body (it stands, like the body) and a
              10 cm box 50 cm above the floor 1.5 m on the other side (it floats)
outfit.blend  a hood skinned 100% to ``head``; a sword parented to the non-deform bone
              ``weapon_r`` (a child of ``hand_r``) with a ``weapon_r`` vertex group, its grip
              through the hand; a shirt tube skinned to ``spine_02`` and ``spine_03`` whose
              bottom ring has no weights; a plate skinned 100% to ``thigh_r``, 5 mm in front
              of the thigh
cases.json    where the planted things are (world space, meters)
"""

import itertools
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)
base = bpy.data.filepath
info = {}


def body_and_rig():
    body = max((o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature()), key=lambda o: len(o.data.vertices))
    return body, body.find_armature()


def world_co(obj) -> np.ndarray:
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.array([tuple(obj.matrix_world @ v.co) for v in me.vertices])
    ev.to_mesh_clear()
    return co


def region(body, bone) -> np.ndarray:
    """World coordinates of the vertices ``bone`` dominates."""
    gi = body.vertex_groups[bone].index
    co = world_co(body)
    keep = [v.index for v in body.data.vertices if v.groups and max(v.groups, key=lambda g: g.weight).group == gi]
    return co[keep]


def add_island(body, center, radius, group):
    bm = bmesh.new()
    bm.from_mesh(body.data)
    n0 = len(bm.verts)
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radius, matrix=Matrix.Translation(body.matrix_world.inverted() @ Vector(center)))
    bm.to_mesh(body.data)
    bm.free()
    body.vertex_groups[group].add(list(range(n0, len(body.data.vertices))), 1.0, "REPLACE")


def mesh_object(name, bm, rig=None, groups=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    if rig is not None:
        obj.parent = rig
        obj.modifiers.new("Armature", "ARMATURE").object = rig
    for bone, idx in (groups or {}).items():
        obj.vertex_groups.new(name=bone).add(idx, 1.0, "REPLACE")
    return obj


def box(size, center):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1.0)))
    return bm


def save(name):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name), copy=True)
    bpy.ops.wm.open_mainfile(filepath=base)


# ---------------------------------------------------------------- floaters and touching islands

body, rig = body_and_rig()
head = region(body, "head")
top = head[np.argmax(head[:, 2])]
add_island(body, top + np.array([0, 0, 0.15 + 0.04]), 0.04, "head")
info["float"] = {"center_m": (top + [0, 0, 0.19]).tolist(), "gap_m": 0.15}
save("float.blend")

body, rig = body_and_rig()
head = region(body, "head")
front = head[np.argmin(head[:, 1])]  # the face looks toward -Y
add_island(body, front + np.array([0, -(0.0075 + 0.01), 0]), 0.01, "head")
info["tusk"] = {"center_m": (front + [0, -0.0175, 0]).tolist(), "gap_m": 0.0075}
save("tusk.blend")

body, rig = body_and_rig()
head = region(body, "head")
front = head[np.argmin(head[:, 1])]
side = head[np.argmax(head[:, 0])]
add_island(body, front + np.array([0, -(0.01 - 0.003), 0]), 0.01, "head")  # sunk 3 mm into the face
add_island(body, side + np.array([0.01 + 0.001, 0, 0]), 0.01, "head")  # 1 mm off the side
add_island(body, (head.min(axis=0) + head.max(axis=0)) / 2, 0.01, "head")  # inside the head
save("touch.blend")

lowest = float(world_co(body_and_rig()[0])[:, 2].min())
mesh_object("crate", box((0.4, 0.4, 0.4), (1.5, 0.0, lowest + 0.2)))
mesh_object("hover", box((0.1, 0.1, 0.1), (-1.5, 0.0, lowest + 0.55)))
info["crate"] = {"hover_center_m": [-1.5, 0.0, lowest + 0.55]}
save("crate.blend")

# ---------------------------------------------------------------- outfit: hood, sword, shirt, plate

body, rig = body_and_rig()
head, hand = region(body, "head"), region(body, "hand_r")
spine = np.concatenate([region(body, "spine_02"), region(body, "spine_03")])
thigh = region(body, "thigh_r")

bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = rig.data.edit_bones
w = eb.new("weapon_r")
w.head = eb["hand_r"].tail
w.tail = eb["hand_r"].tail + Vector((0, 0, -0.1))
w.parent = eb["hand_r"]
w.use_deform = False
bpy.ops.object.mode_set(mode="OBJECT")

# hood: the head's bounding ellipsoid, open at the face and below
lo, hi = head.min(axis=0), head.max(axis=0)
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z < 0.1 and f.calc_center_median().y < 0.2], context="FACES")
bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector((lo + hi) / 2)) @ Matrix.Diagonal((*((hi - lo) / 2), 1.0)), verts=bm.verts)
hood = mesh_object("hood", bm, rig, {"head": list(range(len(bm.verts)))})

# sword: grip through the hand, blade hanging down; parented to the non-deform weapon bone
hc = (hand.min(axis=0) + hand.max(axis=0)) / 2
sword = mesh_object("sword", box((0.03, 0.012, 0.7), hc + np.array([0, 0, -0.25])), groups={"weapon_r": list(range(8))})
mw = sword.matrix_world.copy()
sword.parent, sword.parent_type, sword.parent_bone = rig, "BONE", "weapon_r"
bpy.context.view_layer.update()
sword.matrix_world = mw

# shirt: an open tube around the torso; ring 0 has no weights, rings 1-4 spine_02, 5-9 spine_03
slo, shi = spine.min(axis=0), spine.max(axis=0)
c, r = (slo + shi) / 2, (shi - slo) / 2 * 1.15
bm = bmesh.new()
rings = [[bm.verts.new((c[0] + r[0] * math.cos(2 * math.pi * i / 24), c[1] + r[1] * math.sin(2 * math.pi * i / 24),
                        slo[2] + (shi[2] - slo[2]) * k / 9)) for i in range(24)] for k in range(10)]
for a, b in itertools.pairwise(rings):
    for i in range(24):
        bm.faces.new((a[i], a[(i + 1) % 24], b[(i + 1) % 24], b[i]))
shirt = mesh_object("shirt", bm, rig, {"spine_02": list(range(24, 120)), "spine_03": list(range(120, 240))})

# plate: 5 mm in front of the thigh's frontmost point, skinned rigidly to thigh_r
p = thigh[np.argmin(thigh[:, 1])]
plate = mesh_object("plate", box((0.08, 0.006, 0.08), p + np.array([0, -(0.005 + 0.003), 0])), rig,
                    {"thigh_r": list(range(8))})
info["outfit"] = {"plate_gap_m": 0.005, "sword_center_m": (hc + [0, 0, -0.25]).tolist()}
save("outfit.blend")

with open(os.path.join(out_dir, "cases.json"), "w", encoding="utf-8") as f:
    json.dump(info, f, indent=1)
print("CASES", sorted(info))
