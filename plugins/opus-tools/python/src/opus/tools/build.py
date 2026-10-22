"""Build and export tools (WP-E): ``spec_build``, ``export_asset``; CLI ``opus spec build`` and
``opus export`` (docs/S0B_DESIGN.md §11, §12, §15). WP0 stub: every call raises "not built yet"
until WP-E replaces the bodies.
"""

from __future__ import annotations

from opus.tools import emit, not_built

PACKAGE = "WP-E"
ENGINES = ("ue", "godot", "unity")


def spec_build(path: str, out: str = "", exports: str = "blend,glb", finish: bool = True, seed: int = -1) -> str:
    """Build a spec in Blender: emit one mesh per part, read it back (emit_hash against the
    evaluator), finish (bevel, weighted normals, triangulate), save the .blend and export.
    exports: comma-separated blend, glb, fbx_ue; finish: false skips finishing; seed -1 = the
    spec's. Returns {"blend", "exports", "hash", "emit_hash", "match", "readback", "post_eval",
    "consistency", "ledger", "seconds"}."""
    raise not_built("spec_build", PACKAGE)


def export_asset(path: str, engine: str, out_dir: str = "", collision: bool = True, round_trip: bool = True) -> str:
    """Export a built asset (a spec or its .blend) for an engine: ue (FBX, UCX_ hulls, SOCKET_
    empties, import script and checklist), godot (.glb, -convcolonly hulls) or unity (FBX). Writes
    a <id>.opus.json sidecar, re-imports the files to verify them (round_trip) and applies the
    licence policy. Returns {"files", "sidecar", "round_trip": {"ok","findings"}, "licence":
    {"ok","blocked"}, "engine_script", "checklist"}."""
    raise not_built("export_asset", PACKAGE)


def hash_check(path: str, seed: int = -1) -> dict:
    """CLI ``opus spec build --hash-check``: the host eval_hash, the Blender evaluator's
    eval_hash, the emitted read-back's geom_hash and the tie rule Blender shows."""
    raise not_built("spec build --hash-check", PACKAGE)


def register(tool) -> None:
    for fn in (spec_build, export_asset):
        tool(fn)


def add_cli(sub, groups) -> None:
    s = groups["spec"].add_parser("build", help="emit, finish, save and export in Blender")
    s.add_argument("path")
    s.add_argument("-o", "--out", default="")
    s.add_argument("--exports", default="blend,glb", help="comma-separated: blend, glb, fbx_ue")
    s.add_argument("--no-finish", action="store_true")
    s.add_argument("--seed", type=int, default=-1)
    s.add_argument("--hash-check", action="store_true", help="print the host, Blender and read-back hashes and the tie rule")

    s = sub.add_parser("export", help="export a built asset for an engine")
    s.add_argument("path")
    s.add_argument("--engine", required=True, choices=ENGINES)
    s.add_argument("--out-dir", default="")
    s.add_argument("--no-collision", action="store_true")
    s.add_argument("--no-round-trip", action="store_true")


def run_cli(args) -> int | None:
    if args.cmd == "export":
        emit(export_asset(args.path, args.engine, args.out_dir, collision=not args.no_collision,
                          round_trip=not args.no_round_trip))
        return 0
    if args.cmd == "spec" and args.spec_cmd == "build":
        if args.hash_check:
            emit(hash_check(args.path, args.seed))
        else:
            emit(spec_build(args.path, args.out, args.exports, finish=not args.no_finish, seed=args.seed))
        return 0
    return None
