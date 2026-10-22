"""Spec language tools (WP-A): ``spec_new``, ``spec_validate``, ``dims_resolve``; CLI ``opus spec
new|validate|resolve`` and ``opus dims`` (docs/S0B_DESIGN.md §5, §6, §15). WP0 stub: every call
raises "not built yet" until WP-A replaces the bodies.
"""

from __future__ import annotations

from opus.tools import emit, names, not_built

PACKAGE = "WP-A"
ARCHETYPES = ("sword", "axe", "round_shield", "chest", "barrel", "chair", "generic")


def spec_new(archetype: str, id: str, kind: str = "assembly", out: str = "", camera: str = "",
             style: str = "") -> str:
    """Start a spec (``<id>.spec.json``) from a template: archetype sword, axe, round_shield,
    chest, barrel, chair or generic; kind assembly (other kinds validate their envelope only).
    out: the file to write (default ``<project>/<id>.spec.json``); camera: a bible camera profile;
    style: lowpoly | stylized | hd | pixel3d. Returns {"path", "todo": the dims you must fill
    ("/dims/blade_len: user or record"), "derived": camera numbers, "candidates": table refs per dim}."""
    raise not_built("spec_new", PACKAGE)


def spec_validate(path: str, log: bool = True) -> str:
    """Validate a spec (T0: schema, units and frame, sourced numbers, anchors, names, references,
    cycles, licences, records) and resolve its dims. Returns {"ok", "findings" (finding contract),
    "resolved": {dim: value, min, max, unit, src, tag}, "derived": {"px_per_m": ...},
    "tables_version"}. log: record each hard T0 finding as a validator_rejection in the open run."""
    raise not_built("spec_validate", PACKAGE)


def dims_resolve(spec_or_category: str, wielder: str = "", style: str = "", seed: int = -1) -> str:
    """Resolve dimensions: a spec path gives its dims sheet; a category (weapon/sword, prop/chair...)
    gives the template's sheet. wielder: "ansur2:male:p50" (default the spec's); seed -1 = the
    spec's. Returns {"sheet": {dim: value, min, max, unit, src, tag}, "conflicts", "tables_version",
    "findings"}."""
    raise not_built("dims_resolve", PACKAGE)


def spec_resolve(path: str, seeds: str = "", out: str = "") -> dict:
    """CLI ``opus spec resolve``: write the resolved spec JSON per seed (golden files)."""
    raise not_built("spec resolve", PACKAGE)


def register(tool) -> None:
    for fn in (spec_new, spec_validate, dims_resolve):
        tool(fn)


def add_cli(sub, groups) -> None:
    g = groups["spec"]
    s = g.add_parser("new", help="start a spec from a template")
    s.add_argument("archetype", choices=ARCHETYPES)
    s.add_argument("--id", required=True, help="spec id: ^[a-z][a-z0-9_]{1,63}$")
    s.add_argument("--kind", default="assembly")
    s.add_argument("-o", "--out", default="")
    s.add_argument("--camera", default="")
    s.add_argument("--style", default="")

    s = g.add_parser("validate", help="T0 rules and the resolved dims sheet")
    s.add_argument("path")
    s.add_argument("--no-log", action="store_true", help="do not log validator rejections in the run ledger")

    s = g.add_parser("resolve", help="write the resolved spec JSON (per seed)")
    s.add_argument("path")
    s.add_argument("--seeds", default="", help="comma-separated, e.g. 0,1,7 (default: the spec's seed)")
    s.add_argument("-o", "--out", default="", help="output folder or file")

    s = sub.add_parser("dims", help="resolve dimensions for a spec or a category")
    s.add_argument("spec_or_category")
    s.add_argument("--wielder", default="")
    s.add_argument("--style", default="")
    s.add_argument("--seed", type=int, default=-1)


def run_cli(args) -> int | None:
    if args.cmd == "dims":
        emit(dims_resolve(args.spec_or_category, args.wielder, args.style, args.seed))
        return 0
    if args.cmd != "spec":
        return None
    if args.spec_cmd == "new":
        emit(spec_new(args.archetype, args.id, args.kind, args.out, args.camera, args.style))
        return 0
    if args.spec_cmd == "validate":
        emit(spec_validate(args.path, log=not args.no_log))
        return 0
    if args.spec_cmd == "resolve":
        emit(spec_resolve(args.path, ",".join(names(args.seeds)), args.out))
        return 0
    return None
