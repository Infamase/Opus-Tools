"""Hands holding things: grips on objects, the grip solver, and the grip check."""

import json
import subprocess
from pathlib import Path

import pytest

from opus.blender.runner import BLENDER_MODULES, BlenderNotFound, find_blender, run_task

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    d = tmp_path_factory.mktemp("grip")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_props.py"), "--", str(d)],
                   check=True, capture_output=True, timeout=300)
    run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 6000, "out_blend": str(d / "human.blend")})
    return d


@pytest.fixture(scope="module")
def club(work):
    from opus.threed.grip import grip_define

    sheet, rep = grip_define(work / "club.blend", "Club", part="Club")
    return sheet, rep


def test_hands_have_fingers_that_do_not_share_skin(work):
    out = work / "weights.json"
    subprocess.run([BLENDER, "-b", str(work / "human.blend"), "--python", str(SCRIPTS / "weight_probe.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    r = json.loads(out.read_text())
    assert r["finger_verts"] > 100
    assert r["shared"] == 0


def test_grip_define_fits_the_handle(club):
    sheet, rep = club
    assert sheet.exists()
    assert rep["grip"] == "SOCKET_grip_main"
    assert rep["radius"] == pytest.approx(0.016, abs=0.002)
    assert rep["axis"] == pytest.approx([0, 0, 1], abs=0.01)
    assert rep["palm_side"] == pytest.approx([0, 1, 0], abs=0.01)


def test_club_is_gripped_without_sinking_in(work, club):
    from opus.threed.grip import grip_hold

    sheet, rep = grip_hold(work / "human.blend", work / "club.blend", side="r", out_blend=work / "holding_club.blend")
    c = rep["contact"]
    assert sheet.exists() and Path(rep["file"]).exists()
    assert c["verdict"] == "good grip", rep["text"]
    assert not [r for r, v in c["regions"].items() if v["status"] == "inside"]
    assert {"index", "middle", "ring", "pinky"} <= set(c["fingers_touching"])
    assert rep["weapon_bone"] == "weapon_r" and rep["action"] == "Grip_Club_r"
    # the saved file passes the independent check too
    assert "good grip" in run_task("grip_check", {"path": rep["file"], "side": "r"})["text"]


def test_check_catches_handles_through_the_palm_and_floating(work, club):
    for mode, expect in (("inside", "sinks in"), ("floating", "floating")):
        out = work / f"naive_{mode}.blend"
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "place_naive.py"), "--",
                        str(BLENDER_MODULES), str(work / "human.blend"), str(work / "club.blend"), str(out), mode],
                       check=True, capture_output=True, timeout=300)
        rep = run_task("grip_check", {"path": str(out), "side": "r", "object": "Club"})
        c = rep["sides"]["r"]["contact"]
        assert c["verdict"] == expect, rep["text"]
        if mode == "inside":
            assert c["regions"]["palm"]["depth_mm"] > 5


def test_pistol_first_person_with_index_on_the_trigger(work):
    from opus.threed.grip import grip_define, grip_hold

    _, g = grip_define(work / "pistol.blend", "Pistol", part="Pistol", up=[0, 0, 1], point_axis="-Y", hand="r",
                       style="pistol", center=0.62, index="trigger", trigger=[0, -0.034, 0.09])
    assert g["palm_side"] == pytest.approx([-1, 0, 0], abs=0.02)  # a right palm presses the grip's right side
    sheet, rep = grip_hold(work / "human.blend", work / "pistol.blend", side="r", pose="fp_hip")
    assert rep["contact"]["verdict"] == "good grip", rep["text"]
    assert rep["fingers"]["index"]["status"].startswith("on trigger")
    assert float(rep["fingers"]["index"]["status"].split("(")[1].split(" ")[0]) < 3.0
    assert rep["aim_vs_hand_deg"] < 15
    assert rep["reach_error_m"] < 0.01
    assert sheet.exists()


def test_support_hand_reaches_a_rifle_handguard(work):
    from opus.threed.grip import grip_define, grip_hold

    rifle = work / "rifle.blend"
    grip_define(rifle, "Rifle", name="main", part="Rifle", up=[0, 0, 1], point_axis="-Y", hand="r", style="pistol",
                center=0.6, index="trigger", trigger=[0, 0.009, 0.065])
    grip_define(rifle, "Rifle", name="fore", part="Handguard", up=[0, -1, 0], palm_side=[0, 0, -1], hand="l")
    _, right = grip_hold(work / "human.blend", rifle, grip="main", side="r", pose="fp_hip", offset=[0.0, 0.1, 0.22],
                         out_blend=work / "rifle_r.blend")
    assert right["reach_error_m"] < 0.01
    _, left = grip_hold(work / "rifle_r.blend", grip="fore", side="l", move="hand", out_blend=work / "rifle_rl.blend")
    assert left["reach_error_m"] < 0.01
    assert not [r for r, v in left["contact"]["regions"].items() if v["status"] == "inside"]
    assert len(left["contact"]["fingers_touching"]) >= 3
