"""Signed distance that holds at edges and corners, and penetration a closest-point test misses."""

import json
import subprocess
from pathlib import Path

import pytest

from opus.blender.runner import BLENDER_MODULES, BlenderNotFound, find_blender, run_task
from opus.threed.understand import summarize

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


def test_faces_reversed_against_their_neighbours_are_turned_to_agree(sdf):
    """One reversed face used to make the cube "open", and the winding number then read 471
    of 500 points near it as outside."""
    cube = sdf["cube, one face reversed"]
    assert cube["closed"] and cube["new_wrong"] == 0 and cube["one_wrong"] == 0 and cube["max_err"] < 1e-9


def test_thin_plate_sheets_face_out_of_the_wall_whatever_their_shape(sdf):
    """A sheet has no volume to orient by: the concave side of a curved plate and flat plates
    at some angles were turned inward, and parts that only dip into one face read as passing
    right through it."""
    curved = sdf["curved plate, box 0.5 mm past its concave side"]
    assert curved["sides"] == 2 and curved["sides_face_apart"]
    assert curved["kind"] == "crossing" and 0.4 < curved["sheet_mm"] < 1.0 and curved["depth_mm"] < 1.0
    turned = sdf["rotated plates, box sunk 0.05 mm"]
    assert turned["sides_face_apart"] == 40 and turned["kinds"] == {"crossing": 40}
    assert turned["deepest_mm"] == pytest.approx(0.05, abs=0.005)


def test_a_clamp_on_both_faces_is_not_through_the_plate(sdf):
    """Each jaw sits behind the far sheet; only the sheet a part crosses counts it as behind."""
    clamp = sdf["clamp, both jaws 0.05 mm into a 2 mm plate"]
    assert clamp["kind"] == "crossing"
    assert clamp["sheet_mm"] == pytest.approx(0.05, abs=0.005) and clamp["depth_mm"] == pytest.approx(0.05, abs=0.005)


def test_an_object_scaled_to_zero_has_no_solid(sdf):
    zero = sdf["object scaled to 0"]
    assert zero["alone_is_none"] and zero["with_another_tris"] == 12
    # flattened instead: its opposite normals cancel, and points beside it used to read inside
    assert zero["flat_lid_open"] and zero["flat_lid_inside"] == 0 and zero["flat_lid_depth_mm"] < 1e-3


def test_winding_of_a_large_open_part_sums_distant_clusters(sdf):
    """Exact winding costs every triangle per query; a 29k-triangle capless handle made the
    grip solver 16x slower than v0.3."""
    tube = sdf["open tube, clustered winding"]
    assert tube["open"] and tube["tris"] > 20000 and tube["inside"] > 50
    assert tube["max_err"] < 0.03 and tube["side_wrong"] == 0
    assert tube["us_signed1"] < tube["us_exact"] / 4


def test_box_pushed_through_a_thin_plate_is_a_penetration(work):
    rep = run_task("report", {"path": str(work / "through.blend")})
    pens = {frozenset((p["a"], p["b"])): p for p in rep["penetrations"]}
    p = pens[frozenset(("Plate", "Box"))]
    assert p["kind"] == "through" and p["thin_part"] == "Plate"
    assert p["thickness_mm"] == pytest.approx(2.0, abs=0.1)
    assert p["past_sheet_mm"] == pytest.approx(11.0, abs=0.5)  # box top 10 mm above, plate bottom 1 mm below
    assert p["triangles"] > 0 and p["depth_mm"] >= 11.0
    assert p["at_m"] == pytest.approx([0.01, 0.005, 0.0], abs=0.003)
    assert p["check"] == "penetration" and p["class"] == "report" and p["pass"] is False
    pin = pens[frozenset(("Box", "Pin"))]
    # its deepest corner is 15 mm from the box's sides and bottom
    assert pin["kind"] == "embedded" and pin["inside"] == "Pin" and pin["triangles"] == 0
    assert pin["depth_mm"] == pytest.approx(15.0, abs=0.2)
    assert frozenset(("Plate", "Pin")) not in pens
    assert any({c["a"], c["b"]} == {"Plate", "Box"} and c["kind"] == "intersecting" for c in rep["contacts"])
    assert "(penetrations are reported, not gated: fine for hidden joints on static props" in summarize(rep)  # REP-2


def test_parts_that_only_touch_are_not_penetrations(work):
    rep = run_task("report", {"path": str(work / "touching.blend")})  # with a lid scaled to 0: no faces, no crash
    assert rep["penetrations"] == []
    touching = {frozenset((c["a"], c["b"])) for c in rep["contacts"] if c["kind"] == "touching"}
    assert {frozenset(("Plate", "Block")), frozenset(("Block", "Side"))} <= touching
    assert rep["gaps"] == []


def test_abutting_roof_bays_touch_without_penetrating(tmp_path):
    """Two bays of a kit roof meet at x = 4 m with no vertex past it; float noise in that plane
    put one slab 'behind' the other's sheets, a 76 mm penetration."""
    roof = tmp_path / "roof_pair.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "roof_pair.py"), "--", str(roof)],
                   check=True, capture_output=True, timeout=300)
    rep = run_task("report", {"path": str(roof)})
    assert rep["penetrations"] == []
    roof_pair = [{k: c[k] for k in ("a", "b", "kind")} for c in rep["contacts"]]
    assert {"a": "roof_back_01", "b": "roof_back_02", "kind": "touching"} in roof_pair
    assert all(c["gap_mm"] == 0 for c in rep["contacts"])  # REP-1 adds the gap to each contact


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
