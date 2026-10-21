"""Run ledger: events round-trip through .opus/runs, and run_stats gets the numbers right."""

import json
import os
import sys

import anyio
import pytest

from opus import runs
from opus.cli import main as cli

T0 = 1_789_970_400.0  # 2026-09-21 06:00 UTC: a fixed clock, and no local midnight within hours of it


@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.godot").write_text("")
    return tmp_path


def test_ledger_round_trip(project):
    start = runs.log("run_start", near=project, now=T0, task="knight", asset="art/knight.blend", label="v0.4", model="m")
    assert start["run"].endswith("-knight") and start["tool_version"]
    runs.log("iteration", near=project, now=T0 + 60, n=1, tier="T2", hard_fail_count=2, findings="floating_parts, grip x2")
    runs.log("validator_rejection", near=project, now=T0 + 70, check="mesh_lint", reason="unknown category")
    runs.log("iteration", near=project, now=T0 + 200, n=2, tier="T5", hard_fail_count=0, findings="")
    runs.log("judge_round", near=project, now=T0 + 250, kind="blind_read", questions=1, failed=0)
    acc = runs.log("accept", near=project, now=T0 + 300, values="blind_read_top1=knight; tris=31200")
    runs.log("tokens", near=project, now=T0 + 310, input=12000, output=3400)  # usage is read after the run closes

    assert acc["iterations_to_accept"] == 2 and acc["wall_clock_s"] == 300
    assert acc["values"] == {"blind_read_top1": "knight", "tris": 31200}
    files = list((project / ".opus" / "runs").glob("*.jsonl"))
    assert len(files) == 1 and files[0].stem.count("-") == 2  # <date>.jsonl
    lines = [json.loads(x) for x in files[0].read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in lines] == ["run_start", "iteration", "validator_rejection", "iteration", "judge_round",
                                           "accept", "tokens"]
    assert {e["run"] for e in lines} == {start["run"]}
    assert lines[1]["findings"] == {"floating_parts": 1, "grip": 2}
    assert runs.read_events(project) == lines

    r = runs.run_summaries(project)[0]
    assert (r["accepted"], r["iterations_to_hard_pass"], r["iterations_to_accept"], r["hard_fail_count_first"]) == (True, 2, 2, 2)
    assert (r["judge_rounds"], r["validator_rejections"], r["wall_clock_s"]) == (1, 1, 300)
    assert (r["tokens_input"], r["tokens_output"], r["model"]) == (12000, 3400, "m")
    assert r["failures"] == {"floating_parts": 1, "grip": 2} and r["rejections"] == {"mesh_lint": 1}


def test_events_go_to_the_latest_open_run(project):
    a = runs.log("run_start", near=project, now=T0, task="barrel", asset="barrel.blend")["run"]
    b = runs.log("run_start", near=project, now=T0 + 1, task="chest", asset="chest.blend")["run"]
    assert runs.log("iteration", near=project, now=T0 + 2, n=1, hard_fail_count=1)["run"] == b
    runs.log("accept", near=project, now=T0 + 3)
    assert runs.log("iteration", near=project, now=T0 + 4, n=1, hard_fail_count=0)["run"] == a
    runs.log("abandon", near=project, now=T0 + 5, reason="cap")
    with pytest.raises(ValueError, match="no open run"):
        runs.log("iteration", near=project, n=2, hard_fail_count=0)
    with pytest.raises(ValueError, match="closed"):
        runs.log("judge_round", run=b, near=project, kind="checklist")
    # the user turning down an accepted asset reopens its run
    runs.log("user_rejection", run=b, near=project, now=T0 + 6, reason="too plain")
    assert runs.log("iteration", near=project, now=T0 + 7, n=2, hard_fail_count=0)["run"] == b
    again = runs.log("accept", near=project, now=T0 + 10)
    assert again["iterations_to_accept"] == 2 and again["wall_clock_s"] == 9
    assert runs.log("tokens", near=project, now=T0 + 500, input=5, output=1)["run"] == b  # the latest run, closed or not
    runs.log("tokens", run=a, near=project, now=T0 + 600, input=7, output=2)
    stats = runs.run_stats(project)
    assert stats["by_task"]["chest"]["median_user_rejections"] == 1
    barrel = stats["by_task"]["barrel"]
    assert barrel["accepted"] == 0 and barrel["median_tokens_input"] == 7
    assert barrel["median_wall_clock_s"] == 5  # tokens read later don't stretch the run


def test_bad_events_are_refused(project):
    with pytest.raises(ValueError, match="unknown event"):
        runs.log("finish", near=project)
    with pytest.raises(ValueError, match="task id or an asset"):
        runs.log("run_start", near=project)
    run = runs.log("run_start", near=project, task="sword")["run"]
    with pytest.raises(ValueError, match="already exists"):
        runs.log("run_start", run=run, near=project, task="sword")
    with pytest.raises(ValueError, match="unknown fields"):
        runs.log("iteration", near=project, n=1, hard_fail_count=0, reason="oops")
    with pytest.raises(ValueError, match="missing"):
        runs.log("iteration", near=project, n=1)
    with pytest.raises(ValueError, match="no run"):
        runs.log("accept", run="nope", near=project)


def test_findings_and_values_parse():
    assert runs.parse_findings("contact_gap, floating_part x2; non_manifold:3") == {
        "contact_gap": 1, "floating_part": 2, "non_manifold": 3}
    assert runs.parse_findings("box2, grip x 2") == {"box2": 1, "grip": 2}
    assert runs.parse_findings(["grip", "grip", "lint"]) == {"grip": 2, "lint": 1}
    assert runs.parse_findings('{"grip": 2}') == {"grip": 2}
    assert runs.parse_values("tris=3120, ok=true, top1=dire wolf") == {"tris": 3120, "ok": True, "top1": "dire wolf"}
    assert runs.parse_values("top1=wolf, then dog; iou=0.82") == {"top1": "wolf, then dog", "iou": 0.82}


def _synthetic(project):
    """3 knight runs (hard pass at 3, at 2, never) and 1 barrel run (hard pass at 1)."""
    def run(task, t, fails, close, *, judge=0, rejections=(), tokens=(), values=None):
        r = runs.log("run_start", near=project, now=t, task=task, asset=f"{task}.blend", label="v0.4")["run"]
        for i, f in enumerate(fails, 1):
            runs.log("iteration", run=r, near=project, now=t + 10 * i, n=i, hard_fail_count=f,
                     findings=["floating_parts"] * min(f, 1) + ["grip"] * max(0, f - 1))
        for _ in range(judge):
            runs.log("judge_round", run=r, near=project, now=t + 50, kind="blind_read", questions=1, failed=0)
        for check in rejections:
            runs.log("validator_rejection", run=r, near=project, now=t + 55, check=check)
        for i, o in tokens:
            runs.log("tokens", run=r, near=project, now=t + 60, input=i, output=o)
        runs.log(close[0], run=r, near=project, now=t + close[1], values=values)

    run("knight", T0, [3, 1, 0], ("accept", 600), judge=2, rejections=["mesh_lint"], tokens=[(1000, 200), (500, 100)],
        values={"blind_read_top1": "knight", "tris": 30000})
    run("knight", T0 + 1000, [2, 0], ("accept", 300), judge=1, tokens=[(3000, 500)],
        values={"blind_read_top1": "soldier", "tris": 36000})
    run("knight", T0 + 2000, [4, 4], ("abandon", 900), rejections=["grip_check", "mesh_lint"])
    run("barrel", T0 + 3000, [0], ("accept", 120))


def test_run_stats_numbers(project):
    _synthetic(project)
    s = runs.run_stats(project)
    o = s["overall"]
    assert (o["tasks"], o["runs"], o["accepted"], o["open_runs"]) == (2, 4, 3, 0)
    assert o["median_iterations_to_hard_pass"] == 2.5  # 1, 2, 3 and a never (worst)
    assert o["median_wall_clock_s"] == 450  # 120, 300, 600, 900
    assert o["median_tokens_input"] == 2250 and o["median_tokens_output"] == 400  # only runs that logged tokens
    k = s["by_task"]["knight"]
    assert (k["runs"], k["accepted"]) == (3, 2)
    assert k["median_iterations_to_hard_pass"] == 3  # 2, 3, never
    assert k["median_iterations_to_accept"] == 3
    assert k["median_hard_fail_count_first"] == 3
    assert k["median_judge_rounds"] == 1 and k["median_validator_rejections"] == 1
    assert k["median_wall_clock_s"] == 600
    assert k["failure_histogram"] == {"grip": 9, "floating_parts": 5}
    assert k["rejection_histogram"] == {"mesh_lint": 2, "grip_check": 1}
    assert k["values"] == {"blind_read_top1": {"knight": 1, "soldier": 1}, "tris": 33000}
    b = s["by_task"]["barrel"]
    assert b["median_iterations_to_hard_pass"] == 1 and b["median_tokens_input"] is None
    assert runs.run_stats(project, task="barrel")["overall"]["runs"] == 1
    assert runs.run_stats(project, label="v0.5")["overall"]["runs"] == 0


def test_never_passing_task_has_no_median():
    r = {"iterations_to_hard_pass": None, "iterations_to_accept": None, "hard_fail_count_first": 4, "judge_rounds": 0,
         "validator_rejections": 0, "user_rejections": 0, "wall_clock_s": 10, "tokens_input": None,
         "tokens_output": None, "accepted": False, "failures": {}, "rejections": {}, "values": {}}
    agg = runs.aggregate([r, dict(r, iterations_to_hard_pass=2)])
    assert agg["median_iterations_to_hard_pass"] is None  # (2 + never) / 2 is still never


def test_summarize_writes_numbers_only(project, tmp_path):
    _synthetic(project)
    out = tmp_path / "results" / "v0.4.json"
    path, data = runs.summarize("v0.4", project, out=out)
    assert path == out and json.loads(out.read_text(encoding="utf-8")) == data
    assert data["suite"]["tasks"] == 24 and len(data["suite"]["hash"]) == 12
    assert set(data["by_task"]) == {"knight", "barrel"} and len(data["missing_tasks"]) == 22
    assert data["overall"]["median_iterations_to_hard_pass"] == 2.5
    assert ".blend" not in out.read_text(encoding="utf-8")  # no asset paths
    assert runs.summarize("v0.5", project, out=tmp_path / "x.json")[1]["overall"]["runs"] == 0
    assert runs.summarize("v0.5", project, all_runs=True, out=tmp_path / "x.json")[1]["overall"]["runs"] == 4


def test_compare_uses_a_sign_test(tmp_path):
    ids = [f"t{i:02}" for i in range(24)]
    base = {"label": "v0.4", "by_task": {t: {"median_iterations_to_hard_pass": 4} for t in ids}}
    new = {"label": "s3", "by_task": {t: {"median_iterations_to_hard_pass": 2 if i < 17 else 6} for i, t in enumerate(ids)}}
    new["by_task"]["t23"]["median_iterations_to_hard_pass"] = None  # never passed: worse than 4
    for name, data in (("v0.4", base), ("s3", new)):
        (tmp_path / "results").mkdir(exist_ok=True)
        (tmp_path / "results" / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    c = runs.compare("v0.4", "s3", evals=tmp_path)
    assert (c["tasks_compared"], c["lower_on"], c["higher_on"], c["ties"]) == (24, 17, 7, 0)
    assert c["p_sign_one_sided"] == pytest.approx(0.032, abs=0.001)  # the S3 exit's p ≈ 0.03
    assert runs.sign_test(0, 0) == 1.0


def test_transcript_tokens(tmp_path):
    session = tmp_path / "sess.jsonl"
    msg = {"id": "msg_1", "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100,
                                    "cache_read_input_tokens": 1000, "output_tokens": 50}}
    lines = [{"type": "user", "message": {"role": "user", "content": "hi"}},
             {"type": "assistant", "message": msg}, {"type": "assistant", "message": msg},  # one message, two blocks
             {"type": "assistant", "message": {"id": "msg_2", "usage": {"input_tokens": 5, "output_tokens": 7}}}]
    session.write_text("\n".join(map(json.dumps, lines)) + "\nnot json\n", encoding="utf-8")
    sub = tmp_path / "sess" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-1.jsonl").write_text(json.dumps(
        {"message": {"id": "msg_3", "usage": {"input_tokens": 1, "output_tokens": 2}}}), encoding="utf-8")
    assert runs.transcript_tokens(session) == {"input": 1115, "output": 57, "messages": 2}
    assert runs.transcript_tokens(tmp_path) == {"input": 1116, "output": 59, "messages": 3}


def test_cli_run_log_and_stats(project, capsys):
    d = str(project)
    assert cli(["run-log", "run_start", "task=chair", "asset=chair.blend", "label=v0.4", "--dir", d]) == 0
    assert cli(["run-log", "iteration", "n=1", "hard_fail_count=0", "findings=floating_parts", "--dir", d]) == 0
    assert cli(["run-log", "accept", "values=tris=4800", "--dir", d]) == 0
    capsys.readouterr()
    assert cli(["run-stats", "--dir", d]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["by_task"]["chair"]["median_iterations_to_hard_pass"] == 1
    assert stats["by_task"]["chair"]["values"] == {"tris": 4800}


def test_cli_keeps_numeric_looking_labels_as_typed(project, capsys):
    d = str(project)
    assert cli(["run-log", "run_start", "task=007", "label=1.10", "--dir", d]) == 0
    start = json.loads(capsys.readouterr().out)
    assert (start["task"], start["label"]) == ("007", "1.10")
    assert cli(["run-log", "iteration", "n=2", "hard_fail_count=1", "--dir", d]) == 0
    assert json.loads(capsys.readouterr().out)["n"] == 2  # the schema still makes numbers of numeric fields
    assert runs.run_stats(project, label="1.10")["overall"]["runs"] == 1


def test_other_jsonl_files_at_the_project_root_do_not_hide_the_runs(project):
    runs.log("run_start", near=project, now=T0, task="wolf")
    (project / "dialogue.jsonl").write_text('{"line": "hello"}\n', encoding="utf-8")
    assert runs.run_stats(project)["overall"]["runs"] == 1
    assert len(runs.read_events(project / ".opus" / "runs")) == 1  # the runs folder itself still works


async def _mcp(tmp_path, calls):
    from mcp import ClientSession, StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "opus.mcp_server"],
                                   env={**os.environ, "OPUS_PROJECT_DIR": str(tmp_path)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            return tools, [await session.call_tool(name, args) for name, args in calls]


def test_run_tools_over_mcp(project):
    tools, results = anyio.run(_mcp, project, [
        ("run_log", {"event": "run_start", "task": "axe", "asset": "axe.blend", "label": "v0.4"}),
        ("run_log", {"event": "iteration", "n": 1, "tier": "T2", "hard_fail_count": 1, "findings": "grip"}),
        ("run_log", {"event": "iteration", "n": 2, "hard_fail_count": 0}),
        ("run_log", {"event": "tokens", "input_tokens": 900, "output_tokens": 90}),
        ("run_log", {"event": "accept", "values": "grip_verdict=good grip; tris=540"}),
        ("run_log", {"event": "iteration", "n": 3, "hard_fail_count": 0}),
        ("run_stats", {}),
    ])
    assert {"run_log", "run_stats"} <= tools
    for r in results[:5]:
        assert not r.is_error, r.content[0].text
    assert json.loads(results[4].content[0].text)["values"] == {"grip_verdict": "good grip", "tris": 540}
    assert results[5].is_error and "no open run" in results[5].content[0].text
    stats = json.loads(results[6].content[0].text)
    axe = stats["by_task"]["axe"]
    assert (axe["median_iterations_to_hard_pass"], axe["median_tokens_input"]) == (2, 900)
    assert axe["failure_histogram"] == {"grip": 1}
