"""Pixel Cleanup: turn AI-generated or painted "fake pixel art" into true pixel art.

Pipeline: find the real pixel grid → sample each cell's center → remove a flat background
→ snap colors to a palette (or a small automatic one) → binarize alpha → remove strays and
noise → optional outline. The result is native resolution, one array cell per art pixel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from opus import imaging as im
from opus.paths import output_path
from opus.pixel import analysis as an
from opus.pixel.color import hex_to_rgb, rgb_to_hex, rgb_to_oklab
from opus.pixel.palette import Palette, apply_palette, extract_colors, load_palette


@dataclass
class Grid:
    px: float  # cell width in source pixels
    py: float  # cell height
    ox: float  # x of the first cell boundary
    oy: float
    confidence: float  # phase coherence of edges on this grid, 0..1

    @property
    def found(self) -> bool:
        return self.px >= 1.5 and self.py >= 1.5 and self.confidence >= 0.3


def _edge_profile(rgb: np.ndarray, axis: int) -> np.ndarray:
    """Mean absolute color change between neighboring columns (axis=1) or rows (axis=0)."""
    d = np.abs(np.diff(rgb.astype(np.float32), axis=axis)).sum(-1)
    return d.mean(axis=0 if axis == 1 else 1)


def _periodogram(g: np.ndarray, periods: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalized Fourier response of the edge profile at each candidate period.

    Before measuring period p, the profile's moving average over one period is subtracted.
    That keeps everything that repeats every p pixels and removes slow changes, such as
    the sprite's overall silhouette, which would otherwise fake a long period.
    """
    n = len(g)
    x = np.arange(n)
    cs = np.concatenate([[0.0], np.cumsum(g)])
    R = np.zeros(len(periods))
    Z = np.zeros(len(periods), dtype=complex)
    for i, p in enumerate(periods):
        w = max(2, int(round(p)))
        lo = np.clip(x - w // 2, 0, n)
        hi = np.clip(x - w // 2 + w, 0, n)
        r = g - (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1)
        z = np.sum(r * np.exp(2j * np.pi * x / p))
        Z[i] = z
        R[i] = abs(z) / (np.abs(r).sum() + 1e-9)
    return R, Z


MIN_CELLS = 8  # a sprite is at least this many art pixels across
MIN_RESPONSE = 0.12  # periodogram response below this is noise, not a grid


def _square_grid(gx: np.ndarray, gy: np.ndarray, p_min: float = 2.0, p_max: float = 64.0):
    """Candidate square cell sizes with per-axis phases, from the edge profiles.

    Art pixels are square, so both axes vote on one period. A pulse train with period p
    also repeats at p/2, p/3, … but cancels at 2p, so the true cell size is normally the
    *largest* period whose response is close to the best. Candidates come back largest
    first as (period, phase_x, phase_y, response); the caller checks each one against the
    image and keeps the first that really reconstructs it.
    """
    hi = min(p_max, len(gx) / MIN_CELLS, len(gy) / MIN_CELLS)
    if hi <= p_min + 0.1:
        return []
    periods = np.arange(p_min, hi, 0.05)
    Rx, _ = _periodogram(gx, periods)
    Ry, _ = _periodogram(gy, periods)
    R = 0.5 * (Rx + Ry)
    is_peak = np.r_[False, (R[1:-1] >= R[:-2]) & (R[1:-1] >= R[2:]), False]
    cand = np.where(is_peak & (R >= 0.5 * R.max()) & (R >= MIN_RESPONSE))[0]
    # merge candidates closer than 6% (ripples on one lobe)
    lobes: list[list[int]] = []
    for c in sorted(cand, key=lambda i: periods[i]):
        if lobes and periods[c] <= periods[lobes[-1][-1]] * 1.06:
            lobes[-1].append(int(c))
        else:
            lobes.append([int(c)])
    out = []
    for lobe in sorted(lobes, key=lambda lb: -periods[lb[-1]])[:5]:
        center = periods[lobe[int(np.argmax(R[lobe]))]]
        fine = np.arange(max(p_min, center * 0.97), center * 1.03, 0.005)
        Rxf, Zxf = _periodogram(gx, fine)
        Ryf, Zyf = _periodogram(gy, fine)
        Rf = 0.5 * (Rxf + Ryf)
        k = int(np.argmax(Rf))
        p = float(fine[k])
        phase_x = (np.angle(Zxf[k]) / (2.0 * np.pi) * p) % p
        phase_y = (np.angle(Zyf[k]) / (2.0 * np.pi) * p) % p
        out.append((p, float(phase_x), float(phase_y), float(Rf[k])))
    return out


def _comb(g: np.ndarray, p: float, phases: np.ndarray) -> np.ndarray:
    """Mean edge energy at positions phase + k·p (linear interpolation), per phase."""
    n = len(g)
    k = np.arange(int(n / p) + 1)
    pos = phases[:, None] + k[None, :] * p
    valid = pos <= n - 1
    i0 = np.clip(np.floor(pos).astype(int), 0, n - 1)
    i1 = np.clip(i0 + 1, 0, n - 1)
    f = pos - np.floor(pos)
    vals = np.where(valid, g[i0] * (1 - f) + g[i1] * f, 0.0)
    return vals.sum(1) / np.maximum(valid.sum(1), 1)


def _refine(gx: np.ndarray, gy: np.ndarray, p0: float, span: float = 0.08) -> tuple[float, float, float]:
    """Pin down the exact cell size near ``p0``: boundaries should land on the edges.

    Within ±8% of a candidate there are no harmonics to confuse things, so the period and
    phases whose comb collects the most edge energy on both axes win.
    """
    best = (-1.0, p0, 0.0, 0.0)
    mx, my = gx.mean() + 1e-9, gy.mean() + 1e-9
    for p in np.linspace(p0 * (1 - span), p0 * (1 + span), 161):
        phases = np.arange(0.0, p, 0.1)
        sx, sy = _comb(gx, p, phases), _comb(gy, p, phases)
        jx, jy = int(np.argmax(sx)), int(np.argmax(sy))
        score = sx[jx] / mx + sy[jy] / my
        if score > best[0]:
            best = (score, float(p), float(phases[jx]), float(phases[jy]))
    return best[1], best[2], best[3]


MAX_NATIVE_COLORS = 256  # clean pixel art; AI and painted images have thousands
MAX_CELL_SPREAD = 0.025  # 90th-percentile color spread inside cells: real grids ~0.01-0.02, wrong ones 0.03+


def detect_grid(rgba: np.ndarray) -> Grid:
    """Estimate the art-pixel grid of an image.

    Exact for clean integer upscales. Images that already look like clean native pixel art
    (few colors, no upscale) are left alone. Otherwise each candidate cell size is tried,
    largest first, and accepted only if the insides of its cells are nearly uniform.
    """
    k = an.detect_upscale(rgba)
    if k > 1:
        return Grid(float(k), float(k), 0.0, 0.0, 1.0)
    if len(extract_colors(an.normalize_transparent(rgba))[0]) <= MAX_NATIVE_COLORS:
        return Grid(1.0, 1.0, 0.0, 0.0, 1.0)  # already native pixel art
    rgb = im.over(rgba, (128, 128, 128))
    gx, gy = _edge_profile(rgb, 1), _edge_profile(rgb, 0)
    for p0, _, _, _ in _square_grid(gx, gy):
        p, ox, oy = _refine(gx, gy, p0)
        # boundaries sit between columns: phase is measured on the diff signal, shift by +1
        grid = Grid(p, p, (ox + 1.0) % p, (oy + 1.0) % p, 1.0)
        _, spread = _sample(rgba, grid)
        if spread <= MAX_CELL_SPREAD:
            grid.confidence = float(max(0.0, min(1.0, 1.0 - spread / MAX_CELL_SPREAD + 0.3)))
            return grid
    return Grid(1.0, 1.0, 0.0, 0.0, 0.0)


def _spans(n: int, p: float, o: float) -> list[tuple[float, float]]:
    starts = np.arange(o - p, n, p)
    return [(s, s + p) for s in starts if 0 <= s + p * 0.5 < n]


def _sample(rgba: np.ndarray, grid: Grid, margin: float = 0.25) -> tuple[np.ndarray, float]:
    """Median color of each cell's center, plus the 90th-percentile color spread inside cells."""
    h, w = rgba.shape[:2]
    cols = _spans(w, grid.px, grid.ox)
    rows = _spans(h, grid.py, grid.oy)
    lab = rgb_to_oklab(rgba[..., :3].astype(np.float64))
    alpha = rgba[..., 3].astype(np.float64) / 255.0
    out = np.zeros((len(rows), len(cols), 4), np.uint8)
    spreads = np.zeros((len(rows), len(cols)))
    m_x, m_y = grid.px * margin, grid.py * margin
    for i, (y0, y1) in enumerate(rows):
        ya, yb = int(np.clip(round(y0 + m_y), 0, h - 1)), int(np.clip(round(y1 - m_y), 1, h))
        yb = max(yb, ya + 1)
        for j, (x0, x1) in enumerate(cols):
            xa, xb = int(np.clip(round(x0 + m_x), 0, w - 1)), int(np.clip(round(x1 - m_x), 1, w))
            xb = max(xb, xa + 1)
            out[i, j] = np.median(rgba[ya:yb, xa:xb].reshape(-1, 4), axis=0).astype(np.uint8)
            cl = lab[ya:yb, xa:xb].reshape(-1, 3)
            ca = alpha[ya:yb, xa:xb].reshape(-1)
            d = np.linalg.norm(cl - np.median(cl, axis=0), axis=1) + np.abs(ca - np.median(ca))
            spreads[i, j] = float(d.mean())
    spread = float(np.percentile(spreads, 90)) if spreads.size else 1.0
    return out, spread


def sample_cells(rgba: np.ndarray, grid: Grid, margin: float = 0.25) -> np.ndarray:
    """Median color of the central part of each grid cell → native-resolution image."""
    if not grid.found:
        return rgba.copy()
    return _sample(rgba, grid, margin)[0]


def remove_background(rgba: np.ndarray, mode: str = "auto", tol: float = 0.035) -> tuple[np.ndarray, str | None]:
    """Make a flat background transparent by flood-filling from the border.

    ``mode``: "auto" (only when ≥55% of the border is one color), "none", or a hex color.
    Returns (image, removed_color_hex or None).
    """
    if mode == "none" or (rgba[..., 3] < 255).mean() > 0.05:
        return rgba, None  # already has transparency
    h, w = rgba.shape[:2]
    lab = rgb_to_oklab(rgba[..., :3].astype(np.float64))
    border = np.concatenate([rgba[0], rgba[-1], rgba[:, 0], rgba[:, -1]])[:, :3].astype(np.float64)
    if mode == "auto":
        bg = np.median(border, axis=0)  # robust to noise and a few sprite pixels
        d = np.linalg.norm(rgb_to_oklab(border) - rgb_to_oklab(bg), axis=-1)
        if (d < tol).mean() < 0.55:
            return rgba, None
    else:
        bg = np.array(hex_to_rgb(mode), dtype=np.float64)
    near = np.linalg.norm(lab - rgb_to_oklab(bg), axis=-1) < tol
    # flood fill from border pixels that match the background
    filled = np.zeros((h, w), bool)
    frontier = np.zeros((h, w), bool)
    frontier[0, :], frontier[-1, :], frontier[:, 0], frontier[:, -1] = True, True, True, True
    frontier &= near
    while frontier.any():
        filled |= frontier
        grow = np.zeros_like(frontier)
        for dy, dx in an.N4:
            grow |= an.neighbor(frontier, dy, dx, False)
        frontier = grow & near & ~filled
    out = rgba.copy()
    out[filled] = 0
    return out, rgb_to_hex(bg)


def auto_palette(rgba: np.ndarray, max_colors: int, merge_distance: float = 0.02) -> Palette:
    """A small palette for the opaque pixels (median cut, then near-duplicates merged)."""
    px = rgba[rgba[..., 3] > 0][:, :3]
    if len(px) == 0:
        return Palette([(0, 0, 0)])
    strip = Image.fromarray(px.reshape(1, -1, 3).astype(np.uint8), "RGB")
    q = strip.quantize(colors=max(2, min(256, max_colors)), method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[: 3 * 256], dtype=np.uint8).reshape(-1, 3)
    used = np.unique(np.array(q).ravel())
    cols = pal[used]
    lab = rgb_to_oklab(cols.astype(np.float64))
    keep: list[int] = []
    for i in range(len(cols)):
        if all(np.linalg.norm(lab[i] - lab[j]) >= merge_distance for j in keep):
            keep.append(i)
    return Palette([tuple(int(v) for v in cols[i]) for i in keep], name="auto", source="auto_palette")


def despeckle(rgba: np.ndarray, min_votes: int = 4) -> tuple[np.ndarray, int, int]:
    """Drop stray pixels; recolor orphans that sit inside a mostly uniform neighborhood."""
    out = rgba.copy()
    strays, orphans = an.single_pixels(out)
    out[strays] = 0
    keys = an.color_keys(out)
    fixed = 0
    ys, xs = np.nonzero(orphans)
    for y, x in zip(ys.tolist(), xs.tolist()):
        votes: dict[int, int] = {}
        for dy, dx in an.N8:
            yy, xx = y + dy, x + dx
            if 0 <= yy < out.shape[0] and 0 <= xx < out.shape[1] and out[yy, xx, 3] > 0:
                kk = int(keys[yy, xx])
                votes[kk] = votes.get(kk, 0) + 1
        if votes:
            kk, n = max(votes.items(), key=lambda t: t[1])
            if n >= min_votes:
                out[y, x] = [(kk >> 24) & 255, (kk >> 16) & 255, (kk >> 8) & 255, kk & 255]
                fixed += 1
    return out, int(strays.sum()), fixed


def trim(rgba: np.ndarray, pad: int = 0) -> np.ndarray:
    """Crop to the bounding box of opaque pixels, keeping ``pad`` transparent pixels around."""
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    if len(ys) == 0:
        return rgba
    y0, y1 = max(0, ys.min() - pad), min(rgba.shape[0], ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(rgba.shape[1], xs.max() + 1 + pad)
    return rgba[y0:y1, x0:x1]


def add_outline(rgba: np.ndarray, color) -> np.ndarray:
    """1-px outline just outside the silhouette (8-connected), canvas grown by 1 px."""
    padded = np.pad(rgba, ((1, 1), (1, 1), (0, 0)))
    opaque = padded[..., 3] > 0
    ring = np.zeros_like(opaque)
    for dy, dx in an.N8:
        ring |= an.neighbor(opaque, dy, dx, False)
    ring &= ~opaque
    padded[ring] = (*color, 255)
    return padded


def cleanup(
    path: str | Path,
    palette=None,
    max_colors: int = 24,
    background: str = "auto",
    outline: str = "none",
    despeckle_votes: int = 4,
    crop: bool = True,
    out: str | Path | None = None,
) -> tuple[Path, Path, dict]:
    """Clean an image into native pixel art. Returns (clean_png, preview_png, report)."""
    path = Path(path)
    src = im.load_rgba(path)
    grid = detect_grid(src)
    native = sample_cells(src, grid)
    native, bg_removed = remove_background(native, background)
    if crop and bg_removed is not None or crop and (native[..., 3] == 0).any():
        native = trim(native)
    colors_before = int(len(extract_colors(native)[0]))
    pal = load_palette(palette) or auto_palette(native, max_colors)
    native = apply_palette(native, pal)
    native, strays, recolored = despeckle(native, despeckle_votes)
    if outline and outline != "none":
        if outline in ("dark", "darkest"):
            lab_l = rgb_to_oklab(pal.array.astype(np.float64))[:, 0]
            color = tuple(int(v) for v in pal.array[int(np.argmin(lab_l))])
        else:
            color = hex_to_rgb(outline)
        native = add_outline(native, color)
    used = extract_colors(native)[0]

    clean_path = Path(out) if out else output_path("pixel_cleanup", f"{path.stem}_clean", near=path)
    im.save_rgba(native, clean_path)

    sheet = im.Sheet(
        title=f"Pixel Cleanup · {path.name}",
        subtitle=(
            f"grid {grid.px:.2f}x{grid.py:.2f} px (confidence {grid.confidence:.1f}) -> "
            f"{native.shape[1]}x{native.shape[0]} native · {len(used)} colors"
        ),
    )
    before = Image.fromarray(im.over(src, im.checkerboard(src.shape[0], src.shape[1], 12)))
    before.thumbnail((560, 560), Image.LANCZOS)
    k = im.zoom_to_fit(native.shape[0], native.shape[1], 560)
    big = im.upscale(native, k)
    after = im.draw_grid(im.over(big, im.checkerboard(big.shape[0], big.shape[1], max(4, 2 * k))), k)
    sheet.add_row(
        "Before / after",
        [im.Tile(before, "original"), im.Tile(im.to_image(after), f"cleaned, zoom x{k}")],
    )
    preview_path = clean_path.with_name(clean_path.stem + "_preview.png")
    sheet.render().save(preview_path)

    report = {
        "file": str(path),
        "grid": asdict(grid) | {"found": grid.found},
        "native_size": [int(native.shape[1]), int(native.shape[0])],
        "background_removed": bg_removed,
        "palette": pal.name or pal.source,
        "colors_before_quantize": colors_before,
        "colors_after": int(len(used)),
        "strays_removed": strays,
        "orphans_recolored": recolored,
        "outline": outline,
        "clean": str(clean_path),
        "preview": str(preview_path),
    }
    if not grid.found:
        report["note"] = "No pixel grid detected; treated the image as native resolution."
    return clean_path, preview_path, report
