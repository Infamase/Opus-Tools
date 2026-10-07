"""Build a small test barrel (bulged cylinder + two iron bands) and save it.

Run: blender -b --factory-startup --python make_barrel.py -- out.blend [--defects]
--defects adds a flipped face, a loose vertex and a floating part for Mesh Lint tests.
"""
import math
import sys

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
out, defects = argv[0], "--defects" in argv

bpy.ops.wm.read_factory_settings(use_empty=True)


def lathe(name, profile, segments=16, color=(0.5, 0.3, 0.15, 1)):
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = [bm.verts.new((r * math.cos(2 * math.pi * i / segments), r * math.sin(2 * math.pi * i / segments), z))
                for i in range(segments)]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    mat = bpy.data.materials.new(name + "_mat")
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
    me.materials.append(mat)
    return obj


body = lathe("Barrel", [(0.26, 0.0), (0.30, 0.15), (0.32, 0.45), (0.30, 0.75), (0.26, 0.9)], color=(0.45, 0.27, 0.12, 1))
for i, z in enumerate((0.16, 0.74)):
    lathe(f"Band{i}", [(0.305, z - 0.03), (0.31, z), (0.305, z + 0.03)], color=(0.2, 0.2, 0.22, 1))

if defects:
    me = body.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.faces[3].normal_flip()            # one flipped face
    bm.verts.new((0.0, 0.0, 1.4))        # loose vertex
    bm.to_mesh(me)
    bm.free()
    lid = lathe("FloatingLid", [(0.2, 1.1), (0.2, 1.14)], color=(0.4, 0.25, 0.1, 1))  # floats above
    body.scale = (1.0, 1.0, 1.2)         # unapplied scale

bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAVED", out)
