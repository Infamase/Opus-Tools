"""Test props for grip tests: a club (round handle) and a pistol (angled grip, trigger).

    blender -b --factory-startup --python make_props.py -- out_dir
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)


def mesh_object(name, build, parent=None):
    bm = bmesh.new()
    build(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def cylinder(r, z0, z1, segments=24):
    return lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r, depth=z1 - z0,
                                            matrix=Matrix.Translation((0, 0, (z0 + z1) / 2)))


def box(size, center, rot_x=0.0):
    m = Matrix.Translation(center) @ Matrix.Rotation(math.radians(rot_x), 4, "X") @ Matrix.Diagonal((*size, 1.0))
    return lambda bm: bmesh.ops.create_cube(bm, size=1.0, matrix=m)


bpy.ops.wm.read_factory_settings(use_empty=True)
club = mesh_object("Club", cylinder(0.016, 0.0, 0.17))
mesh_object("ClubHead", cylinder(0.04, 0.17, 0.32), parent=club)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "club.blend"))

bpy.ops.wm.read_factory_settings(use_empty=True)
pistol = mesh_object("Pistol", box((0.03, 0.048, 0.11), (0, 0.02, 0.055), rot_x=15.0))  # grip, slanted back
mesh_object("Slide", box((0.03, 0.2, 0.036), (0, -0.055, 0.128)), parent=pistol)
mesh_object("Trigger", box((0.008, 0.006, 0.022), (0, -0.03, 0.09)), parent=pistol)
mesh_object("Guard", box((0.01, 0.055, 0.006), (0, -0.03, 0.068)), parent=pistol)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "pistol.blend"))

bpy.ops.wm.read_factory_settings(use_empty=True)
rifle = mesh_object("Rifle", box((0.035, 0.05, 0.11), (0, 0.06, 0.03), rot_x=15.0))  # pistol grip
mesh_object("Receiver", box((0.05, 0.42, 0.07), (0, -0.04, 0.115)), parent=rifle)
mesh_object("Stock", box((0.04, 0.3, 0.1), (0, 0.32, 0.1)), parent=rifle)
mesh_object("Barrel", lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.012, radius2=0.012, depth=0.3,
                                                       matrix=Matrix.Translation((0, -0.4, 0.125)) @ Matrix.Rotation(math.radians(90), 4, "X")), parent=rifle)
mesh_object("Handguard", lambda bm: bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.022, radius2=0.022, depth=0.2,
                                                          matrix=Matrix.Translation((0, -0.33, 0.1)) @ Matrix.Rotation(math.radians(90), 4, "X")), parent=rifle)
mesh_object("Trigger", box((0.008, 0.006, 0.022), (0, 0.012, 0.065)), parent=rifle)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "rifle.blend"))
