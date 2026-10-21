"""The 24-task eval suite: every spec loads and validates, and the suite covers what §9 asks."""

import copy
import importlib.util
import inspect
import shutil
import subprocess

import pytest

from opus import runs
from opus.cli import main as cli

EVALS = runs.evals_dir()
pytestmark = pytest.mark.skipif(not (EVALS / "tasks").is_dir(), reason="no evals/ folder (set OPUS_EVALS_DIR)")


@pytest.fixture(scope="module")
def tasks():
    return runs.load_tasks()


def by_id(tasks):
    return {t["id"]: t for t in tasks}


def test_all_specs_load_and_validate(tasks):
    assert len(tasks) == 24
    assert runs.validate_suite(tasks) == []


def test_regression_subjects_come_first(tasks):
    assert [t["id"] for t in tasks[:8]] == ["knight", "goblin", "wolf", "dragon", "chest", "barrel", "house", "sword"]
    assert sum(bool(t.get("regression")) for t in tasks) == 8


def test_category_tasks_cover_the_roadmap(tasks):
    cat = [t for t in tasks if not t.get("regression")]
    assert len(cat) == 16
    assert {t["category"] for t in cat} == set(runs.CATEGORIES) - {"building"}
    covers = {(t["category"], c) for t in cat for c in t.get("covers", [])}
    for category, needed in runs.COVERAGE.items():
        assert {(category, n) for n in needed} <= covers
    # the first-person rifle is held in two hands, and both hands are checked
    rifle = by_id(tasks)["fp_rifle"]
    assert rifle["camera"]["profile"] == "viewmodel"
    sides = {c["args"]["side"] for c in rifle["accept"] if c["tool"] == "grip_check" and c["metric"] == "verdict"}
    assert sides == {"l", "r"}
    assert {t["style"] for t in tasks} == {"lowpoly", "hd", "pixel"}
    assert {t["engine"] for t in tasks} == {"unreal", "godot"}


def test_every_task_has_the_required_fields(tasks):
    for t in tasks:
        for field in runs.TASK_FIELDS:
            assert t.get(field) not in (None, ""), (t["id"], field)
        assert t["brief"].strip() and t["title"].strip()
        hard = [c for c in t["accept"] if c["class"] == "hard"]
        assert hard, t["id"]
        assert all(c["tool"] in runs.METRICS for c in t["accept"]), t["id"]
        assert set(runs.SCORE_FIELDS) <= set(t["score"]), t["id"]
        for r in t["references"]:
            assert r["url"].startswith("https://") and r["license"].lower() in runs.REF_LICENSES
    # every task is judged on what it is: a blind read names the subject, or an animation is measured
    for t in tasks:
        tools = {c["tool"] for c in t["accept"] if c["class"] == "hard"}
        assert "blind_read_sheet" in tools or t["category"] == "animation", t["id"]


def test_check_args_are_real_tool_parameters(tasks):
    """Every check's args name parameters the MCP tool really has (camera ids come from opus.camera)."""
    from opus import mcp_server

    for t in tasks:
        for c in t["accept"]:
            fn = getattr(mcp_server, c["tool"], None)
            if fn is None:  # probe and art_director checks are not tools
                continue
            extra = set(c.get("args") or {}) - set(inspect.signature(fn).parameters)
            assert not extra, f"{t['id']}/{c['id']}: {c['tool']} has no parameter(s) {sorted(extra)}"
            cam = (c.get("args") or {}).get("camera")
            assert not cam or cam in runs.CAMERAS, f"{t['id']}/{c['id']}: unknown camera {cam}"


def test_validator_catches_broken_specs(tasks):
    good = by_id(tasks)["knight"]
    assert runs.validate_task(good) == []

    def broken(**changes):
        spec = copy.deepcopy(good)
        for k, v in changes.items():
            if v is None:
                spec.pop(k)
            else:
                spec[k] = v
        return " | ".join(runs.validate_task(spec))

    assert "missing brief" in broken(brief=None)
    assert "category" in broken(category="vehicle")
    assert "regression" in broken(regression=False)
    assert "CC0 or public domain" in broken(references=[{"url": "https://example.com/a.png", "license": "CC BY 4.0"}])
    assert "camera.profile" in broken(camera={"profile": "cinematic", "distances_m": [3]})
    assert "sprite_px" in broken(style="pixel")
    assert "positive numbers" in broken(budgets={"tris": -1})
    assert "score is missing" in broken(score=["accepted"])

    def check(**changes):
        c = {"id": "x", "tool": "model_report", "metric": "floating_parts", "op": "==", "value": 0, "class": "hard", **changes}
        return " | ".join(runs.validate_task({**copy.deepcopy(good), "accept": [c]}))

    assert check() == ""
    assert "not a v0.4 check" in check(tool="spec_check")
    assert "no metric 'iou'" in check(metric="iou")
    assert "between needs" in check(op="between", value=[2, 1])
    assert "unknown key 'rim and grip touch the board'" in check(**{"rim and grip touch the board": None})
    assert "measure" in check(tool="probe", metric="seam_gap_mm")
    assert "names" in check(tool="blind_read_sheet", metric="top1_names_subject", value=True)
    assert "2-5 yes/no" in check(tool="art_director", metric="checklist_no", questions=["Only one?"])
    assert "at least one hard check" in check(**{"class": "soft"})
    assert "uncalibrated heuristic" in check(tool="proportion_check", metric="unintended_findings")
    assert "uncalibrated heuristic" in check(tool="readability_check", metric="defining_under_floor")


def test_camera_checks_run_at_the_task_camera(tasks):
    """readability_check and blind_read_sheet measure at a camera. Without args.camera they use
    the eval project's default (ue_tp_1080), so a Godot task's check must name godot_tp."""
    assert runs._default_camera() == "ue_tp_1080"
    wolf = copy.deepcopy(by_id(tasks)["wolf"])
    read = next(c for c in wolf["accept"] if c["tool"] == "readability_check")
    assert read["args"]["camera"] == "godot_tp" and runs.validate_task(wolf) == []
    del read["args"]["camera"]
    errs = runs.validate_suite([wolf if t["id"] == "wolf" else t for t in tasks])
    assert errs == [f"wolf.yaml: accept[{wolf['accept'].index(read)}]: readability_check must run at the task's camera "
                    "'godot_tp' (no args.camera, so the tools use 'ue_tp_1080'); set args.camera: godot_tp"]
    read["args"]["camera"] = "ue_tp_1080"
    assert "(args.camera 'ue_tp_1080')" in " | ".join(runs.validate_task(wolf))
    # a first-person task checks at the view model, and may check its world model at a named third-person camera
    rifle = copy.deepcopy(by_id(tasks)["fp_rifle"])
    blind = next(c for c in rifle["accept"] if c["tool"] == "blind_read_sheet")
    assert blind["args"]["camera"] == "ue_tp_1080" and runs.validate_task(rifle) == []
    del blind["args"]["camera"]
    assert "blind_read_sheet must run at the task's camera 'viewmodel'" in " | ".join(runs.validate_task(rifle))
    # every camera check in the committed suite runs at its task's camera
    for t in tasks:
        for c in t["accept"]:
            if c["tool"] in runs.CAMERA_CHECKS:
                cam = (c.get("args") or {}).get("camera") or runs._default_camera()
                assert cam == t["camera"]["profile"] or t["camera"]["profile"] == "viewmodel", (t["id"], c["id"])


def _judge():
    path = EVALS / "judge.py"
    if not path.is_file():
        pytest.skip("no evals/judge.py")
    spec = importlib.util.spec_from_file_location("eval_judge", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_judge_rechecks_one_question_and_reads_comma_names():
    judge = _judge()
    assert judge.check_args("checklist", ["Is the tail moving?"]) == []  # a re-check asks only what failed
    assert judge.check_args("blind", [], "a,b|c") == ["a", "b", "c"]
    assert judge.check_args("blind", [], "House, cottage|medieval house") == ["house", "cottage", "medieval house"]
    for questions in ([], ["Is it red?"] * 6):
        with pytest.raises(SystemExit, match="1-5 questions"):
            judge.check_args("checklist", questions)


def test_suite_level_problems_are_reported(tasks):
    errs = runs.validate_suite([t for t in tasks if t["id"] not in ("wolf", "crow")])
    assert "suite: 22 tasks, expected 24" in errs
    assert "suite: regression subjects missing: ['wolf']" in errs
    assert "suite: no creature task covers flyer" in errs


def test_prompt_carries_brief_and_protocol(tasks):
    knight = by_id(tasks)["knight"]
    p = runs.task_prompt(knight)
    assert p.startswith(knight["brief"].strip())
    assert 'run_log(event="run_start", task="knight"' in p
    assert "run_start returns the run id; pass run=<that id> on every later run_log call" in p
    for c in knight["accept"]:
        assert f"] {c['id']}: {c['tool']}(" in p
    assert 'values="blind_read_top1=...; grip_verdict=...; tris=..."' in p
    assert "https://www.metmuseum.org/art/collection/search/23232" in p
    assert "names: knight | armored knight | man-at-arms" in p


def test_suite_hash_ignores_line_endings(tmp_path):
    (tmp_path / "tasks").mkdir()
    for f in (EVALS / "tasks").glob("*.yaml"):
        (tmp_path / "tasks" / f.name).write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    assert runs.suite_hash(tmp_path) == runs.suite_hash(EVALS)
    shutil.copy(EVALS / "tasks" / "knight.yaml", tmp_path / "tasks" / "knight.yaml")
    (tmp_path / "tasks" / "barrel.yaml").write_text("id: barrel\n", encoding="utf-8")
    assert runs.suite_hash(tmp_path) != runs.suite_hash(EVALS)


def test_only_specs_and_summaries_are_committed():
    try:
        out = subprocess.run(["git", "ls-files", "--", "."], cwd=EVALS, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    for name in out.split():
        assert (name in ("README.md", ".gitignore", "judge.py") or (name.startswith("tasks/") and name.endswith(".yaml"))
                or (name.startswith("results/") and name.endswith((".json", ".md")))), name


def test_cli_lists_and_validates(capsys):
    group = "eval"
    assert cli([group, "validate"]) == 0
    assert "24 tasks valid" in capsys.readouterr().out
    assert cli([group, "list"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 24 and lines[0].startswith("knight") and "regression" in lines[0]
    assert cli([group, "prompt", "wolf_trot"]) == 0
    assert "LH 0, RF 0, RH 0.5, LF 0.5" in capsys.readouterr().out
