"""Proportion Check and Reference Match: numbers instead of guesses.

Both compare silhouettes. The model's silhouettes are rendered orthographically, scaled to
a common height and aligned at the feet, then compared with either canon blockouts built
at the same height (proportion_check) or a concept/reference image (reference_match).
Overlays show where the model sticks out (red) and where it is missing volume (blue).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from opus import imaging as im
from opus.blender.runner import run_task
from opus.paths import cache_dir, output_path
from opus.pixel.color import rgb_to_oklab

NORM_H = 480  # silhouettes are compared at this height in pixels
BANDS = 20
BOTH, MODEL_ONLY, REF_ONLY, BG = (205, 205, 212), (235, 80, 70), (70, 170, 255), (34, 35, 40)

HUMANOID_REGIONS = [  # (top fraction of height from the floor, name); first match from the top wins
    (0.87, "head"), (0.81, "neck"), (0.72, "shoulders and chest"), (0.61, "waist"), (0.49, "hips"),
    (0.27, "thighs"), (0.06, "lower legs"), (0.0, "feet"),
]
ROLE_ALIASES = {
    "upperarm": ("upperarml", "leftarm", "leftupperarm", "upperarmleft", "larm"),
    "lowerarm": ("lowerarml", "forearml", "leftforearm", "leftlowerarm"),
    "hand": ("handl", "lefthand"),
    "thigh": ("thighl", "leftupleg", "leftupperleg", "upperlegl"),
    "calf": ("calfl", "shinl", "leftleg", "leftlowerleg", "lowerlegl"),
    "foot": ("footl", "leftfoot"),
}
# the blockout's joints at each end of those bones (its hand bone runs wrist to knuckles)
CANON_BONES = {"upperarm": ("shoulder_l", "elbow_l"), "lowerarm": ("elbow_l", "wrist_l"), "hand": ("wrist_l", "knuckles_l"),
               "thigh": ("hip_l", "knee_l"), "calf": ("knee_l", "ankle_l"), "foot": ("ankle_l", "ball_l")}


# ---------------------------------------------------------------- masks

def render_mask(path: str | Path) -> np.ndarray:
    """A silhouette render (black on white) -> boolean mask."""
    return np.asarray(Image.open(path).convert("L")) < 128


def image_mask(path: str | Path, threshold: float = 0.0, max_side: int = 700) -> np.ndarray:
    """Subject mask of a reference image: its alpha, or everything not connected to a
    background that matches the image border. ``threshold`` is the OKLab distance that still
    counts as background; 0 adapts it to how uniform the border is."""
    img = Image.open(path)
    img.thumbnail((max_side, max_side))
    if img.mode in ("RGBA", "LA", "P"):
        a = np.asarray(img.convert("RGBA"))[..., 3]
        if (a < 128).mean() > 0.03:
            return _largest_parts(a >= 128)
    lab = rgb_to_oklab(np.asarray(img.convert("RGB")))
    border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    bg = np.median(border, axis=0)
    spread = np.linalg.norm(border - bg, axis=-1)
    if not threshold:
        # flat backdrops get a tight threshold, textured paper or gradients a looser one
        threshold = float(np.clip(np.quantile(spread, 0.9) * 2.5, 0.025, 0.12))
    like_bg = np.linalg.norm(lab - bg, axis=-1) < threshold
    seed = np.zeros_like(like_bg)
    seed[0], seed[-1], seed[:, 0], seed[:, -1] = like_bg[0], like_bg[-1], like_bg[:, 0], like_bg[:, -1]
    reach = seed
    for _ in range(4 * max(like_bg.shape)):
        grown = reach.copy()
        grown[1:] |= reach[:-1]
        grown[:-1] |= reach[1:]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= like_bg
        if (grown == reach).all():
            break
        reach = grown
    return _largest_parts(~reach)


def _largest_parts(mask: np.ndarray, keep: float = 0.02) -> np.ndarray:
    """Drop specks and captions: keep connected parts of at least ``keep`` x the largest."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    sizes = [0]
    flat = mask.ravel()
    lab = labels.ravel()
    for start in np.flatnonzero(flat):
        if lab[start]:
            continue
        n = len(sizes)
        lab[start] = n
        stack, count = [start], 0
        while stack:
            i = stack.pop()
            count += 1
            y, x = divmod(i, w)
            for j, ok in ((i - w, y > 0), (i + w, y < h - 1), (i - 1, x > 0), (i + 1, x < w - 1)):
                if ok and flat[j] and not lab[j]:
                    lab[j] = n
                    stack.append(j)
        sizes.append(count)
    if len(sizes) == 1:
        return mask
    sizes = np.array(sizes)
    good = sizes >= keep * sizes[1:].max()
    good[0] = False
    return good[labels]


def crop(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    if not len(ys):
        raise ValueError("the silhouette is empty")
    return mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def to_height(mask: np.ndarray, h: int = NORM_H) -> np.ndarray:
    m = crop(mask)
    w = max(1, round(m.shape[1] * h / m.shape[0]))
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127


def align(a: np.ndarray, b: np.ndarray, b_scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Both on one canvas, feet on the bottom row, centered on their bounding boxes.
    ``b_scale`` resizes b relative to a (1.0 = same height)."""
    if b_scale != 1.0:
        hb = max(1, round(b.shape[0] * b_scale))
        b = np.asarray(Image.fromarray(b.astype(np.uint8) * 255).resize((max(1, round(b.shape[1] * b_scale)), hb), Image.NEAREST)) > 127
    h = max(a.shape[0], b.shape[0])
    w = max(a.shape[1], b.shape[1]) + 4
    out = []
    for m in (a, b):
        c = np.zeros((h, w), bool)
        x0 = (w - m.shape[1]) // 2
        c[h - m.shape[0] :, x0 : x0 + m.shape[1]] = m
        out.append(c)
    return out[0], out[1]


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else 0.0


def band_widths(mask: np.ndarray, bands: int = BANDS) -> np.ndarray:
    """Mean filled width per horizontal band (top band first), as a fraction of the height."""
    h = mask.shape[0]
    rows = mask.sum(axis=1) / h
    edges = np.linspace(0, h, bands + 1).astype(int)
    return np.array([rows[a:b].mean() if b > a else 0.0 for a, b in zip(edges, edges[1:])])


def region_name(frac_from_floor: float, humanoid: bool) -> str:
    if humanoid:
        for top, name in HUMANOID_REGIONS:
            if frac_from_floor >= top:
                return name
    return f"{frac_from_floor * 100:.0f}% up"


def band_findings(model: np.ndarray, ref: np.ndarray, humanoid: bool, label: str, tol: float = 0.025) -> list[dict]:
    """Bands where the model is wider or narrower than the reference by more than ``tol`` of
    the height, merged into runs."""
    dm, dr = band_widths(model), band_widths(ref)
    diff = dm - dr
    out, i = [], 0
    while i < BANDS:
        if abs(diff[i]) <= tol:
            i += 1
            continue
        sign = np.sign(diff[i])
        j = i
        while j + 1 < BANDS and abs(diff[j + 1]) > tol and np.sign(diff[j + 1]) == sign:
            j += 1
        top, bottom = 1 - i / BANDS, 1 - (j + 1) / BANDS
        mid = (top + bottom) / 2
        rel = float(diff[i : j + 1].mean() / max(dr[i : j + 1].mean(), 1e-3))
        out.append({
            "view": label, "from_pct": round(bottom * 100), "to_pct": round(top * 100),
            "region": region_name(mid, humanoid), "model_wider": bool(sign > 0),
            "diff_pct_of_height": round(float(diff[i : j + 1].mean()) * 100, 1), "relative_pct": round(rel * 100),
        })
        i = j + 1
    return out


# ---------------------------------------------------------------- humanoid landmarks

def _runs_at(mask: np.ndarray, row: int, cx: int) -> tuple[int, int] | None:
    line = mask[row]
    if not line[cx]:
        return None
    left = cx - np.argmin(line[cx::-1]) + 1 if not line[: cx + 1].all() else 0
    right = cx + np.argmin(line[cx:]) - 1 if not line[cx:].all() else len(line) - 1
    return int(left), int(right)


def humanoid_landmarks(front: np.ndarray) -> dict:
    """Landmark ratios from a front silhouette (cropped, feet at the bottom)."""
    m = crop(front)
    h, w = m.shape
    top_rows = m[: max(2, h // 12)]
    cx = int(np.median(np.nonzero(top_rows)[1]))
    widths = np.array([(lambda r: (r[1] - r[0] + 1) if r else 0)(_runs_at(m, y, cx)) for y in range(h)], float)
    k = max(1, h // 60)
    sm = np.convolve(widths, np.ones(k) / k, mode="same")
    # neck: the first narrowing below the head that widens again into shoulders
    neck = None
    for y in range(int(h * 0.03), int(h * 0.5)):
        if 0 < sm[y] < 0.88 * sm[:y].max() and sm[y : y + int(h * 0.15)].max() > 1.3 * sm[y]:
            while y + 1 < h and 0 < sm[y + 1] <= sm[y]:
                y += 1  # down to the bottom of the valley
            neck = y
            break
    # crotch: the top of the gap between the legs on the center line (thighs that touch
    # lower down still leave the notch under the pelvis)
    center_filled = np.array([m[y, max(0, cx - 1) : cx + 2].any() for y in range(h)])
    empty = [y for y in range(int(h * 0.3), h) if not center_filled[y]]
    crotch = min(empty) if len(empty) >= max(2, h // 50) else None
    # where the legs visibly split: the top of the gap that runs up from the floor
    split = h
    while split > int(h * 0.3) and not center_filled[split - 1]:
        split -= 1
    out = {"width_span": round(w / h, 4), "center_px": cx}
    if neck is not None:
        out["neck"] = round(neck / h, 4)
        out["head_width"] = round(float(sm[:neck].max()) / h, 4)
        sh = sm[neck : neck + int(h * 0.12)]
        out["shoulder_span"] = round(float(sh.max()) / h, 4)
    if split < h - max(2, h // 50):
        out["leg_split"] = round((h - split) / h, 4)
    if crotch is not None:
        out["crotch_height"] = round((h - crotch) / h, 4)
        hips = sm[max(0, crotch - int(h * 0.08)) : crotch]
        if len(hips):
            out["hip_width"] = round(float(hips.max()) / h, 4)
        if "neck" in out:
            lo, hi = int(h * out["neck"]) + int(h * 0.15), crotch - int(h * 0.08)
            window = sm[lo:hi][sm[lo:hi] > 0] if hi > lo else []
            if len(window):
                out["waist_width"] = round(float(window.min()) / h, 4)
    return out


METRIC_WORDS = {
    "crotch_height": ("legs", "longer", "shorter"),
    "neck": ("head and neck region", "taller", "shorter"),
    "head_width": ("head", "wider", "narrower"),
    "shoulder_span": ("shoulders", "wider", "narrower"),
    "hip_width": ("hips", "wider", "narrower"),
    "waist_width": ("waist", "wider", "narrower"),
    "width_span": ("overall width (arms)", "wider", "narrower"),
}


def compare_landmarks(model: dict, canon: dict, tol: float = 0.08) -> list[dict]:
    out = []
    model, canon = dict(model), dict(canon)
    # thighs that touch hide the crotch notch in one silhouette but not the other: then
    # compare where the legs visibly split instead
    notch = [("crotch_height" in d and "leg_split" in d and d["crotch_height"] - d["leg_split"] > 0.03) for d in (model, canon)]
    if notch[0] != notch[1] and "leg_split" in model and "leg_split" in canon:
        model["crotch_height"], canon["crotch_height"] = model["leg_split"], canon["leg_split"]
    for key, (what, more, less) in METRIC_WORDS.items():
        if key not in model or key not in canon or not canon[key]:
            continue
        rel = model[key] / canon[key] - 1
        if abs(rel) > tol:
            out.append({"metric": key, "model": model[key], "canon": canon[key], "relative_pct": round(rel * 100),
                        "text": f"{what} {abs(rel) * 100:.0f}% {more if rel > 0 else less} than the canon"})
    return out


def _norm(name: str) -> str:
    n = "".join(ch for ch in name.lower() if ch.isalnum())
    for prefix in ("mixamorig", "def", "org", "mch"):
        if n.startswith(prefix) and len(n) > len(prefix) + 2:
            n = n[len(prefix) :]
    return n


def bone_ratios(bones: dict, height: float) -> dict:
    """Left-side limb bone lengths over body height, found by common naming conventions."""
    by_norm = {_norm(n): v for n, v in bones.items()}
    out = {}
    for role, aliases in ROLE_ALIASES.items():
        for a in aliases:
            if a in by_norm:
                h, t = (np.array(p) for p in by_norm[a])
                out[role] = round(float(np.linalg.norm(t - h)) / height, 4)
                break
    return out


def canon_bone_ratios(joints: dict, height: float) -> dict:
    return {r: round(float(np.linalg.norm(np.array(joints[b]) - np.array(joints[a]))) / height, 4)
            for r, (a, b) in CANON_BONES.items() if a in joints and b in joints}


# ---------------------------------------------------------------- overlays

def overlay(model: np.ndarray, ref: np.ndarray, guides: list[tuple[float, str]] | None = None, size: int = 380) -> Image.Image:
    a, b = model, ref
    rgb = np.empty(a.shape + (3,), np.uint8)
    rgb[:] = BG
    rgb[a & b] = BOTH
    rgb[a & ~b] = MODEL_ONLY
    rgb[~a & b] = REF_ONLY
    img = Image.fromarray(rgb)
    scale = size / img.height
    img = img.resize((max(1, round(img.width * scale)), size), Image.NEAREST)
    pad = Image.new("RGB", (img.width + 70, size + 10), BG)
    pad.paste(img, (64, 5))
    d = ImageDraw.Draw(pad)
    f = im.font(11)
    for frac, text in guides or []:
        y = 5 + (1 - frac) * size
        d.line([(60, y), (pad.width, y)], fill=(110, 112, 120), width=1)
        d.text((2, y - 7), im.fit_text(text, f, 58), fill=(170, 172, 180), font=f)
    return pad


def _legend(ref_name: str) -> str:
    return f"gray both · red model only · blue {ref_name} only"


# ---------------------------------------------------------------- tools

def proportion_check(
    path: str | Path,
    archetype: str = "humanoid",
    preset: str = "auto",
    pose: str = "auto",
    objects: list[str] | None = None,
    out: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Compare a model's proportions with canon blockouts built at the model's height."""
    path = Path(path).expanduser().resolve()
    if archetype not in ("humanoid", "quadruped", "dragon"):
        raise ValueError("archetype must be humanoid, quadruped or dragon")
    work = cache_dir("proportion", near=path) / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    res = run_task(
        "silhouettes",
        {"path": str(path), "out_dir": str(work), "objects": objects or None, "views": ["front", "right"],
         "canon": archetype, "presets": None if preset == "auto" else [preset], "pose": pose},
        timeout=timeout,
    )
    model = {v: to_height(render_mask(d["path"])) for v, d in res["model"]["views"].items()}
    height = res["model"]["size_m"][2]
    humanoid = archetype == "humanoid"
    scores = {}
    for name, c in res["canons"].items():
        cm = {v: to_height(render_mask(d["path"])) for v, d in c["views"].items()}
        scores[name] = {"masks": cm, "iou": {v: iou(*align(model[v], cm[v])) for v in model}}
    best = max(scores, key=lambda n: sum(scores[n]["iou"].values()))
    canon = res["canons"][best]
    cm = scores[best]["masks"]
    report = {
        "file": str(path), "archetype": archetype, "canon": best, "pose": canon.get("pose"), "height_m": round(height, 3),
        "iou": {v: round(x, 3) for v, x in scores[best]["iou"].items()},
        "iou_by_canon": {n: round(sum(s["iou"].values()) / len(s["iou"]), 3) for n, s in scores.items()},
        "findings": [],
    }
    guides = []
    if humanoid:
        lm_model, lm_canon = humanoid_landmarks(model["front"]), humanoid_landmarks(cm["front"])
        report["landmarks"] = {"model": lm_model, "canon": lm_canon}
        if "neck" in lm_model and "neck" in lm_canon and canon.get("heads_tall"):
            report["heads_tall_estimate"] = round(canon["heads_tall"] * lm_canon["neck"] / lm_model["neck"], 2)
            report["canon_heads_tall"] = canon["heads_tall"]
        report["findings"] += compare_landmarks(lm_model, lm_canon)
        lmm = canon["landmarks_m"]
        guides = [(lmm[k] / height, k) for k in ("chin", "shoulder", "waist", "crotch", "knee") if k in lmm]
        if res["model"].get("bones"):
            mb, cb = bone_ratios(res["model"]["bones"], height), canon_bone_ratios(canon["joints_m"], height)
            report["bone_ratios"] = {"model": mb, "canon": cb}
            for role in mb:
                if role in cb and abs(mb[role] / cb[role] - 1) > 0.1:
                    rel = mb[role] / cb[role] - 1
                    report["findings"].append({"metric": f"bone:{role}", "relative_pct": round(rel * 100),
                                               "text": f"{role} bone {abs(rel) * 100:.0f}% {'longer' if rel > 0 else 'shorter'} than the canon"})
    bands = []
    for v in model:
        a, b = align(model[v], cm[v])
        bands += band_findings(a, b, humanoid, "front" if v == "front" else "side")
    report["bands"] = bands
    for bnd in bands:
        report["findings"].append({
            "metric": f"band:{bnd['view']}", "relative_pct": bnd["relative_pct"],
            "text": f"{bnd['view']} view, {bnd['region']} ({bnd['from_pct']}-{bnd['to_pct']}% of height): model "
                    f"{abs(bnd['relative_pct'])}% {'wider' if bnd['model_wider'] else 'narrower'}",
        })
    sheet = im.Sheet(
        title=f"Proportion Check · {path.name} vs {archetype} canon '{best}'",
        subtitle=f"height {height:.2f} m · IoU front {report['iou'].get('front', 0):.2f}, side {report['iou'].get('right', 0):.2f}"
                 + (f" · ~{report['heads_tall_estimate']} heads tall (canon {canon['heads_tall']})" if "heads_tall_estimate" in report else ""),
    )
    tiles = []
    for v in model:
        a, b = align(model[v], cm[v])
        tiles.append(im.Tile(overlay(a, b, guides), f"{'front' if v == 'front' else 'side'}: {_legend('canon')}"))
    sheet.add_row("Model vs canon (same height, feet aligned)", tiles)
    out_path = Path(out) if out else output_path("proportion", path.stem, near=path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.render().save(out_path)
    report["sheet"] = str(out_path)
    report["text"] = _summary(report)
    return out_path, report


def _summary(rep: dict) -> str:
    lines = []
    if "canon" in rep:
        lines.append(f"Closest canon: {rep['canon']} (silhouette IoU front {rep['iou'].get('front', 0):.2f}, side {rep['iou'].get('right', 0):.2f})")
    else:
        lines.append(f"Silhouette IoU vs reference: {rep['iou']:.2f}" + (" (reference mirrored)" if rep.get("flipped") else ""))
    if "heads_tall_estimate" in rep:
        lines.append(f"About {rep['heads_tall_estimate']} heads tall (canon {rep['canon_heads_tall']})")
    if not rep["findings"]:
        lines.append("No proportion differences above tolerance.")
    for f in rep["findings"]:
        lines.append(f"- {f['text']}")
    return "\n".join(lines)


def reference_match(
    path: str | Path,
    reference: str | Path,
    view: str = "front",
    humanoid: bool = False,
    objects: list[str] | None = None,
    out: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Compare the model's silhouette from ``view`` with a concept or reference image."""
    path = Path(path).expanduser().resolve()
    reference = Path(reference).expanduser().resolve()
    if view not in ("front", "back", "right", "left"):
        raise ValueError("view must be front, back, right or left")
    work = cache_dir("reference", near=path) / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    res = run_task("silhouettes", {"path": str(path), "out_dir": str(work), "objects": objects or None, "views": [view]},
                   timeout=timeout)
    model = to_height(render_mask(res["model"]["views"][view]["path"]))
    ref = to_height(image_mask(reference))
    straight = align(model, ref)
    flipped = align(model, ref[:, ::-1])
    use_flip = iou(*flipped) > iou(*straight) + 0.01
    a, b = flipped if use_flip else straight
    bands = band_findings(a, b, humanoid, view)
    report = {
        "file": str(path), "reference": str(reference), "view": view, "flipped": use_flip,
        "iou": round(iou(a, b), 3),
        "aspect": {"model": round(crop(model).shape[1] / NORM_H, 3), "reference": round(crop(ref).shape[1] / NORM_H, 3)},
        "bands": bands,
        "findings": [{"metric": "band", "relative_pct": x["relative_pct"],
                      "text": f"{x['region']} ({x['from_pct']}-{x['to_pct']}% of height): model {abs(x['relative_pct'])}% "
                              f"{'wider' if x['model_wider'] else 'narrower'} than the reference"} for x in bands],
    }
    if humanoid:
        lm_m, lm_r = humanoid_landmarks(a), humanoid_landmarks(b)
        report["landmarks"] = {"model": lm_m, "reference": lm_r}
        report["findings"] += [{**f, "text": f["text"].replace("canon", "reference")} for f in compare_landmarks(lm_m, lm_r)]
    ref_img = Image.open(reference).convert("RGB")
    ref_img.thumbnail((380, 390))
    sheet = im.Sheet(title=f"Reference Match · {path.name} vs {reference.name}",
                     subtitle=f"{view} view · silhouette IoU {report['iou']:.2f}" + (" · reference mirrored to match" if use_flip else ""))
    sheet.add_row("Overlay (same height, feet aligned)", [im.Tile(overlay(a, b), _legend("reference")), im.Tile(ref_img, "reference")])
    out_path = Path(out) if out else output_path("reference", path.stem, near=path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.render().save(out_path)
    report["sheet"] = str(out_path)
    report["text"] = _summary(report)
    return out_path, report
