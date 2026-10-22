"""Gate tools (WP-D): ``spec_check``, ``defect_inject``, ``gate_calibrate``; CLI ``opus spec check``
and ``opus gates inject|calibrate|fixtures`` (docs/S0B_DESIGN.md §9, §15). WP0 stub: every call
raises "not built yet" until WP-D replaces the bodies.
"""

from __future__ import annotations

from opus.tools import emit, not_built

PACKAGE = "WP-D"


def spec_check(path: str, built: str = "", tiers: str = "T0-T2", profile: str = "", parts: str = "",
               all: bool = False) -> str:
    """Run the gates on a spec: T0 (spec rules), T1 (evaluator: anchors, sheet measures, relations,
    symmetry) and T2 (geometry: manifold, shells, contacts, floating parts, overlaps, grounding),
    cheapest first, stopping at the first tier with a hard failure unless all=true. built: a
    .blend or read-back .npz from spec_build (adds the emitted/finished stages and T2b); tiers:
    "T0-T2", "T0,T1", "T2b"; profile: cad_clean | kitbash | organic (default the spec's); parts:
    comma-separated part names to re-check. Returns {"ok", "stopped_at", "hard_fail_count",
    "hard_magnitude", "soft_score", "findings", "by_tier", "unavailable", "round", "evidence"}."""
    raise not_built("spec_check", PACKAGE)


def defect_inject(gate: str = "all", fixtures: str = "ab6", seeds: int = 8, n_per: int = 200,
                  check_armed: bool = False, write_armed: bool = False) -> str:
    """Maintainers: plant known defects (contact, floating, manifold, sheet, relation, naming,
    overlap) at a stated size into clean fixtures and measure each gate's recall. gate: a family
    or "all"; fixtures: ab6; seeds: fixture seeds 0..seeds-1; n_per: plants per family and size.
    check_armed: fail when an armed check misses its recall; write_armed: write data/gates/armed.json
    from a passing run. Returns per family {"planted", "ineligible", "detected", "recall", "recall_2x",
    "clean_failures", "by_spec", "by_mode", "misses", "ok"}."""
    raise not_built("defect_inject", PACKAGE)


def gate_calibrate(check: str, corpus: str, planted: bool = True, noise: bool = False) -> str:
    """Maintainers: sweep a check's threshold over a clean corpus (a folder or a fixture set) and
    planted defects; noise=true measures the metric's noise over seeds or render jitters and writes
    ε to data/gates/noise.json. Returns {"check", "n_clean", "n_planted", "recall",
    "false_alarm_rate", "threshold", "table", "promote", "written"}."""
    raise not_built("gate_calibrate", PACKAGE)


def gate_fixtures(build: str = "", seeds: int = 3) -> dict:
    """CLI ``opus gates fixtures``: list the fixture sets, or with --build build their emitted and
    finished read-backs in Blender (cached)."""
    raise not_built("gates fixtures", PACKAGE)


def register(tool) -> None:
    for fn in (spec_check, defect_inject, gate_calibrate):
        tool(fn)


def add_cli(sub, groups) -> None:
    s = groups["spec"].add_parser("check", help="run the gates (T0-T2, T2b with --built)")
    s.add_argument("path")
    s.add_argument("--built", default="")
    s.add_argument("--tiers", default="T0-T2")
    s.add_argument("--profile", default="")
    s.add_argument("--parts", default="")
    s.add_argument("--all", action="store_true", help="run every tier even after a hard failure")

    g = groups["gates"]
    s = g.add_parser("inject", help="plant defects and measure each gate's recall")
    s.add_argument("gate", nargs="?", default="all")
    s.add_argument("--fixtures", default="ab6")
    s.add_argument("--seeds", type=int, default=8)
    s.add_argument("--n-per", type=int, default=200)
    s.add_argument("--check-armed", action="store_true")
    s.add_argument("--write-armed", action="store_true")

    s = g.add_parser("calibrate", help="sweep a check's threshold over clean and planted sets")
    s.add_argument("check")
    s.add_argument("--corpus", required=True)
    s.add_argument("--no-planted", action="store_true")
    s.add_argument("--noise", action="store_true")

    s = g.add_parser("fixtures", help="list fixture sets, or build their Blender read-backs")
    s.add_argument("--build", default="", help="a fixture set to build, e.g. ab6")
    s.add_argument("--seeds", type=int, default=3)


def run_cli(args) -> int | None:
    if args.cmd == "spec" and args.spec_cmd == "check":
        emit(spec_check(args.path, args.built, args.tiers, args.profile, args.parts, all=args.all))
        return 0
    if args.cmd != "gates":
        return None
    if args.gates_cmd == "inject":
        emit(defect_inject(args.gate, args.fixtures, args.seeds, args.n_per, args.check_armed, args.write_armed))
        return 0
    if args.gates_cmd == "calibrate":
        emit(gate_calibrate(args.check, args.corpus, planted=not args.no_planted, noise=args.noise))
        return 0
    if args.gates_cmd == "fixtures":
        emit(gate_fixtures(args.build, args.seeds))
        return 0
    return None
