"""3D understanding for Claude: look from any angle, see labeled parts, read a structure report.

Blender renders and measures (``opus_bl/inspect3d.py``); this module draws labels and
writes the sheets and summaries.
"""

from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageDraw

from opus import imaging as im
from opus.blender.runner import run_task
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
    for p in rep.get("penetrations", [])[:10]:
        at = ", ".join(f"{v:.3f}" for v in p["at_m"])
        if p["kind"] == "through":
            other = p["b"] if p["thin_part"] == p["a"] else p["a"]
            what = (f"{other} passes right through {p['thin_part']} (a {p['thickness_mm']:g} mm plate; "
                    f"{p['past_sheet_mm']:g} mm to pull it clear)")
        elif p["kind"] == "embedded":
            what = f"{p['inside']} is buried inside {p['b'] if p['inside'] == p['a'] else p['a']}"
        else:
            what = f"{p['a']} and {p['b']} cut into each other ({p['triangles']} crossing triangle pairs)"
        lines.append(f"Penetration: {what}, ~{p['depth_mm']:g} mm deep, at ({at}) m")
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
    timeout: int = 900,
) -> tuple[Path, str]:
    """Unlabeled silhouettes and clay views under a neutral file name, for a reviewer who must
    identify the model without being told what it is. Returns (sheet, prompt for the reviewer)."""
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
    token = hashlib.sha1(f"{path}{time.time()}".encode()).hexdigest()[:10]
    out = cache_dir("blind", near=path) / f"model_{token}.jpg"
    sheet.render().save(out, quality=90)
    return out, BLIND_PROMPT.format(path=out)
