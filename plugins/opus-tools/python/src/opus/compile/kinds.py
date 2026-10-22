"""The evaluator contract for every kind (docs/S0B_DESIGN.md §7.1).

What each level returns: ``proxy2d`` -> :class:`Proxy2D`; ``frames`` and ``transforms`` ->
EvalMesh with ``frames`` (F, P, 16); ``heightfield`` -> EvalMesh with ``fields["height"]`` (and its
grid triangles at ``build``); ``skeleton`` -> EvalMesh with ``fields["skeleton"]``; ``contract`` ->
EvalMesh without triangles and the contract in ``extra``; every other level -> EvalMesh with
triangles. S0b evaluates ``assembly`` only; the others raise :class:`KindNotAvailable`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PROXY2D_FORMAT = "opus.proxy2d/1"


class KindNotAvailable(ValueError):           # a ValueError, so MCP shows its message to Claude
    def __init__(self, kind: str, sprint: str):
        self.kind, self.sprint = kind, sprint
        super().__init__(f"kind {kind!r} is not available yet: it arrives in sprint {sprint} "
                         "(S0b evaluates assembly only)")


KINDS = {"assembly": "S0b", "body.human": "S1", "body.creature": "S2", "garment": "S7", "harness": "S7",
         "terrain": "S9", "tree": "S9", "building": "S10", "kit": "S10", "layout": "S10",
         "motion": "S5", "face": "S10", "hair": "S10"}
LEVELS = {"assembly": ("fit", "build"), "body.human": ("fit", "build"),
          "body.creature": ("proxy2d", "confirm", "build"), "garment": ("envelope", "build"),
          "harness": ("envelope", "build"), "terrain": ("heightfield", "build"), "tree": ("skeleton", "build"),
          "building": ("fit", "build"), "kit": ("fit", "build"), "layout": ("transforms",),
          "motion": ("frames",), "face": ("contract",), "hair": ("contract",)}
POST_EVAL_KINDS = {"garment", "harness", "tree", "face", "hair"}
AVAILABLE = ("assembly",)  # kinds this release evaluates
# what each level returns (the docstring's table as data)
LEVEL_RETURNS = {"proxy2d": "Proxy2D", "frames": "EvalMesh.frames", "transforms": "EvalMesh.frames",
                 "heightfield": "EvalMesh.fields[height]", "skeleton": "EvalMesh.fields[skeleton]",
                 "contract": "EvalMesh.extra"}


def check_kind_level(kind: str, level: str) -> None:
    """Raise ValueError for an unknown kind or a level the kind does not have, and
    KindNotAvailable for a kind from a later sprint."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; kinds: {sorted(KINDS)}")
    if level not in LEVELS[kind]:
        raise ValueError(f"kind {kind!r} has levels {LEVELS[kind]}, not {level!r}")
    if kind not in AVAILABLE:
        raise KindNotAvailable(kind, KINDS[kind])


@dataclass
class Prim2D:
    part: str
    kind: str                      # "ellipse" | "stadium" | "polygon"
    params: dict                   # centre, axes, angle | end points, radius | points


@dataclass
class Proxy2D:                     # body.creature level "proxy2d" (S2): projected primitives per view
    views: dict[str, list[Prim2D]]
    smooth_k: float
    source: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"format": PROXY2D_FORMAT, "smooth_k": float(self.smooth_k), "source": self.source,
                "views": {v: [{"part": p.part, "kind": p.kind, "params": p.params} for p in prims]
                          for v, prims in self.views.items()}}

    @staticmethod
    def from_json(d) -> Proxy2D:
        if d.get("format", PROXY2D_FORMAT) != PROXY2D_FORMAT:
            raise ValueError(f"not a {PROXY2D_FORMAT} document: format {d.get('format')!r}")
        return Proxy2D(views={v: [Prim2D(p["part"], p["kind"], dict(p["params"])) for p in prims]
                              for v, prims in d["views"].items()},
                       smooth_k=float(d["smooth_k"]), source=dict(d.get("source") or {}))
