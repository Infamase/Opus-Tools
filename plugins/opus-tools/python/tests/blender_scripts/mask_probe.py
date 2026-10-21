"""Render the scene's part map with the pre-S0a settings and in mask mode, to count blended pixels.

    blender -b file.blend --python mask_probe.py -- blender_modules_dir out_dir
"""

import json
import os
import sys

modules, out = sys.argv[sys.argv.index("--") + 1 :][:2]
sys.path.insert(0, modules)

import bpy  # noqa: E402

from opus_bl import inspect3d, lookdev  # noqa: E402

objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
mode, parts = inspect3d.parts_of(objs)
colors, ctype = inspect3d._paint_parts(mode, parts)
lookdev._render_settings(200)
cam = lookdev._camera()
inspect3d.aim(cam, 30, 20, inspect3d._all_points(objs))
setups = {
    # the old silhouette pass (FLAT, anti-aliased) and the old part-map pass (STUDIO, cavity, outline)
    "old_flat_aa8": lambda: lookdev._workbench(light="FLAT", color_type=ctype, cavity=False, outline=False),
    "old_parts": lambda: lookdev._workbench(light="STUDIO", color_type=ctype, cavity=True, outline=True),
    "mask": lambda: lookdev.mask_mode(color_type=ctype),
}
renders = {}
for name, setup in setups.items():
    setup()
    renders[name] = bpy.context.scene.render.filepath = os.path.join(out, f"{name}.png")
    bpy.ops.render.render(write_still=True)
expected = [lookdev.srgb8(c) for c in colors.values()] + [lookdev.srgb8(lookdev.BG)]
with open(os.path.join(out, "mask_probe.json"), "w", encoding="utf-8") as f:
    json.dump({"expected": expected, "renders": renders}, f)
