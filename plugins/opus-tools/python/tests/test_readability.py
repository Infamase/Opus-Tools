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


@pytest.fixture(scope="module")
def hostile(work):
    out = work / "hostile"
    out.mkdir()
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "hostile_scene.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    return out


@needs_blender
@pytest.mark.parametrize("variant", ["glare", "p3", "linked"])
def test_part_map_ignores_the_files_compositor_display_and_shared_meshes(hostile, work, variant):
    """A glare in the file's compositor or a P3 display shifts every ID color, and linked
    duplicates share one mesh's color attribute; any of them read every part as hidden."""
    from opus.threed.understand import readability_check

    _, rep = readability_check(hostile / f"{variant}.blend", camera="ue_tp_1080", distances=[3.5],
                               defining=["Body", "Wheel_L", "Wheel_R"], out=work / f"hostile_{variant}.jpg")
    (lv,) = rep["levels"]
    assert lv["unmatched_px"] == 0 and lv["parts_hidden"] == 0
    d = {x["part"]: x for x in lv["defining"]}
    assert {x["status"] for x in d.values()} == {"ok"}
    assert d["Wheel_L"]["area_px"] == pytest.approx(d["Wheel_R"]["area_px"], rel=0.1)
    assert d["Wheel_L"]["extent_px"] < d["Body"]["extent_px"]  # one wheel, not both
    assert not any("hidden" in w or "no part color" in w for w in rep["warnings"])
    if variant != "linked":  # the silhouette pass (also the game-size blind read) stays pure black and white
        res = run_task("views", {"path": str(hostile / f"{variant}.blend"), "out_dir": str(work / f"hv_{variant}"),
                                 "size": 200, "shots": [{"view": "front", "pass": "silhouette"}]})
        assert blended(res["tiles"][0]["path"], [(0, 0, 0), (255, 255, 255)]) == 0


def test_a_part_map_that_does_not_decode_warns(tmp_path, monkeypatch):
    """Pixels that match no ID color would otherwise read as every part hidden, silently."""
    from opus.threed import understand

    parts = np.zeros((20, 20, 4), np.uint8)
    parts[5:15, 5:15] = (230, 120, 40, 255)  # a shifted ID color, as a compositor grade makes
    Image.fromarray(parts, "RGBA").save(tmp_path / "parts.png")
    Image.fromarray(np.full((20, 20, 3), 90, np.uint8)).save(tmp_path / "shaded.png")
    fake = {"mode": "objects", "parts": [{"name": "Box", "object": "Box", "color8": [255, 158, 0]}], "size_m": [1, 1, 1.8],
            "renders": [{"shot": "game", "azimuth": 0.0, "elevation": 0.0, "level": "typical", "distance_m": 3.5,
                         "crop": [0, 0, 20, 20], "clipped": False, "projected_height_px": 10.0,
                         "parts_projected": {"Box": [10.0, 100.0]},
                         "files": {"parts": str(tmp_path / "parts.png"), "shaded": str(tmp_path / "shaded.png")}}]}
    monkeypatch.setattr(understand, "run_task", lambda *a, **k: fake)
    _, rep = understand.readability_check(tmp_path / "box.blend", camera="ue_tp_1080", distances=[3.5],
                                          defining=["Box"], out=tmp_path / "read.jpg")
    assert rep["levels"][0]["unmatched_px"] == 100
    assert any("100 subject pixels match no part color" in w for w in rep["warnings"])


ID_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255)]


def fake_readability(tmp_path, rects: dict, size_m=(1, 1, 1.8), levels=(("typical", 3.5),), azimuth=0.0, elevation=0.0):
    """A readability task result whose part map has one rectangle (y0, y1, x0, x1) per part."""
    parts = np.zeros((60, 60, 4), np.uint8)
    for (y0, y1, x0, x1), col in zip(rects.values(), ID_COLORS):
        parts[y0:y1, x0:x1] = (*col, 255)
    Image.fromarray(parts, "RGBA").save(tmp_path / "parts.png")
    Image.fromarray(np.full((60, 60, 3), 90, np.uint8)).save(tmp_path / "shaded.png")
    proj = {n: [float(max(y1 - y0, x1 - x0)), float((y1 - y0) * (x1 - x0))] for n, (y0, y1, x0, x1) in rects.items()}
    return {"mode": "objects", "parts": [{"name": n, "object": n, "color8": list(col)} for n, col in zip(rects, ID_COLORS)],
            "size_m": list(size_m),
            "renders": [{"shot": "game", "azimuth": azimuth, "elevation": elevation, "level": name, "distance_m": d,
                         "crop": [0, 0, 60, 60], "clipped": False, "projected_height_px": 50.0, "parts_projected": proj,
                         "files": {"parts": str(tmp_path / "parts.png"), "shaded": str(tmp_path / "shaded.png")}}
                        for name, d in levels]}


def test_defining_names_match_any_case_and_unmatched_ones_count(tmp_path, monkeypatch):
    """'boss' measures Boss; 'band' matches nothing and is reported per level, never dropped."""
    from opus.threed import understand

    fake = fake_readability(tmp_path, {"Board": (5, 55, 5, 55), "Rim": (2, 5, 5, 55), "Boss": (25, 35, 25, 35)},
                            levels=(("typical", 6.0), ("far", 20.0)))
    monkeypatch.setattr(understand, "run_task", lambda *a, **k: fake)
    _, rep = understand.readability_check(tmp_path / "round_shield.blend", camera="godot_tp", distances=[6, 20],
                                          defining=["boss", "rim", "band"], out=tmp_path / "read.jpg")
    assert rep["defining_not_found"] == ["band"]
    for lv in rep["levels"]:
        d = {x["part"]: x for x in lv["defining"]}
        assert set(d) == {"boss", "rim", "band"}
        assert d["boss"]["status"] == "ok" and d["boss"]["area_px"] == 100 and d["boss"]["matched"] == ["Boss"]
        assert d["rim"]["status"] == "ok" and d["rim"]["min_width_px"] == 3
        assert d["band"]["status"] == "not_found" and d["band"]["area_px"] == 0
        assert sum(x["status"] != "ok" for x in lv["defining"]) == 1  # what defining_under_floor counts
    assert any("defining parts not found: ['band']" in w for w in rep["warnings"])
    assert "* band: not found" in rep["text"]
    full = json.loads(Path(rep["all_parts"]).read_text(encoding="utf-8"))
    assert full["defining_not_found"] == ["band"]
    assert {x["part"] for x in full["levels"][0]["parts"] if x["defining"]} == {"Rim", "Boss"}


def test_a_defining_prefix_measures_its_parts_as_one_group(tmp_path, monkeypatch):
    from opus.threed import understand

    fake = fake_readability(tmp_path, {"Staves": (10, 50, 10, 50), "hoop_top": (12, 14, 10, 50),
                                       "hoop_mid": (29, 31, 10, 50), "hoop_bottom": (46, 48, 10, 50)})
    monkeypatch.setattr(understand, "run_task", lambda *a, **k: fake)
    _, rep = understand.readability_check(tmp_path / "barrel.blend", camera="godot_tp", distances=[6],
                                          defining=["hoop", "STAVES", "hoop_m*"], out=tmp_path / "read.jpg")
    assert "defining_not_found" not in rep or not rep["defining_not_found"]
    d = {x["part"]: x for x in rep["levels"][0]["defining"]}
    assert d["hoop"]["matched"] == ["hoop_top", "hoop_mid", "hoop_bottom"]
    assert d["hoop"]["area_px"] == 3 * 2 * 40 and d["hoop"]["min_width_px"] == 2
    assert d["STAVES"]["matched"] == ["Staves"]
    assert d["hoop_m*"]["matched"] == ["hoop_mid"]
    assert not any("not found" in w for w in rep["warnings"])


def test_a_camera_inside_the_subject_is_flagged(tmp_path, monkeypatch):
    """A 16 x 8 x 8 m house seen from 3.5 m: the camera stands inside it."""
    from opus.threed import understand

    fake = fake_readability(tmp_path, {"House": (5, 55, 5, 55)}, size_m=(16, 8, 8),
                            levels=(("close", 1.5), ("typical", 3.5), ("far", 15.0)))
    monkeypatch.setattr(understand, "run_task", lambda *a, **k: fake)
    _, rep = understand.readability_check(tmp_path / "house.blend", camera="ue_tp_1080", out=tmp_path / "read.jpg")
    inside = {lv["level"]: lv["camera_inside"] for lv in rep["levels"]}
    assert inside == {"close": True, "typical": True, "far": False}
    assert "camera inside the subject at 3.5 m: sizes describe its inside" in rep["warnings"]
    assert not any("at 15 m" in w for w in rep["warnings"])
    assert understand.camera_inside([16, 8, 8], 90.0, 0.0, 3.5)  # from the side, 3.5 m is still within 8 m
    assert not understand.camera_inside([16, 8, 8], 90.0, 0.0, 8.5)
    assert not understand.camera_inside([16, 8, 8], 0.0, 0.0, None)  # an orthographic camera


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


@needs_blender
def test_blind_read_at_game_size_says_when_the_viewmodel_is_a_fallback(boxes):
    from opus.threed.understand import blind_read_sheet

    _, prompt = blind_read_sheet(boxes, game_size=True, camera="viewmodel", distances=[0.45])
    assert "FALLBACK view-model" in prompt and "viewmodel missing" in prompt
    _, prompt = blind_read_sheet(boxes, game_size=True, camera="unity_tp", distances=[4])
    assert "FALLBACK" not in prompt and "Note:" not in prompt
