"""Body blockouts: proportions follow the canon, the rig binds, and posing moves the right side."""

import json
import subprocess
from pathlib import Path

import pytest

from opus.blender.runner import BlenderNotFound, find_blender, run_task
from opus.tables import load_table

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"
UE_HUMANOID = {
    "root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "clavicle_l", "upperarm_l",
    "lowerarm_l", "hand_l", "thigh_l", "calf_l", "foot_l", "ball_l", "upperarm_r", "thigh_r",
}


def build(tmp_path, **kw):
    out = tmp_path / f"{kw['archetype']}_{kw['preset']}.blend"
    rep = run_task("body", {"target_tris": 4000, "out_blend": str(out), **kw})
    return out, rep


def probe(tmp_path, blend):
    """Bone lengths and skin measurements of a built blockout (body_probe.py)."""
    out = tmp_path / "probe.json"
    subprocess.run([BLENDER, "-b", str(blend), "--python", str(SCRIPTS / "body_probe.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    return json.loads(out.read_text())


@pytest.mark.parametrize(
    "archetype,preset",
    [("humanoid", "realistic"), ("humanoid", "heroic"), ("humanoid", "stylized"), ("humanoid", "chibi"),
     ("quadruped", "dog"), ("quadruped", "horse"), ("quadruped", "cat"), ("dragon", "western")],
)
def test_every_preset_builds_and_binds(tmp_path, archetype, preset):
    out, rep = build(tmp_path, archetype=archetype, preset=preset)
    assert out.exists()
    assert rep["binding"] == "automatic"
    assert 2000 < rep["tris"] < 4800
    assert {"root", "pelvis", "spine_01", "head", "thigh_l", "thigh_r"} <= set(rep["bones"])


def test_humanoid_landmarks_follow_the_canon(tmp_path):
    _, rep = build(tmp_path, archetype="humanoid", preset="realistic", height=1.8)
    assert UE_HUMANOID <= set(rep["bones"])
    assert rep["height_m"] == 1.8 and rep["heads_tall"] == 7.5
    lm = rep["landmarks_m"]
    hu = 1.8 / 7.5
    assert lm["head_height"] == pytest.approx(hu, rel=0.02)
    assert lm["crotch"] == pytest.approx(3.65 * hu, rel=0.02)
    assert lm["knee"] == pytest.approx(2.05 * hu, rel=0.02)
    assert rep["joints_m"]["knee_l"][2] == pytest.approx(lm["knee"], abs=0.01)
    # left is +X; the rig is symmetric
    assert rep["joints_m"]["knuckles_l"][0] == pytest.approx(-rep["joints_m"]["knuckles_r"][0], abs=1e-3)
    assert rep["joints_m"]["knuckles_l"][0] > 0.4
    fingers = {f"{f}_0{i}_{s}" for f in ("thumb", "index", "middle", "ring", "pinky") for i in (1, 2, 3) for s in "lr"}
    assert fingers <= set(rep["bones"])


def test_posing_a_bone_moves_only_that_side(tmp_path):
    out, _ = build(tmp_path, archetype="humanoid", preset="stylized")
    probe = tmp_path / "probe.json"
    subprocess.run(
        [BLENDER, "-b", str(out), "--python", str(SCRIPTS / "pose_probe.py"), "--", "upperarm_l", str(probe)],
        check=True, capture_output=True, timeout=300,
    )
    r = json.loads(probe.read_text())
    assert r["max_move"] > 0.1
    assert r["moved_left"] > 100
    assert r["moved_right"] < r["moved_left"] * 0.05


def test_dragon_wings_fold_with_the_finger_bones(tmp_path):
    out, rep = build(tmp_path, archetype="dragon", preset="western")
    assert {"wing_upperarm_l", "wing_forearm_r", "wing_finger_01_l", "wing_finger_04_r"} <= set(rep["bones"])
    probe = tmp_path / "probe.json"
    subprocess.run(
        [BLENDER, "-b", str(out), "--python", str(SCRIPTS / "pose_probe.py"), "--", "wing_forearm_l", str(probe)],
        check=True, capture_output=True, timeout=300,
    )
    r = json.loads(probe.read_text())
    assert r["max_move"] > 0.3  # membrane and spars follow the wing
    assert r["moved_right"] < r["moved_left"] * 0.05


def test_unknown_preset_is_a_clear_error(tmp_path):
    from opus.blender.runner import BlenderTaskError

    with pytest.raises(BlenderTaskError, match="humanoid presets"):
        build(tmp_path, archetype="humanoid", preset="gnome")


def test_realistic_hand_and_foot_measure_inside_ansur(tmp_path):
    out, rep = build(tmp_path, archetype="humanoid", preset="realistic", height=1.8)
    r = probe(tmp_path, out)
    male = load_table("anthro_ansur2")["sexes"]["male"]["measures"]
    for name in ("foot_length", "hand_length"):
        band = male[name]
        assert band["min"] < r[name] / r["height"] < band["max"], (name, r[name] / r["height"], band)
    # the canon's landmark says what was built
    assert rep["landmarks_m"]["foot"] == pytest.approx(r["foot_length"], rel=0.03)


@pytest.mark.parametrize("preset,donor,mt_f,digits", [
    ("dog", "wolf", 0.437, {"ball_l"}),
    ("cat", "felid", 0.35, {"ball_l"}),
    ("horse", "horse", 0.806, {"pastern_l", "hoof_l", "fpastern_l", "fhoof_l"}),
])
def test_hind_legs_follow_garland_and_janis(tmp_path, preset, donor, mt_f, digits):
    out, rep = build(tmp_path, archetype="quadruped", preset=preset)
    L = probe(tmp_path, out)["lengths"]
    assert L["foot_l"] / L["thigh_l"] == pytest.approx(mt_f, rel=0.1)  # metatarsal / femur
    assert L["calf_l"] / L["thigh_l"] == pytest.approx(1.0, rel=0.1)  # tibia ~ femur
    assert digits | {d[:-1] + "r" for d in digits} <= set(L)  # phalanges are their own bones
    assert rep["hindlimb"]["donor"] == donor and rep["hindlimb"]["mt_f"] == pytest.approx(mt_f, rel=0.1)


def test_horse_fetlock_and_pastern_bend_the_skin(tmp_path):
    out, rep = build(tmp_path, archetype="quadruped", preset="horse")
    assert rep["binding"] == "automatic"
    assert {"fetlock_l", "coronet_l", "ffetlock_r", "fcoronet_r"} <= set(rep["joints_m"])
    assert {"pastern_l", "hoof_l", "fpastern_l", "fhoof_r"} <= set(probe(tmp_path, out)["weighted_bones"])
    moved = tmp_path / "pose.json"
    subprocess.run([BLENDER, "-b", str(out), "--python", str(SCRIPTS / "pose_probe.py"), "--", "pastern_l", str(moved)],
                   check=True, capture_output=True, timeout=300)
    r = json.loads(moved.read_text())
    assert r["moved_left"] > 20 and r["max_move"] > 0.03
    assert r["moved_right"] == 0
