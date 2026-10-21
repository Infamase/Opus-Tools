"""`opus` command line: the same tools as the MCP server, for batch jobs, CI and the terminal."""

from __future__ import annotations

import argparse
import json
import sys


def _print(data) -> None:
    print(data if isinstance(data, str) else json.dumps(data, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
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
    s.add_argument("--budget", type=int, default=0)
    s.add_argument("--deforming", choices=["auto", "true", "false"], default="auto")

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

    s = sub.add_parser("report", help="structure report with a labeled part map")
    s.add_argument("path")
    s.add_argument("--objects", default="")

    s = sub.add_parser("proportion", help="compare proportions with canon bodies")
    s.add_argument("path")
    s.add_argument("--archetype", default="humanoid", choices=["humanoid", "quadruped", "dragon"])
    s.add_argument("--preset", default="auto")
    s.add_argument("--pose", default="auto")

    s = sub.add_parser("refmatch", help="compare a silhouette with a reference image")
    s.add_argument("path")
    s.add_argument("reference")
    s.add_argument("--view", default="front", choices=["front", "back", "right", "left"])
    s.add_argument("--humanoid", action="store_true")

    s = sub.add_parser("blind", help="unlabeled sheet for a blind recognizability test")
    s.add_argument("path")
    s.add_argument("--game-size", action="store_true", help="add views at true game pixel size")
    s.add_argument("--camera", default="", help="camera profile (default: the bible's)")
    s.add_argument("--distances", default="", help="meters, comma-separated")

    s = sub.add_parser("readability", help="part map and feature widths at true game pixel size")
    s.add_argument("path")
    s.add_argument("--camera", default="", help="camera profile (default: the bible's), or viewmodel")
    s.add_argument("--distances", default="", help="meters, comma-separated (default: close, typical, far)")
    s.add_argument("--defining", default="", help="defining parts, comma-separated")
    s.add_argument("--view", default="", help='a named view or "azimuth,elevation"')
    s.add_argument("--floor", type=float, default=2.0, help="min width floor in px (soft)")
    s.add_argument("--objects", default="")

    s = sub.add_parser("grip-define", help="mark a grip on an object")
    s.add_argument("path")
    s.add_argument("object")
    s.add_argument("--name", default="main")
    s.add_argument("--part", default="")
    s.add_argument("--up", default="")
    s.add_argument("--palm-side", default="")
    s.add_argument("--point-axis", default="")
    s.add_argument("--hand", default="r", choices=["r", "l"])
    s.add_argument("--center", type=float, default=0.5)
    s.add_argument("--style", default="power", choices=["power", "pistol"])
    s.add_argument("--index", default="curl", choices=["curl", "trigger", "extended"])
    s.add_argument("--trigger", default="")

    s = sub.add_parser("hold", help="put an object with a grip in a rigged hand")
    s.add_argument("rig")
    s.add_argument("object_path", nargs="?", default="")
    s.add_argument("--grip", default="")
    s.add_argument("--side", default="r", choices=["r", "l"])
    s.add_argument("--pose", default="rest", choices=["rest", "front", "fp_hip", "fp_ads"])
    s.add_argument("--move", default="object", choices=["object", "hand"])
    s.add_argument("--offset", default="")
    s.add_argument("-o", "--out", default="")

    s = sub.add_parser("grip-check", help="measure how hands hold objects in a scene")
    s.add_argument("path")
    s.add_argument("--side", default="r", choices=["r", "l", "both"])
    s.add_argument("--object", default="")
    s.add_argument("--fp", action="store_true")

    s = sub.add_parser("lineup", help="asset beside human-made exemplars at game size, in both orders")
    s.add_argument("images", nargs="+")
    s.add_argument("--exemplars", nargs="+", required=True)
    s.add_argument("--height", type=int, default=96)
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
    s.add_argument("action", choices=["show", "init"])
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

    a = ap.parse_args(argv)
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
        rep = mesh_lint(a.path, objects=names, budget_tris=a.budget, deforming=flag)
        _print(rep["text"])
        return 0 if rep["game_ready"] else 1
    elif a.cmd == "body":
        from opus.threed.body import body_blockout

        _, rep = body_blockout(a.archetype, a.preset, a.height, a.pose, a.tris, out=a.out or None, glb=a.glb)
        _print(rep)
    elif a.cmd == "look":
        from opus.threed.understand import look_at

        sep = ";" if (";" in a.views or a.views.split(",")[0].strip().lstrip("-").replace(".", "").isdigit()) else ","
        sheet, rep = look_at(a.path, views=[v.strip() for v in a.views.split(sep) if v.strip()], pass_=a.render_pass,
                             target=a.target, zoom=a.zoom, isolate=a.isolate, ortho=a.ortho)
        _print(rep)
    elif a.cmd == "report":
        from opus.threed.understand import model_report

        names = [x.strip() for x in a.objects.split(",") if x.strip()] or None
        sheet, rep = model_report(a.path, objects=names)
        _print(rep["text"] + f"\n\nsheet: {sheet}")
    elif a.cmd == "proportion":
        from opus.threed.proportion import proportion_check

        sheet, rep = proportion_check(a.path, archetype=a.archetype, preset=a.preset, pose=a.pose)
        _print(rep["text"] + f"\n\nsheet: {sheet}")
    elif a.cmd == "refmatch":
        from opus.threed.proportion import reference_match

        sheet, rep = reference_match(a.path, a.reference, view=a.view, humanoid=a.humanoid)
        _print(rep["text"] + f"\n\nsheet: {sheet}")
    elif a.cmd == "blind":
        from opus.threed.understand import blind_read_sheet

        dist = [float(x) for x in a.distances.split(",") if x.strip()] or None
        sheet, prompt = blind_read_sheet(a.path, game_size=a.game_size, camera=a.camera, distances=dist)
        _print(prompt)
    elif a.cmd == "readability":
        from opus.threed.understand import readability_check

        dist = [float(x) for x in a.distances.split(",") if x.strip()] or None
        names = [x.strip() for x in a.objects.split(",") if x.strip()] or None
        sheet, rep = readability_check(a.path, camera=a.camera, distances=dist, view=a.view, floor_px=a.floor, objects=names,
                                       defining=[x.strip() for x in a.defining.split(",") if x.strip()] or None)
        _print(rep["text"] + f"\n\nsheet: {sheet}\nall parts: {rep['all_parts']}")
    elif a.cmd in ("grip-define", "hold", "grip-check"):
        from opus.threed import grip

        def floats(t):
            return [float(x) for x in t.replace(";", ",").split(",")] if t else None

        if a.cmd == "grip-define":
            sheet, rep = grip.grip_define(a.path, a.object, a.name, a.part, up=floats(a.up), palm_side=floats(a.palm_side),
                                          center=a.center, style=a.style, index=a.index, trigger=floats(a.trigger),
                                          point_axis=a.point_axis, hand=a.hand)
            _print(rep)
        elif a.cmd == "hold":
            sheet, rep = grip.grip_hold(a.rig, a.object_path or None, grip=a.grip, side=a.side, pose=a.pose, move=a.move,
                                        offset=floats(a.offset), out_blend=a.out or None)
            _print(rep["text"] + f"\n\nsheet: {sheet}\nfile: {rep['file']}")
        else:
            sheet, rep = grip.grip_check(a.path, a.side, a.object, a.fp)
            _print(rep["text"] + f"\n\nsheet: {sheet}")
    elif a.cmd in ("lineup", "ab"):
        from opus import critique

        if a.cmd == "lineup":
            rep = critique.lineup_sheet(a.images, a.exemplars, a.height, a.seed, a.background, a.fit, a.view, a.render_pass)
        else:
            rep = critique.ab_sheet(a.first, a.second, a.height, a.seed, a.background, a.question or critique.AB_QUESTION,
                                    view=a.view, render_pass=a.render_pass)
        _print(rep)
    elif a.cmd == "bible":
        from opus.bible import init_bible, load_bible

        _print(str(init_bible(a.dir, project=a.project)) if a.action == "init" else load_bible(a.dir))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
