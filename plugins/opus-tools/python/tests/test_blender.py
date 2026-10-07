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
    assert len(list(Path(rep["tiles_dir"]).glob("*.png"))) == 13


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
