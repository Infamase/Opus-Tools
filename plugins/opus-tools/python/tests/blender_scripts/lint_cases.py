"""Mesh Lint cases that used to read wrong, saved into one folder.

    blender -b --factory-startup --python lint_cases.py -- out_dir

- rot120.blend / rot120_flip.blend: a closed cylinder rotated 120 degrees about X (a prop in a
  hand), as built and with one side face reversed.
- flat.glb / flat_flip.glb: a closed, flat-shaded mesh in two parts (box and cylinder),
  exported to glTF, whose importer splits every vertex; the second with one triangle reversed.
- rigid.blend: a skinned Body with no vertex groups, and props on a weapon_r bone: AxeHead (an
  8-sided cylinder, so n-gon caps) under a bone-parented empty, Blade parented to the bone.
- tusk_float.blend / tusk_touch.blend: one mesh "goblin" in pieces: a body on the ground, a
  head sunk into it, an eye inside the head, and a tusk beside the face 7.5 mm off the head
  (1 mm off in tusk_touch). The tusk's box lies inside the head's box.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mesh_object(name, build, flat=False, flip_face=None):
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")  # the shape builders fill it (calc_uvs)
    build(bm)
    if flat:
        for f in bm.faces:
            f.smooth = False
    if flip_face is not None:
        bm.faces.ensure_lookup_table()
        bm.faces[flip_face].normal_flip()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def cylinder(r, depth, segments=8, at=(0, 0, 0)):
    return lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r, depth=depth,
                                            matrix=Matrix.Translation(at), calc_uvs=True)


def box(size, at):
    return lambda bm: bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(at) @ Matrix.Diagonal((*size, 1.0)),
                                            calc_uvs=True)


def save(name):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name))


# ---------------------------------------------------------------- rotated past 90 degrees
for flip in (False, True):
    reset()
    blade = mesh_object("blade", cylinder(0.05, 1.0), flip_face=0 if flip else None)  # face 0: a side
    blade.rotation_euler = (math.radians(120), 0, 0)
    blade.location = (0, 0, 0.5)
    save("rot120_flip.blend" if flip else "rot120.blend")


# ---------------------------------------------------------------- flat-shaded glTF
def two_parts(bm):
    box((0.4, 0.4, 0.3), (0, 0, 0.15))(bm)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
    cylinder(0.1, 0.4, segments=16, at=(0.6, 0, 0.2))(bm)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])


for flip in (False, True):
    reset()
    mesh_object("Crate", two_parts, flat=True, flip_face=5 if flip else None)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, "flat_flip.glb" if flip else "flat.glb"), export_format="GLB")


# ---------------------------------------------------------------- props on a bone
reset()
scene = bpy.context.scene
arm = bpy.data.objects.new("Armature", bpy.data.armatures.new("Armature"))
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.data.edit_bones
root = eb.new("root")
root.head, root.tail = (0, 0, 0), (0, 0, 0.5)
hand = eb.new("hand_r")
hand.head, hand.tail, hand.parent = (0, 0, 0.5), (0, 0, 1.0), root
weapon = eb.new("weapon_r")
weapon.head, weapon.tail, weapon.parent, weapon.use_deform = (0.3, 0, 1.0), (0.3, 0.1, 1.0), hand, False
bpy.ops.object.mode_set(mode="OBJECT")

body = mesh_object("Body", box((0.3, 0.3, 1.0), (0, 0, 0.5)))
body.parent = arm
body.modifiers.new("Armature", "ARMATURE").object = arm  # skinned, but no vertex groups
holder = bpy.data.objects.new("Axe", None)
scene.collection.objects.link(holder)
head = mesh_object("AxeHead", cylinder(0.04, 0.1, segments=8))
blade = mesh_object("Blade", box((0.02, 0.2, 0.05), (0, 0, 0)))
for o in (holder, blade):
    o.parent, o.parent_type, o.parent_bone = arm, "BONE", "weapon_r"
head.parent = holder
bpy.context.view_layer.update()
holder.matrix_world = Matrix.Translation((0.3, 0.0, 1.0))
bpy.context.view_layer.update()
head.matrix_world = Matrix.Translation((0.3, 0.0, 1.1))
blade.matrix_world = Matrix.Translation((0.3, 0.1, 1.0))
save("rigid.blend")


# ---------------------------------------------------------------- a tusk off the face
def goblin(gap):
    H, R, r = Vector((0, 0, 1.2)), 0.15, 0.02

    def build(bm):
        box((0.6, 0.4, 1.06), (0, 0, 0.53))(bm)  # body; the head sinks 1 cm into its top
        head = bmesh.ops.create_icosphere(bm, subdivisions=4, radius=R, matrix=Matrix.Translation(H), calc_uvs=True)
        # the tusk goes beside the face, a little up, off the head vertex there
        want = Vector((-1, -1, 0.5)).normalized()
        u = max(((v.co - H).normalized() for v in head["verts"]), key=lambda d: d.dot(want))
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r, matrix=Matrix.Translation(H + Vector((0, -0.08, 0))),
                                   calc_uvs=True)  # an eye inside the head
        aim = Vector((0, 0, -1)).rotation_difference(-u).to_matrix().to_4x4()  # its pole faces the head
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r, matrix=Matrix.Translation(H + u * (R + gap + r)) @ aim,
                                   calc_uvs=True)
    return build


for name, gap in (("tusk_float.blend", 0.0075), ("tusk_touch.blend", 0.001)):
    reset()
    mesh_object("goblin", goblin(gap))
    save(name)

print("LINT CASES SAVED", out_dir)
