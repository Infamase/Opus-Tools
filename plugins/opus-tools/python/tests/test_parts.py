"""Parts on skinned assets: floating islands and skinned objects in the structure report,
rigid and bone-parented meshes in part maps, and bone targets in look_at."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from opus.blender.runner import BlenderNotFound, find_blender, run_task

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"
HIGHLIGHT, DIM = (1.0, 0.45, 0.05), (0.55, 0.55, 0.58)  # opus_bl.inspect3d


def srgb8(color):
    return np.array([round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)) for v in color[:3]])


def count(path, color, tol=2) -> int:
    rgb = np.asarray(Image.open(path).convert("RGB")).reshape(-1, 3).astype(int)
    return int((np.abs(rgb - srgb8(color)).max(axis=1) <= tol).sum())


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    return tmp_path_factory.mktemp("parts")


@pytest.fixture(scope="module")
def human(work):
    out = work / "human.blend"
    run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 5000, "out_blend": str(out)})
    return out


@pytest.fixture(scope="module")
def cases(human, work):
    d = work / "cases"
    subprocess.run([BLENDER, "-b", str(human), "--python", str(SCRIPTS / "parts_cases.py"), "--", str(d)],
                   check=True, capture_output=True, timeout=300)
    return d, json.loads((d / "cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def outfit(cases):
    return run_task("report", {"path": str(cases[0] / "outfit.blend")})


# ---------------------------------------------------------------- floating islands (REP-1)

def test_an_island_planted_off_a_skinned_body_is_a_gap(cases):
    d, info = cases
    rep = run_task("report", {"path": str(d / "float.blend")})
    assert rep["mode"] == "bones"
    (g,) = rep["gaps"]
    assert g["island"] is True and g["part"].startswith("humanoid_realistic island ")
    assert g["nearest"] == "humanoid_realistic"
    assert g["gap_m"] == pytest.approx(0.15, abs=0.01)
    assert g["center_m"] == pytest.approx(info["float"]["center_m"], abs=0.01)


def test_a_tusk_island_7_5_mm_off_the_face_is_a_gap(cases):
    d, info = cases
    rep = run_task("report", {"path": str(d / "tusk.blend")})
    (g,) = rep["gaps"]
    assert g["island"] is True and g["gap_m"] == pytest.approx(0.0075, abs=0.0015)
    assert g["center_m"] == pytest.approx(info["tusk"]["center_m"], abs=0.005)


def test_islands_that_touch_or_sit_inside_do_not_float(cases):
    rep = run_task("report", {"path": str(cases[0] / "touch.blend")})  # sunk 3 mm, 1 mm off, wholly inside
    assert rep["gaps"] == []


def test_skinned_objects_are_in_the_contact_graph_with_a_3_mm_tolerance(outfit):
    """A plate skinned to the thigh, 5 mm off it, floats; the bounding-diagonal tolerance alone
    (0.4% of 2.5 m) would have called it touching."""
    gaps = {g["part"]: g for g in outfit["gaps"]}
    assert set(gaps) == {"plate"}
    assert 0.004 < gaps["plate"]["gap_m"] < 0.012 and "island" not in gaps["plate"]
    pairs = {frozenset((c["a"], c["b"])): c for c in outfit["contacts"]}
    assert frozenset(("sword", "humanoid_realistic")) in pairs  # its grip runs through the hand
    assert all("gap_mm" in c for c in outfit["contacts"])


def test_penetrations_are_reported_not_gated(outfit):
    (pen,) = [p for p in outfit["penetrations"] if {p["a"], p["b"]} == {"sword", "humanoid_realistic"}]
    assert pen["class"] == "report" and pen["check"] == "penetration"
    assert pen["depth_mm"] > 1 and pen["kind"] in ("crossing", "through", "embedded")


def test_barrel_report_is_unchanged(work):
    out = work / "barrel.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_barrel.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    rep = run_task("report", {"path": str(out)})
    bands = {frozenset(("Barrel", "Band0")), frozenset(("Barrel", "Band1"))}
    assert rep["mode"] == "objects" and rep["gaps"] == []
    assert {frozenset((c["a"], c["b"])) for c in rep["contacts"]} == bands
    assert {frozenset((p["a"], p["b"])) for p in rep["penetrations"]} == bands  # the bands sit in the staves


# ---------------------------------------------------------------- part names (PARTS-1)

def test_rigid_and_bone_parented_meshes_are_object_parts_with_unique_names(outfit):
    names = [p["name"] for p in outfit["parts"]]
    assert len(names) == len(set(names))
    assert {"hood", "sword", "plate", "shirt", "shirt:spine_02", "shirt:spine_03", "head", "spine_02"} <= set(names)
    assert outfit["mode"] == "bones+objects"
    by = {p["name"]: p for p in outfit["parts"]}
    assert by["hood"]["bone"] == "head" and by["plate"]["bone"] == "thigh_r"
    assert by["sword"]["size_m"][2] == pytest.approx(0.7, abs=0.01)
    assert by["shirt"]["verts"] == 24  # the unweighted bottom ring


def test_part_map_of_an_outfit_decodes_every_pixel(cases, work):
    from opus.threed.understand import readability_check

    _, rep = readability_check(cases[0] / "outfit.blend", camera="ue_tp_1080", distances=[3.5], defining=["head", "hood", "sword"],
                               view="front", out=work / "outfit_read.jpg")
    (lv,) = rep["levels"]
    assert lv["unmatched_px"] == 0
    assert not any("not found" in w for w in rep["warnings"])
    d = {x["part"]: x for x in lv["defining"]}
    assert min(d[n]["area_px"] for n in ("head", "hood", "sword")) > 0
    assert (d["head"]["area_px"], d["head"]["extent_px"]) != (d["hood"]["area_px"], d["hood"]["extent_px"])


# ---------------------------------------------------------------- bone targets in look_at (LOOK-1)

def test_isolating_a_bone_target_renders_only_the_hand_and_its_fingers(human, work):
    res = run_task("views", {"path": str(human), "out_dir": str(work / "iso"), "size": 200, "target": "hand_r", "isolate": True,
                             "shots": [{"view": "front", "pass": "focus", "zoom": 2}, {"view": "front", "pass": "parts", "zoom": 2}]})
    assert {"hand_r", "thumb_01_r", "index_03_r", "pinky_02_r"} <= set(res["focus"])
    assert not {"lowerarm_r", "thigh_r", "hand_l"} & set(res["focus"])
    focus, parts = res["tiles"]
    assert count(focus["path"], HIGHLIGHT) > 1500 and count(focus["path"], DIM) == 0
    assert {lb["name"] for lb in parts["labels"]} <= set(res["focus"])


def test_a_bone_target_behind_the_body_gets_a_cutaway(human, work):
    """From the right, hand_r is behind the body, and the camera framing it sits inside the torso."""
    res = run_task("views", {"path": str(human), "out_dir": str(work / "cut"), "size": 200, "target": "hand_r",
                             "shots": [{"view": "right", "pass": "focus", "zoom": 0.4}, {"view": "left", "pass": "focus", "zoom": 0.4}]})
    behind, near = res["tiles"]
    assert behind["cutaway"] is True and behind["view"] == "right · cutaway"
    assert count(behind["path"], HIGHLIGHT) > 0.8 * count(near["path"], HIGHLIGHT) > 1000  # the whole hand shows
    assert not near.get("cutaway") and near["view"] == "left"
