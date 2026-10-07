"""Pixel-level measurements behind the Sprite Inspector.

Everything works on RGBA uint8 arrays at *native* resolution (one array cell = one art
pixel). ``detect_upscale`` recovers native resolution from cleanly upscaled exports.
"""

from __future__ import annotations

import numpy as np

from opus.pixel.color import rgb_to_oklab

LIGHT_DIRS = {
    "top-left": (-1.0, -1.0),
    "top": (0.0, -1.0),
    "top-right": (1.0, -1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
    "front": (0.0, 0.0),
}


def neighbor(a: np.ndarray, dy: int, dx: int, fill=0) -> np.ndarray:
    """out[y, x] = a[y + dy, x + dx], or ``fill`` outside the image."""
    h, w = a.shape[:2]
    out = np.empty_like(a)
    out[...] = fill
    y0, y1 = max(0, -dy), min(h, h - dy)
    x0, x1 = max(0, -dx), min(w, w - dx)
    if y0 < y1 and x0 < x1:
        out[y0:y1, x0:x1] = a[y0 + dy : y1 + dy, x0 + dx : x1 + dx]
    return out


N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
N4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def normalize_transparent(rgba: np.ndarray) -> np.ndarray:
    """Zero the RGB of fully transparent pixels so they compare equal."""
    out = rgba.copy()
    out[out[..., 3] == 0] = 0
    return out


def color_keys(rgba: np.ndarray) -> np.ndarray:
    """Pack RGBA into one uint32 per pixel for fast equality tests."""
    a = rgba.astype(np.uint32)
    return (a[..., 0] << 24) | (a[..., 1] << 16) | (a[..., 2] << 8) | a[..., 3]


def detect_upscale(rgba: np.ndarray, max_k: int = 32, tol: float = 0.995) -> int:
    """Largest integer k such that the image is (almost) entirely k×k uniform blocks."""
    rgba = normalize_transparent(rgba)
    h, w = rgba.shape[:2]
    best = 1
    for k in range(2, min(max_k, h, w) + 1):
        if h % k or w % k:
            continue
        blocks = rgba.reshape(h // k, k, w // k, k, 4)
        uniform = np.all(blocks == blocks[:, :1, :, :1, :], axis=(1, 3, 4))
        if uniform.mean() >= tol:
            best = k
    return best


def to_native(rgba: np.ndarray) -> tuple[np.ndarray, int]:
    k = detect_upscale(rgba)
    return (normalize_transparent(rgba)[::k, ::k] if k > 1 else normalize_transparent(rgba)), k


def lightness_map(rgba: np.ndarray) -> np.ndarray:
    return rgb_to_oklab(rgba[..., :3].astype(np.float64))[..., 0]


def single_pixels(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(strays, orphans): opaque pixels sharing a color with none of their 8 neighbors.

    Strays have no opaque neighbor at all (lost specks). Orphans sit among other colors:
    sometimes an intentional glint, but in quantity they are noise (typical of AI output).
    Checkerboard dithering is not flagged because diagonal neighbors match.
    """
    keys = color_keys(normalize_transparent(rgba))
    opaque = rgba[..., 3] > 0
    same = np.zeros(keys.shape, dtype=bool)
    any_opaque = np.zeros(keys.shape, dtype=bool)
    for dy, dx in N8:
        nk = neighbor(keys, dy, dx, 0)
        same |= nk == keys
        any_opaque |= (neighbor(rgba[..., 3], dy, dx, 0) > 0)
    lonely = opaque & ~same
    return lonely & ~any_opaque, lonely & any_opaque


def dark_line_mask(rgba: np.ndarray, quantile: float = 0.25) -> np.ndarray:
    """Opaque pixels in the darkest band of the sprite's lightness range (outlines, line art)."""
    opaque = rgba[..., 3] > 0
    if not opaque.any():
        return opaque
    L = lightness_map(rgba)
    lo, hi = L[opaque].min(), L[opaque].max()
    return opaque & (L <= lo + quantile * (hi - lo) + 1e-9)


def boundary_mask(rgba: np.ndarray) -> np.ndarray:
    """Opaque pixels touching transparency (or the image edge) through a 4-neighbor."""
    opaque = rgba[..., 3] > 0
    edge = np.zeros_like(opaque)
    for dy, dx in N4:
        edge |= ~neighbor(opaque, dy, dx, False)
    return opaque & edge


def jaggy_elbows(line: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(elbows, clumps) in 1-px line art.

    An elbow is an L-shaped corner pixel on a curve: it touches two line pixels that already
    touch each other diagonally, and neither arm continues straight. Removing it keeps the
    line connected and makes the curve cleaner ("doubles" / jaggies). True box corners,
    whose arms continue straight, are not flagged. Clumps are 2×2 blocks of line pixels
    (uneven line weight).
    """
    n = {d: neighbor(line, d[0], d[1], False) for d in N8}
    n2 = {d: neighbor(line, 2 * d[0], 2 * d[1], False) for d in N4}
    elbows = np.zeros_like(line)
    for vy in (-1, 1):
        for hx in (-1, 1):
            v, h, diag = (vy, 0), (0, hx), (vy, hx)
            l_shape = line & n[v] & n[h] & ~n[diag]
            # no other orthogonal line neighbors (keeps T-junctions and thick lines out)
            others = [d for d in N4 if d not in (v, h)]
            l_shape &= ~n[others[0]] & ~n[others[1]]
            straight = n2[v] | n2[h]
            elbows |= l_shape & ~straight
    clumps = line & n[(0, 1)] & n[(1, 0)] & n[(1, 1)]
    return elbows, clumps


def distance_from_edge(opaque: np.ndarray, cap: int = 64) -> np.ndarray:
    """Chessboard distance of each opaque pixel from transparency (1 at the silhouette edge)."""
    dist = np.zeros(opaque.shape, dtype=np.int32)
    cur = opaque.copy()
    for d in range(1, cap + 1):
        if not cur.any():
            break
        dist[cur] = d
        eroded = cur.copy()
        for dy, dx in N8:
            eroded &= neighbor(cur, dy, dx, False)
        cur = eroded
    return dist


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 8 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def shading_report(rgba: np.ndarray, light: str = "top-left") -> dict:
    """Does lightness follow the light direction, or just the distance from the outline?

    Pillow shading (dark rim, bright middle, regardless of light) shows up as lightness that
    correlates with distance-from-edge much more strongly than with the light direction.
    """
    opaque = rgba[..., 3] > 0
    line = dark_line_mask(rgba)
    body = opaque & ~line
    if body.sum() < 16:
        return {"checked": False}
    L = lightness_map(rgba)
    dist = distance_from_edge(opaque).astype(np.float64)
    ys, xs = np.nonzero(body)
    cy, cx = ys.mean(), xs.mean()
    lx, ly = LIGHT_DIRS.get(light, LIGHT_DIRS["top-left"])
    norm = max(1e-9, (lx * lx + ly * ly) ** 0.5)
    proj = ((xs - cx) * lx + (ys - cy) * ly) / norm if norm > 1e-6 else np.zeros_like(xs, float)
    c_edge = _corr(L[body], dist[body])
    c_light = _corr(L[body], proj)
    pillow = bool(c_edge > 0.45 and c_edge > c_light + 0.15)
    return {
        "checked": True,
        "light": light,
        "lightness_vs_light_direction": round(c_light, 2),
        "lightness_vs_distance_from_edge": round(c_edge, 2),
        "pillow_shading_likely": pillow,
    }


def tile_seams(rgba: np.ndarray) -> dict:
    """How visible the wrap-around seams are when the image tiles (1.0 = like the interior)."""
    lab = rgb_to_oklab(rgba[..., :3].astype(np.float64))
    a = rgba[..., 3:4].astype(np.float64) / 255.0
    lab = np.concatenate([lab, a], axis=-1)
    eps = 1e-6

    def ratio(axis: int) -> float:
        d_int = np.linalg.norm(np.diff(lab, axis=axis), axis=-1).mean()
        first = np.take(lab, 0, axis=axis)
        last = np.take(lab, -1, axis=axis)
        d_wrap = np.linalg.norm(last - first, axis=-1).mean()
        return float(d_wrap / (d_int + eps))

    rx, ry = ratio(1), ratio(0)
    return {
        "horizontal_seam_ratio": round(rx, 2),
        "vertical_seam_ratio": round(ry, 2),
        "transparent_fraction": round(float((rgba[..., 3] == 0).mean()), 3),
        "seams_visible": bool(rx > 1.8 or ry > 1.8),
    }


def split_frames(rgba: np.ndarray, fw: int, fh: int) -> list[np.ndarray]:
    """Row-major frames of a sprite sheet, skipping fully transparent cells."""
    h, w = rgba.shape[:2]
    frames = []
    for y in range(0, h - fh + 1, fh):
        for x in range(0, w - fw + 1, fw):
            f = rgba[y : y + fh, x : x + fw]
            if (f[..., 3] > 0).any():
                frames.append(f)
    return frames


def frame_report(frames: list[np.ndarray]) -> dict:
    if not frames:
        return {"frames": 0}
    baselines, centers, counts, color_sets = [], [], [], []
    for f in frames:
        op = f[..., 3] > 0
        ys, xs = np.nonzero(op)
        baselines.append(int(ys.max()))
        centers.append((float(xs.mean()), float(ys.mean())))
        counts.append(int(op.sum()))
        color_sets.append({tuple(c) for c in f[op][:, :3].tolist()})
    diffs = []
    for a, b in zip(frames, frames[1:] + frames[:1]):
        changed = np.any(a != b, axis=-1)
        diffs.append(round(float(changed.mean()), 3))
    union = set().union(*color_sets)
    common = set.intersection(*color_sets) if color_sets else set()
    cx = [c[0] for c in centers]
    cy = [c[1] for c in centers]
    return {
        "frames": len(frames),
        "baseline_jitter_px": int(max(baselines) - min(baselines)),
        "center_jitter_px": [round(max(cx) - min(cx), 1), round(max(cy) - min(cy), 1)],
        "pixel_count_range": [min(counts), max(counts)],
        "colors_total": len(union),
        "colors_not_in_every_frame": len(union - common),
        "changed_fraction_per_step": diffs[:-1],
        "loop_seam_changed_fraction": diffs[-1],
    }


def contrast_report(rgba: np.ndarray, backgrounds: dict[str, tuple[int, int, int]]) -> dict:
    opaque = rgba[..., 3] > 0
    if not opaque.any():
        return {}
    L = lightness_map(rgba)[opaque]
    edge = boundary_mask(rgba)
    Ledge = lightness_map(rgba)[edge] if edge.any() else L
    out = {}
    for name, rgb in backgrounds.items():
        Lb = float(rgb_to_oklab(np.array(rgb, dtype=np.float64))[0])
        out[name] = {
            "mean_lightness_gap": round(abs(float(L.mean()) - Lb), 3),
            "silhouette_edge_gap": round(abs(float(Ledge.mean()) - Lb), 3),
        }
    return out
