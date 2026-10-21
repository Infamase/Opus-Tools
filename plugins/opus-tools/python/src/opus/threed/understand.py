"""3D understanding for Claude: look from any angle, see labeled parts, read a structure report.

Blender renders and measures (``opus_bl/inspect3d.py``); this module draws labels and
writes the sheets and summaries.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from opus import imaging as im
from opus.bible import camera_profile, load_bible
from opus.blender.runner import run_task
from opus.camera import JOHNSON_PX, johnson
from opus.paths import cache_dir, output_path

NAMED = ("front", "right", "back", "left", "top", "bottom", "three_quarter", "three_quarter_back")
PASSES = ("shaded", "clay", "wire", "silhouette", "normals", "parts", "focus")
LABEL_W = 115


def parse_view(v) -> dict:
    """"front", "three_quarter", or "azimuth,elevation" in degrees (0 = front, 90 = right side)."""
    if isinstance(v, (list, tuple)):
        return {"azimuth": float(v[0]), "elevation": float(v[1])}
    v = str(v).strip()
    if v in NAMED:
        return {"view": v}
    try:
        az, el = (float(x) for x in v.replace(" ", "").split(","))
    except ValueError:
        raise ValueError(f"view {v!r}: use one of {NAMED} or 'azimuth,elevation' in degrees") from None
    return {"azimuth": az, "elevation": el}


def _view_title(t: dict) -> str:
    if t.get("view"):
        return t["view"].replace("three_quarter", "3/4")
    return f"az {t['azimuth']:g}°, el {t['elevation']:g}°"


def _labeled(path: str, labels: list[dict] | None) -> Image.Image:
    """Put part labels in side margins with leader lines to their anchor points."""
    img = Image.open(path).convert("RGB")
    if not labels:
        return img
    w, h = img.size
    canvas = Image.new("RGB", (w + 2 * LABEL_W, h), (38, 39, 44))
    canvas.paste(img, (LABEL_W, 0))
    d = ImageDraw.Draw(canvas)
    f = im.font(12)
    step = 15
    for side in ("left", "right"):
        group = sorted(
            [lb for lb in labels if (lb["x"] < 0.5) == (side == "left")], key=lambda lb: lb["y"]
        )
        # spread label rows so they never overlap, keeping them near their anchors
        ys, last = [], -step
        for lb in group:
            y = max(lb["y"] * h, last + step)
            ys.append(y)
            last = y
        overflow = (ys[-1] + step - h) if ys else 0
        if overflow > 0:
            ys = [max(6.0, y - overflow) for y in ys]
            for i in range(1, len(ys)):
                ys[i] = max(ys[i], ys[i - 1] + step)
        for lb, y in zip(group, ys):
            col = tuple(int(c * 255) for c in lb["color"])
            ax, ay = LABEL_W + lb["x"] * w, lb["y"] * h
            text = im.fit_text(lb["name"], f, LABEL_W - 12)
            tw = f.getlength(text)
            tx = 6 if side == "left" else LABEL_W + w + 6
            end_x = tx + tw + 3 if side == "left" else tx - 3
            line_col = col if lb.get("visible", True) else (120, 120, 128)
            d.line([(end_x, y + 7), (ax, ay)], fill=line_col, width=1)
            if lb.get("visible", True):
                d.ellipse([ax - 3, ay - 3, ax + 3, ay + 3], fill=col, outline=(0, 0, 0))
            else:
                d.ellipse([ax - 3, ay - 3, ax + 3, ay + 3], outline=line_col)
            d.text((tx, y), text, fill=col if lb.get("visible", True) else (150, 150, 158), font=f)
    return canvas


def look_at(
    path: str | Path,
    views: list | None = None,
    pass_: str = "clay",
    target: str = "",
    zoom: float = 1.0,
    isolate: bool = False,
    ortho: bool = False,
    objects: list[str] | None = None,
    size: int = 560,
    out: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Render the asset (or one part of it) from the requested views in one pass."""
    path = Path(path).expanduser().resolve()
    if pass_ not in PASSES:
        raise ValueError(f"pass must be one of {PASSES}")
    shots = [{**parse_view(v), "pass": pass_, "zoom": zoom, "ortho": ortho} for v in (views or ["three_quarter"])]
    work = cache_dir("look", near=path) / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    res = run_task(
        "views",
        {"path": str(path), "out_dir": str(work), "shots": shots, "objects": objects or None,
         "target": target, "isolate": isolate, "size": size},
        timeout=timeout,
    )
    focus = f" · framed on {target}" if target else ""
    sheet = im.Sheet(title=f"Look · {path.name}", subtitle=f"{pass_} pass{focus} · zoom {zoom:g} · {res['mode']} parts: {len(res['parts'])}")
    tiles = [im.Tile(_labeled(t["path"], t["labels"]), _view_title(t)) for t in res["tiles"]]
    per_row = 2 if pass_ == "parts" else 4  # labeled tiles need room to stay readable
    for i in range(0, len(tiles), per_row):
        sheet.add_row("Views" if i == 0 else "", tiles[i : i + per_row])
    out_path = Path(out) if out else output_path("look", path.stem, suffix=".jpg", near=path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.render().save(out_path, quality=90)
    return out_path, {"sheet": str(out_path), "mode": res["mode"], "parts": res["parts"], "target": res["target"]}


def _fmt_size(s) -> str:
    return " x ".join(f"{v:.2f}" for v in s) + " m"


def summarize(rep: dict, max_parts: int = 40) -> str:
    b = rep["bounds_m"]
    lines = [
        f"Asset {_fmt_size(b['size'])} (W x D x H) · {'on the floor' if rep['on_floor'] else 'NOT on the floor (lowest z %.3f m)' % b['min'][2]}"
        f" · {'centered' if rep['centered_x'] else 'off-center in X'}",
        f"Parts ({len(rep['parts'])}, one per "
        f"{ {'objects': 'object', 'bones': 'bone region'}.get(rep['mode'], 'bone region or object') }):",
    ]
    for p in rep["parts"][:max_parts]:
        bits = [f"  - {p['name']}: {_fmt_size(p['size_m'])}"]
        if p.get("shape"):
            bits.append(p["shape"])
        if p.get("main_axis"):
            bits.append(f"long axis {p['main_axis']}")
        if "bone_length_m" in p:
            bits.append(f"bone {p['bone_length_m']:.3f} m, girth r {p['girth_radius_m']:.3f} m")
        lines.append(", ".join(bits))
    if len(rep["parts"]) > max_parts:
        lines.append(f"  ... and {len(rep['parts']) - max_parts} more")
    if rep["contacts"]:
        lines.append("Contacts: " + "; ".join(f"{c['a']} + {c['b']} ({c['kind']})" for c in rep["contacts"][:20]))
    for g in rep["gaps"][:10]:
        lines.append(f"Floating: {g['part']} is {g['gap_m'] * 100:.1f} cm from {g['nearest']}")
    s = rep["symmetry"]
    if s["symmetric"]:
        lines.append(f"Symmetry: mirror-symmetric across x = {s['plane_x_m']} (median offset {s['offset_pct_of_size']}% of size)")
    else:
        worst = ", ".join(f"{a['part']} ({a['median_offset_m'] * 100:.1f} cm)" for a in s["asymmetric_parts"][:5])
        lines.append(f"Symmetry: asymmetric, median offset {s['offset_pct_of_size']}% of size" + (f"; most: {worst}" if worst else ""))
    bal = rep["balance"]
    if "com_over_footprint" in bal:
        lines.append("Balance: center of mass is over the footprint" if bal["com_over_footprint"]
                     else f"Balance: center of mass is outside the footprint, leaning toward {bal.get('leans_toward')}")
    if rep.get("rig"):
        r = rep["rig"]
        lines.append(f"Rig: {r['armature']}, {r['bones']} bones, {r['style']} naming")
    return "\n".join(lines)


def model_report(
    path: str | Path,
    objects: list[str] | None = None,
    views: list | None = None,
    size: int = 520,
    out: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Structure report plus a labeled part map. Returns (sheet, report with ``text``)."""
    path = Path(path).expanduser().resolve()
    rep = run_task("report", {"path": str(path), "objects": objects or None}, timeout=timeout)
    rep["text"] = summarize(rep)
    sheet_path, _ = look_at(
        path, views=views or ["front", "right", "three_quarter"], pass_="parts", objects=objects, size=size,
        out=out or output_path("model_report", path.stem, suffix=".jpg", near=path), timeout=timeout,
    )
    rep["sheet"] = str(sheet_path)
    rep.pop("stats", None)
    return sheet_path, rep


BLIND_PROMPT = """You are shown an unlabeled 3D model as silhouettes and clay renders. Without being
told what it is: (1) name what you think it is, with 3 ranked guesses and a confidence for
each; (2) list the visual features that drove your guess; (3) say what looks ambiguous, wrong
or off-model; (4) say whether it still reads at the small, game-distance size. Image: {path}"""


def blind_read_sheet(
    path: str | Path,
    objects: list[str] | None = None,
    distance_px: int = 96,
    game_size: bool = False,
    camera: str = "",
    distances: list[float] | None = None,
    timeout: int = 900,
) -> tuple[Path, str]:
    """Unlabeled silhouettes and clay views under a neutral file name, for a reviewer who must
    identify the model without being told what it is. ``game_size`` adds the silhouette and a
    clay view at TRUE game pixel size for a camera profile (default: the bible's) at its
    distances, upscaled nearest-neighbor. Returns (sheet, prompt for the reviewer)."""
    import hashlib

    path = Path(path).expanduser().resolve()
    work = cache_dir("blind", near=path) / f"render_{time.strftime('%Y%m%d-%H%M%S')}"
    shots = [{"view": v, "pass": "silhouette", "ortho": v != "three_quarter"} for v in ("front", "right", "three_quarter")]
    shots.append({"view": "three_quarter", "pass": "clay"})
    res = run_task("views", {"path": str(path), "out_dir": str(work), "shots": shots, "objects": objects or None, "size": 360},
                   timeout=timeout)
    tiles = [im.Tile(Image.open(t["path"]).convert("RGB"), "") for t in res["tiles"]]
    clay = Image.open(res["tiles"][-1]["path"]).convert("RGB")
    small = clay.resize((distance_px, distance_px), Image.LANCZOS)
    tiles.append(im.Tile(small.resize((distance_px * 3, distance_px * 3), Image.NEAREST), f"seen at {distance_px} px"))
    sheet = im.Sheet(title="Blind read", subtitle="What is this?")
    sheet.add_row("Silhouettes", tiles[:3])
    sheet.add_row("Form", tiles[3:])
    if game_size:
        profile = camera_profile(load_bible(path), camera)
        shot = _profile_shot(profile)
        turned = dict(shot) if profile.projection == "ortho" else {"azimuth": shot["azimuth"] + 35.0, "elevation": shot["elevation"]}
        g = run_task("readability", {
            "path": str(path), "out_dir": str(work / "game"), "camera": camera_args(profile),
            "levels": _levels(profile, distances), "objects": objects or None,
            "shots": [{"key": "sil", **shot, "passes": ["silhouette"]}, {"key": "clay", **turned, "passes": ["clay"]}],
        }, timeout=timeout)
        for key, label in (("sil", "Silhouette at game size"), ("clay", "Form at game size")):
            row = []
            for r in (r for r in g["renders"] if r["shot"] == key):
                img, how = _fit(Image.open(next(iter(r["files"].values()))).convert("RGB"), 250, 340, smooth=key == "clay")
                dist = f"{r['distance_m']:g} m" if profile.projection == "persp" else "screen"
                row.append(im.Tile(img, f"{dist} · {how}"))
            sheet.add_row(label, row)
    token = hashlib.sha1(f"{path}{time.time()}".encode()).hexdigest()[:10]
    out = cache_dir("blind", near=path) / f"model_{token}.jpg"
    sheet.render().save(out, quality=90)
    return out, BLIND_PROMPT.format(path=out)


# ---------------------------------------------------------------- readability at game size

SOFT_NOTE = ("Part floors are SOFT warnings until calibrated on CC0 characters at game size (OVERHAUL §2.0 #6). "
             "Johnson levels use the subject's height: ~8 px recognizes the class, ~13 px identifies it (50%).")
AZIMUTH = {"front": 0.0, "right": 90.0, "back": 180.0, "left": 270.0}
MAP_BG = (38, 39, 44)
OTHER_PART = (95, 96, 104)
UNMATCHED = (255, 0, 255)


def camera_args(profile) -> dict:
    """What the Blender renderer needs from a camera profile."""
    return {"projection": profile.projection, "vfov_deg": profile.vfov_deg, "ortho_h": profile.ortho_h,
            "res_w": profile.res_w, "res_h": profile.res_h, "near_m": profile.near_m, "scale": profile.scale}


def _levels(profile, distances=None) -> list[list]:
    if profile.projection == "ortho":
        return [["screen", None]]
    levels = profile.levels()
    if distances:
        named = {d: n for n, d in levels}
        return [[named.get(float(d), f"{float(d):g} m"), float(d)] for d in distances]
    if not levels:
        raise ValueError(f"camera {profile.name} has no distances; give some in meters")
    return [list(lv) for lv in levels]


def _profile_shot(profile) -> dict:
    return {"azimuth": AZIMUTH.get(profile.view, 0.0), "elevation": float(profile.elevation_deg)}


def decode_parts(rgba: np.ndarray, colors8: list, tol: int = 3) -> tuple[np.ndarray, int]:
    """Part index per pixel of a mask-mode part map (-1 background, -2 a subject pixel that
    matches no part color), and how many such unmatched pixels there are (0 when nothing blended)."""
    labels = np.full(rgba.shape[:2], -1, dtype=np.int32)
    idx = np.nonzero(rgba[..., 3] > 0)
    px = rgba[idx][:, :3].astype(np.int16)
    lab = np.full(len(px), -2, dtype=np.int32)
    for i, c in enumerate(colors8):
        lab[np.abs(px - np.array(c[:3], dtype=np.int16)).max(axis=1) <= tol] = i
    labels[idx] = lab
    return labels, int((lab == -2).sum())


def _erode(m: np.ndarray, square: bool) -> np.ndarray:
    out = np.zeros_like(m)
    c = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    if square:
        c &= m[:-2, :-2] & m[:-2, 2:] & m[2:, :-2] & m[2:, 2:]
    out[1:-1, 1:-1] = c
    return out


def _erosions_to_vanish(m: np.ndarray) -> int:
    m = np.pad(m, 1)
    k = 0
    while m.any():
        m = _erode(m, square=k % 2 == 1)  # alternating 4- and 8-neighbor steps: close to a disc
        k += 1
    return k


def min_width_px(mask: np.ndarray) -> int:
    """A part's width in pixels: twice its largest inscribed radius, found by eroding the mask
    until it vanishes (on a 2x supersampled mask for thin parts, so a 1-px line is 1 and a 2-px
    bar is 2). A sword blade's width, not its length."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return 0
    m = mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    k = _erosions_to_vanish(m)
    if k > 8:  # wide parts: the 1x count is within a pixel
        return 2 * k - 1
    return _erosions_to_vanish(np.repeat(np.repeat(m, 2, axis=0), 2, axis=1))


def extent_px(mask: np.ndarray) -> int:
    """A part's longest dimension in pixels (the largest of 16 projected spans)."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return 0
    if len(ys) > 40000:
        keep = np.linspace(0, len(ys) - 1, 40000).astype(int)
        ys, xs = ys[keep], xs[keep]
    a = np.linspace(0, np.pi, 16, endpoint=False)
    proj = np.outer(xs, np.cos(a)) + np.outer(ys, np.sin(a))
    return int(round(float((proj.max(axis=0) - proj.min(axis=0)).max()))) + 1


def _status(area: int, width: int, projected_area: float, floor_px: float) -> str:
    """ok, thin (under the floor), hidden (big enough but covered in this view) or vanished."""
    if area == 0:
        return "hidden" if projected_area >= 4 else "vanished"
    return "thin" if width < floor_px else "ok"


def _measure(labels: np.ndarray, members: list[int], projected_area: float, floor_px: float) -> dict:
    m = np.isin(labels, members)
    area = int(m.sum())
    width = min_width_px(m) if area else 0
    return {"area_px": area, "min_width_px": width, "extent_px": extent_px(m) if area else 0,
            "status": _status(area, width, projected_area, floor_px)}


def _fit(img: Image.Image, height: int, max_w: int, smooth: bool = False) -> tuple[Image.Image, str]:
    """Upscale a small game-size image by a whole factor (nearest), or shrink a big one to fit."""
    k = min(height // img.height, max_w // img.width)
    if k >= 1:
        return img.resize((img.width * k, img.height * k), Image.NEAREST), ("true size" if k == 1 else f"x{k} nearest")
    s = min(height / img.height, max_w / img.width)
    size = (max(1, round(img.width * s)), max(1, round(img.height * s)))
    return img.resize(size, Image.LANCZOS if smooth else Image.NEAREST), f"shown at {s:.0%}"


def _part_map_image(labels: np.ndarray, colors8: list, defining: set) -> Image.Image:
    table = np.array([c if (not defining or i in defining) else OTHER_PART for i, c in enumerate(colors8)] + [UNMATCHED, MAP_BG],
                     dtype=np.uint8)
    idx = np.where(labels >= 0, labels, np.where(labels == -2, len(colors8), len(colors8) + 1))
    return Image.fromarray(table[idx], "RGB")


def _table_order(rows: list[dict]) -> list[dict]:
    """Defining parts first, then visible parts thinnest first, then hidden and vanished ones."""
    return sorted(rows, key=lambda x: (not x["defining"], x["area_px"] == 0, x["min_width_px"], x["part"]))


def _table_image(rows: list[dict], colors: dict, height: int, width: int = 330) -> Image.Image:
    img = Image.new("RGB", (width, max(height, 80)), MAP_BG)
    d = ImageDraw.Draw(img)
    f = im.font(12)
    cols = ((150, "px"), (205, "width"), (255, "extent"))
    y = 4
    d.text((6, y), "part", fill=im.FG_DIM, font=f)
    for x, h in cols:
        d.text((x - f.getlength(h), y), h, fill=im.FG_DIM, font=f)
    d.text((265, y), "status", fill=im.FG_DIM, font=f)
    fit = (img.height - 24) // 15
    if len(rows) > fit:
        fit -= 1
        hidden = sum(r["area_px"] == 0 for r in rows[fit:])
        d.text((6, 4 + 15 * (fit + 1)), f"+ {len(rows) - fit} more ({hidden} hidden or vanished)", fill=im.FG_DIM, font=f)
    for r in rows[:fit]:
        y += 15
        name = ("* " if r.get("defining") else "") + r["part"]
        d.text((6, y), im.fit_text(name, f, 100), fill=tuple(colors.get(r["part"], im.FG_TEXT)), font=f)
        for (x, _), v in zip(cols, (r["area_px"], r["min_width_px"], r["extent_px"])):
            d.text((x - f.getlength(str(v)), y), str(v), fill=im.FG_TEXT, font=f)
        bad = r["status"] != "ok"
        d.text((265, y), r["status"], fill=(255, 150, 60) if bad and r.get("defining") else (im.FG_DIM if bad else im.FG_TEXT), font=f)
    return img


def _squint(parts_rgba: np.ndarray, shaded: np.ndarray, sigma: float) -> tuple[Image.Image, Image.Image]:
    """Silhouette and value, blurred as if squinting (sigma about 1/50 of the subject height)."""
    pad = int(3 * sigma) + 2
    sil = np.pad(np.where(parts_rgba[..., 3] > 0, 25, 225).astype(np.uint8), pad, constant_values=225)
    val = np.pad(np.asarray(Image.fromarray(shaded).convert("L")), pad, mode="edge")
    blur = ImageFilter.GaussianBlur(sigma)
    return (Image.fromarray(sil, "L").filter(blur).convert("RGB"), Image.fromarray(val, "L").filter(blur).convert("RGB"))


def _level_name(lv: dict) -> str:
    """"typical 3.5 m", or just "40 m" for a distance the profile doesn't name."""
    where = f"{lv['distance_m']:g} m" if lv["distance_m"] else ""
    return lv["level"] if lv["level"] == where or not where else f"{lv['level']} {where}"


def readability_text(rep: dict) -> str:
    cam = rep["camera"]
    lines = [f"Camera {cam['name']}: {cam.get('label', '')}" + (f" · NOTE {cam['note']}" if cam.get("note") else ""),
             f"View az {rep['view']['azimuth']:g}°, el {rep['view']['elevation']:g}° · {rep['subject']['parts']} parts "
             f"({rep['subject']['mode']}) · subject {rep['subject']['height_m']:.2f} m tall"]
    for lv in rep["levels"]:
        exp = f" (height x px/m = {lv['expected_height_px']:.0f}, ratio {lv['height_ratio']:.3f})" if "height_ratio" in lv else ""
        lines.append(f"- {_level_name(lv)}: {lv['px_per_m']:.0f} px/m, subject {lv['height_px']} px tall{exp}"
                     f"{' CLIPPED by the frame' if lv['clipped'] else ''}, Johnson: {lv['johnson']}; "
                     f"{lv['parts_below_floor']} of {lv['parts_total']} parts under {rep['floor_px']:g} px, "
                     f"{lv['parts_hidden']} hidden or vanished")
        for dfn in lv["defining"]:
            lines.append(f"    * {dfn['part']}: {dfn['min_width_px']} px wide, {dfn['extent_px']} px long ({dfn['status']})")
    lines += [f"WARNING (soft): {w}" for w in rep["warnings"]]
    lines.append(SOFT_NOTE)
    return "\n".join(lines)


def readability_check(
    path: str | Path,
    camera: str = "",
    distances: list[float] | None = None,
    defining: list[str] | None = None,
    view: str = "",
    floor_px: float = 2.0,
    objects: list[str] | None = None,
    out: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Will the asset read in the game? Renders its part map at TRUE game pixel size (the
    profile's FOV and resolution at each distance, cropped to the subject, mask mode) and
    measures per part the visible pixels, min width and extent, plus the subject's height
    against Johnson's criteria. ``defining`` lists the feature brief's 5-7 defining parts (part,
    bone or object names); those under ``floor_px`` or gone get soft warnings."""
    path = Path(path).expanduser().resolve()
    profile = camera_profile(load_bible(path), camera)
    levels = _levels(profile, distances)
    shot = {"key": "game", **(parse_view(view) if view else _profile_shot(profile)), "passes": ["parts", "shaded"]}
    work = cache_dir("readability", near=path) / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    res = run_task("readability", {"path": str(path), "out_dir": str(work), "camera": camera_args(profile),
                                   "levels": levels, "objects": objects or None, "shots": [shot]}, timeout=timeout)
    parts = res["parts"]
    colors8 = [p["color8"] for p in parts]
    groups, unknown = {}, []
    for name in defining or []:
        idx = [i for i, p in enumerate(parts) if p["name"] == name] or [i for i, p in enumerate(parts) if p["object"] == name]
        if idx:
            groups[name] = idx
        else:
            unknown.append(name)
    def_idx = {i for idx in groups.values() for i in idx}
    height_m = res["size_m"][2]
    first = res["renders"][0]
    rep = {"file": str(path), "camera": profile.summary(), "view": {"azimuth": first["azimuth"], "elevation": first["elevation"]},
           "subject": {"height_m": height_m, "size_m": res["size_m"], "mode": res["mode"], "parts": len(parts)},
           "floor_px": floor_px, "levels": [], "warnings": [], "soft": SOFT_NOTE}
    if profile.fallback:
        rep["warnings"].append(profile.note)
    if unknown:
        rep["warnings"].append(f"defining parts not found: {unknown}; parts are {[p['name'] for p in parts][:40]}")
    full, images = [], []
    for r in res["renders"]:
        rgba = im.load_rgba(r["files"]["parts"])
        shaded = np.asarray(Image.open(r["files"]["shaded"]).convert("RGB"))
        labels, unmatched = decode_parts(rgba, colors8)
        ppm = profile.px_per_m(r["distance_m"] if profile.projection == "persp" else None)
        rows_ = np.nonzero((labels != -1).any(axis=1))[0]
        cols_ = np.nonzero((labels != -1).any(axis=0))[0]
        h_px = int(np.ptp(rows_) + 1) if len(rows_) else 0
        hull = {k: v[1] for k, v in r.get("parts_projected", {}).items()}
        rows = [{"part": p["name"], **_measure(labels, [i], hull.get(p["name"], 0.0), floor_px), "defining": i in def_idx}
                for i, p in enumerate(parts)]
        dfn = [{"part": n, **_measure(labels, idx, sum(hull.get(parts[i]["name"], 0.0) for i in idx), floor_px)}
               for n, idx in groups.items()]
        level = {"level": r["level"], "distance_m": r["distance_m"] if profile.projection == "persp" else None,
                 "px_per_m": round(ppm, 2), "height_px": h_px, "width_px": int(np.ptp(cols_) + 1) if len(cols_) else 0,
                 "clipped": r["clipped"], "johnson": johnson(h_px), "unmatched_px": unmatched,
                 "parts_total": len(parts), "parts_hidden": sum(x["status"] in ("hidden", "vanished") for x in rows),
                 "parts_below_floor": sum(x["status"] == "thin" for x in rows), "defining": dfn}
        if abs(first["elevation"]) < 1e-6:
            level["expected_height_px"] = round(height_m * ppm, 1)
            level["height_ratio"] = round(h_px / max(height_m * ppm, 1e-9), 4)
        where = _level_name(level)
        if r["clipped"]:
            rep["warnings"].append(f"{where}: the subject overflows the {profile.res_w}x{profile.res_h} frame; sizes are cut")
        if h_px < JOHNSON_PX["identify"]:
            rep["warnings"].append(f"{where}: the whole subject is {h_px} px tall, under ~13 px (Johnson identify)")
        for x in dfn:
            if x["status"] == "thin":
                rep["warnings"].append(f"{where}: defining part {x['part']} is {x['min_width_px']} px wide (< {floor_px:g} px)")
            elif x["status"] != "ok":
                rep["warnings"].append(f"{where}: defining part {x['part']} is {x['status']}"
                                       + (" behind other parts in this view" if x["status"] == "hidden" else " (under a pixel)"))
        order = _table_order(rows)
        level["parts"] = order[:12]
        rep["levels"].append(level)
        full.append({**level, "parts": rows})
        images.append((r, rgba, shaded, labels, order))

    # the sheet: per level the game-size image, its part map and the numbers; then a squint
    pname = {p["name"]: tuple(p["color8"]) for p in parts}
    sheet = im.Sheet(title=f"Readability · {path.name}",
                     subtitle=f"{profile.name}: {profile.label} · view az {first['azimuth']:g}°, el {first['elevation']:g}° · "
                              f"floors are soft until calibrated")
    for (r, rgba, shaded, labels, order), lv in zip(images, rep["levels"]):
        game, how = _fit(Image.fromarray(shaded), 260, 420, smooth=True)
        pmap, _ = _fit(_part_map_image(labels, [tuple(c) for c in colors8], def_idx), 260, 420)
        label = (f"{_level_name(lv)} · {lv['px_per_m']:.0f} px/m · subject {lv['height_px']} px ({lv['johnson']})"
                 + (" · clipped by the frame" if lv["clipped"] else ""))
        sheet.add_row(label, [im.Tile(game, f"game size, {how}"), im.Tile(pmap, "part map" + (" (defining in color)" if def_idx else "")),
                              im.Tile(_table_image(order, pname, game.height), "")])
    pick = next((i for i, lv in enumerate(rep["levels"]) if lv["level"] == "typical"), len(images) // 2)
    r, rgba, shaded, labels, _ = images[pick]
    sigma = max(1.0, rep["levels"][pick]["height_px"] / 50)
    sil, val = _squint(rgba, shaded, sigma)
    sheet.add_row(f"Squint at {rep['levels'][pick]['level']} (blur sigma {sigma:.1f} px)",
                  [im.Tile(_fit(sil, 220, 420, smooth=True)[0], "silhouette"), im.Tile(_fit(val, 220, 420, smooth=True)[0], "value")])
    rep["squint"] = {"level": rep["levels"][pick]["level"], "sigma_px": round(sigma, 2)}
    out_path = Path(out) if out else output_path("readability", path.stem, suffix=".jpg", near=path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.render().save(out_path, quality=92)
    data = out_path.with_suffix(".json")
    data.write_text(json.dumps({**rep, "levels": full}, indent=1, default=str), encoding="utf-8")
    rep.update({"sheet": str(out_path), "all_parts": str(data), "renders_dir": str(work)})
    rep["text"] = readability_text(rep)
    return out_path, rep
