"""Camera profiles and the numbers they decide (docs/OVERHAUL.md §2.2).

One formula, ``px_per_m = H / (2·d·tan(vfov/2))``, says how many screen pixels a meter
covers at distance d. From it follow the smallest feature worth modelling, circle segment
counts, bevel widths, texel density, LOD switch distances and fracture sizes.

The presets are defaults only. The project's real camera settings live in the bible's
``camera`` section and override them (``opus.bible.camera_profile``). The first-person
view-model camera is never assumed: without one in the bible a check uses a fallback that
says so.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace

# Johnson's criteria (Johnson 1958): line pairs across a target at 50% probability; 1 lp = 2 px.
# Derived for whole targets in sensor imagery, so they are a calibration anchor, not a pass mark.
JOHNSON_LP = {"detect": 1.0, "orient": 1.4, "recognize": 4.0, "identify": 6.4}
JOHNSON_PX = {k: 2 * v for k, v in JOHNSON_LP.items()}

DETAIL_GEOMETRY_PX = 3.0  # >= 3 px on screen: model it
DETAIL_MAP_PX = 1.0  # 1-3 px: normal map or trim; < 1 px: omit
LEVELS = ("close", "typical", "far")


# ---------------------------------------------------------------- formulas

def vfov_from_hfov(hfov_deg: float, aspect: float = 16 / 9) -> float:
    """Vertical FOV for a horizontal one: 2·atan(tan(hfov/2)/aspect). 90° at 16:9 → 58.7°."""
    return math.degrees(2 * math.atan(math.tan(math.radians(hfov_deg) / 2) / aspect))


def hfov_from_vfov(vfov_deg: float, aspect: float = 16 / 9) -> float:
    return math.degrees(2 * math.atan(math.tan(math.radians(vfov_deg) / 2) * aspect))


def px_per_m(d: float, vfov_deg: float, res_h: int = 1080) -> float:
    """Screen pixels per meter at distance ``d`` (m) for a perspective camera."""
    return res_h / (2 * d * math.tan(math.radians(vfov_deg) / 2))


def ortho_px_per_m(view_height_m: float, res_h: int = 1080) -> float:
    """Screen pixels per meter for an orthographic camera showing ``view_height_m`` vertically."""
    return res_h / view_height_m


def on_screen_px(size_m: float, ppm: float) -> float:
    return size_m * ppm


def min_feature_m(px: float, ppm: float) -> float:
    """The world size that covers ``px`` pixels: 4 px at 274 px/m = 14.6 mm."""
    return px / ppm


def detail_tier(size_m: float, ppm: float) -> str:
    """geometry (>= 3 px), map (1-3 px: normal or trim) or omit (< 1 px), judged at d_closest."""
    px = size_m * ppm
    if px >= DETAIL_GEOMETRY_PX:
        return "geometry"
    return "map" if px >= DETAIL_MAP_PX else "omit"


def circle_segments(radius_m: float, ppm: float, eps_px: float = 0.5, min_sides: int = 3) -> int:
    """Sides for a round section whose sagitta error stays under ``eps_px`` on screen:
    n = ceil(π / acos(1 - ε/r)), ε = eps_px / px_per_m."""
    x = 1 - (eps_px / ppm) / radius_m
    if x <= -1:
        return min_sides
    return max(min_sides, math.ceil(math.pi / math.acos(x) - 1e-9))


def bevel_width(ppm: float, thickness_m: float | None = None, px: float = 1.5) -> float:
    """Bevel width: ``px`` pixels on screen, clamped to 2-25% of the part's thickness when given."""
    w = px / ppm
    if thickness_m:
        w = min(max(w, 0.02 * thickness_m), 0.25 * thickness_m)
    return w


def texel_density(ppm: float) -> int:
    """Texels per meter: px_per_m at d_closest, snapped to the nearest power of two in log scale."""
    return 2 ** round(math.log2(ppm))


def texture_size(td: float, area_m2: float, eta: float = 0.7, pow2: bool = True) -> float:
    """Texture side for ``area_m2`` of surface at density ``td``: R = TD·√(A/η), η = UV packing
    efficiency (0.6-0.75). Rounded up to a power of two unless ``pow2`` is off."""
    r = td * math.sqrt(area_m2 / eta)
    return 2 ** math.ceil(math.log2(r)) if pow2 else r


def bake_padding(mips: int | None = None, td: float | None = None, ppm_far: float | None = None) -> int:
    """Island padding in texels, 2^k for the k mip levels that stay visible. k is given, or
    derived from how far the texture is minified at the farthest distance (TD / px_per_m)."""
    if mips is None:
        if not (td and ppm_far):
            raise ValueError("give mips, or td and ppm_far")
        mips = max(0, math.ceil(math.log2(td / ppm_far) - 1e-9))
    return 2 ** int(mips)


def lod_switch_distance(error_m: float, vfov_deg: float, res_h: int = 1080, tau_px: float = 1.0) -> float:
    """Distance where a LOD with geometric error ``error_m`` shows ``tau_px`` of error:
    d = e·H / (2·tan(vfov/2)·τ). 1 cm at 1440p, vfov 58.7° → 12.8 m."""
    return error_m * res_h / (2 * math.tan(math.radians(vfov_deg) / 2) * tau_px)


def min_fracture_fragment(ppm: float, k_px: float = 8.0) -> float:
    """Smallest fracture fragment edge: k_px / px_per_m, with k_px 6-10 (heuristic)."""
    return k_px / ppm


def johnson(px: float) -> str:
    """The highest Johnson level ``px`` pixels across a target reach (50% probability)."""
    level = "below detection"
    for name, need in JOHNSON_PX.items():
        if px >= need:
            level = name
    return level


# ---------------------------------------------------------------- profiles

@dataclass
class CameraProfile:
    """A game camera: projection, FOV (on the engine's own axis), resolution and the distances
    at which assets are seen. View-model profiles add ``near_m`` and ``scale``."""

    name: str
    label: str = ""
    engine: str = "any"  # unreal | godot | unity | any
    projection: str = "persp"  # persp | ortho
    fov_axis: str = "vertical"  # horizontal (Unreal) | vertical (Godot, Unity)
    fov_deg: float = 60.0
    res_w: int = 1920
    res_h: int = 1080
    ortho_h: float = 0.0  # visible world height in m (ortho)
    distances: dict = field(default_factory=dict)  # close / typical / far, meters from the camera
    view: str = "front"  # the side of the subject the camera usually sees
    elevation_deg: float = 0.0  # camera height angle above the subject
    near_m: float = 0.0  # view-model near plane
    scale: float = 1.0  # view-model scale toward the camera (UE First Person Scale)
    viewmodel: bool = False
    fallback: bool = False  # True when a required setting was missing and a default stood in
    note: str = ""

    @property
    def aspect(self) -> float:
        return self.res_w / self.res_h

    @property
    def vfov_deg(self) -> float:
        return vfov_from_hfov(self.fov_deg, self.aspect) if self.fov_axis == "horizontal" else self.fov_deg

    @property
    def hfov_deg(self) -> float:
        return self.fov_deg if self.fov_axis == "horizontal" else hfov_from_vfov(self.fov_deg, self.aspect)

    def px_per_m(self, d: float | None = None) -> float:
        if self.projection == "ortho":
            return ortho_px_per_m(self.ortho_h, self.res_h)
        if not d:
            raise ValueError(f"camera {self.name}: a perspective camera needs a distance")
        return px_per_m(d, self.vfov_deg, self.res_h)

    def levels(self) -> list[tuple[str, float | None]]:
        """(name, distance) pairs to check; an orthographic camera has one scale."""
        if self.projection == "ortho":
            return [("screen", None)]
        return [(k, float(self.distances[k])) for k in LEVELS if self.distances.get(k)] + [
            (k, float(v)) for k, v in self.distances.items() if k not in LEVELS and v
        ]

    def derived(self) -> dict:
        """The numbers a modeller needs per distance."""
        rows = []
        for name, d in self.levels():
            ppm = self.px_per_m(d)
            row = {"level": name, "d_m": d, "px_per_m": round(ppm, 1),
                   "feature_4px_mm": round(min_feature_m(4, ppm) * 1000, 1),
                   "feature_13px_m": round(min_feature_m(13, ppm), 3)}
            if self.viewmodel and d:
                row["depth_m"] = round(d * self.scale, 3)  # where the scaled view-model renders
                row["inside_near_plane"] = bool(self.near_m and d * self.scale < self.near_m)
            rows.append(row)
        out = {"levels": rows}
        if rows:
            out["texel_density"] = texel_density(rows[0]["px_per_m"])
        return out

    def summary(self) -> dict:
        """The profile's settings that apply, plus the derived numbers."""
        skip = {"ortho_h"} if self.projection == "persp" else {"fov_axis", "fov_deg", "distances"}
        if not self.viewmodel:
            skip |= {"near_m", "scale", "viewmodel"}
        s = {k: v for k, v in asdict(self).items() if k not in skip and v not in ("", None) and v is not False}
        if self.projection == "persp":
            s["vfov_deg"] = round(self.vfov_deg, 2)
            s["hfov_deg"] = round(self.hfov_deg, 2)
        s.update(self.derived())
        return s


PRESETS: dict[str, CameraProfile] = {
    p.name: p
    for p in (
        CameraProfile("ue_tp_1080", "Unreal third person, 1080p, hfov 90 (vfov 58.7)", "unreal", fov_axis="horizontal",
                      fov_deg=90.0, distances={"close": 1.5, "typical": 3.5, "far": 15.0}),
        CameraProfile("ue_fp_1080", "Unreal first person (world camera), 1080p, hfov 90", "unreal", fov_axis="horizontal",
                      fov_deg=90.0, distances={"close": 1.0, "typical": 5.0, "far": 25.0}),
        CameraProfile("godot_tp", "Godot Camera3D default, 1080p, vfov 75 (keep height)", "godot", fov_deg=75.0,
                      distances={"close": 2.0, "typical": 6.0, "far": 20.0}),
        CameraProfile("unity_tp", "Unity Camera default, 1080p, vfov 60", "unity", fov_deg=60.0,
                      distances={"close": 1.5, "typical": 4.0, "far": 15.0}),
        CameraProfile("topdown", "Top-down, 1080p, vfov 60, looking down 60°", fov_deg=60.0, elevation_deg=60.0,
                      distances={"close": 8.0, "typical": 10.0, "far": 14.0}),
        CameraProfile("sidescroller", "Side-scroller, orthographic, 12 m tall view at 1080p", projection="ortho",
                      ortho_h=12.0, view="right"),
    )
}
VIEWMODEL_DISTANCES = {"close": 0.35, "typical": 0.45, "far": 0.7}
FIELDS = {f for f in CameraProfile.__dataclass_fields__} - {"name", "viewmodel", "fallback", "note"}


def preset(name: str) -> CameraProfile:
    if name not in PRESETS:
        raise ValueError(f"unknown camera profile {name!r}; presets: {sorted(PRESETS)}")
    return replace(PRESETS[name], distances=dict(PRESETS[name].distances))


def apply(profile: CameraProfile, fields: dict, name: str | None = None) -> CameraProfile:
    """``profile`` with the given fields replaced (distances merge per level)."""
    fields = dict(fields or {})
    fields.pop("base", None)
    unknown = set(fields) - FIELDS
    if unknown:
        raise ValueError(f"camera profile {name or profile.name}: unknown keys {sorted(unknown)}; allowed: {sorted(FIELDS)}")
    dist = {**profile.distances, **(fields.pop("distances", None) or {})}
    return replace(profile, name=name or profile.name, distances=dist, **fields)


def viewmodel(block: dict | None, world: CameraProfile) -> CameraProfile:
    """The first-person view-model camera from the bible's ``camera.viewmodel`` block. Without
    one, a fallback (the world camera's FOV, near 0.1 m, scale 1) that is labeled as such."""
    block = dict(block or {})
    base = replace(world, name="viewmodel", viewmodel=True, view="front", elevation_deg=0.0,
                   distances=dict(VIEWMODEL_DISTANCES), near_m=0.1, scale=1.0, projection="persp")
    if not block.get("fov_deg"):
        return replace(
            base, fallback=True,
            label=f"FALLBACK view-model: {world.name}'s FOV, near 0.1 m, scale 1 (not read from the project)",
            note="viewmodel missing: set camera.viewmodel in opus.project.yaml from the project's first-person "
                 "settings (Unreal: First Person Field Of View and Scale; Godot/Unity: the second camera's FOV and near)",
        )
    vm = apply(base, block, name="viewmodel")
    return replace(vm, label=vm.label if block.get("label") else f"view-model, {vm.fov_axis} FOV {vm.fov_deg:g}")
