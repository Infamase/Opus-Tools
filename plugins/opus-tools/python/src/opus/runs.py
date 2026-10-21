"""Run ledger and eval suite: how many tries an asset takes, measured.

Every asset run appends events to ``<project>/.opus/runs/<date>.jsonl``, one JSON object per
line: run_start, iteration (one round of checks), validator_rejection, judge_round,
user_rejection, tokens, accept, abandon and grade (an independent grader's verdict on the
closed run). ``run_stats`` turns them into the numbers the overhaul is judged by
(docs/OVERHAUL.md §1 and §2.6): iterations to a hard pass, judge rounds, wall-clock, tokens and
a histogram of the checks that failed. A graded run counts as accepted only when its last grade
says so.

The eval suite is a fixed set of 24 asset tasks in ``evals/tasks/*.yaml`` at the repo root.
``summarize`` writes one run set's numbers to ``evals/results/<label>.json``, so every later
sprint is compared with the v0.4 baseline. Asset outputs are never committed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import time
from pathlib import Path

import yaml

from opus import camera as _camera
from opus.paths import opus_dir, plugin_root, project_base

# ---------------------------------------------------------------- run ledger

EVENTS: dict[str, dict[str, type]] = {
    "run_start": {"task": str, "asset": str, "label": str, "model": str, "tool_version": str},
    "iteration": {"n": int, "tier": str, "hard_fail_count": int, "findings": dict},
    "validator_rejection": {"check": str, "reason": str},
    "judge_round": {"kind": str, "questions": int, "failed": int},
    "user_rejection": {"reason": str},
    "tokens": {"input": int, "output": int},
    "accept": {"iterations_to_accept": int, "wall_clock_s": float, "values": dict},
    "abandon": {"reason": str, "values": dict},
    "grade": {"accepted": bool, "failed": list, "note": str},
}
REQUIRED = {"iteration": ("n", "hard_fail_count"), "tokens": ("input", "output"), "grade": ("accepted",)}
CLOSING = ("accept", "abandon")
# arrive after a run closed: usage is read at the end, the grader and the user judge last
LATE = ("tokens", "user_rejection", "grade")
NAMED = ("grade",)  # a grader works from a run id, never from "the latest run"


def runs_dir(near=None) -> Path:
    d = opus_dir(project_base(near)) / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tool_version() -> str:
    """The installed plugin's version (plugin.json), else the Python package's."""
    try:
        return json.loads((plugin_root() / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        from opus import __version__

        return __version__


NO_FINDINGS = ("none", "0", "-", "")
_CHECK_ID = re.compile(r"[A-Za-z0-9_.:/-]+")


def _check_id(name) -> str:
    name = str(name).strip()
    if not _CHECK_ID.fullmatch(name):
        raise ValueError(f"findings are failing check ids such as 'floating_parts, grip x2', not prose (got {name!r})")
    return name


def parse_checks(checks) -> list[str]:
    """Failing check ids as a list without repeats, from the same inputs as ``parse_findings``."""
    if _num(checks) and checks == 0:
        return []
    if _num(checks):
        raise ValueError(f"failed lists the failing check ids, such as 'blind_read, lint', not a count (got {checks!r})")
    return list(parse_findings(checks))


def parse_findings(findings) -> dict[str, int]:
    """Failing checks as {check: count}, from a dict, a list of names, JSON, or text such as
    "contact_gap, floating_part x2, non_manifold:3". "none", "0" and "-" mean no failures.
    Anything that is not a check id (prose) is refused."""
    if not findings:
        return {}
    if isinstance(findings, str):
        text = findings.strip()
        if text.lower() in NO_FINDINGS:
            return {}
        if text.startswith(("{", "[")):
            return parse_findings(json.loads(text))
        out: dict[str, int] = {}
        for item in re.split(r"[,;\n]+", text):
            m = re.fullmatch(r"\s*(.+?)(?:\s+[x×]\s*(\d+)|\s*:\s*(\d+))?\s*", item)
            if m and item.strip():
                name = _check_id(m.group(1))
                out[name] = out.get(name, 0) + int(m.group(2) or m.group(3) or 1)
        return out
    if isinstance(findings, dict):
        return {_check_id(k): int(v) for k, v in findings.items()}
    out = {}
    for name in map(_check_id, findings):
        out[name] = out.get(name, 0) + 1
    return out


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    text = str(v).strip().lower()
    if text in ("true", "yes", "y", "1"):
        return True
    if text in ("false", "no", "n", "0"):
        return False
    raise ValueError(v)


def _scalar(v: str):
    for kind in (int, float):
        try:
            return kind(v)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(v.lower(), v)


def parse_values(values) -> dict:
    """A task's score fields as {name: value}, from a dict, JSON, or "tris=3120; blind_read_top1=wolf"."""
    if not values:
        return {}
    if isinstance(values, dict):
        return {str(k): v for k, v in values.items()}
    text = str(values).strip()
    if text.startswith("{"):
        return parse_values(json.loads(text))
    out = {}
    for item in re.split(r"[;\n]+" if re.search(r"[;\n]", text) else ",", text):
        k, sep, v = item.partition("=") if "=" in item else item.partition(":")
        if sep and k.strip():
            out[k.strip()] = _scalar(v.strip())
    return out


_KINDS = {str: "text", int: "integer", float: "number", bool: "true or false", dict: "name=value pairs",
          list: "failing check ids"}
_MUST = {int: "an integer", float: "a number", bool: "true or false"}


def _schema(event: str) -> str:
    """The event's fields and their kinds, for error messages."""
    return ", ".join(f"{k} ({'failing check ids' if k == 'findings' else _KINDS[t]})" for k, t in EVENTS[event].items())


def _clean(event: str, fields: dict) -> dict:
    allowed = EVENTS[event]
    data = {k: v for k, v in fields.items() if v is not None and v != ""}
    unknown = set(data) - set(allowed)
    if unknown:
        raise ValueError(f"{event}: unknown fields {sorted(unknown)}; allowed: {sorted(allowed)}")
    missing = [k for k in REQUIRED.get(event, ()) if k not in data]
    if missing:
        raise ValueError(f"{event}: missing {missing}")
    for k, kind in allowed.items():
        if k not in data:
            continue
        v = data[k]
        try:
            if kind is dict:
                data[k] = parse_values(v) if k == "values" else parse_findings(v)
            elif kind is list:
                data[k] = parse_checks(v)
            elif kind is bool:
                data[k] = _bool(v)
            elif kind is int:
                data[k] = int(v)
            elif kind is float:
                data[k] = round(float(v), 3)
            else:
                data[k] = str(v)
        except (TypeError, ValueError) as e:
            if kind in (dict, list):
                raise ValueError(f"{event}: {e}") from None
            raise ValueError(f"{event}: {k} must be {_MUST[kind]} (got {v!r}); fields: {_schema(event)}") from None
    return data


def _sources(src=None) -> list[Path]:
    """The ledger files behind ``src``: a .jsonl file, a project (its .opus/runs, even when
    other .jsonl files sit at its root), or a folder of ledger files."""
    p = Path(src or os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()).expanduser().resolve()
    if p.is_file():
        return [p]
    if (p / ".opus" / "runs").is_dir():
        p = p / ".opus" / "runs"
    if p.is_dir() and (any(p.glob("*.jsonl")) or (p.name == "runs" and p.parent.name == ".opus")):
        return sorted(p.glob("*.jsonl"))
    d = project_base(p) / ".opus" / "runs"
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


def read_events(src=None) -> list[dict]:
    """Every event behind ``src`` (see ``_sources``), oldest first. Unreadable lines are skipped."""
    events = []
    for path in _sources(src):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("event") in EVENTS and e.get("run"):
                events.append(e)
    return sorted(events, key=lambda e: e.get("ts", 0))


def _group(events: list[dict]) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {}
    for e in events:
        runs.setdefault(e["run"], []).append(e)
    return runs


def _is_open(run_events: list[dict]) -> bool:
    """A run closes on accept or abandon; a user rejection after an accept reopens it."""
    state = [e["event"] for e in run_events if e["event"] in CLOSING + ("user_rejection",)]
    return not state or state[-1] == "user_rejection"


def _which_run(runs: dict[str, list[dict]], open_runs: list[str]) -> str:
    """Why an event without a run id can't pick one: the open runs, newest first."""
    rows = []
    for r in sorted(open_runs, key=lambda r: runs[r][0].get("ts", 0), reverse=True):
        start = next((e for e in runs[r] if e["event"] == "run_start"), runs[r][0])
        what = f"task {start['task']}" if start.get("task") else f"asset {start.get('asset') or '?'}"
        rows.append(f"{r} ({what}, started {time.strftime('%H:%M', time.localtime(start.get('ts', 0)))})")
    return (f"{len(rows)} runs are open: {', '.join(rows)}; pass run=<id> (--run <id> on the command line), "
            "the id run_start returned")


def log(event: str, run: str = "", near=None, now: float | None = None, **fields) -> dict:
    """Append one event to the project's ledger and return it.

    run_start opens a run and names it (or uses ``run``). Other events go to ``run`` or, when
    empty, to the one open run (tokens and user_rejection: the most recent run, open or not).
    With several runs open, ``run`` is required: parallel sessions share one ledger. A grade
    (an independent grader's verdict, logged after the run closed) needs ``run`` whenever the
    ledger holds more than one run. accept fills in iterations_to_accept and wall_clock_s from
    the run unless given.
    """
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r}; known: {sorted(EVENTS)}")
    data = _clean(event, fields)
    folder = runs_dir(near)
    ts = time.time() if now is None else float(now)
    runs = _group(read_events(folder))
    if event == "run_start":
        if not (data.get("task") or data.get("asset")):
            raise ValueError("run_start needs a task id or an asset")
        data.setdefault("tool_version", tool_version())
        if not run:
            stem = re.sub(r"[^A-Za-z0-9_-]+", "_", data.get("task") or Path(data["asset"]).stem).strip("_")[:40]
            run = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(ts))}-{stem or 'run'}"
            base, k = run, 1
            while run in runs:
                k += 1
                run = f"{base}-{k}"
        elif run in runs:
            raise ValueError(f"run {run!r} already exists")
    else:
        if not run:
            candidates = [r for r, evs in runs.items() if event in LATE or _is_open(evs)]
            if not candidates:
                raise ValueError("no open run in this project: log run_start first")
            if event in NAMED and len(candidates) > 1:
                raise ValueError(f"{event}: {len(candidates)} runs in this ledger; pass run=<id> (--run <id> on the "
                                 "command line), the id of the run being graded")
            if event not in LATE and len(candidates) > 1:
                raise ValueError(_which_run(runs, candidates))
            run = max(candidates, key=lambda r: runs[r][0].get("ts", 0))
        elif run not in runs:
            raise ValueError(f"no run {run!r} in {folder}")
        if event not in LATE and not _is_open(runs[run]):
            raise ValueError(f"run {run!r} is closed; start a new run")
        if event == "accept":
            its = [e for e in runs[run] if e["event"] == "iteration"]
            data.setdefault("iterations_to_accept", max((e.get("n", 0) for e in its), default=0))
            data.setdefault("wall_clock_s", round(ts - runs[run][0].get("ts", ts), 3))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
    entry = {"event": event, "run": run, "t": stamp, "ts": round(ts, 3), **data}
    with open(folder / f"{time.strftime('%Y-%m-%d', time.localtime(ts))}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


PROSE = "(prose)"


def _failing(findings: dict) -> dict[str, int]:
    """One iteration's findings as check ids. Ledgers written before v0.4.1, which refuses prose,
    can hold "none" (no failure) and prose fragments; these count as one PROSE entry each."""
    out: dict[str, int] = {}
    for k, v in (findings or {}).items():
        name = str(k).strip()
        if name.lower() in NO_FINDINGS:
            continue
        name = name if _CHECK_ID.fullmatch(name) else PROSE
        out[name] = out.get(name, 0) + v
    return out


def summarize_run(evs: list[dict]) -> dict:
    """One run's numbers. Iterations to a hard pass = the first check round with no hard failure.
    A run is accepted when it closed with accept and, if it was graded, its last grade accepts it;
    the checks that grade failed count in its failures."""
    start = next((e for e in evs if e["event"] == "run_start"), evs[0])
    its = [e for e in evs if e["event"] == "iteration"]
    passed = next((e for e in its if e.get("hard_fail_count") == 0), None)
    closes = [e for e in evs if e["event"] in CLOSING]
    last = closes[-1] if closes and not _is_open(evs) else None
    toks = [e for e in evs if e["event"] == "tokens"]
    grade = next((e for e in reversed(evs) if e["event"] == "grade"), None)
    grade_failed = list(grade.get("failed") or []) if grade else []
    failures: dict[str, int] = {}
    for e in its:
        for k, v in _failing(e.get("findings")).items():
            failures[k] = failures.get(k, 0) + v
    for k in grade_failed:
        failures[k] = failures.get(k, 0) + 1
    rejections: dict[str, int] = {}
    for e in evs:
        if e["event"] == "validator_rejection":
            k = e.get("check") or "?"
            rejections[k] = rejections.get(k, 0) + 1
    self_accepted = last is not None and last["event"] == "accept"
    accepted = self_accepted and (grade is None or grade.get("accepted") is True)
    end = max(e.get("ts", 0) for e in evs if e["event"] not in LATE or e is start)
    return {
        "run": start["run"],
        "task": start.get("task", ""),
        "asset": start.get("asset", ""),
        "label": start.get("label", ""),
        "tool_version": start.get("tool_version", ""),
        "accepted": accepted,
        "self_accepted": self_accepted,
        "graded": grade is not None,
        "grade_failed": grade_failed,
        "abandoned": last is not None and last["event"] == "abandon",
        "open": _is_open(evs),
        "iterations": len(its),
        "iterations_to_hard_pass": passed.get("n", its.index(passed) + 1) if passed else None,
        "iterations_to_accept": last.get("iterations_to_accept") if accepted else None,
        "hard_fail_count_first": its[0].get("hard_fail_count") if its else None,
        "judge_rounds": sum(e["event"] == "judge_round" for e in evs),
        "validator_rejections": sum(rejections.values()),
        "user_rejections": sum(e["event"] == "user_rejection" for e in evs),
        "wall_clock_s": last.get("wall_clock_s") if self_accepted else round(end - start.get("ts", 0), 3),
        "tokens_input": sum(e.get("input", 0) for e in toks) if toks else None,
        "tokens_output": sum(e.get("output", 0) for e in toks) if toks else None,
        "failures": failures,
        "rejections": rejections,
        "model": start.get("model", ""),
        "values": last.get("values", {}) if last else {},
    }


def _median(values, missing_is_worst: bool = False):
    """Median, ignoring missing values; or counting them as worse than any (a run that never
    reached the point), in which case a median that lands on one is reported as None."""
    vals = [math.inf if v is None else v for v in values] if missing_is_worst else [v for v in values if v is not None]
    if not vals:
        return None
    m = statistics.median(vals)
    return None if math.isinf(m) else round(m, 2)


def _histogram(dicts) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _values(dicts) -> dict:
    """Score fields over runs: the median of numbers, a count per answer for anything else."""
    seen: dict[str, list] = {}
    for d in dicts:
        for k, v in d.items():
            seen.setdefault(k, []).append(v)
    out = {}
    for k, vs in sorted(seen.items()):
        if all(_num(v) for v in vs):
            out[k] = _median(vs)
        else:
            out[k] = _histogram({str(v).lower() if isinstance(v, bool) else str(v): 1} for v in vs)
    return out


def aggregate(runs: list[dict]) -> dict:
    """Medians over runs; runs that never reached a hard pass or an accept count as worst.
    accepted counts the graders' verdict where there is one, self_accepted the builders' own."""
    return {
        "runs": len(runs),
        "accepted": sum(r["accepted"] for r in runs),
        "self_accepted": sum(r.get("self_accepted", r["accepted"]) for r in runs),
        "graded": sum(r.get("graded", False) for r in runs),
        "median_iterations_to_hard_pass": _median([r["iterations_to_hard_pass"] for r in runs], True),
        "median_iterations_to_accept": _median([r["iterations_to_accept"] for r in runs], True),
        "median_hard_fail_count_first": _median([r["hard_fail_count_first"] for r in runs]),
        "median_judge_rounds": _median([r["judge_rounds"] for r in runs]),
        "median_validator_rejections": _median([r["validator_rejections"] for r in runs]),
        "median_user_rejections": _median([r["user_rejections"] for r in runs]),
        "median_wall_clock_s": _median([r["wall_clock_s"] for r in runs]),
        "median_tokens_input": _median([r["tokens_input"] for r in runs]),
        "median_tokens_output": _median([r["tokens_output"] for r in runs]),
        "failure_histogram": _histogram(r["failures"] for r in runs),
        "grade_failure_histogram": _histogram({k: 1 for k in r.get("grade_failed", ())} for r in runs),
        "rejection_histogram": _histogram(r["rejections"] for r in runs),
        "values": _values(r["values"] for r in runs),
    }


def run_summaries(src=None, task: str = "", label: str = "") -> list[dict]:
    runs = [summarize_run(evs) for evs in _group(read_events(src)).values()]
    return [r for r in runs if (not task or r["task"] == task) and (not label or r["label"] == label)]


def run_stats(src=None, task: str = "", label: str = "") -> dict:
    """Per task (or asset, for runs outside the eval suite) and overall: median iterations to
    a hard pass and to accept, judge rounds, validator and user rejections, wall-clock, tokens
    where logged, and a histogram of the checks that failed."""
    runs = run_summaries(src, task, label)
    by_task: dict[str, list[dict]] = {}
    for r in runs:
        by_task.setdefault(r["task"] or r["asset"], []).append(r)
    return {
        "overall": {"tasks": len(by_task), "open_runs": sum(r["open"] for r in runs), **aggregate(runs)},
        "by_task": {k: aggregate(v) for k, v in sorted(by_task.items())},
    }


def transcript_tokens(*paths) -> dict:
    """Token use in Claude Code session transcripts (``~/.claude/projects/<project>/*.jsonl``;
    folders are searched, so a session's subagent transcripts count too). input adds fresh,
    cache-write and cache-read input tokens. Each API message is counted once."""
    usage: dict = {}
    files: list[Path] = []
    for p in (Path(x).expanduser() for x in paths):
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                usage[msg.get("id") or f"{f}:{i}"] = msg["usage"]
    fresh = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return {
        "input": sum(int(u.get(k) or 0) for u in usage.values() for k in fresh),
        "output": sum(int(u.get("output_tokens") or 0) for u in usage.values()),
        "messages": len(usage),
    }


# ---------------------------------------------------------------- eval suite

SUITE_SIZE = 24
REGRESSION = ("knight", "goblin", "wolf", "dragon", "chest", "barrel", "house", "sword")  # §9, S3
CATEGORIES = ("character", "clothing", "armor", "weapon", "prop", "building", "creature", "landscape", "foliage", "animation")
STYLES = ("lowpoly", "hd", "pixel")
ENGINES = ("unreal", "godot", "unity")
# camera profile ids are opus.camera's presets plus the first-person view-model camera
CAMERAS = (*_camera.PRESETS, "viewmodel")
ORTHO_CAMERAS = tuple(n for n, p in _camera.PRESETS.items() if p.projection == "ortho")
# what the 16 category tasks must cover between them (§9, S0a), by category
COVERAGE = {
    "character": ("hd_human", "stylized", "lowpoly", "chibi"),
    "weapon": ("first_person", "two_handed"),
    "creature": ("quadruped", "flyer"),
    "animation": ("walk_cycle", "quadruped_trot", "sword_attack", "prop_articulation"),
}
# checks use v0.4 tools only; a probe is a short measuring script for what no tool covers yet
METRICS: dict[str, tuple | None] = {
    "mesh_lint": ("errors", "findings", "tris"),
    "model_report": ("floating_parts", "missing_contacts", "penetrations", "on_floor", "com_over_footprint", "symmetric",
                     "rig_style", "width_m", "length_m", "height_m", "longest_m"),
    "proportion_check": ("closest_canon", "unintended_findings"),
    "reference_match": ("iou",),
    "readability_check": ("defining_under_floor", "subject_px"),
    "blind_read_sheet": ("top1_names_subject",),
    "grip_check": ("verdict", "body_clipping_verts"),
    "sprite_inspect": ("semi_transparent_pixels", "strays", "off_palette_pixels", "color_count", "jaggy_elbows",
                       "colors_not_in_every_frame"),
    "art_director": ("checklist_no",),
    "probe": None,
}
# uncalibrated heuristics stay soft until defect injection and clean fixtures calibrate them
# (§2.5): fixed-tolerance proportions (percentile-based in S1) and the readability floors
SOFT_ONLY = {("proportion_check", "unintended_findings"), ("readability_check", "defining_under_floor"),
             ("readability_check", "subject_px")}
CAMERA_CHECKS = ("readability_check", "blind_read_sheet")  # their numbers depend on the camera
OPS = ("==", "!=", "<=", ">=", "<", ">", "between", "in")
CLASSES = ("hard", "soft", "report")
SCORE_FIELDS = ("accepted", "iterations_to_hard_pass", "iterations_to_accept", "hard_fail_count_first",
                "validator_rejections", "judge_rounds", "user_rejections", "wall_clock_s", "tokens_input", "tokens_output")
REF_LICENSES = ("cc0", "public domain")
TASK_FIELDS = ("id", "title", "category", "brief", "style", "engine", "camera", "references", "budgets", "accept", "score")
TASK_OPTIONAL = ("regression", "covers", "caps")
# a stray key usually means an unquoted comma split a value inside {...}
CHECK_FIELDS = ("id", "tool", "args", "metric", "op", "value", "class", "note", "measure", "names", "questions")


def evals_dir() -> Path:
    """$OPUS_EVALS_DIR, else ``evals/`` at the repo root. A marketplace install carries only the
    plugin folder, so point OPUS_EVALS_DIR at a clone's ``evals`` there."""
    env = os.environ.get("OPUS_EVALS_DIR", "").strip()
    return Path(env).expanduser().resolve() if env else plugin_root().parents[1] / "evals"


def load_tasks(folder=None) -> list[dict]:
    """Every task spec in ``<evals>/tasks``, regression subjects first, each with its ``_file``."""
    folder = Path(folder) if folder else evals_dir()
    tasks = []
    for path in sorted((folder / "tasks").glob("*.yaml")):
        try:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ValueError(f"{path.name}: {e}") from e
        spec = spec if isinstance(spec, dict) else {"_invalid": True}
        spec["_file"] = str(path)
        tasks.append(spec)

    def order(t):
        reg = t.get("id") in REGRESSION
        cat = CATEGORIES.index(t["category"]) if t.get("category") in CATEGORIES else len(CATEGORIES)
        return (not reg, REGRESSION.index(t["id"]) if reg else cat, str(t.get("id")))

    return sorted(tasks, key=order)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_errors(c, where: str) -> list[str]:
    if not isinstance(c, dict):
        return [f"{where}: a check must be a mapping"]
    errs = [f"{where}: unknown key {k!r} (quote values that contain commas)" for k in c if k not in CHECK_FIELDS]
    tool, metric, op = c.get("tool"), c.get("metric"), c.get("op")
    if not c.get("id"):
        errs.append(f"{where}: no id")
    if tool not in METRICS:
        errs.append(f"{where}: tool {tool!r} is not a v0.4 check; use one of {sorted(METRICS)}")
    elif METRICS[tool] is not None and metric not in METRICS[tool]:
        errs.append(f"{where}: {tool} has no metric {metric!r}; known: {list(METRICS[tool])}")
    if not metric:
        errs.append(f"{where}: no metric")
    if op not in OPS:
        errs.append(f"{where}: op {op!r} not in {OPS}")
    if "value" not in c:
        errs.append(f"{where}: no value")
    v = c.get("value")
    if op == "between" and not (isinstance(v, list) and len(v) == 2 and all(map(_num, v)) and v[0] <= v[1]):
        errs.append(f"{where}: between needs [low, high]")
    if op == "in" and not (isinstance(v, list) and v):
        errs.append(f"{where}: in needs a list")
    if op in ("<=", ">=", "<", ">") and not _num(v):
        errs.append(f"{where}: {op} needs a number")
    if c.get("class") not in CLASSES:
        errs.append(f"{where}: class must be one of {CLASSES}")
    elif c["class"] == "hard" and (tool, metric) in SOFT_ONLY:
        errs.append(f"{where}: {tool} {metric} is an uncalibrated heuristic, so its class is soft (§2.5)")
    if tool == "probe" and not c.get("measure"):
        errs.append(f"{where}: a probe says how it measures (measure)")
    if tool == "blind_read_sheet" and not (isinstance(c.get("names"), list) and c["names"]):
        errs.append(f"{where}: a blind read lists the accepted names (names)")
    if tool == "art_director" and not (isinstance(c.get("questions"), list) and 2 <= len(c["questions"]) <= 5):
        errs.append(f"{where}: a checklist asks 2-5 yes/no questions (questions)")
    return errs


def _default_camera() -> str:
    """The camera a check without one runs at in an eval project (``project_bible init`` in an
    empty folder: no engine marker, no camera.profile)."""
    from opus.bible import camera_profile

    return camera_profile({}, "").name


def _camera_errors(c, profile: str, where: str) -> list[str]:
    """A check whose numbers depend on the camera must run at the task's camera. A first-person
    (viewmodel) task may also check its world model at a third-person camera, named in args."""
    if not isinstance(c, dict) or c.get("tool") not in CAMERA_CHECKS:
        return []
    args = c.get("args") if isinstance(c.get("args"), dict) else {}
    given = args.get("camera")
    used = given or _default_camera()
    if used == profile or (profile == "viewmodel" and given in CAMERAS):
        return []
    how = f"args.camera {given!r}" if given else f"no args.camera, so the tools use {used!r}"
    return [f"{where}: {c['tool']} must run at the task's camera {profile!r} ({how}); set args.camera: {profile}"]


def validate_task(spec: dict) -> list[str]:
    """Problems with one task spec (empty when it is valid)."""
    name = Path(spec.get("_file", "?")).name
    if spec.get("_invalid"):
        return [f"{name}: not a mapping"]
    errs = [f"{name}: missing {k}" for k in TASK_FIELDS if k not in spec]
    errs += [f"{name}: unknown key {k!r}" for k in spec if k not in TASK_FIELDS + TASK_OPTIONAL + ("_file",)]
    tid = spec.get("id")
    if tid is not None and (not re.fullmatch(r"[a-z][a-z0-9_]*", str(tid)) or Path(name).stem != tid):
        errs.append(f"{name}: id {tid!r} must be lower_snake_case and match the file name")
    for k in ("title", "brief"):
        if k in spec and not (isinstance(spec[k], str) and spec[k].strip()):
            errs.append(f"{name}: {k} is empty")
    if "category" in spec and spec["category"] not in CATEGORIES:
        errs.append(f"{name}: category {spec['category']!r} not in {CATEGORIES}")
    if "style" in spec and spec["style"] not in STYLES:
        errs.append(f"{name}: style {spec['style']!r} not in {STYLES}")
    if "engine" in spec and spec["engine"] not in ENGINES:
        errs.append(f"{name}: engine {spec['engine']!r} not in {ENGINES}")
    if bool(spec.get("regression")) != (tid in REGRESSION):
        errs.append(f"{name}: regression must be true exactly for {REGRESSION}")
    if not isinstance(spec.get("covers", []), list):
        errs.append(f"{name}: covers must be a list")
    cam = spec.get("camera")
    if "camera" in spec:
        if not isinstance(cam, dict) or cam.get("profile") not in CAMERAS:
            errs.append(f"{name}: camera.profile must be one of {CAMERAS}")
        else:
            dist = cam.get("distances_m")
            positive = isinstance(dist, list) and dist and all(_num(d) and d > 0 for d in dist)
            if cam["profile"] not in ORTHO_CAMERAS and not positive:
                errs.append(f"{name}: camera.distances_m needs positive distances")
            if spec.get("style") == "pixel" and not (isinstance(cam.get("sprite_px"), int) and cam["sprite_px"] > 0):
                errs.append(f"{name}: pixel tasks give camera.sprite_px")
    refs = spec.get("references")
    if "references" in spec:
        if not isinstance(refs, list):
            errs.append(f"{name}: references must be a list ([] for none)")
        else:
            for i, r in enumerate(refs):
                if not (isinstance(r, dict) and str(r.get("url", "")).startswith("https://")):
                    errs.append(f"{name}: references[{i}] needs an https url")
                elif str(r.get("license", "")).lower() not in REF_LICENSES:
                    errs.append(f"{name}: references[{i}] must be CC0 or public domain")
    budgets = spec.get("budgets")
    if "budgets" in spec and not (isinstance(budgets, dict) and budgets
                                  and all(_num(v) and v > 0 for v in budgets.values())):
        errs.append(f"{name}: budgets must be positive numbers")
    checks = spec.get("accept")
    if "accept" in spec:
        if not (isinstance(checks, list) and checks):
            errs.append(f"{name}: accept needs checks")
        else:
            for i, c in enumerate(checks):
                errs += _check_errors(c, f"{name}: accept[{i}]")
                if isinstance(cam, dict) and cam.get("profile") in CAMERAS:
                    errs += _camera_errors(c, cam["profile"], f"{name}: accept[{i}]")
            ids = [c.get("id") for c in checks if isinstance(c, dict)]
            if len(ids) != len(set(ids)):
                errs.append(f"{name}: check ids repeat")
            if not any(isinstance(c, dict) and c.get("class") == "hard" for c in checks):
                errs.append(f"{name}: accepted needs at least one hard check")
    if "score" in spec:
        missing = [f for f in SCORE_FIELDS if f not in (spec["score"] or [])]
        if missing:
            errs.append(f"{name}: score is missing {missing}")
    return errs


def validate_suite(tasks: list[dict]) -> list[str]:
    """Every task's problems plus the suite's: 24 tasks, the 8 regression subjects, and the 16
    category tasks covering every category and the subjects §9 names."""
    errs = [e for t in tasks for e in validate_task(t)]
    ids = [t.get("id") for t in tasks]
    if len(tasks) != SUITE_SIZE:
        errs.append(f"suite: {len(tasks)} tasks, expected {SUITE_SIZE}")
    if len(ids) != len(set(ids)):
        errs.append("suite: task ids repeat")
    missing = [r for r in REGRESSION if r not in ids]
    if missing:
        errs.append(f"suite: regression subjects missing: {missing}")
    cat_tasks = [t for t in tasks if t.get("id") not in REGRESSION]
    have = {t.get("category") for t in cat_tasks}
    errs += [f"suite: no category task for {c}" for c in CATEGORIES if c != "building" and c not in have]
    for cat, needed in COVERAGE.items():
        covered = {c for t in cat_tasks if t.get("category") == cat for c in (t.get("covers") or [])}
        errs += [f"suite: no {cat} task covers {n}" for n in needed if n not in covered]
    for field, values in (("style", STYLES), ("engine", ("unreal", "godot"))):
        used = {t.get(field) for t in tasks}
        errs += [f"suite: no task with {field} {v}" for v in values if v not in used]
    return errs


def suite_hash(folder=None) -> str:
    """Short hash of the task specs (line endings normalized, so a Windows checkout matches)."""
    folder = Path(folder) if folder else evals_dir()
    h = hashlib.sha256()
    for path in sorted((folder / "tasks").glob("*.yaml")):
        h.update(path.name.encode())
        h.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def _check_line(c: dict) -> str:
    val = c["value"] if isinstance(c["value"], str) else json.dumps(c["value"])
    args = ", ".join(f"{k}={json.dumps(v)}" for k, v in (c.get("args") or {}).items())
    line = f"  - [{c['class']}] {c['id']}: {c['tool']}({args}) {c['metric']} {c['op']} {val}"
    for key in ("names", "questions"):
        if c.get(key):
            line += f"; {key}: " + " | ".join(c[key])
    for key in ("measure", "note"):
        if c.get(key):
            line += f"; {key}: {c[key]}"
    return line


def task_prompt(spec: dict) -> str:
    """What to paste into a fresh session to run one task: the brief, then the eval protocol."""
    cam = spec["camera"]
    view = f"{cam.get('distances_m')} m" if cam.get("distances_m") else f"{cam.get('sprite_px')} px sprites"
    refs = "".join(f"\n  - {r['url']} ({r['license']}): {r.get('note', '')}" for r in spec.get("references") or [])
    extras = [f for f in spec["score"] if f not in SCORE_FIELDS]
    return f"""{spec['brief'].strip()}

---
Eval protocol (task {spec['id']}; see evals/README.md):
- First call run_log(event="run_start", task="{spec['id']}", asset=<the file you will make>, label=<the label the user gives, e.g. v0.4>). run_start returns the run id; pass run=<that id> on every later run_log call (other sessions may share the ledger).
- Style {spec['style']}, engine {spec['engine']}, camera {cam['profile']} at {view}. Budgets: {json.dumps(spec['budgets'])}.
- References (download into refs/, never commit): {refs or 'none'}
- Accepted means every hard check passes:
{chr(10).join(_check_line(c) for c in spec['accept'])}
- After each change, run the hard checks and log run_log(event="iteration", n=<round>, tier=<cheapest failing tier>, hard_fail_count=<hard checks failing>, findings=<their ids>). A probe is a short Blender script you write to measure what no tool covers yet.
- Blind reads and checklists go to a fresh art-director subagent that sees only the sheet and the questions, never file names, this brief or this protocol; "unclear" counts as No. Log each as judge_round.
- Log every rejected tool call (bad arguments, a failed Blender script) as validator_rejection.
- When every hard check passes, run the soft checks once and log accept with values="{'; '.join(f'{f}=...' for f in extras)}". At 10 rounds, 2 judge rounds without a pass, or 90 minutes, log abandon with the reason and the same values.
"""


def summarize(label: str, runs_src=None, evals=None, all_runs: bool = False, out=None) -> tuple[Path, dict]:
    """Write a run set's summary numbers (no paths, no assets) to ``evals/results/<label>.json``."""
    folder = Path(evals) if evals else evals_dir()
    ids = [t["id"] for t in load_tasks(folder)]
    runs = run_summaries(runs_src, label="" if all_runs else label)
    in_suite = [r for r in runs if r["task"] in ids]
    per_task = {t: [r for r in in_suite if r["task"] == t] for t in ids}
    by_task = {t: aggregate(rs) for t, rs in per_task.items() if rs}
    data = {
        "label": label,
        "created": time.strftime("%Y-%m-%d"),
        "tool_versions": sorted({r["tool_version"] for r in in_suite if r["tool_version"]}),
        "models": sorted({r["model"] for r in in_suite if r["model"]}),
        "suite": {"tasks": len(ids), "hash": suite_hash(folder)},
        "missing_tasks": [t for t in ids if t not in by_task],
        "runs_outside_suite": len(runs) - len(in_suite),
        "overall": {"tasks": len(by_task), **aggregate(in_suite)},
        "by_task": by_task,
    }
    path = Path(out) if out else folder / "results" / f"{re.sub(r'[^A-Za-z0-9._-]+', '_', label)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return path, data


def _load_result(ref, folder: Path) -> dict:
    """A results file by label (``v0.4`` → results/v0.4.json) or by path."""
    p = Path(ref)
    if not (str(ref).endswith(".json") or p.is_file()):
        p = folder / "results" / f"{ref}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def sign_test(wins: int, losses: int) -> float:
    """One-sided sign test: P(at least ``wins`` of ``wins + losses`` fair coin flips)."""
    n = wins + losses
    return round(sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n, 4) if n else 1.0


def compare(base, new, evals=None, metric: str = "median_iterations_to_hard_pass") -> dict:
    """Per task, ``metric`` (lower is better; a task never passed counts as worst) in two result
    files, with the tasks where ``new`` is lower and a one-sided sign test (§9 cut rule)."""
    folder = Path(evals) if evals else evals_dir()
    a, b = _load_result(base, folder), _load_result(new, folder)
    rows, lower, higher, ties = {}, 0, 0, 0
    for tid in sorted(set(a["by_task"]) & set(b["by_task"])):
        x, y = a["by_task"][tid].get(metric), b["by_task"][tid].get(metric)
        xi, yi = (math.inf if v is None else v for v in (x, y))
        lower, higher, ties = lower + (yi < xi), higher + (yi > xi), ties + (yi == xi)
        rows[tid] = [x, y]
    return {"metric": metric, "base": a.get("label"), "new": b.get("label"), "tasks_compared": len(rows),
            "lower_on": lower, "higher_on": higher, "ties": ties, "p_sign_one_sided": sign_test(lower, higher),
            "by_task": rows}
