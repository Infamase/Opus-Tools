"""Look, model report, proportion check and reference match against real Blender renders."""

import os
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from opus.blender.runner import BlenderNotFound, find_blender, run_task

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    return tmp_path_factory.mktemp("understand")


@pytest.fixture(scope="module")
def human(work):
    out = work / "human.blend"
    rep = run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 5000, "out_blend": str(out)})
    return out, rep


@pytest.fixture(scope="module")
def barrel(work):
    out = work / "barrel.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_barrel.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    return out


def test_model_report_of_a_prop(barrel, work):
    from opus.threed.understand import model_report

    sheet, rep = model_report(barrel, out=work / "barrel_report.jpg", size=300)
    assert sheet.exists()
    assert rep["mode"] == "objects" and {p["name"] for p in rep["parts"]} == {"Barrel", "Band0", "Band1"}
    shapes = {p["name"]: p["shape"] for p in rep["parts"]}
    assert shapes["Band0"] == "plate / slab"
    assert any({c["a"], c["b"]} == {"Barrel", "Band0"} for c in rep["contacts"])
    assert rep["gaps"] == []
    assert rep["symmetry"]["symmetric"] and rep["on_floor"]
    assert "Parts (3, one per object)" in rep["text"]


def test_model_report_splits_a_skinned_body_by_bone(human, work):
    from opus.threed.understand import model_report

    sheet, rep = model_report(human[0], out=work / "human_report.jpg", size=300)
    names = {p["name"] for p in rep["parts"]}
    assert rep["mode"] == "bones" and {"head", "upperarm_l", "thigh_r"} <= names
    thigh = next(p for p in rep["parts"] if p["name"] == "thigh_l")
    assert thigh["main_axis"] == "vertical (Z)" and thigh["bone_length_m"] > 0.3
    assert rep["rig"]["style"].startswith("unreal")
    assert rep["balance"]["com_over_footprint"] is True


def test_look_at_frames_a_bone_region_from_any_angle(human, work):
    from opus.threed.understand import look_at

    sheet, rep = look_at(human[0], views=["front", "30,20", "three_quarter_back"], pass_="focus",
                         target="hand_l", zoom=1.5, size=240, out=work / "look.jpg")
    assert sheet.exists() and rep["target"] == "hand_l"
    with pytest.raises(Exception, match="no part named"):
        look_at(human[0], target="tentacle_l", size=120, out=work / "x.jpg")


def test_proportion_check_flags_short_legs_and_big_head(human, work):
    from opus.threed.proportion import proportion_check

    out, rep = human
    _, good = proportion_check(out, preset="realistic", out=work / "good.png")
    assert good["iou"]["front"] > 0.95
    assert not [f for f in good["findings"] if not f["metric"].startswith("band")]
    bad = work / "bad.blend"
    lm = rep["landmarks_m"]
    subprocess.run([BLENDER, "-b", str(out), "--python", str(SCRIPTS / "distort_body.py"), "--", str(bad),
                    str(lm["crotch"]), str(lm["chin"])], check=True, capture_output=True, timeout=300)
    sheet, rep = proportion_check(bad, preset="realistic", out=work / "bad.png")
    assert sheet.exists()
    metrics = {f["metric"]: f["relative_pct"] for f in rep["findings"]}
    assert metrics["crotch_height"] < -10  # legs shorter
    assert metrics["head_width"] > 20
    assert rep["heads_tall_estimate"] < 6.5


def test_proportion_check_picks_the_closest_canon(work):
    from opus.threed.proportion import proportion_check

    chibi = work / "chibi.blend"
    run_task("body", {"archetype": "humanoid", "preset": "chibi", "target_tris": 4000, "out_blend": str(chibi)})
    _, rep = proportion_check(chibi, out=work / "chibi.png")
    assert rep["canon"] == "chibi"
    assert rep["heads_tall_estimate"] == pytest.approx(3.0, abs=0.3)


def test_reference_match_finds_a_mirrored_side_view(work):
    from opus.threed.proportion import reference_match

    dog = work / "dog.blend"
    run_task("body", {"archetype": "quadruped", "preset": "dog", "target_tris": 4000, "out_blend": str(dog)})
    shot = run_task("views", {"path": str(dog), "out_dir": str(work / "ref"), "size": 400,
                              "shots": [{"view": "right", "pass": "clay", "ortho": True}]})
    concept = work / "dog_concept.png"
    Image.open(shot["tiles"][0]["path"]).transpose(Image.FLIP_LEFT_RIGHT).save(concept)
    sheet, rep = reference_match(dog, concept, view="right", out=work / "match.png")
    assert sheet.exists()
    assert rep["flipped"] is True and rep["iou"] > 0.9
