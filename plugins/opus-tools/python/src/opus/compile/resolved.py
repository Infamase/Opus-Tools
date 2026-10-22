"""The resolved spec: what ``dims_resolve`` produces and the compiler consumes (docs/S0B_DESIGN.md
§4.8, K2). Plain JSON; these TypedDicts only describe it. JSON Schema:
``data/schema/opus.resolved.1.schema.json``. Pydantic never crosses into ``opus.compile`` (K1),
so Blender's Python can import this module.
"""

# No ``from __future__ import annotations`` here: TypedDict reads NotRequired from evaluated
# annotations.
from typing import NotRequired, TypedDict

RESOLVED_FORMAT = "opus.resolved/1"
DIM_UNITS = ("m", "ratio", "deg", "count", "kg")
DIM_TAGS = ("measured", "derived", "recalled", "user", "design")
DIM_KINDS = ("table", "record", "range", "expr", "profile", "user", "design")
PLACEMENTS = ("attach", "squeeze", "translate", "reflect", "orient")
ORIGINS = ("bottom_center", "none")  # or "socket:<name>"


class RDim(TypedDict):
    value: float
    min: float
    max: float
    unit: str        # "m" | "ratio" | "deg" | "count" | "kg"
    src: str         # human-readable provenance
    tag: str         # measured | derived | recalled | user | design
    kind: str        # table | record | range | expr | profile | user | design
    path: str        # "/dims/<name>"
    licence_id: str | None
    measure: NotRequired[str]          # "<part>:<measure key>" (§4.6)
    tol: NotRequired[float]            # relative tolerance for dim_measure
    int: NotRequired[bool]
    sanity: NotRequired[list[float]]   # resolved [lo, hi]


class RCamera(TypedDict):
    name: str
    projection: str
    vfov_deg: float
    ortho_h: float
    res_w: int
    res_h: int
    d_close: float
    d_typical: float
    d_far: float
    near_m: float
    scale: float
    view: str
    elevation_deg: float
    viewmodel: bool    # viewmodel picks contact_fp_m (§9.2)


class RFeature(TypedDict):
    rank: int
    id: str
    parts: list[str]
    views: list[str]
    min_px: float


class RPart(TypedDict):
    name: str
    src: str
    builder: NotRequired[str]      # absent for reflect parts
    params: NotRequired[dict]      # dim name, expr string, "@<attr>", "auto", preset word, profile key
    place: dict | None             # {"attach"|"squeeze"|"translate"|"reflect": {...}} | {"orient": word}; None = root at origin
    array: dict | None             # {"radial": {...}} | {"linear": {...}}
    material: str
    edges: dict                    # {"cutting": "sharp", ...}
    post_eval: bool


class ResolvedSpec(TypedDict):
    resolved: str                  # "opus.resolved/1"
    id: str
    rev: int
    kind: str
    category: str
    style: str
    seed: int
    tables_version: str
    camera: RCamera
    origin: str                    # "bottom_center" | "socket:<name>" | "none"
    wielder: dict[str, float]      # "wielder.hand_length" -> m; {} without a wielder
    features: list[RFeature]
    dims: dict[str, RDim]
    profiles: dict[str, dict]      # literal param string -> that one resolved variant (§14.2)
    parts: list[RPart]
    relations: list[dict]          # as written; EvalMesh.relations holds the expansion
    sockets: dict[str, dict]       # name -> {"ref": "part:anchor"} | {"grip": part, "center": float, "palm": word, "up": word, "hand": "r|l"}
    joints: dict[str, dict]        # name -> {"part", "type", "anchor", "axis", "limits_deg": [lo, hi]}
    gates: dict                    # merged thresholds: profiles.json < bible < spec overrides (§9.2)
    provenance: dict               # §5.1


def camera_env(cam: RCamera) -> dict[str, float]:
    """The ``camera.*`` names expressions may read (§4.4): pixels per metre at d_close,
    d_typical and d_far (``opus.camera.px_per_m``; ortho: ``ortho_px_per_m``), and the bevel
    width at d_close (``opus.camera.bevel_width``: 1.5 px, no thickness clamp)."""
    from opus import camera

    def ppm(d: float) -> float:
        if cam["projection"] == "ortho":
            return camera.ortho_px_per_m(cam["ortho_h"], cam["res_h"])
        return camera.px_per_m(d, cam["vfov_deg"], cam["res_h"])

    close = ppm(cam["d_close"])
    return {"camera.ppm_close": close, "camera.ppm_typical": ppm(cam["d_typical"]),
            "camera.ppm_far": ppm(cam["d_far"]), "camera.bevel_close": camera.bevel_width(close)}


def dims_env(resolved: ResolvedSpec) -> dict[str, float]:
    """dims + wielder + camera values as one expression environment."""
    env = {name: float(d["value"]) for name, d in resolved["dims"].items()}
    env.update({k: float(v) for k, v in resolved.get("wielder", {}).items()})
    env.update(camera_env(resolved["camera"]))
    return env
