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

    s = sub.add_parser("bible", help="show or create opus.project.yaml")
    s.add_argument("action", choices=["show", "init"])
    s.add_argument("--dir", default=".")
    s.add_argument("--project", default="")

    s = sub.add_parser("credits", help="write CREDITS.md from the provenance ledger")
    s.add_argument("--dir", default=".")

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
    elif a.cmd == "bible":
        from opus.bible import init_bible, load_bible

        _print(str(init_bible(a.dir, project=a.project)) if a.action == "init" else load_bible(a.dir))
    elif a.cmd == "credits":
        from opus.ledger import write_credits

        _print(str(write_credits(a.dir)))
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
