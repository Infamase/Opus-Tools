"""Preview tool (WP-C): ``spec_preview``; CLI ``opus spec preview`` (docs/S0B_DESIGN.md §8, §15).
WP0 stub: every call raises "not built yet" until WP-C replaces the bodies.
"""

from __future__ import annotations

from opus.tools import emit, not_built

PACKAGE = "WP-C"
DEFAULT_VIEWS = "front,right,back,top,three_quarter"


def spec_preview(path: str, views: str = DEFAULT_VIEWS, size: int = 1024, seed: int = -1) -> list:
    """Evaluate a spec without Blender and draw its blueprint sheet: front, right, back and top
    orthographic views at one scale with part outlines, landmark lines, a 0.1 m / 1 m grid, as-built
    sizes, a 1.8 m figure, a three_quarter view and game-size insets at d_typical and d_far, plus
    the feature-size lint (feature_px_game). views: comma-separated; size: sheet pixels; seed -1 =
    the spec's. Returns [sheet image, {"sheet", "masks": {view: png}, "hash", "tris", "parts":
    [{"name","size_m","px_close","px_far","tier","tris"}], "lint": findings}]."""
    raise not_built("spec_preview", PACKAGE)


def register(tool) -> None:
    tool(spec_preview)


def add_cli(sub, groups) -> None:
    s = groups["spec"].add_parser("preview", help="blueprint sheet and masks from the evaluator (no Blender)")
    s.add_argument("path")
    s.add_argument("--views", default=DEFAULT_VIEWS)
    s.add_argument("--size", type=int, default=1024)
    s.add_argument("--seed", type=int, default=-1)


def run_cli(args) -> int | None:
    if args.cmd == "spec" and args.spec_cmd == "preview":
        out = spec_preview(args.path, args.views, args.size, args.seed)
        emit(out[-1] if isinstance(out, list) else out)
        return 0
    return None
