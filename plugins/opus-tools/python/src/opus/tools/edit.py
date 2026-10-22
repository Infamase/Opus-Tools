"""Spec editing tool (WP-G): ``spec_edit``; CLI ``opus spec edit`` (docs/S0B_DESIGN.md §10, §15).
WP0 stub: every call raises "not built yet" until WP-G replaces the bodies.
"""

from __future__ import annotations

from opus.tools import emit, not_built

PACKAGE = "WP-G"
MODES = ("single", "joint")


def spec_edit(path: str, why: str, patch: str = "", edit: str = "", keep: str = "", mode: str = "single",
              dials: str = "", tag: str = "", dry_run: bool = False, by_user: bool = False) -> str:
    """Change a spec and keep the change only if the gates say it is better (lexicographic: no
    armed hard check that passed may fail; fewer hard failures; then a lower hard magnitude; then a
    lower soft score). why: required; cite the finding you fix as "finding:<check>[:<part>]" (needed
    to set a design dim's value). patch: RFC 6902 JSON (replace, add, remove, test); edit:
    "<dim> = 0.9; <dim> *= 1.1; <dim>.style_mult = 1.2; seed = 3"; keep: relation indices to hold;
    mode: single | joint (joint: Nelder-Mead over up to 3 dials, comma-separated); tag: "locked" runs
    lock(); dry_run: return the candidate's findings and write nothing; by_user: the user asked for
    this change. Parts outside the edit's dependency closure must not change (edit_locality).
    Returns {"accepted", "rule", "rev", "diff", "locality", "findings" (labelled improved,
    unchanged, regressed, new, resolved), "archive", "coupled", "dry_run"}."""
    raise not_built("spec_edit", PACKAGE)


def register(tool) -> None:
    tool(spec_edit)


def add_cli(sub, groups) -> None:
    s = groups["spec"].add_parser("edit", help="change a spec; kept only if the gates improve")
    s.add_argument("path")
    s.add_argument("--why", required=True)
    s.add_argument("--patch", default="", help="RFC 6902 operations as JSON")
    s.add_argument("--edit", default="", help='"<dim> = 0.9; <dim> *= 1.1; seed = 3"')
    s.add_argument("--keep", default="")
    s.add_argument("--mode", default="single", choices=MODES)
    s.add_argument("--dials", default="")
    s.add_argument("--tag", default="")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--by-user", action="store_true")


def run_cli(args) -> int | None:
    if args.cmd == "spec" and args.spec_cmd == "edit":
        emit(spec_edit(args.path, args.why, args.patch, args.edit, args.keep, args.mode, args.dials, args.tag,
                       dry_run=args.dry_run, by_user=args.by_user))
        return 0
    return None
