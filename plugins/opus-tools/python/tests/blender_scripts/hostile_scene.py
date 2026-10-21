"""A cart body and two wheels that share one mesh (linked duplicates), saved three ways: as
is, with a compositor glare that brightens every color, and for a Display P3 monitor.
The part map must ignore all three.

    blender -b --factory-startup --python hostile_scene.py -- out_dir
"""

import os
import sys

import bmesh
import bpy
from mathutils import Matrix

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def cube(name, size):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((*size, 1.0)))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


body = bpy.data.objects.new("Body", cube("Body", (0.6, 0.4, 0.5)))
body.location = (0, 0, 0.55)
scene.collection.objects.link(body)
wheel = bpy.data.objects.new("Wheel_L", cube("Wheel", (0.3, 0.3, 0.3)))
wheel.location = (0.6, 0, 0.15)
scene.collection.objects.link(wheel)
twin = wheel.copy()  # Alt+D: a new object on the same mesh
twin.name = "Wheel_R"
twin.location = (-0.6, 0, 0.15)
scene.collection.objects.link(twin)
assert twin.data == wheel.data
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "linked.blend"))

if hasattr(scene, "compositing_node_group"):  # Blender 5.0+
    tree = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    sink = tree.nodes.new("NodeGroupOutput")
    scene.compositing_node_group = tree
else:
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    sink = tree.nodes.new("CompositorNodeComposite")
layers = tree.nodes.new("CompositorNodeRLayers")
glare = tree.nodes.new("CompositorNodeGlare")
if "Threshold" in glare.inputs:
    glare.inputs["Threshold"].default_value = 0.3
else:
    glare.threshold = 0.3
tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs[0], sink.inputs[0])
scene.render.use_compositing = True
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "glare.blend"))

scene.render.use_compositing = False
scene.display_settings.display_device = "Display P3"
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "p3.blend"))
