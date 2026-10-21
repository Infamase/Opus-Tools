"""Two bays of a modular roof that abut at x = 4 m, rebuilt from the house eval's kit: a
shingled slab plus a beam, two rafters and fourteen posts, 18 pieces per bay, one mesh shared
by both objects (turned 180 degrees about Z, as the kit placed them). model_report read the
pair as cutting 76 mm into each other.

    blender -b --factory-startup --python roof_pair.py -- out.blend
"""

import math
import sys

import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]

# the slab's profile (y, z) at x = 0, run 4 m along x: a sawtooth of six shingle rows on top
SLAB = [(-0.6, 0.0), (4.0, 3.7), (4.0, 4.0), (3.2333333, 3.4533334), (3.2333333, 3.3833334),
        (2.4666667, 2.8366666), (2.4666667, 2.7666667), (1.7, 2.22), (1.7, 2.1500001), (0.9333333, 1.6033334),
        (0.9333333, 1.5333333), (0.1666667, 0.9866667), (0.1666667, 0.9166667), (-0.6, 0.37)]
# the slab's end caps as the kit triangulated them (indices into SLAB)
CAP = [(3, 2, 1), (3, 1, 4), (4, 1, 0), (5, 4, 6), (6, 4, 0), (7, 6, 8), (8, 6, 0), (9, 8, 10), (10, 8, 0),
       (11, 10, 12), (12, 10, 0), (13, 12, 0)]


def post_top(y):  # the underside of the slab
    return 0.4826087 + 0.8043478 * y


verts, faces = [], []


def prism(ring, d, cap=None):
    """Vertices ``ring`` and ``ring`` moved by ``d``, joined by quads, faces turned outward."""
    n, base = len(ring), len(verts)
    verts.extend([Vector(p) for p in ring] + [Vector(p) + Vector(d) for p in ring])
    a = list(range(base, base + n))
    b = [i + n for i in a]
    caps = cap or [range(n - 1, -1, -1)]  # ring indices of the faces closing the x = 0 end
    fs = [[a[i] for i in t] for t in caps] + [[b[i] for i in reversed(t)] for t in caps]
    fs += [[a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]] for i in range(n)]
    c = sum(verts[base:], Vector()) / (2 * n)
    vol = sum((verts[f[0]] - c).dot((verts[f[k]] - c).cross(verts[f[k + 1]] - c)) for f in fs for k in range(1, len(f) - 1))
    faces.extend([f[::-1] for f in fs] if vol < 0 else fs)


prism([(0.0, y, z) for y, z in SLAB], (4.0, 0, 0), CAP)
prism([(0, 0, 0), (4, 0, 0), (4, 0, 0.7036957), (0, 0, 0.7036957)], (0, 0.25, 0))  # eave beam
for x in (0.05, 3.75):  # rafters
    prism([(x, 0, 0), (x, 4, 0), (x, 4, 3.8), (x, 0, post_top(0) + 0.1)], (0.2, 0, 0))
for x in (0.0, 3.95):  # posts, the ones at 3.95 flush with the bay's end
    for y in (0.3, 0.9, 1.5, 2.1, 2.7, 3.3):
        prism([(x, y, 0), (x, y + 0.1, 0), (x, y + 0.1, post_top(y)), (x, y, post_top(y))], (0.05, 0, 0))
    prism([(x, 0, 0), (x, 0.1, 0), (x, 0.1, post_top(0.1)), (x, 0, post_top(0))], (0.05, 0, 0))

bpy.ops.wm.read_factory_settings(use_empty=True)
me = bpy.data.meshes.new("SM_Roof")
me.from_pydata([tuple(v) for v in verts], [], faces)
me.update()
for i, x in enumerate((4.0, 8.0)):
    o = bpy.data.objects.new(f"roof_back_{i + 1:02d}", me)
    bpy.context.scene.collection.objects.link(o)
    o.location = (x, 8.0, 4.0)
    o.rotation_euler = (0, 0, math.pi)
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAVED", out, len(verts), "verts", len(faces), "faces")
