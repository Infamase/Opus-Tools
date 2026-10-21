"""`opus` command line: the same tools as the MCP server, for batch jobs, CI and the terminal."""

from __future__ import annotations

import argparse
import json
import sys

from opus.blender.runner import BlenderNotFound, BlenderTaskError

ERRORS = (ValueError, FileNotFoundError, FileExistsError, BlenderNotFound, BlenderTaskError)


def _print(data) -> None:
    print(data if isinstance(data, str) else json.dumps(data, indent=1, default=str))


def _names(text: str) -> list[str] | None:
    return [x.strip() for x in text.split(",") if x.strip()] or None


def _report(a, sheet, rep: dict, *extra: str) -> None:
    """The report's text and sheet path, or with --json all of it, as the MCP tool returns it."""
    if a.json:
        rep.setdefault("sheet", str(sheet))
        _print(rep)
    else:
        _print("\n".join([rep["text"] + f"\n\nsheet: {sheet}", *extra]))


def _run_log_fields() -> str:
    """run-log's epilog: every event with its fields, from the event schema."""
    from opus.runs import EVENTS, REQUIRED

    kinds = {int: " (int)", float: " (float)"}
    lines = ["events and their fields (* = required):"]
    for event, fields in EVENTS.items():
        names = [f"{k}{'*' if k in REQUIRED.get(event, ()) else ''}{kinds.get(t, '')}" for k, t in fields.items()]
        lines.append(f"  {event:20} {', '.join(names)}")
    lines += ['findings: failing check names, e.g. "floating_parts, grip x2"; values: "tris=3120; blind_read_top1=wolf".',
              "run_start fills in tool_version; accept fills in iterations_to_accept and wall_clock_s.",
              "--run <id from run_start> picks the run; without it an event goes to the latest open run",
              "(tokens and user_rejection: the latest run), so pass it when several runs are open."]
    return "\n".join(lines)


def _dash_values(ap: argparse.ArgumentParser, argv: list[str]) -> list[str]:
    """Join a value that starts with '-' (-X, -30,10) to its option as --opt=value, so argparse
    does not read it as an unknown flag."""
    out, parser, i = [], ap, 0
    while i < len(argv):
        tok = argv[i]
        out.append(tok)
        if tok == "--":
            return out + argv[i + 1:]
        acts = parser._option_string_actions
        sub = next((x for x in parser._actions if isinstance(x, argparse._SubParsersAction)), None)
        if sub is not None and tok in sub.choices:
            parser = sub.choices[tok]
        elif tok.startswith("--") and tok in acts and acts[tok].nargs is None and i + 1 < len(argv):
            nxt = argv[i + 1]
            if nxt.startswith("-") and not nxt.startswith("--") and nxt not in acts:
                out[-1] = f"{tok}={nxt}"
                i += 1
        i += 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    a = ap.parse_args(_dash_values(ap, sys.argv[1:] if argv is None else list(argv)))
    try:
        return _run(a)
    except ERRORS as e:  # a one-line message the call can be corrected from, not a traceback
        print(f"opus {a.cmd}: error: {e}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="opus", description="Opus Tools: senses for game assets")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("inspect", help="Sprite Inspector")
    s.add_argument("path")
    s.add_argument("--mode", default="sprite", choices=["sprite", "tile", "sheet"])
    s.add_argument("--frame", nargs=2, type=int, metavar=("W", "H"), default=(0, 0))
    s.add_argument("--palette", default="")
    s.add_argument("--light", default="top-left")
    s.add_argument("--max-colors", type=int, default=0)

    s = sub.add_parser("cleanup", help="Pixel Cleanup")
    s.add_argument("path")
    s.add_argument("--palette", default="")
    s.add_argument("--max-colors", type=int, default=24)
    s.add_argument("--background", default="auto")
    s.add_argument("--outline", default="none")
    s.add_argument("--no-crop", action="store_true")
    s.add_argument("-o", "--out", default="")

    s = sub.add_parser("ramp", help="hue-shifted color ramp")
    s.add_argument("base")
    s.add_argument("--steps", type=int, default=5)
    s.add_argument("--hue-shift", type=float, default=25.0)

    s = sub.add_parser("lookdev", help="Look Dev Sheet for a 3D asset")
    s.add_argument("path")
    s.add_argument("--objects", default="")
    s.add_argument("--engine", default="workbench", choices=["workbench", "eevee", "cycles"])
    s.add_argument("--tile", type=int, default=270)

    s = sub.add_parser("lint", help="Mesh Lint for a 3D asset")
    s.add_argument("path")
    s.add_argument("--objects", default="")
    s.add_argument("--category", default="", help="tri budget from the bible: prop_small, prop_large, environment_piece, "
                                                  "character, hero_character (--budget wins)")
    s.add_argument("--budget", type=int, default=0)
    s.add_argument("--deforming", choices=["auto", "true", "false"], default="auto")
    s.add_argument("--json", action="store_true", help="the full report as JSON")

    s = sub.add_parser("body", help="canon-proportioned, rigged body blockout")
    s.add_argument("archetype", choices=["humanoid", "quadruped", "dragon"])
    s.add_argument("--preset", default="")
    s.add_argument("--height", type=float, default=0.0)
    s.add_argument("--pose", default="A", choices=["A", "T"])
    s.add_argument("--tris", type=int, default=10000)
    s.add_argument("--glb", action="store_true")
    s.add_argument("-o", "--out", default="")

    s = sub.add_parser("look", help="look at an asset or part from any angle")
    s.add_argument("path")
    s.add_argument("--views", default="three_quarter", help='names, or "az,el;az,el"')
    s.add_argument("--pass", dest="render_pass", default="clay")
    s.add_argument("--target", default="")
    s.add_argument("--zoom", type=float, default=1.0)
    s.add_argument("--isolate", action="store_true")
    s.add_argument("--ortho", action="store_true")
    s.add_argument("--objects", default="", help="comma-separated object or collection names")

    s = sub.add_parser("report", help="structure report with a labeled part map")
    s.add_argument("path")
    s.add_argument("--objects", default="")
    s.add_argument("--json", action="store_true", help="the full report (gaps, contacts, penetrations...) as JSON")

    s = sub.add_parser("proportion", help="compare proportions with canon bodies")
    s.add_argument("path")
    s.add_argument("--archetype", default="humanoid", choices=["humanoid", "quadruped", "dragon"])
    s.add_argument("--preset", default="auto")
    s.add_argument("--pose", default="auto")
    s.add_argument("--objects", default="", help="comma-separated object or collection names")
    s.add_argument("--json", action="store_true", help="the full report as JSON")

    s = sub.add_parser("refmatch", help="compare a silhouette with a reference image")
    s.add_argument("path")
    s.add_argument("reference")
    s.add_argument("--view", default="front", choices=["front", "back", "right", "left"])
    s.add_argument("--humanoid", action="store_true")
    s.add_argument("--objects", default="", help="comma-separated object or collection names")
    s.add_argument("--json", action="store_true", help="the full report as JSON")

    s = sub.add_parser("blind", help="unlabeled sheet for a blind recognizability test")
    s.add_argument("path")
    s.add_argument("--game-size", action="store_true", help="add views at true game pixel size")
    s.add_argument("--camera", default="", help="camera profile (default: the bible's)")
    s.add_argument("--distances", default="", help="meters, comma-separated")
    s.add_argument("--objects", default="", help="comma-separated object or collection names")
    s.add_argument("--json", action="store_true", help="the sheet and prompt as JSON")

    s = sub.add_parser("readability", help="part map and feature widths at true game pixel size")
    s.add_argument("path")
    s.add_argument("--camera", default="", help="camera profile (default: the bible's), or viewmodel")
    s.add_argument("--distances", default="", help="meters, comma-separated (default: close, typical, far)")
    s.add_argument("--defining", default="", help="defining parts, comma-separated")
    s.add_argument("--view", default="", help='a named view or "azimuth,elevation"')
    s.add_argument("--floor", type=float, default=2.0, help="min width floor in px (soft)")
    s.add_argument("--objects", default="")
    s.add_argument("--json", action="store_true", help="the full report as JSON")

    s = sub.add_parser("grip-define", help="mark a grip on an object")
    s.add_argument("path")
    s.add_argument("object")
    s.add_argument("--name", default="main")
    s.add_argument("--part", default="")
    s.add_argument("--start", default="", help='handle start point "x,y,z" (world, m)')
    s.add_argument("--end", default="", help='handle end point "x,y,z"')
    s.add_argument("--up", default="", help='toward the thumb end: an axis (+Z, -X) or "x,y,z" (default +Z)')
    s.add_argument("--palm-side", default="", help='from the handle toward the palm: an axis (-X) or "x,y,z"')
    s.add_argument("--point-axis", default="", help="pistol grips: the object axis along the forearm, e.g. -Y")
    s.add_argument("--hand", default="r", choices=["r", "l"])
    s.add_argument("--center", type=float, default=0.5)
    s.add_argument("--style", default="power", choices=["power", "pistol"])
    s.add_argument("--index", default="curl", choices=["curl", "trigger", "extended"])
    s.add_argument("--thumb", default="wrap", choices=["wrap", "along"])
    s.add_argument("--trigger", default="", help='the trigger\'s front point "x,y,z"')

    s = sub.add_parser("hold", help="put an object with a grip in a rigged hand")
    s.add_argument("rig")
    s.add_argument("object_path", nargs="?", default="")
    s.add_argument("--grip", default="")
    s.add_argument("--side", default="r", choices=["r", "l"])
    s.add_argument("--pose", default="rest", choices=["rest", "front", "fp_hip", "fp_ads"])
    s.add_argument("--move", default="object", choices=["object", "hand"])
    s.add_argument("--object", default="", help="the object to hold (default: the one with the grip)")
    s.add_argument("--aim-axis", default="-Y", help="the object axis that points forward in fp poses")
    s.add_argument("--offset", default="", help='fp poses: "forward,right,down" in m from the eye')
    s.add_argument("--index", default="", choices=["curl", "trigger", "extended"], help="override the grip's")
    s.add_argument("--thumb", default="", choices=["wrap", "along"], help="override the grip's")
    s.add_argument("-o", "--out", default="")
    s.add_argument("--json", action="store_true", help="the full report as JSON")

    s = sub.add_parser("grip-check", help="measure how hands hold objects in a scene")
    s.add_argument("path")
    s.add_argument("--side", default="r", choices=["r", "l", "both"])
    s.add_argument("--object", default="")
    s.add_argument("--fp", action="store_true")
    s.add_argument("--json", action="store_true", help="the full report (gaps, inside mm, body clipping) as JSON")

    s = sub.add_parser("lineup", help="asset beside human-made exemplars at game size, in both orders")
    s.add_argument("images", nargs="+")
    s.add_argument("--exemplars", nargs="+", required=True)
    s.add_argument("--height", type=int, default=96)
    s.add_argument("--camera", default=None, help="size from this camera profile instead ('' = the bible's)")
    s.add_argument("--distance", type=float, default=0.0, help="meters from the camera (default: typical)")
    s.add_argument("--size-m", type=float, default=0.0, help="subject's real height in m (3D files: measured)")
    s.add_argument("--seed", type=int, default=-1)
    s.add_argument("--background", default="#808080")
    s.add_argument("--fit", default="height", choices=["height", "long_edge"])
    s.add_argument("--view", default="three_quarter")
    s.add_argument("--pass", dest="render_pass", default="shaded", choices=["shaded", "clay", "silhouette"])

    s = sub.add_parser("ab", help="blind A/B pair of two candidates, in both orders")
    s.add_argument("first", metavar="A")
    s.add_argument("second", metavar="B")
    s.add_argument("--question", default="")
    s.add_argument("--height", type=int, default=0)
    s.add_argument("--seed", type=int, default=-1)
    s.add_argument("--background", default="#808080")
    s.add_argument("--view", default="three_quarter")
    s.add_argument("--pass", dest="render_pass", default="shaded", choices=["shaded", "clay", "silhouette"])

    s = sub.add_parser("bible", help="show or create opus.project.yaml")
    s.add_argument("action", nargs="?", default="show", choices=["show", "init"])
    s.add_argument("--dir", default=".")
    s.add_argument("--project", default="")

    s = sub.add_parser("credits", help="write CREDITS.md from the provenance ledger")
    s.add_argument("--dir", default=".")

    s = sub.add_parser("data", help="rebuild the committed fact tables (maintainers)")
    s.add_argument("action", choices=["build"])
    s.add_argument("--tables", action="store_true", required=True)
    s.add_argument("--ansur", default="", help="folder with ANSUR_II_MALE/FEMALE_Public.csv")
    s.add_argument("--out", default="", help="write here instead of data/tables")

    s = sub.add_parser("licence-check", help="what in the provenance ledger blocks export")
    s.add_argument("--dir", default=".")
    s.add_argument("--text", default="", help="classify this licence text instead")
    s.add_argument("--commercial", choices=["true", "false"], default=None)
    s.add_argument("--publish-assets", choices=["true", "false"], default=None)

    sub.add_parser("doctor", help="check integrations")
    sub.add_parser("mcp", help="run the MCP server on stdio")

    s = sub.add_parser("run-log", help="append an event to the run ledger (.opus/runs)", epilog=_run_log_fields(),
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    s.add_argument("event", help="run_start, iteration, validator_rejection, judge_round, user_rejection, tokens, "
                                 "accept or abandon")
    s.add_argument("fields", nargs="*", help='key=value, e.g. n=2 hard_fail_count=1 "findings=floating_parts, grip" '
                                             "(each event's fields are listed below)")
    s.add_argument("--run", default="", help="the run id from run_start")
    s.add_argument("--dir", default=".")

    s = sub.add_parser("run-stats", help="iterations, judge rounds, wall-clock, tokens and failures from the run ledger")
    s.add_argument("--dir", default=".", help="project folder, .opus/runs folder or one .jsonl file")
    s.add_argument("--task", default="")
    s.add_argument("--label", default="")
    s.add_argument("--run", default="", help="one run's numbers, by its id from run_start")

    s = sub.add_parser("eval", help="the 24-task eval suite (evals/ at the repo root, or $OPUS_EVALS_DIR)")
    ev = s.add_subparsers(dest="eval_cmd", required=True)
    for name, text in (("list", "list the tasks"), ("validate", "check every task spec and the suite's coverage")):
        e = ev.add_parser(name, help=text)
        e.add_argument("--evals", default="")
    e = ev.add_parser("prompt", help="the prompt to paste into a fresh session for one task")
    e.add_argument("task")
    e.add_argument("--evals", default="")
    e = ev.add_parser("summarize", help="write a run set's numbers to evals/results/<label>.json")
    e.add_argument("label")
    e.add_argument("--runs", default=".", help="project folder, .opus/runs folder or one .jsonl file")
    e.add_argument("--all", action="store_true", help="every run, not only runs started with this label")
    e.add_argument("--evals", default="")
    e.add_argument("-o", "--out", default="")
    e = ev.add_parser("compare", help="per-task median iterations to a hard pass, new vs base, with a sign test")
    e.add_argument("base", help="a results label (e.g. v0.4) or a results .json")
    e.add_argument("new")
    e.add_argument("--evals", default="")
    e = ev.add_parser("tokens", help="sum the token use in Claude Code session transcripts")
    e.add_argument("transcripts", nargs="+", help="session .jsonl files or folders")
    e.add_argument("--log", action="store_true", help="also log it as a tokens event")
    e.add_argument("--run", default="")
    e.add_argument("--dir", default=".")
    return ap


def _run(a: argparse.Namespace) -> int:
    if a.cmd == "inspect":
        from opus.pixel.inspect import inspect_sprite

        sheet, rep = inspect_sprite(a.path, a.mode, a.frame[0], a.frame[1], a.palette or None, a.light, a.max_colors)
        _print(rep)
    elif a.cmd == "cleanup":
        from opus.pixel.cleanup import cleanup

        _, _, rep = cleanup(a.path, a.palette or None, a.max_colors, a.background, a.outline, crop=not a.no_crop, out=a.out or None)
        _print(rep)
    elif a.cmd == "ramp":
        from opus.pixel.palette import make_ramp

        _print(make_ramp(a.base, a.steps, a.hue_shift).hex())
    elif a.cmd == "lookdev":
        from opus.threed.lookdev import lookdev_sheet

        names = [x.strip() for x in a.objects.split(",") if x.strip()] or None
        _, rep = lookdev_sheet(a.path, objects=names, engine=a.engine, tile=a.tile)
        _print(rep)
    elif a.cmd == "lint":
        from opus.threed.lint import mesh_lint

        names = [x.strip() for x in a.objects.split(",") if x.strip()] or None
        flag = {"auto": None, "true": True, "false": False}[a.deforming]
        budget = a.budget
        if not budget and a.category:
            from opus.bible import load_bible

            budgets = load_bible(a.path)["3d"]["budgets_tris"]
            if a.category not in budgets:
                raise ValueError(f"unknown category {a.category!r}; the bible has {sorted(budgets)}")
            budget = budgets[a.category]
        rep = mesh_lint(a.path, objects=names, budget_tris=budget, deforming=flag)
        _print(rep if a.json else rep["text"])
        return 0 if rep["game_ready"] else 1
    elif a.cmd == "body":
        from opus.threed.body import body_blockout

        _, rep = body_blockout(a.archetype, a.preset, a.height, a.pose, a.tris, out=a.out or None, glb=a.glb)
        _print(rep)
    elif a.cmd == "look":
        from opus.threed.understand import look_at

        sep = ";" if (";" in a.views or a.views.split(",")[0].strip().lstrip("-").replace(".", "").isdigit()) else ","
        sheet, rep = look_at(a.path, views=[v.strip() for v in a.views.split(sep) if v.strip()], pass_=a.render_pass,
                             target=a.target, zoom=a.zoom, isolate=a.isolate, ortho=a.ortho, objects=_names(a.objects))
        _print(rep)
    elif a.cmd == "report":
        from opus.threed.understand import model_report

        names = [x.strip() for x in a.objects.split(",") if x.strip()] or None
        sheet, rep = model_report(a.path, objects=names)
        _report(a, sheet, rep)
    elif a.cmd == "proportion":
        from opus.threed.proportion import proportion_check

        sheet, rep = proportion_check(a.path, archetype=a.archetype, preset=a.preset, pose=a.pose, objects=_names(a.objects))
        _report(a, sheet, rep)
    elif a.cmd == "refmatch":
        from opus.threed.proportion import reference_match

        sheet, rep = reference_match(a.path, a.reference, view=a.view, humanoid=a.humanoid, objects=_names(a.objects))
        _report(a, sheet, rep)
    elif a.cmd == "blind":
        from opus.threed.understand import blind_read_sheet

        dist = [float(x) for x in a.distances.split(",") if x.strip()] or None
        sheet, prompt = blind_read_sheet(a.path, game_size=a.game_size, camera=a.camera, distances=dist,
                                         objects=_names(a.objects))
        _print({"sheet": str(sheet), "prompt": prompt} if a.json else prompt)
    elif a.cmd == "readability":
        from opus.threed.understand import readability_check

        dist = [float(x) for x in a.distances.split(",") if x.strip()] or None
        names = [x.strip() for x in a.objects.split(",") if x.strip()] or None
        sheet, rep = readability_check(a.path, camera=a.camera, distances=dist, view=a.view, floor_px=a.floor, objects=names,
                                       defining=[x.strip() for x in a.defining.split(",") if x.strip()] or None)
        _report(a, sheet, rep, f"all parts: {rep['all_parts']}")
    elif a.cmd in ("grip-define", "hold", "grip-check"):
        from opus.threed import grip

        # points, directions and offsets go in as typed: grip parses "x,y,z" and axis names (+Z, -X)
        if a.cmd == "grip-define":
            sheet, rep = grip.grip_define(a.path, a.object, a.name, a.part, start=a.start, end=a.end, up=a.up,
                                          palm_side=a.palm_side, center=a.center, style=a.style, index=a.index,
                                          thumb=a.thumb, trigger=a.trigger, point_axis=a.point_axis, hand=a.hand)
            _print(rep)
        elif a.cmd == "hold":
            sheet, rep = grip.grip_hold(a.rig, a.object_path or None, object=a.object, grip=a.grip, side=a.side, pose=a.pose,
                                        move=a.move, aim_axis=a.aim_axis, offset=a.offset, index=a.index, thumb=a.thumb,
                                        out_blend=a.out or None)
            _report(a, sheet, rep, f"file: {rep['file']}")
        else:
            sheet, rep = grip.grip_check(a.path, a.side, a.object, a.fp)
            _report(a, sheet, rep)
    elif a.cmd in ("lineup", "ab"):
        from opus import critique

        if a.cmd == "lineup":
            rep = critique.lineup_sheet(a.images, a.exemplars, a.height, a.seed, a.background, a.fit, a.view, a.render_pass,
                                        camera=a.camera, distance_m=a.distance, size_m=a.size_m)
        else:
            rep = critique.ab_sheet(a.first, a.second, a.height, a.seed, a.background, a.question or critique.AB_QUESTION,
                                    view=a.view, render_pass=a.render_pass)
        _print(rep)
    elif a.cmd == "bible":
        from opus.bible import camera_profile, init_bible, load_bible

        if a.action == "init":
            _print(str(init_bible(a.dir, project=a.project)))
            return 0
        bible = load_bible(a.dir)
        for key, name in (("camera_active", ""), ("camera_viewmodel", "viewmodel")):
            try:  # the resolved camera and its derived numbers, as project_bible shows them
                bible[key] = camera_profile(bible, name).summary()
            except ValueError as e:
                bible[key] = {"error": str(e)}
        _print(bible)
    elif a.cmd == "credits":
        from opus.ledger import write_credits

        _print(str(write_credits(a.dir)))
    elif a.cmd == "data":
        from opus.tables import build_tables

        _print(build_tables(a.ansur or None, a.out or None))
    elif a.cmd == "licence-check":
        from opus.ledger import check, classify

        if a.text:
            lid, flags = classify(a.text)
            _print({"licence_id": lid, "flags": flags})
            return 0
        flag = {None: None, "true": True, "false": False}
        rep = check(a.dir, commercial=flag[a.commercial], publish_assets=flag[a.publish_assets])
        _print(rep)
        return 0 if rep["ok"] else 1
    elif a.cmd == "doctor":
        from opus.doctor import doctor, format_report

        rep = doctor()
        _print(format_report(rep))
        return 0 if rep["ok"] else 1
    elif a.cmd == "mcp":
        from opus.mcp_server import main as serve

        serve()
    elif a.cmd == "run-log":
        from opus.runs import log

        # strings as typed: the event schema converts its numeric fields, and a label such as
        # 1.10 stays "1.10"
        fields = dict(f.split("=", 1) for f in a.fields if "=" in f)
        _print(log(a.event, run=a.run, near=a.dir, **fields))
    elif a.cmd == "run-stats":
        from opus import runs

        if a.run:
            by_run = runs._group(runs.read_events(a.dir))
            if a.run not in by_run:
                raise ValueError(f"no run {a.run!r} in {a.dir}; runs: {sorted(by_run)[-10:]}")
            _print(runs.summarize_run(by_run[a.run]))
        else:
            _print(runs.run_stats(a.dir, task=a.task, label=a.label))
    elif a.cmd == "eval":
        from opus import runs

        evals = a.evals if hasattr(a, "evals") and a.evals else None
        if a.eval_cmd == "list":
            for t in runs.load_tasks(evals):
                tag = "regression" if t.get("regression") else t.get("category", "?")
                cols = (t.get("id", "?"), tag, t.get("style", "?"), t.get("engine", "?"))
                print("{:16} {:11} {:8} {:7} ".format(*cols) + t.get("title", ""))
        elif a.eval_cmd == "validate":
            tasks = runs.load_tasks(evals)
            errs = runs.validate_suite(tasks)
            _print("\n".join(errs) if errs else f"{len(tasks)} tasks valid · suite {runs.suite_hash(evals)}")
            return 1 if errs else 0
        elif a.eval_cmd == "prompt":
            spec = next((t for t in runs.load_tasks(evals) if t.get("id") == a.task), None)
            if spec is None:
                raise SystemExit(f"no task {a.task!r}; see `opus eval list`")
            _print(runs.task_prompt(spec))
        elif a.eval_cmd == "summarize":
            path, data = runs.summarize(a.label, a.runs, evals, all_runs=a.all, out=a.out or None)
            _print({"written": str(path), "overall": data["overall"], "missing_tasks": data["missing_tasks"]})
        elif a.eval_cmd == "compare":
            _print(runs.compare(a.base, a.new, evals))
        elif a.eval_cmd == "tokens":
            used = runs.transcript_tokens(*a.transcripts)
            if a.log:
                used["logged"] = runs.log("tokens", run=a.run, near=a.dir, input=used["input"], output=used["output"])
            _print(used)
    return 0


if __name__ == "__main__":
    sys.exit(main())
