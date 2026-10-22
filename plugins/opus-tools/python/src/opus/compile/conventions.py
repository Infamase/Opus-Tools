"""Frames, sides, names, anchors and raster conventions (docs/S0B_DESIGN.md §4.1-4.2).

World: metres, +Z up, -Y front, +X = the object's left (an object faces -Y; in the front view
its left side appears on the viewer's right). Sides: L = +X, R = -X, F = -Y, B = +Y, C = on the
centre plane. Builders work in fixed canonical frames; the ``plane`` (extrude) and ``axis``
(lathe, station_loft) parameters become a proper rotation ``R_b`` folded into the part's matrix.

Raster: pixel (i, j) has its centre at (i + 0.5, j + 0.5), row 0 on top (y down); sensor fit
VERTICAL; ``ortho_h`` is the visible world height; depth is view-space distance along -Z_cam,
interpolated perspective-correctly. Tie rule: a centre on an edge is inside when the edge's
inward normal (image coordinates) has nx > 0, or nx = 0 and ny < 0 (left and bottom edges).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from opus.compile import fmath
from opus.compile.fmath import IDENTITY16

# ---------------------------------------------------------------- frames, sides, names

SIDES = {"L": (1.0, 0.0, 0.0), "R": (-1.0, 0.0, 0.0), "F": (0.0, -1.0, 0.0), "B": (0.0, 1.0, 0.0), "C": None}
NAME_RE = r"^(?P<role>[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)*)_(?P<side>[LRCFB])(?P<index>\d{2})?$"
GROUND = "ground"  # reserved virtual part: the z = 0 plane; anchor ground:top_c at the origin, n = +Z, t = +X
RESERVED_PREFIXES = ("UCX_", "UBX_", "USP_", "UCP_", "SOCKET_", "SM_", "ground")
# reflect planes: which side letters swap (T0 reflect_sides); xy keeps the side
REFLECT_SIDE_SWAP = {"yz": {"L": "R", "R": "L"}, "xz": {"F": "B", "B": "F"}, "xy": {}}
REFLECT_PLANES = ("yz", "xz", "xy")

_NAME = re.compile(NAME_RE)


def parse_name(name: str) -> dict | None:
    """{"role", "side", "index"} for a valid part name, else None (reserved names are invalid)."""
    if is_reserved(name):
        return None
    m = _NAME.match(name)
    return m.groupdict() if m else None


def is_reserved(name: str) -> bool:
    return name == GROUND or any(name.startswith(p) for p in RESERVED_PREFIXES)


def _r(cols) -> tuple[float, ...]:
    """Rotation whose columns are where canonical x, y, z go."""
    x, y, z = cols
    return fmath.from_columns(x, y, z)


# Canonical builder frames -> R_b (where canonical x, y, z go), §4.1 table
R_B_EXTRUDE = {
    "XY": IDENTITY16,
    "XZ": _r(((1, 0, 0), (0, 0, 1), (0, -1, 0))),   # x -> +X, y -> +Z, z -> -Y
    "YZ": _r(((0, -1, 0), (0, 0, 1), (-1, 0, 0))),  # x -> -Y, y -> +Z, z -> -X
}
R_B_AXIS = {
    "z": IDENTITY16,
    "x": _r(((0, 0, -1), (0, 1, 0), (1, 0, 0))),    # x -> -Z, y -> +Y, z -> +X
    "y": _r(((1, 0, 0), (0, 0, -1), (0, 1, 0))),    # x -> +X, y -> -Z, z -> +Y
}
BUILDERS = ("box", "superquadric", "extrude", "lathe", "station_loft")


def r_b(builder: str, params: dict | None = None) -> tuple[float, ...]:
    """The fixed rotation R_b for a builder and its ``plane`` / ``axis`` parameter."""
    params = params or {}
    if builder == "extrude":
        plane = params.get("plane", "XY")
        if plane not in R_B_EXTRUDE:
            raise ValueError(f"extrude plane must be one of {sorted(R_B_EXTRUDE)}; got {plane!r}")
        return R_B_EXTRUDE[plane]
    if builder in ("lathe", "station_loft"):
        axis = params.get("axis", "z")
        if axis not in R_B_AXIS:
            raise ValueError(f"{builder} axis must be one of {sorted(R_B_AXIS)}; got {axis!r}")
        return R_B_AXIS[axis]
    return IDENTITY16


# orient (roots only): M = ORIENT[word] · R_b. "front" lays canonical +Z along -Y (Rx +90°).
ORIENT = {
    "up": IDENTITY16,
    "front": fmath.rot_axis("x", 1),   # Z -> -Y
    "back": fmath.rot_axis("x", -1),   # Z -> +Y
    "left": fmath.rot_axis("y", 1),    # Z -> +X
    "right": fmath.rot_axis("y", -1),  # Z -> -X
    "down": fmath.rot_axis("x", 2),    # Z -> -Z
}
RX180 = fmath.rot_axis("x", 2)
S_LOCAL = (-1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)  # canonical x mirror


def mirror(plane: str, through=(0.0, 0.0, 0.0)) -> tuple[float, ...]:
    """The world mirror S through ``plane`` (yz, xz or xy) and the point ``through``."""
    if plane not in REFLECT_PLANES:
        raise ValueError(f"reflect plane must be one of {REFLECT_PLANES}; got {plane!r}")
    k = {"yz": 0, "xz": 1, "xy": 2}[plane]
    m = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    m[5 * k] = -1.0
    m[4 * k + 3] = 2.0 * float(through[k])
    return tuple(m)


def anchor_frame(p, n, t) -> tuple[float, ...]:
    """The anchor frame as a matrix: columns (t, n × t, n), translation p."""
    y = (n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2], n[0] * t[1] - n[1] * t[0])
    return fmath.from_columns(t, y, n, p)


# ---------------------------------------------------------------- anchor grammar

STATIC_ANCHORS = ("top_c", "bottom_c", "front_c", "back_c", "left_c", "right_c", "top_back", "top_front",
                  "bottom_back", "bottom_front", "rim_+x", "rim_-x", "rim_+y", "rim_-y", "inner_c", "inner_corner")
FAMILIES = ("section_x", "section_y", "section_z", "ring", "side_+x", "side_-x", "side_+y", "side_-y")
ALLOWED_FRACS = ("0/16", "8/16", "16/16")  # literal fractions the grammar allows (T0 free_anchor)
ALLOWED_SIXTEENTHS = ("0", "8", "16")      # literal uvw components the grammar allows
_DIM = r"[a-z_][a-z0-9_]*"
_STATIC = "|".join(re.escape(a) for a in STATIC_ANCHORS)
_FAM = "|".join(re.escape(f) for f in FAMILIES)
_FRAC = r"0/16|8/16|16/16|" + _DIM
_C = r"0|8|16|" + _DIM
ANCHOR_RE = (rf"^(?:(?P<static>{_STATIC})|(?P<fam>{_FAM})@(?P<frac>{_FRAC})"
             rf"|uvw:(?P<u>{_C}),(?P<v>{_C}),(?P<w>{_C})|(?P<profile>[a-z][a-z0-9_]*))$")
# The same shapes with any integer sixteenth, so T0 can say free_anchor instead of a syntax error.
ANCHOR_SYNTAX_RE = (rf"^(?:(?P<static>{_STATIC})|(?P<fam>{_FAM})@(?P<frac>\d+/16|{_DIM})"
                    rf"|uvw:(?P<u>\d+|{_DIM}),(?P<v>\d+|{_DIM}),(?P<w>\d+|{_DIM})|(?P<profile>[a-z][a-z0-9_]*))$")
_ANCHOR = re.compile(ANCHOR_RE)
_ANCHOR_SYNTAX = re.compile(ANCHOR_SYNTAX_RE)

_BOX = {"static": ("top_c", "bottom_c", "front_c", "back_c", "left_c", "right_c",
                   "top_back", "top_front", "bottom_back", "bottom_front"),
        "families": ("section_x", "section_y", "section_z")}
BUILDER_ANCHORS: dict[str, dict[str, tuple[str, ...]]] = {
    "box": _BOX,
    "superquadric": _BOX,
    "extrude": {"static": ("top_c", "bottom_c", "front_c", "back_c", "left_c", "right_c"), "families": ()},
    "lathe": {"static": ("bottom_c", "top_c", "rim_+x", "rim_-x", "rim_+y", "rim_-y"), "families": ("ring",)},
    "station_loft": {"static": ("bottom_c", "top_c"), "families": ("ring", "side_+x", "side_-x", "side_+y", "side_-y")},
}
PRIM_ANCHORS = {"rect_ring": ("inner_c",), "rect_u": ("inner_c",), "angle_l": ("inner_corner",)}
GROUND_ANCHORS = ("top_c",)


def split_ref(ref: str) -> tuple[str, str]:
    """"part:anchor" -> (part, anchor), split at the first ":" (so "p:uvw:8,0,8" works)."""
    part, sep, anchor = ref.partition(":")
    if not sep or not part or not anchor:
        raise ValueError(f"an anchor reference is part:anchor; got {ref!r}")
    return part, anchor


def parse_anchor(anchor: str, strict: bool = True) -> dict:
    """Parse an anchor name: {"kind": "static" | "family" | "uvw" | "profile", "name",
    "frac" (family), "uvw" (3 strings)}. ``strict`` applies the §4.1 grammar (sixteenths 0, 8,
    16 only); ``strict=False`` accepts any integer sixteenth (for T0 free_anchor messages)."""
    m = (_ANCHOR if strict else _ANCHOR_SYNTAX).match(anchor)
    if not m:
        raise ValueError(f"not an anchor: {anchor!r} (static name, family@frac, uvw:a,b,c or a profile anchor)")
    g = m.groupdict()
    if g["static"]:
        return {"kind": "static", "name": g["static"]}
    if g["fam"]:
        return {"kind": "family", "name": g["fam"], "frac": g["frac"]}
    if g["u"] is not None:
        return {"kind": "uvw", "name": "uvw", "uvw": (g["u"], g["v"], g["w"])}
    return {"kind": "profile", "name": g["profile"]}


def free_sixteenths(anchor: str) -> list[str]:
    """Literal sixteenths the grammar forbids (T0 free_anchor), e.g. ["4/16"] for "ring@4/16"."""
    try:
        a = parse_anchor(anchor, strict=False)
    except ValueError:
        return []
    if a["kind"] == "family" and a["frac"][0].isdigit() and a["frac"] not in ALLOWED_FRACS:
        return [a["frac"]]
    if a["kind"] == "uvw":
        return [c for c in a["uvw"] if c[0].isdigit() and c not in ALLOWED_SIXTEENTHS]
    return []


def anchor_dims(anchor: str) -> list[str]:
    """Ratio-dim names an anchor reads (family fraction or uvw components)."""
    a = parse_anchor(anchor, strict=False)
    vals = [a["frac"]] if a["kind"] == "family" else list(a.get("uvw", ()))
    return [v for v in vals if not v[0].isdigit()]


def literal_fraction(text: str) -> float | None:
    """"8/16" -> 0.5, "16" (a uvw component) -> 1.0; None for a dim name."""
    if text[0].isdigit():
        num = text.split("/", 1)[0]
        return int(num) / 16.0
    return None


def builder_anchor_names(builder: str, profile=None) -> dict[str, frozenset[str]]:
    """Anchor names a part can use: {"static": names used alone, "families": names used with
    @frac}; ``uvw:a,b,c`` is valid on every builder. ``profile`` is the resolved profile dict
    (its ``anchors`` join "static") or a prim key such as "prim:rect_u" (adds inner_c)."""
    if builder == GROUND:
        return {"static": frozenset(GROUND_ANCHORS), "families": frozenset()}
    if builder not in BUILDER_ANCHORS:
        raise ValueError(f"unknown builder {builder!r}; builders: {list(BUILDER_ANCHORS)}")
    static = set(BUILDER_ANCHORS[builder]["static"])
    if isinstance(profile, str) and profile.startswith("prim:"):
        static |= set(PRIM_ANCHORS.get(profile[5:], ()))
    elif isinstance(profile, dict):
        static |= set(profile.get("anchors") or {})
        prim = profile.get("prim")
        if prim:
            static |= set(PRIM_ANCHORS.get(prim, ()))
    return {"static": frozenset(static), "families": frozenset(BUILDER_ANCHORS[builder]["families"])}


def anchor_ok(builder: str, anchor: str, profile=None) -> bool:
    """Whether ``anchor`` exists on a part built by ``builder`` (grammar and builder table)."""
    try:
        a = parse_anchor(anchor)
    except ValueError:
        return False
    if a["kind"] == "uvw":
        return builder != GROUND
    names = builder_anchor_names(builder, profile)
    if a["kind"] == "family":
        return a["name"] in names["families"]
    return a["name"] in names["static"]


# ---------------------------------------------------------------- raster conventions

VIEWS = {"front": (0.0, 0.0), "right": (90.0, 0.0), "back": (180.0, 0.0), "left": (270.0, 0.0),
         "top": (0.0, 90.0), "bottom": (0.0, -90.0), "three_quarter": (38.66, 26.6),
         "three_quarter_back": (218.66, 26.6)}   # (azimuth, elevation) in degrees = opus_bl.inspect3d.NAMED_VIEWS
PSEUDO_VIEWS = ("game",)    # the camera profile's own view at d_typical (views.game_camera)
LEVELS = ("close", "typical", "far")                       # = opus.camera.LEVELS
# direction from the target to the camera, as opus_bl.inspect3d.aim: d = (sin az cos el, -cos az cos el, sin el)
TIE_RULE = "left+bottom"    # probed on Mesa llvmpipe 25.2.8 (OpenGL 4.5)
JITTER_PX = (0.137, 0.291)  # anti-tie camera shift for consistency renders (x right, y down)


def view_direction(view) -> tuple[float, float, float]:
    """Unit direction from the target toward the camera for a named view or (azimuth, elevation)."""
    if isinstance(view, str):
        if view not in VIEWS:
            raise ValueError(f"unknown view {view!r}; views: {sorted(VIEWS)}")
        view = VIEWS[view]
    az, el = math.radians(float(view[0])), math.radians(float(view[1]))
    return (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))


@dataclass(frozen=True)
class RasterCamera:
    projection: str          # "persp" | "ortho"
    width: int               # full-frame pixels
    height: int
    vfov_deg: float = 0.0    # persp only; sensor fit VERTICAL (Blender: data.angle_y)
    ortho_h: float = 0.0     # ortho only: visible world height in m (Blender: ortho_scale)
    view: tuple[float, ...] = IDENTITY16   # row-major world -> camera; camera looks down -Z, +Y up, +X right
    crop: tuple[int, int, int, int] | None = None   # (x0, y0, w, h) in full-frame pixels, y down
    near: float = 1e-3
    far: float = 1e4

    def __post_init__(self):
        if self.projection not in ("persp", "ortho"):
            raise ValueError(f"projection must be persp or ortho; got {self.projection!r}")
        if self.width < 1 or self.height < 1:
            raise ValueError(f"a camera needs a positive size; got {self.width}x{self.height}")
        if self.projection == "persp" and not 0 < self.vfov_deg < 180:
            raise ValueError(f"a perspective camera needs 0 < vfov_deg < 180; got {self.vfov_deg}")
        if self.projection == "ortho" and not self.ortho_h > 0:
            raise ValueError(f"an orthographic camera needs ortho_h > 0; got {self.ortho_h}")
        if len(self.view) != 16:
            raise ValueError("view is 16 floats, row-major world -> camera")

    def focal_px(self) -> float:
        """Perspective focal length in pixels: (H/2)/tan(vfov/2)."""
        return (self.height / 2.0) / math.tan(math.radians(self.vfov_deg) / 2.0)

    def ppm(self, depth: float | None = None) -> float:
        """Pixels per metre: ortho H/ortho_h; persp (H/2)/tan(vfov/2)/depth."""
        if self.projection == "ortho":
            return self.height / self.ortho_h
        if not depth:
            raise ValueError("a perspective camera's pixels per metre need a depth")
        return self.focal_px() / float(depth)

    def out_shape(self) -> tuple[int, int]:
        """(h, w) of the crop, else (height, width)."""
        if self.crop is not None:
            return (int(self.crop[3]), int(self.crop[2]))
        return (int(self.height), int(self.width))

    def to_dict(self) -> dict:
        return {"projection": self.projection, "width": int(self.width), "height": int(self.height),
                "vfov_deg": float(self.vfov_deg), "ortho_h": float(self.ortho_h),
                "view": [float(v) for v in self.view],
                "crop": None if self.crop is None else [int(v) for v in self.crop],
                "near": float(self.near), "far": float(self.far)}

    @staticmethod
    def from_dict(d: dict) -> RasterCamera:
        crop = d.get("crop")
        return RasterCamera(projection=d["projection"], width=int(d["width"]), height=int(d["height"]),
                            vfov_deg=float(d.get("vfov_deg", 0.0)), ortho_h=float(d.get("ortho_h", 0.0)),
                            view=tuple(float(v) for v in d.get("view", IDENTITY16)),
                            crop=None if crop is None else tuple(int(v) for v in crop),
                            near=float(d.get("near", 1e-3)), far=float(d.get("far", 1e4)))


def _norm(v) -> tuple[float, float, float]:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n == 0.0:
        raise ValueError("zero-length direction")
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def look_view(target, d, distance) -> tuple[float, ...]:
    """Camera at target + d*distance looking at target. x_cam = normalize(cross(-d, up)), y_cam =
    cross(x_cam, -d), z_cam = d, with up = +Z; for |d.z| > 0.999 up = +Y (top view: image up = +Y)."""
    d = _norm(d)
    up = (0.0, 1.0, 0.0) if abs(d[2]) > 0.999 else (0.0, 0.0, 1.0)
    nd = (-d[0], -d[1], -d[2])
    x = _norm(_cross(nd, up))
    y = _cross(x, nd)
    c = (float(target[0]) + d[0] * distance, float(target[1]) + d[1] * distance, float(target[2]) + d[2] * distance)
    rows = (x, y, d)
    out = []
    for r in rows:
        out += [r[0], r[1], r[2], -(r[0] * c[0] + r[1] * c[1] + r[2] * c[2])]
    return tuple(out + [0.0, 0.0, 0.0, 1.0])


def project(cam: RasterCamera, P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """World points (N,3) -> pixel x (right), pixel y (down) in crop coordinates, depth (m, > 0 in front).
    c = apply(view, P); depth = -c_z
    ortho: k = H/ortho_h; x = W/2 + c_x*k - x0; y = H/2 - c_y*k - y0
    persp: f = (H/2)/tan(vfov/2); x = W/2 + f*c_x/depth - x0; y = H/2 - f*c_y/depth - y0"""
    c = fmath.apply(cam.view, P)
    depth = -c[:, 2]
    x0, y0 = (cam.crop[0], cam.crop[1]) if cam.crop is not None else (0, 0)
    W, H = cam.width, cam.height
    if cam.projection == "ortho":
        k = H / cam.ortho_h
        x = W / 2 + c[:, 0] * k - x0
        y = H / 2 - c[:, 1] * k - y0
    else:
        f = cam.focal_px()
        with np.errstate(divide="ignore", invalid="ignore"):
            x = W / 2 + f * c[:, 0] / depth - x0
            y = H / 2 - f * c[:, 1] / depth - y0
    return x, y, depth


def blender_border(cam: RasterCamera) -> dict | None:
    """Render-border settings for a crop (Blender's border is bottom-up), else None."""
    if cam.crop is None:
        return None
    x0, y0, w, h = cam.crop
    W, H = cam.width, cam.height
    return {"use_border": True, "use_crop_to_border": True, "border_min_x": x0 / W, "border_max_x": (x0 + w) / W,
            "border_min_y": 1 - (y0 + h) / H, "border_max_y": 1 - y0 / H}
