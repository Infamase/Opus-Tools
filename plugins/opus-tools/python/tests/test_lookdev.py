"""Look-dev and look_at render passes: EEVEE's studio light, vertex colours in shaded passes,
and a normals pass that tells faces apart."""

import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from opus.blender.runner import BLENDER_MODULES, BlenderNotFound, BlenderTaskError, find_blender, run_task

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")

# a unit cube whose material takes Base Color from a red color attribute (as glTF imports and
# vertex-painted low-poly assets do), and no image texture
VCOL_CUBE = """
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
o = bpy.context.object
o.name = "crate"
attr = o.data.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
for d in attr.data:
    d.color = (1.0, 0.0, 0.0, 1.0)
mat = bpy.data.materials.new("vcol")
mat.use_nodes = True
nt = mat.node_tree
ca = nt.nodes.new("ShaderNodeVertexColor")
ca.layer_name = "Col"
nt.links.new(ca.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
o.data.materials.append(mat)
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
"""


@pytest.fixture(scope="module")
def crate(tmp_path_factory):
    out = tmp_path_factory.mktemp("lookdev") / "crate.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", VCOL_CUBE, "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    return out


def center(path) -> np.ndarray:
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    h, w = a.shape[:2]
    return a[h // 2 - 2 : h // 2 + 3, w // 2 - 2 : w // 2 + 3].reshape(-1, 3).mean(axis=0)


def is_red(rgb) -> bool:
    r, g, b = rgb
    return r > 100 and r > 2.5 * g and r > 2.5 * b


def test_lookdev_with_eevee_writes_a_sheet(crate, tmp_path):
    from opus.threed.lookdev import lookdev_sheet

    try:
        sheet, rep = lookdev_sheet(crate, engine="eevee", tile=96, out=tmp_path / "sheet.jpg")
    except BlenderTaskError as e:
        if "Cannot read" in str(e) or "studio" in str(e):
            raise  # the studio light lookup, not the GPU
        pytest.skip(f"EEVEE can't initialise headless here: {str(e)[-300:]}")
    assert sheet.exists() and rep["engine"] == "eevee"
    tile = Path(rep["tiles_dir"]) / "shaded_front.png"
    assert tile.exists() and is_red(center(tile))


def test_the_studio_light_resolves_and_a_missing_one_falls_back_to_the_flat_world():
    code = ("import os, sys; sys.path.insert(0, sys.argv[-1]); from opus_bl import lookdev; "
            "p = lookdev._studio_light('studio.exr'); print('FOUND', os.path.isfile(p), os.path.basename(p)); "
            "print('WARN', lookdev._world(lookdev.BG, hdri='missing.exr'))")
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", code, "--", str(BLENDER_MODULES)],
                         capture_output=True, text=True, timeout=300, check=True).stdout
    assert "FOUND True studio.exr" in out
    assert "WARN studio light missing.exr not found" in out


def test_shaded_passes_show_vertex_colours(crate, tmp_path):
    res = run_task("lookdev", {"path": str(crate), "out_dir": str(tmp_path / "ld"), "size": 96, "plan": [["shaded", ["front"]]]})
    assert is_red(center(res["tiles"][0]["path"]))
    res = run_task("views", {"path": str(crate), "out_dir": str(tmp_path / "v"), "size": 96, "shots": [{"view": "front", "pass": "shaded"}]})
    assert is_red(center(res["tiles"][0]["path"]))
    # after the part map, which makes its own color attribute the active one
    cam = {"projection": "persp", "vfov_deg": 60.0, "res_w": 320, "res_h": 240, "near_m": 0.1, "scale": 1.0}
    res = run_task("readability", {"path": str(crate), "out_dir": str(tmp_path / "r"), "camera": cam, "levels": [["near", 2.5]],
                                   "shots": [{"key": "front", "view": "front", "passes": ["parts", "shaded"]}]})
    assert is_red(center(res["renders"][0]["files"]["shaded"]))


def test_normals_pass_tells_the_faces_of_a_cube_apart(crate, tmp_path):
    res = run_task("views", {"path": str(crate), "out_dir": str(tmp_path / "n"), "size": 160,
                             "shots": [{"view": "three_quarter", "pass": "normals"}]})
    rgb = np.asarray(Image.open(res["tiles"][0]["path"]).convert("RGB")).reshape(-1, 3)
    colors, n = np.unique(rgb // 8, axis=0, return_counts=True)  # 8-level bins absorb sampling noise
    big = colors[n > 0.03 * len(rgb)]
    bg = rgb[0] // 8
    faces = [c for c in big if np.abs(c.astype(int) - bg).max() > 1]
    assert len(faces) >= 3
