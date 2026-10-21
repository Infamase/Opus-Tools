"""Integration tests that run a real headless Blender. Skipped when Blender isn't available."""

import subprocess
from pathlib import Path

import pytest

from opus.blender.runner import BlenderNotFound, find_blender

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"


def make_barrel(tmp_path: Path, defects: bool = False) -> Path:
    out = tmp_path / ("barrel_defects.blend" if defects else "barrel.blend")
    cmd = [BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_barrel.py"), "--", str(out)]
    if defects:
        cmd.append("--defects")
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return out


def test_lookdev_sheet(tmp_path):
    from opus.threed.lookdev import lookdev_sheet

    sheet, rep = lookdev_sheet(make_barrel(tmp_path), engine="workbench", tile=160)
    assert sheet.exists()
    assert rep["totals"]["objects"] == 3 and rep["totals"]["tris"] == 340
    assert rep["dimensions_m"] == pytest.approx([0.64, 0.64, 0.9], abs=0.01)
    assert len(list(Path(rep["tiles_dir"]).glob("*.png"))) == 14


def test_mesh_lint_finds_planted_defects(tmp_path):
    from opus.threed.lint import mesh_lint

    rep = mesh_lint(make_barrel(tmp_path, defects=True), budget_tris=300)
    checks = {(f["check"], f["object"]): f for f in rep["findings"]}
    assert checks[("flipped_normals", "Barrel")]["count"] == 1
    assert ("loose_geometry", "Barrel") in checks
    assert ("unapplied_scale", "Barrel") in checks
    assert ("floating_part", "FloatingLid") in checks
    assert ("over_budget", "(asset)") in checks
    assert rep["game_ready"] is False
    assert "NOT game-ready" in rep["text"]


def test_mesh_lint_clean_barrel_has_no_geometry_errors(tmp_path):
    from opus.threed.lint import mesh_lint

    rep = mesh_lint(make_barrel(tmp_path))
    errors = [f for f in rep["findings"] if f["severity"] == "error"]
    assert errors == []


@pytest.fixture(scope="module")
def lint_cases(tmp_path_factory):
    d = tmp_path_factory.mktemp("lint_cases")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "lint_cases.py"), "--", str(d)],
                   check=True, capture_output=True, timeout=300)
    return d


def _checks(rep: dict) -> dict:
    return {(f["check"], f["object"]): f for f in rep["findings"]}


def test_mesh_lint_reads_normals_in_world_space_on_rotated_objects(lint_cases):
    """A closed cylinder rotated 120 degrees (a prop in a hand) read as 4 faces pointing inward."""
    from opus.threed.lint import mesh_lint

    rep = mesh_lint(lint_cases / "rot120.blend")
    assert rep["objects"][0]["flipped_faces"] == 0
    assert not {"flipped_normals", "inside_out"} & {f["check"] for f in rep["findings"]}, rep["text"]
    rep = mesh_lint(lint_cases / "rot120_flip.blend")
    assert _checks(rep)[("flipped_normals", "blade")]["count"] == 1


def test_mesh_lint_welds_what_the_gltf_importer_split(lint_cases):
    """The importer splits every flat-shaded vertex: each face was its own piece, so faces
    'pointed inward', edges were open and neighbouring faces 'intersected'."""
    from opus.threed.lint import mesh_lint

    rep = mesh_lint(lint_cases / "flat.glb")
    assert rep["game_ready"] and rep["summary"]["error"] == 0, rep["text"]
    crate = rep["objects"][0]
    assert crate["islands"] == 2 and crate["flipped_faces"] == 0
    assert any(n.startswith("welded for import") for n in crate["notes"])
    checks = _checks(rep)
    assert ("intersecting_parts", "(asset)") not in checks and ("open_edges", "Crate") not in checks
    rep = mesh_lint(lint_cases / "flat_flip.glb")
    assert _checks(rep)[("flipped_normals", "Crate")]["count"] == 1


def test_mesh_lint_treats_props_on_a_bone_as_rigid(lint_cases):
    """deforming=true demanded vertex groups (and errored on n-gons) on props parented to a
    bone, the form grip_hold gives them."""
    from opus.threed.lint import mesh_lint

    rep = mesh_lint(lint_cases / "rigid.blend", deforming=True)
    checks = _checks(rep)
    assert ("weights_missing", "Body") in checks  # skinned, with no vertex groups: still an error
    assert ("weights_missing", "AxeHead") not in checks and ("weights_missing", "Blade") not in checks
    assert checks[("ngons", "AxeHead")]["severity"] == "info"
    objs = {o["name"]: o for o in rep["objects"]}
    assert objs["AxeHead"]["rigid_attachment"] == objs["Blade"]["rigid_attachment"] == "weapon_r"
    assert objs["Body"]["deforming"] and not objs["AxeHead"]["deforming"] and "rigid_attachment" not in objs["Body"]


def test_mesh_lint_measures_how_far_a_floating_piece_is_off(lint_cases):
    """A tusk 7.5 mm off the head passed: its box lies inside the head's box."""
    from opus.threed.lint import mesh_lint

    rep = mesh_lint(lint_cases / "tusk_float.blend")
    floats = [f for f in rep["findings"] if f["check"] == "floating_part"]
    assert len(floats) == 1, rep["text"]  # the tusk; the eye sits inside the head, the head in the body
    assert floats[0]["gap_mm"] == pytest.approx(7.5, abs=0.2) and floats[0]["nearest"] == "goblin"
    assert "7.5 mm" in floats[0]["message"]
    rep = mesh_lint(lint_cases / "tusk_touch.blend")  # 1 mm off: within the 2 mm tolerance
    assert not [f for f in rep["findings"] if f["check"] == "floating_part"], rep["text"]
