"""The project bible: one per-project file of style rules and budgets every tool reads.

``opus.project.yaml`` lives at the game's root (next to ``project.godot``). Missing keys fall
back to the defaults below, so a bible can start nearly empty and grow.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from opus.paths import BIBLE_NAME, find_project_root

DEFAULTS: dict = {
    "project": "",
    "styles": [],  # any of: pixel, lowpoly, hd
    "cameras": [],  # any of: first-person, third-person, top-down, side-scroller
    "commercial": False,  # personal/non-commercial by default; True blocks NC assets
    "pixel": {
        "palette": "",  # file path (relative to the project), lospec:<slug>, or hex list
        "max_colors": 32,
        "light": "top-left",
        "outline": "dark",  # dark | selective | none
        "native_height_px": 0,  # typical character height in art pixels (0 = unset)
        "game_background": "",  # hex color the sprites are usually seen against
    },
    "3d": {
        "budgets_tris": {
            "prop_small": 500,
            "prop_large": 3000,
            "environment_piece": 2000,
            "character": 8000,
            "hero_character": 20000,
        },
        "texel_density_px_per_m": 512,
        "origin": "bottom_center",
        "lookdev_engine": "workbench",  # eevee for PBR/HD materials
    },
    "camera": {
        "profile": "",  # "" = picked from the engine and `cameras`; else a preset or an override name
        "distances": {},  # per profile: {close, typical, far} in meters from the camera
        "overrides": {},  # the project's real settings: {name: {base: preset, fov_deg, res_h, ...}}
        "viewmodel": {},  # first-person view-model camera: {fov_deg, fov_axis, near_m, scale}; never assumed
    },
    "animation": {"fps": 30, "feel": ""},
    "audio": {"lufs": {"sfx": -18, "ui": -20, "music": -16, "ambience": -24, "voice": -18}},
    "taste_notes": [],  # short lessons learned from the user's ratings
}

TEMPLATE = """\
# Opus project bible: style rules and budgets that every Opus tool reads.
# Keep it short. Anything left out falls back to the toolkit defaults.

project: {project}
styles: [{styles}]          # pixel, lowpoly, hd
cameras: [{cameras}]        # first-person, third-person, top-down, side-scroller
commercial: false           # true = block non-commercial models and assets

pixel:
  palette: ""               # e.g. palettes/game.hex or lospec:endesga-32
  max_colors: 32            # per sprite
  light: top-left           # light direction for shading checks
  outline: dark             # dark | selective | none
  native_height_px: 0       # typical character height in art pixels
  game_background: ""       # hex color sprites are usually seen against

3d:
  budgets_tris:
    prop_small: 500
    prop_large: 3000
    environment_piece: 2000
    character: 8000
    hero_character: 20000
  texel_density_px_per_m: 512
  origin: bottom_center
  lookdev_engine: workbench # eevee for PBR/HD materials

camera:                     # the game camera decides how much detail reads (opus.camera)
  profile: ""               # "" = from the engine and cameras above; or ue_tp_1080, ue_fp_1080,
                            # godot_tp, unity_tp, topdown, sidescroller, or a name under overrides
  distances: {{}}             # meters, per profile: {{ue_tp_1080: {{close: 1.5, typical: 3.5, far: 15}}}}
  overrides: {{}}             # your real settings: {{ue_tp_1080: {{fov_deg: 100, res_w: 2560, res_h: 1440}}}}
                            # or a new profile: {{my_cam: {{base: godot_tp, fov_deg: 70}}}}
  viewmodel: {{}}             # first-person arms/weapon camera, read from the project, e.g.
                            # {{fov_deg: 90, fov_axis: horizontal, near_m: 0.1, scale: 1.0}}

animation:
  fps: 30
  feel: ""                  # e.g. "snappy, weighty landings"

audio:
  lufs: {{sfx: -18, ui: -20, music: -16, ambience: -24, voice: -18}}

taste_notes: []             # lessons from your ratings, added over time
"""


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_bible(near=None) -> dict:
    """The merged bible for the project containing ``near`` (defaults if none exists)."""
    root = find_project_root(near)
    data: dict = {}
    path = root / BIBLE_NAME if root else None
    if path and path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    bible = _merge(DEFAULTS, data)
    bible["_root"] = str(root) if root else None
    bible["_file"] = str(path) if path and path.exists() else None
    return bible


def resolve_palette_spec(bible: dict) -> str:
    """The bible's palette spec with file paths made absolute."""
    spec = (bible.get("pixel") or {}).get("palette") or ""
    if spec and bible.get("_root") and not spec.lower().startswith("lospec:") and "#" not in spec:
        p = Path(bible["_root"]) / spec
        if p.exists():
            return str(p)
    return spec


def detect_engine(bible: dict) -> str:
    """unreal, godot or unity from the project's files; unreal when nothing says otherwise."""
    root = Path(bible["_root"]) if bible.get("_root") else None
    if root is not None:
        if (root / "project.godot").exists():
            return "godot"
        if (root / "ProjectSettings" / "ProjectVersion.txt").exists():
            return "unity"
    return "unreal"


def camera_profile(bible: dict, name: str = ""):
    """The camera profile ``name`` (default: the bible's ``camera.profile``, else picked from the
    engine and ``cameras``) with the bible's overrides and distances applied. ``viewmodel``
    gives the first-person view-model camera, or a labeled fallback when the bible has none."""
    from dataclasses import replace

    from opus import camera

    cam = bible.get("camera") or {}
    overrides = cam.get("overrides") or {}
    engine = detect_engine(bible)
    default = {"unreal": "ue_tp_1080", "godot": "godot_tp", "unity": "unity_tp"}[engine]
    name = name or cam.get("profile") or ""
    note = ""
    if name == "viewmodel":
        world = camera_profile(bible, default if cam.get("profile") == "viewmodel" else "")
        if world.projection != "persp":
            world = camera_profile(bible, default)
        return camera.viewmodel(cam.get("viewmodel"), world)
    if not name:
        view = (bible.get("cameras") or ["third-person"])[0]
        name = {"top-down": "topdown", "side-scroller": "sidescroller"}.get(view, default)
        if view == "first-person":
            name = "ue_fp_1080" if engine == "unreal" else default
        note = f"auto-picked from engine {engine} and camera {view}; set camera.profile in opus.project.yaml"
    if name in overrides:
        fields = overrides[name] or {}
        base = fields.get("base") or (name if name in camera.PRESETS else default)
        profile = camera.apply(camera.preset(base), fields, name=name)
    else:
        profile = camera.preset(name)
    dist = (cam.get("distances") or {}).get(name)
    if dist:
        profile = camera.apply(profile, {"distances": dist})
    return replace(profile, note=note) if note else profile


def init_bible(root: str | Path, project: str = "", styles=(), cameras=()) -> Path:
    root = Path(root).expanduser().resolve()
    path = root / BIBLE_NAME
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    path.write_text(
        TEMPLATE.format(project=project or root.name, styles=", ".join(styles), cameras=", ".join(cameras)),
        encoding="utf-8",
    )
    return path
