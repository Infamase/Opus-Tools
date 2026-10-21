"""Signed distance that holds at edges and corners, and penetration a closest-point test misses."""

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
    d = tmp_path_factory.mktemp("geom")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_penetration.py"), "--", str(d)],
                   check=True, capture_output=True, timeout=300)
    return d


@pytest.fixture(scope="module")
def sdf(work):
    out = work / "sdf.json"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "sdf_probe.py"), "--",
                    str(BLENDER_MODULES), str(out)], check=True, capture_output=True, timeout=300)
    return {c["case"]: c for c in json.loads(out.read_text(encoding="utf-8"))}


def test_sign_is_right_near_cube_edges_and_corners_where_the_face_normal_flips(sdf):
    cube = sdf["cube, rotated, near edges and corners"]
    assert cube["closed"] and cube["outside"] > 1000 and cube["inside"] > 200
    assert cube["new_wrong"] == 0 and cube["one_wrong"] == 0
    assert cube["max_err"] < 1e-6  # distances match the exact box distance
    assert cube["one_vs_batch"] < 1e-9  # the solver's one-point path agrees with the batch path
    # the old closest-face-normal sign: points in a face's plane beyond its edge are a coin toss
    assert cube["old_wrong"] > 20
    assert sdf["cube, axis-aligned"]["new_wrong"] == 0


def test_sign_is_right_around_a_sharp_edge(sdf):
    wedge = sdf["wedge, 30 degree edge"]
    assert wedge["new_wrong"] == 0 and wedge["one_wrong"] == 0 and wedge["max_err"] < 1e-9
    assert wedge["old_wrong"] > 50  # outside points read as inside when the BVH returns the other face


def test_open_meshes_and_overlapping_parts_use_winding_and_union(sdf):
    hole = sdf["open box, winding number"]
    assert not hole["closed"] and hole["inside"] > 100
    assert hole["new_wrong"] == 0 and hole["one_wrong"] == 0
    union = sdf["two overlapping cubes"]
    assert union["parts"] == 2 and union["new_wrong"] == 0 and union["one_wrong"] == 0
    for case in ("cube, faces turned inward", "cube, mirrored object"):  # both read as outward
        assert sdf[case]["new_wrong"] == 0 and sdf[case]["one_wrong"] == 0 and sdf[case]["max_err"] < 1e-9
        assert sdf[case]["old_wrong"] == sdf[case]["points"]  # the old sign read them inside out


def test_closest_point_tests_miss_a_box_through_a_plate_but_overlap_does_not(sdf):
    p = sdf["box through plate"]
    assert p["box_verts_inside"] == p["plate_verts_inside"] == 0
    assert p["old_box_verts_inside"] == p["old_plate_verts_inside"] == 0
    assert p["kind"] == "through" and p["triangles"] > 0
    assert p["thickness_mm"] == pytest.approx(2.0, abs=0.01) and p["sheet_mm"] == pytest.approx(11.0, abs=0.01)


def test_box_pushed_through_a_thin_plate_is_a_penetration(work):
    rep = run_task("report", {"path": str(work / "through.blend")})
    pens = {frozenset((p["a"], p["b"])): p for p in rep["penetrations"]}
    p = pens[frozenset(("Plate", "Box"))]
    assert p["kind"] == "through" and p["thin_part"] == "Plate"
    assert p["thickness_mm"] == pytest.approx(2.0, abs=0.1)
    assert p["past_sheet_mm"] == pytest.approx(11.0, abs=0.5)  # box top 10 mm above, plate bottom 1 mm below
    assert p["triangles"] > 0 and p["depth_mm"] >= 11.0
    assert p["at_m"] == pytest.approx([0.01, 0.005, 0.0], abs=0.003)
    assert p["check"] == "penetration" and p["class"] == "hard" and p["pass"] is False
    pin = pens[frozenset(("Box", "Pin"))]
    # its deepest corner is 15 mm from the box's sides and bottom
    assert pin["kind"] == "embedded" and pin["inside"] == "Pin" and pin["triangles"] == 0
    assert pin["depth_mm"] == pytest.approx(15.0, abs=0.2)
    assert frozenset(("Plate", "Pin")) not in pens
    assert any({c["a"], c["b"]} == {"Plate", "Box"} and c["kind"] == "intersecting" for c in rep["contacts"])


def test_parts_that_only_touch_are_not_penetrations(work):
    rep = run_task("report", {"path": str(work / "touching.blend")})
    assert rep["penetrations"] == []
    touching = {frozenset((c["a"], c["b"])) for c in rep["contacts"] if c["kind"] == "touching"}
    assert {frozenset(("Plate", "Block")), frozenset(("Block", "Side"))} <= touching
    assert rep["gaps"] == []


def test_grip_check_catches_a_plate_cut_through_the_forearm(tmp_path):
    rig = tmp_path / "human.blend"
    run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 6000, "out_blend": str(rig)})
    cut = tmp_path / "plate_arm.blend"
    subprocess.run([BLENDER, "-b", str(rig), "--python", str(SCRIPTS / "plate_through_arm.py"), "--", str(cut)],
                   check=True, capture_output=True, timeout=300)
    rep = run_task("grip_check", {"path": str(cut), "side": "r", "object": "Plate"})
    body = rep["sides"]["r"]["contact"]["body"]
    assert body["verts_inside"] == 0  # no skin vertex sits inside the 2 mm plate
    assert body["crossing_triangles"] > 0 and body["depth_mm"] > 10
    assert "lowerarm_r" in body["where"]
    assert "clips the body" in rep["sides"]["r"]["contact"]["verdict"]
