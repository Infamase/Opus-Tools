"""Mask mode, readability at true game pixel size, and the game-size blind read."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from opus import camera as c
from opus.blender.runner import BLENDER_MODULES, BlenderNotFound, find_blender, run_task
from opus.threed.understand import decode_parts, extent_px, min_width_px

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

needs_blender = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"
BG = (0.16, 0.16, 0.18)  # opus_bl.lookdev.BG


def srgb8(color):
    return tuple(round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)) for v in color[:3])


def blended(path, expected, tol=2) -> int:
    """Pixels that are none of the expected colors (part colors and background)."""
    rgb = np.asarray(Image.open(path).convert("RGB")).reshape(-1, 3).astype(int)
    near = np.zeros(len(rgb), bool)
    for e in expected:
        near |= np.abs(rgb - np.array(e)).max(axis=1) <= tol
    return int((~near).sum())


# ---------------------------------------------------------------- host measurements (no Blender)

def bar(h, w, rows=slice(None), cols=slice(None)):
    m = np.zeros((h, w), bool)
    m[rows, cols] = True
    return m


@pytest.mark.parametrize("width", [1, 2, 3, 4, 7, 12])
def test_min_width_of_bars(width):
    assert min_width_px(bar(40, 60, slice(10, 10 + width), slice(5, 50))) == width
    assert min_width_px(bar(60, 40, slice(5, 50), slice(10, 10 + width))) == width


def test_min_width_of_dots_diagonals_and_wide_parts():
    assert min_width_px(bar(5, 5, 2, 2)) == 1
    assert min_width_px(np.eye(30, dtype=bool)) == 1
    assert min_width_px(np.zeros((5, 5), bool)) == 0
    assert abs(min_width_px(bar(200, 200, slice(20, 80), slice(10, 190))) - 60) <= 1


def test_extent():
    assert extent_px(bar(40, 60, slice(10, 13), slice(5, 50))) == 45
    assert abs(extent_px(np.eye(30, dtype=bool)) - 42) <= 1  # the diagonal, 29·√2 + 1


def test_decode_counts_blended_pixels():
    rgba = np.zeros((4, 4, 4), np.uint8)
    rgba[0, :2] = (200, 10, 10, 255)
    rgba[1, :2] = (10, 10, 200, 255)
    rgba[2, 0] = (105, 10, 105, 255)  # an anti-aliased mix of the two
    labels, unmatched = decode_parts(rgba, [(201, 10, 10), (10, 10, 200)])
    assert unmatched == 1
    assert labels[0, 0] == 0 and labels[1, 1] == 1 and labels[2, 0] == -2 and labels[3, 3] == -1


# ---------------------------------------------------------------- Blender

@pytest.fixture(scope="module")
def work(tmp_path_factory):
    return tmp_path_factory.mktemp("readability")


@pytest.fixture(scope="module")
def boxes(work):
    out = work / "two_boxes.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "two_boxes.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    return out


@pytest.fixture(scope="module")
def human(work):
    out = work / "human.blend"
    run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 5000, "out_blend": str(out)})
    return out


@needs_blender
def test_mask_mode_has_no_blended_edge_pixels(boxes, work):
    out = work / "probe"
    out.mkdir()
    subprocess.run([BLENDER, "-b", str(boxes), "--python", str(SCRIPTS / "mask_probe.py"), "--", str(BLENDER_MODULES), str(out)],
                   check=True, capture_output=True, timeout=300)
    probe = json.loads((out / "mask_probe.json").read_text(encoding="utf-8"))
    counts = {k: blended(p, probe["expected"]) for k, p in probe["renders"].items()}
    assert counts["mask"] == 0
    assert counts["old_flat_aa8"] > 0  # anti-aliasing alone blends the part colors at edges
    assert counts["old_parts"] > counts["old_flat_aa8"]


@needs_blender
def test_part_map_pass_renders_in_mask_mode(boxes, work):
    res = run_task("views", {"path": str(boxes), "out_dir": str(work / "views"), "size": 240,
                             "shots": [{"view": "three_quarter", "pass": "parts"}, {"view": "front", "pass": "silhouette"}]})
    parts, sil = res["tiles"]
    assert {lb["name"] for lb in parts["labels"]} == {"BoxA", "BoxB"}
    assert blended(parts["path"], [srgb8(lb["color"]) for lb in parts["labels"]] + [srgb8(BG)]) == 0
    assert blended(sil["path"], [(0, 0, 0), (255, 255, 255)]) == 0


@needs_blender
def test_readability_heights_match_px_per_m_on_a_body(human, work):
    from opus.threed.understand import readability_check

    sheet, rep = readability_check(human, camera="ue_tp_1080", distances=[1.5, 3.5, 15, 40],
                                   defining=["head", "hand_l", "index_03_l", "tentacle"], out=work / "read.jpg")
    assert sheet.exists() and Path(rep["all_parts"]).exists()
    lv = {x["level"]: x for x in rep["levels"]}
    assert set(lv) == {"close", "typical", "far", "40 m"}
    assert lv["close"]["clipped"] and lv["close"]["height_px"] == 1080
    for name in ("typical", "far", "40 m"):
        x = lv[name]
        assert not x["clipped"] and x["unmatched_px"] == 0
        assert x["height_px"] == pytest.approx(1.8 * c.preset("ue_tp_1080").px_per_m(x["distance_m"]), rel=0.02)
        assert x["johnson"] == "identify"
    head = {d["part"]: d for d in lv["typical"]["defining"]}["head"]
    assert head["status"] == "ok" and 30 < head["min_width_px"] < 60
    # the fingertip falls under the 2 px floor at 15 m: 1 px wide since the 0.82 HU hand, gone with the old 0.75
    tip = {d["part"]: d for d in lv["far"]["defining"]}["index_03_l"]
    assert tip["status"] in ("thin", "vanished") and tip["min_width_px"] < 2
    assert any("defining part index_03_l" in w for w in rep["warnings"])
    assert any("tentacle" in w for w in rep["warnings"])
    assert any("40 m: defining part hand_l" in w for w in rep["warnings"])
    assert "SOFT" in rep["text"] and "soft" in rep


@needs_blender
def test_readability_orthographic_and_viewmodel_fallback(boxes, work):
    from opus.threed.understand import readability_check

    _, rep = readability_check(boxes, camera="sidescroller", out=work / "side.jpg")
    (lv,) = rep["levels"]
    assert lv["px_per_m"] == pytest.approx(90) and lv["height_px"] == pytest.approx(162, abs=1)
    _, rep = readability_check(boxes, camera="viewmodel", distances=[0.7], view="front", out=work / "vm.jpg")
    assert rep["camera"]["fallback"] is True
    assert any("viewmodel missing" in w for w in rep["warnings"])


@needs_blender
def test_readability_cli(boxes, capsys):
    from opus.cli import main

    assert main(["readability", str(boxes), "--camera", "unity_tp", "--defining", "BoxA", "--view", "30,10"]) == 0
    out = capsys.readouterr().out
    assert "Camera unity_tp" in out and "* BoxA:" in out and "View az 30°, el 10°" in out


@needs_blender
def test_blind_read_sheet_at_game_size(human, work):
    from opus.threed.understand import blind_read_sheet

    sheet, prompt = blind_read_sheet(human, game_size=True, camera="ue_tp_1080", distances=[3.5, 15, 40])
    assert sheet.exists() and "human" not in sheet.name
    assert Image.open(sheet).height > 900  # two game-size rows under the full-size views
    assert "game-distance" in prompt
