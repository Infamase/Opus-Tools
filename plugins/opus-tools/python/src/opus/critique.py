"""Judge sheets for the critique protocol: lineups beside human-made exemplars and A/B pairs.

A judge sees only letters. Every subject is cut out of its background, scaled to the same
on-screen height and placed in a seeded random order, and every sheet comes with a second
sheet in the other order: LLM judges have position bias, so a pick counts only when both
orders name the same source. The key (letter -> source) goes back to the caller and is never
drawn on a sheet, stored in its metadata or used in its file name.
"""

from __future__ import annotations

import random
import secrets
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from opus import imaging as im
from opus.paths import cache_dir
from opus.pixel.color import hex_to_rgb, rgb_to_hex, rgb_to_oklab

LETTERS = "ABCDEFGH"
MODEL_SUFFIXES = (".blend", ".glb", ".gltf", ".fbx", ".obj")
PASSES = ("shaded", "clay", "silhouette")
FITS = ("height", "long_edge")
BACKGROUND = "#808080"
MAX_SHEET_H = 900

LINEUP_PROMPT = """The image shows {n} game assets labelled {first} to {last}, at the pixel size they
have on screen in the game (each game pixel is drawn as a {zoom}x{zoom} block). Which one doesn't
belong with the others, or looks least professionally made? First write one or two lines per
letter on its shape, proportions, detail and color compared with the rest. Then end with exactly
one line: ANSWER: <letter>. Judge only this image: don't open other files and don't read
anything into file names. Image: {path}"""

AB_PROMPT = """The image shows two versions of the same game asset, labelled A (left) and B (right){size}.
Question: {question}
First compare them on what the question asks, in a few lines. Then end with exactly one line:
ANSWER: A or ANSWER: B. Judge only this image: don't open other files and don't read anything
into file names. Image: {path}"""

AB_QUESTION = "Which one looks more professionally made and reads better?"


# ---------------------------------------------------------------- subjects

def _grow_runs(reach: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Spread ``reach`` along each row through the whole run of ``ok`` pixels it touches."""
    start = ok.copy()
    start[:, 1:] &= ~ok[:, :-1]
    run = np.cumsum(start.ravel()).reshape(ok.shape) * ok  # run id per ok pixel, 0 elsewhere
    hit = np.zeros(int(run.max()) + 1, bool)
    hit[run[reach & ok]] = True
    hit[0] = False
    return hit[run]


def flood_from_border(ok: np.ndarray) -> np.ndarray:
    """Pixels of ``ok`` 4-connected to the image border. Grows whole row and column runs per
    pass, so it needs one pass per turn of a path instead of one per pixel."""
    reach = np.zeros_like(ok)
    reach[0], reach[-1], reach[:, 0], reach[:, -1] = ok[0], ok[-1], ok[:, 0], ok[:, -1]
    count = int(reach.sum())
    while True:
        reach = _grow_runs(_grow_runs(reach, ok).T, ok.T).T
        if int(reach.sum()) == count:
            return reach
        count = int(reach.sum())


def cutout(rgba: np.ndarray) -> tuple[np.ndarray, str]:
    """The subject alone, cropped to its bounding box with binary alpha.

    Transparent margins are trimmed; a flat background (most of the border one color) is
    flood-filled from the border, so subject pixels of the same color survive. Anything else
    is kept whole. Returns (RGBA, "alpha" | "keyed #rrggbb" | "kept").
    """
    rgba = rgba.copy()
    if (rgba[..., 3] < 128).mean() > 0.01:
        how = "alpha"
    else:
        lab = rgb_to_oklab(rgba[..., :3])
        border = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
        bg = np.median(border, axis=0)
        spread = np.linalg.norm(border - bg, axis=-1)
        # flat backdrops get a tight threshold, gradients and paper a looser one
        thr = float(np.clip(np.quantile(spread, 0.9) * 2.5, 0.025, 0.12))
        if (spread < thr).mean() < 0.55:
            return rgba, "kept"
        rgb_bg = np.median(np.concatenate([rgba[0], rgba[-1], rgba[:, 0], rgba[:, -1]])[:, :3], axis=0)
        how = "keyed " + rgb_to_hex(rgb_bg)
        rgba[flood_from_border(np.linalg.norm(lab - bg, axis=-1) < thr), 3] = 0
    # hard edges for every subject, so soft or haloed cut-outs don't give one away
    rgba[..., 3] = np.where(rgba[..., 3] >= 128, 255, 0).astype(np.uint8)
    ys, xs = np.nonzero(rgba[..., 3])
    if not len(ys):
        raise ValueError("no subject found: the image is empty or all background")
    return rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], how


def _ref(shape, fit: str) -> int:
    return shape[0] if fit == "height" else max(shape[:2])


def scale_to(rgba: np.ndarray, height_px: int, fit: str = "height", resample=Image.NEAREST) -> tuple[np.ndarray, float]:
    """Scale a cut-out so its height (or long edge) is ``height_px``. Returns (RGBA, factor)."""
    h, w = rgba.shape[:2]
    s = height_px / _ref(rgba.shape, fit)
    size = (max(1, round(w * s)), max(1, round(h * s)))
    return np.array(Image.fromarray(np.ascontiguousarray(rgba), "RGBA").resize(size, resample)), s


def defringe(cut: np.ndarray, scale: float) -> np.ndarray:
    """Erode a keyed cut-out by up to half a target pixel: its rim mixes the subject with the
    old background (anti-aliasing, JPEG ringing) and would show as a halo after shrinking."""
    n = min(3, int(0.5 / scale))
    m = cut[..., 3] > 0
    for _ in range(n):
        p = np.pad(m, 1)
        m = m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    if n < 1 or not m.any():
        return cut
    out = cut.copy()
    out[~m, 3] = 0
    ys, xs = np.nonzero(m)
    return out[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def _scaled(subject: dict, target: int, fit: str, resample=Image.NEAREST) -> np.ndarray:
    cut = subject["cut"]
    if subject["background"].startswith("keyed"):
        cut = defringe(cut, target / _ref(cut.shape, fit))
    cell, scale = scale_to(cut, target, fit, resample)
    subject["scale"] = round(scale, 4)
    return cell


def _render(path: Path, view: str, render_pass: str, size: int, timeout: int) -> np.ndarray:
    """One view of a 3D file through the same renderer as look_at."""
    from opus.blender.runner import run_task
    from opus.threed.understand import parse_view

    with tempfile.TemporaryDirectory(prefix="opus_judge_") as tmp:
        res = run_task("views", {"path": str(path), "out_dir": tmp, "size": size,
                                 "shots": [{**parse_view(view), "pass": render_pass}]}, timeout=timeout)
        return im.load_rgba(res["tiles"][0]["path"])


def _subjects(sources: list[tuple[str, str]], view: str, render_pass: str, render_size: int, timeout: int) -> list[dict]:
    if render_pass not in PASSES:
        raise ValueError(f"render_pass must be one of {PASSES}")
    out = []
    for src, role in sources:
        p = Path(src).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"{p} does not exist")
        arr = _render(p, view, render_pass, render_size, timeout) if p.suffix.lower() in MODEL_SUFFIXES else im.load_rgba(p)
        try:
            cut, how = cutout(arr)
        except ValueError as e:
            raise ValueError(f"{p}: {e}") from None
        out.append({"source": str(p), "role": role, "cut": cut, "background": how,
                    "subject_px": [int(cut.shape[1]), int(cut.shape[0])]})
    return out


# ---------------------------------------------------------------- sheets

def _strip(cells: list[np.ndarray], background: tuple, gap: int) -> tuple[np.ndarray, list[float]]:
    """Cells side by side on one backdrop with their bottoms on a common ground line, at 1x."""
    h = max(c.shape[0] for c in cells)
    w = sum(c.shape[1] for c in cells) + gap * (len(cells) + 1)
    canvas = np.empty((h + 2 * gap, w, 3), np.uint8)
    canvas[:] = background
    x, centers = gap, []
    for c in cells:
        y = gap + h - c.shape[0]
        region = canvas[y : y + c.shape[0], x : x + c.shape[1]]
        canvas[y : y + c.shape[0], x : x + c.shape[1]] = im.over(c, region)
        centers.append(x + c.shape[1] / 2)
        x += c.shape[1] + gap
    return canvas, centers


def _auto_zoom(h: int, w: int) -> int:
    return max(1, min(16, im.MAX_SHEET_WIDTH // max(w, 1), MAX_SHEET_H // max(h, 1)))


def _sheet(cells: list[np.ndarray], background: tuple, gap: int, zoom: int, caption: str) -> Image.Image:
    """The judge's image: a caption, the strip upscaled nearest-neighbour, letters underneath."""
    strip, centers = _strip(cells, background, gap)
    big = im.upscale(strip, zoom)
    f_cap, f_letter = im.font(14), im.font(28)
    top, bottom = 26, 44
    sheet = Image.new("RGB", (big.shape[1], big.shape[0] + top + bottom), im.BG_SHEET)
    sheet.paste(Image.fromarray(big, "RGB"), (0, top))
    d = ImageDraw.Draw(sheet)
    d.text((8, 5), im.fit_text(caption, f_cap, big.shape[1] - 16), fill=im.FG_DIM, font=f_cap)
    for letter, cx in zip(LETTERS, centers):
        x0, y0, x1, y1 = d.textbbox((0, 0), letter, font=f_letter)
        d.text((cx * zoom - (x0 + x1) / 2, top + big.shape[0] + (bottom - y0 - y1) / 2), letter,
               fill=im.FG_TEXT, font=f_letter)
    return sheet


def _save(sheet: Image.Image, tool: str, near) -> Path:
    """Save under a random, meaningless name (no metadata), so neither the name nor the file
    says which subject is which or which order this is."""
    out = cache_dir(tool, near=near) / f"{tool}_{secrets.token_hex(5)}.png"
    sheet.save(out)
    return out


def _pick_seed(seed: int | None) -> int:
    return secrets.randbelow(2**31) if seed is None or seed < 0 else int(seed)


def reverse_order(order: list[int]) -> list[int]:
    """The order reversed. With an odd count the middle subject would keep its place, so it
    also swaps with its left neighbour: every subject moves between the two sheets."""
    rev = list(order[::-1])
    if len(rev) % 2 and len(rev) > 1:
        m = len(rev) // 2
        rev[m - 1], rev[m] = rev[m], rev[m - 1]
    return rev


def _both_orders(subjects: list[dict], cells: list[np.ndarray], order: list[int], background: str, gap: int,
                 zoom: int, caption: str, tool: str, near) -> tuple[list[Path], list[dict], int]:
    bg = hex_to_rgb(background)
    strip_h = max(c.shape[0] for c in cells) + 2 * gap
    strip_w = sum(c.shape[1] for c in cells) + gap * (len(cells) + 1)
    zoom = zoom or _auto_zoom(strip_h, strip_w)
    caption = caption.format(zoom=zoom)
    paths, keys = [], []
    for s in subjects:
        s["letters"] = []
    for seq in (order, reverse_order(order)):
        sheet = _sheet([cells[i] for i in seq], bg, gap, zoom, caption)
        paths.append(_save(sheet, tool, near))
        keys.append({LETTERS[pos]: subjects[i]["source"] for pos, i in enumerate(seq)})
        for pos, i in enumerate(seq):
            subjects[i]["letters"].append(LETTERS[pos])
    return paths, keys, zoom


def _report(subjects: list[dict], paths: list[Path], keys: list[dict], seed: int, zoom: int) -> dict:
    return {
        "sheets": [str(p) for p in paths],
        "key": keys,
        "subjects": [{k: s[k] for k in ("source", "role", "letters", "background", "subject_px", "scale")} for s in subjects],
        "seed": seed,
        "zoom": zoom,
    }


def _warnings(subjects: list[dict], width: int, zoom: int) -> list[str]:
    out = [f"{Path(s['source']).name} is smaller than the target and was enlarged x{s['scale']:.2f}; its pixels "
           "look blockier than the others'. Use a larger image." for s in subjects if s["scale"] > 1.05]
    out += [f"{Path(s['source']).name}: no transparent or flat background found, so the whole image is the "
            "subject. Crop it to the subject first." for s in subjects if s["background"] == "kept"]
    if width * zoom > im.MAX_SHEET_WIDTH:
        out.append("The sheet is wider than 1500 px and will be downscaled for a reviewer; lower height_px "
                   "or use fewer subjects.")
    return out


def lineup_sheet(
    images: list,
    exemplars: list,
    height_px: int = 96,
    seed: int | None = None,
    background: str = BACKGROUND,
    fit: str = "height",
    view: str = "three_quarter",
    render_pass: str = "shaded",
    zoom: int = 0,
    near=None,
    timeout: int = 900,
) -> dict:
    """The asset render(s) beside 2-3 human-made exemplars at true game size, for "which one
    doesn't belong / looks least professionally made".

    Every subject is cut out (transparent or flat-background margins), scaled nearest-neighbour
    to ``height_px`` on-screen pixels (the long edge with ``fit="long_edge"``), placed in a
    seeded random order labelled only A, B, C... over ``background``, and the sheet is upscaled
    nearest-neighbour for viewing. A second sheet holds the reversed order (see
    ``reverse_order``); letters always run left to right, so each sheet has its own key. 3D
    files are rendered first, all alike (``view``, ``render_pass``). Returns sheet paths, the
    keys (letter -> source) for the caller only, each subject's letters, and the prompts.
    """
    if not images:
        raise ValueError("give at least one asset image")
    if not exemplars:
        raise ValueError("give 2-3 human-made exemplars to line the asset up against")
    if len(images) + len(exemplars) > len(LETTERS):
        raise ValueError(f"at most {len(LETTERS)} subjects per lineup")
    if fit not in FITS:
        raise ValueError(f"fit must be one of {FITS}")
    if height_px < 4:
        raise ValueError("height_px is the subject's on-screen height in game pixels (at least 4)")
    seed = _pick_seed(seed)
    sources = [(str(p), "asset") for p in images] + [(str(p), "exemplar") for p in exemplars]
    subjects = _subjects(sources, view, render_pass, int(np.clip(4 * height_px, 512, 1024)), timeout)
    cells = [_scaled(s, height_px, fit) for s in subjects]
    order = list(range(len(subjects)))
    random.Random(seed).shuffle(order)
    gap = max(3, round(0.15 * height_px))
    edge = "tall" if fit == "height" else "on the long edge"
    caption = f"Lineup at game size: {len(cells)} subjects, {height_px} px {edge}, each pixel shown {{zoom}}x"
    paths, keys, zoom = _both_orders(subjects, cells, order, background, gap, zoom, caption, "lineup", near or images[0])
    rep = _report(subjects, paths, keys, seed, zoom)
    rep["height_px"] = height_px
    rep["prompts"] = [LINEUP_PROMPT.format(n=len(cells), first="A", last=LETTERS[len(cells) - 1], zoom=zoom, path=p)
                      for p in paths]
    width = sum(c.shape[1] for c in cells) + gap * (len(cells) + 1)
    rep["warnings"] = _warnings(subjects, width, zoom)
    if not 2 <= len(exemplars) <= 3:
        rep["warnings"].append(f"{len(exemplars)} exemplar(s): the protocol lines an asset up against 2-3.")
    return rep


def ab_sheet(
    a,
    b,
    height_px: int = 0,
    seed: int | None = None,
    background: str = BACKGROUND,
    question: str = AB_QUESTION,
    fit: str = "height",
    view: str = "three_quarter",
    render_pass: str = "shaded",
    zoom: int = 0,
    near=None,
    timeout: int = 900,
) -> dict:
    """Two candidates side by side, as a pair of sheets in both orders (A|B, then swapped).

    ``height_px`` > 0 shows both at that game size (nearest-neighbour, upscaled for viewing);
    0 shows them large at a shared height for detail. The seed picks which candidate is on
    the left first. Letters always run left to right, so each sheet has its own key.
    """
    if fit not in FITS:
        raise ValueError(f"fit must be one of {FITS}")
    seed = _pick_seed(seed)
    size = int(np.clip(4 * height_px, 512, 1024)) if height_px else 1024
    subjects = _subjects([(str(a), "a"), (str(b), "b")], view, render_pass, size, timeout)
    gap = max(3, round(0.15 * (height_px or 200)))
    if height_px:
        target, resample, edge = height_px, Image.NEAREST, f", at game size ({height_px} px)"
    else:
        # large enough to see detail, small enough that both fit under 1500 px, never enlarged
        refs = [_ref(s["cut"].shape, fit) for s in subjects]
        room = (im.MAX_SHEET_WIDTH - 3 * gap) / sum(s["cut"].shape[1] / r for s, r in zip(subjects, refs))
        target = max(4, int(min(640, room, *refs)))
        resample, edge, zoom = Image.LANCZOS, "", 1
    cells = [_scaled(s, target, fit, resample) for s in subjects]
    order = [0, 1] if random.Random(seed).random() < 0.5 else [1, 0]
    caption = (f"A/B at game size: {height_px} px, each pixel shown {{zoom}}x" if height_px
               else "A/B: two versions at the same height")
    paths, keys, zoom = _both_orders(subjects, cells, order, background, gap, zoom, caption, "ab", near or a)
    rep = _report(subjects, paths, keys, seed, zoom)
    rep["height_px"] = height_px
    rep["prompts"] = [AB_PROMPT.format(size=edge, question=question, path=p) for p in paths]
    width = sum(c.shape[1] for c in cells) + gap * 3
    rep["warnings"] = _warnings(subjects, width, zoom) if height_px else []
    return rep
