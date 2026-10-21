"""The `opus` command line without Blender: the tools are faked, so these check what the CLI
passes in, prints and returns."""

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from opus import cli, runs
from opus.bible import init_bible, load_bible
from opus.blender.runner import BlenderTaskError
from opus.threed import grip, lint, proportion, understand


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.delenv("OPUS_PROJECT_DIR", raising=False)
    (tmp_path / "project.godot").write_text("")
    (tmp_path / "axe.blend").write_bytes(b"")
    return tmp_path


def _fake(monkeypatch, module, name, result):
    """Replace module.name with a fake returning a copy of ``result``; returns the recorded calls."""
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return copy.deepcopy(result)

    monkeypatch.setattr(module, name, fake)
    return calls


def _tile(proj) -> str:
    p = proj / "tile.png"
    Image.new("RGB", (32, 32), (90, 90, 90)).save(p)
    return str(p)


# ---------------------------------------------------------------- CLI-1: --json

def test_json_flag_prints_the_numbers_the_mcp_tools_return(proj, monkeypatch, capsys):
    blend = str(proj / "axe.blend")
    report = {"text": "Asset 0.04 x 0.20 x 0.90 m\nContacts: haft + head (touching)",
              "gaps": [{"a": "haft", "b": "head", "gap_m": 0.0}], "contacts": [{"a": "haft", "b": "head"}],
              "penetrations": [], "bounds": {"size": [0.04, 0.2, 0.9]}, "sheet": "/x/report.jpg"}
    _fake(monkeypatch, understand, "model_report", (Path("/x/report.jpg"), dict(report)))
    assert cli.main(["report", blend]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Asset 0.04") and "sheet: /x/report.jpg" in text and '"gaps"' not in text  # default unchanged
    assert cli.main(["report", blend, "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["gaps"][0]["gap_m"] == 0.0 and out["contacts"] and out["text"].startswith("Asset") and out["sheet"]

    check = {"text": "Right hand: good grip", "sides": {"r": {"object": "axe", "contact": {
        "verdict": "good grip", "body": {"verts_inside": 12, "crossing_triangles": 3}}}}, "sheet": "/x/check.jpg"}
    _fake(monkeypatch, grip, "grip_check", (Path("/x/check.jpg"), check))
    assert cli.main(["grip-check", blend, "--side", "r", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["sides"]["r"]["contact"]["body"]["verts_inside"] == 12 and out["sheet"] == "/x/check.jpg"

    _fake(monkeypatch, lint, "mesh_lint", {"text": "2 errors", "game_ready": False, "findings": [{"check": "non_manifold"}]})
    assert cli.main(["lint", blend, "--json"]) == 1  # the exit code still says whether it is game-ready
    assert json.loads(capsys.readouterr().out)["findings"][0]["check"] == "non_manifold"

    _fake(monkeypatch, understand, "blind_read_sheet", (Path("/x/blind.jpg"), "What is this?"))
    assert cli.main(["blind", blend, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"sheet": "/x/blind.jpg", "prompt": "What is this?"}

    for cmd, module, name in (("proportion", proportion, "proportion_check"), ("refmatch", proportion, "reference_match"),
                              ("readability", understand, "readability_check")):
        _fake(monkeypatch, module, name, (Path("/x/s.jpg"), {"text": "t", "iou": 0.81, "all_parts": {}}))
        args = [cmd, blend] + ([blend] if cmd == "refmatch" else []) + ["--json"]
        assert cli.main(args) == 0, cmd
        out = json.loads(capsys.readouterr().out)
        assert out["iou"] == 0.81 and out["sheet"] == "/x/s.jpg", cmd


# ---------------------------------------------------------------- CLI-2: axis names, values starting with '-'

def test_grip_define_takes_axis_names_and_dash_values(proj, monkeypatch, capsys):
    blend = str(proj / "axe.blend")
    rep = {"object": "axe", "grip": "SOCKET_grip_main", "length": 0.4, "radius": 0.015, "index": "curl", "thumb": "wrap",
           "tiles": [{"path": _tile(proj), "label": "front"}]}
    calls = _fake(monkeypatch, grip, "run_task", rep)
    assert cli.main(["grip-define", blend, "haft", "--up", "+Z", "--palm-side", "-X"]) == 0
    params = calls[-1][0][1]
    assert params["up"] == [0, 0, 1] and params["palm_side"] == [-1, 0, 0]
    assert json.loads(capsys.readouterr().out)["sheet"]

    assert cli.main(["grip-define", blend, "pistol", "--point-axis", "-Y", "--start", "-0.01,0,0.1", "--end", "-0.01,0,0.2",
                     "--thumb", "along", "--trigger", "0,-0.05,0.15", "--hand", "l"]) == 0
    params = calls[-1][0][1]
    assert params["point_axis"] == "-Y" and params["start"] == [-0.01, 0, 0.1] and params["end"] == [-0.01, 0, 0.2]
    assert params["thumb"] == "along" and params["trigger"] == [0, -0.05, 0.15] and params["hand"] == "l"


def test_look_and_hold_read_values_that_start_with_a_dash(proj, monkeypatch, capsys):
    blend = str(proj / "axe.blend")
    calls = _fake(monkeypatch, understand, "look_at", (Path("/x/look.jpg"), {"views": 1}))
    assert cli.main(["look", blend, "--views", "-30,10", "--objects", "haft, head"]) == 0
    assert calls[-1][1]["views"] == ["-30,10"] and calls[-1][1]["objects"] == ["haft", "head"]
    assert cli.main(["look", blend, "--views=-30,10;200,40"]) == 0
    assert calls[-1][1]["views"] == ["-30,10", "200,40"]

    rep = {"object": "rifle", "contact": {"verdict": "good grip"}, "text": "Right hand: good grip", "file": "/x/held.blend",
           "tiles": [{"path": _tile(proj), "label": "palm"}]}
    calls = _fake(monkeypatch, grip, "run_task", rep)
    assert cli.main(["hold", blend, blend, "--pose", "fp_hip", "--offset", "-0.1,0.15,0.25", "--aim-axis", "+X",
                     "--object", "rifle", "--index", "trigger", "--thumb", "along"]) == 0
    params = calls[-1][0][1]
    assert params["offset"] == [-0.1, 0.15, 0.25] and params["aim_axis"] == "+X" and params["object"] == "rifle"
    assert params["index"] == "trigger" and params["thumb"] == "along"
    assert "Right hand: good grip" in capsys.readouterr().out


# ---------------------------------------------------------------- CLI-3: options the MCP twins have

def test_objects_option_reaches_the_tools(proj, monkeypatch, capsys):
    blend = str(proj / "axe.blend")
    for cmd, module, name in (("proportion", proportion, "proportion_check"), ("refmatch", proportion, "reference_match")):
        calls = _fake(monkeypatch, module, name, (Path("/x/s.jpg"), {"text": "t"}))
        args = [cmd, blend] + ([blend] if cmd == "refmatch" else []) + ["--objects", "body,head"]
        assert cli.main(args) == 0
        assert calls[-1][1]["objects"] == ["body", "head"], cmd
    calls = _fake(monkeypatch, understand, "blind_read_sheet", (Path("/x/b.jpg"), "prompt"))
    assert cli.main(["blind", blend, "--objects", "body"]) == 0
    assert calls[-1][1]["objects"] == ["body"]
    capsys.readouterr()


def test_lint_category_takes_the_bible_budget(proj, monkeypatch, capsys):
    init_bible(proj, project="T")
    blend = str(proj / "axe.blend")
    calls = _fake(monkeypatch, lint, "mesh_lint", {"text": "ok", "game_ready": True})
    assert cli.main(["lint", blend, "--category", "prop_small"]) == 0
    assert calls[-1][1]["budget_tris"] == load_bible(proj)["3d"]["budgets_tris"]["prop_small"]
    assert cli.main(["lint", blend, "--category", "prop_small", "--budget", "123"]) == 0
    assert calls[-1][1]["budget_tris"] == 123
    assert cli.main(["lint", blend, "--category", "spaceship"]) == 2
    assert "unknown category 'spaceship'" in capsys.readouterr().err


def test_run_stats_for_one_run(proj, capsys):
    run = runs.log("run_start", near=proj, task="axe", label="v0.4")["run"]
    runs.log("iteration", near=proj, n=1, hard_fail_count=2, findings="floating_parts")
    runs.log("iteration", near=proj, n=2, hard_fail_count=0)
    assert cli.main(["run-stats", "--dir", str(proj), "--run", run]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["run"] == run and out["iterations"] == 2 and out["iterations_to_hard_pass"] == 2
    assert cli.main(["run-stats", "--dir", str(proj), "--run", "nope"]) == 2
    err = capsys.readouterr().err
    assert "no run 'nope'" in err and run in err


def test_bible_shows_by_default_with_the_cameras(proj, capsys):
    init_bible(proj, project="T")
    assert cli.main(["bible", "--dir", str(proj)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["camera_active"]["name"] and "camera_viewmodel" in out


# ---------------------------------------------------------------- CLI-4: one-line errors

def test_bad_arguments_are_one_line_errors(proj, monkeypatch, capsys):
    assert cli.main(["run-log", "validator_rejection", "tool=x", "--dir", str(proj)]) == 2
    err = capsys.readouterr().err
    assert "opus run-log: error:" in err and "allowed: ['check', 'reason']" in err and "Traceback" not in err

    assert cli.main(["grip-define", str(proj / "axe.blend"), "haft", "--up", "+W"]) == 2
    assert "up: give an axis such as +Z or -X, or x,y,z" in capsys.readouterr().err

    def boom(*a, **k):
        raise BlenderTaskError("Blender exited with code 1 before writing a result:\nlast log line")

    monkeypatch.setattr(understand, "run_task", boom)
    assert cli.main(["report", str(proj / "axe.blend")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("opus report: error: Blender exited") and "last log line" in err


# ---------------------------------------------------------------- CLI-5: help that lists the fields

def test_run_log_help_lists_every_event_and_field(capsys):
    with pytest.raises(SystemExit):
        cli.main(["run-log", "--help"])
    out = capsys.readouterr().out
    for event, fields in runs.EVENTS.items():
        assert event in out
        for field in fields:
            assert field in out, (event, field)
    assert "hard_fail_count* (int)" in out and "wall_clock_s (float)" in out
