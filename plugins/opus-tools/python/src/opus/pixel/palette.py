"""Palette Lab: load palettes, build hue-shifted ramps, lock images to a palette, swap palettes.

Palettes can come from a file (.hex, .txt, .gpl, .pal, .json, or a palette image), an inline
list of hex colors, or ``lospec:<slug>`` (fetched once from lospec.com and cached).
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from opus.imaging import font
from opus.pixel.color import (
    hex_to_rgb,
    hue_delta,
    oklab_in_gamut,
    oklch_to_oklab,
    oklch_to_rgb,
    rgb_to_hex,
    rgb_to_oklab,
    rgb_to_oklch,
)

HEX_RE = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

# Hue targets for ramp shifting: highlights drift warm, shadows drift cool.
WARM_HUE = 80.0
COOL_HUE = 280.0
ACHROMATIC_CHROMA = 0.025
# Very light and very dark steps of a ramp naturally lose chroma; below this they still
# count as part of a hue family, not as grays.
FAINT_CHROMA = 0.012


@dataclass
class Palette:
    colors: list[tuple[int, int, int]]
    name: str = ""
    source: str = ""
    notes: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.colors)

    @property
    def array(self) -> np.ndarray:
        return np.array(self.colors, dtype=np.uint8).reshape(-1, 3)

    def hex(self) -> list[str]:
        return [rgb_to_hex(c) for c in self.colors]


def _dedupe(colors) -> list[tuple[int, int, int]]:
    seen, out = set(), []
    for c in colors:
        t = tuple(int(v) for v in c[:3])
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _cache_root() -> Path:
    base = os.environ.get("OPUS_CACHE_DIR") or os.environ.get("CLAUDE_PLUGIN_DATA")
    root = Path(base) if base else Path.home() / ".cache" / "opus-tools"
    d = root / "palettes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch_lospec(slug: str) -> Palette:
    slug = slug.strip().lower()
    cached = _cache_root() / f"{slug}.hex"
    if not cached.exists():
        url = f"https://lospec.com/palette-list/{slug}.hex"
        with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 - fixed https host
            cached.write_text(r.read().decode("utf-8"))
    pal = _parse_hex_text(cached.read_text())
    pal.name, pal.source = slug, f"lospec:{slug}"
    return pal


def _parse_hex_text(text: str) -> Palette:
    colors = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("//"):
            continue
        for m in HEX_RE.finditer(line):
            colors.append(hex_to_rgb(m.group(1)))
    return Palette(_dedupe(colors))


def _parse_gpl(text: str) -> Palette:
    colors, name = [], ""
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith("name:"):
            name = s.split(":", 1)[1].strip()
            continue
        parts = s.split()
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            colors.append(tuple(int(p) for p in parts[:3]))
    return Palette(_dedupe(colors), name=name)


def _parse_jasc(text: str) -> Palette:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    colors = []
    for ln in lines[3:]:
        parts = ln.split()
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            colors.append(tuple(int(p) for p in parts[:3]))
    return Palette(_dedupe(colors))


def _from_image(path: Path) -> Palette:
    with Image.open(path) as im:
        arr = np.array(im.convert("RGBA")).reshape(-1, 4)
    arr = arr[arr[:, 3] > 0][:, :3]
    return Palette(_dedupe(arr.tolist()))


def load_palette(spec) -> Palette | None:
    """Resolve a palette spec. Returns None for an empty spec."""
    if spec is None or (isinstance(spec, str) and not spec.strip()):
        return None
    if isinstance(spec, Palette):
        return spec
    if isinstance(spec, (list, tuple)):
        return Palette(_dedupe(hex_to_rgb(c) if isinstance(c, str) else c for c in spec), source="inline")
    s = str(spec).strip()
    if s.lower().startswith("lospec:"):
        return _fetch_lospec(s.split(":", 1)[1])
    p = Path(s).expanduser()
    if p.exists():
        suffix = p.suffix.lower()
        text_loaders = {".gpl": _parse_gpl, ".pal": _parse_jasc}
        if suffix in (".png", ".gif", ".webp", ".bmp"):
            pal = _from_image(p)
        elif suffix == ".json":
            data = json.loads(p.read_text())
            cols = data.get("colors", data) if isinstance(data, dict) else data
            pal = load_palette(list(cols))
            if isinstance(data, dict):
                pal.name = data.get("name", "")
        elif suffix in text_loaders:
            text = p.read_text(errors="replace")
            pal = _parse_jasc(text) if text.startswith("JASC-PAL") else text_loaders[suffix](text)
        else:
            pal = _parse_hex_text(p.read_text(errors="replace"))
        pal.name = pal.name or p.stem
        pal.source = str(p)
        return pal
    tokens = HEX_RE.findall(s)
    if tokens:
        return Palette(_dedupe(hex_to_rgb(t) for t in tokens), source="inline")
    raise ValueError(f"could not resolve palette {spec!r} (file not found and no hex colors in it)")


def save_hex(palette: Palette, path: str | Path) -> Path:
    path = Path(path)
    path.write_text("\n".join(h.lstrip("#") for h in palette.hex()) + "\n")
    return path


# ---------------------------------------------------------------- analysis

def extract_colors(rgba: np.ndarray, alpha_threshold: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Unique opaque colors (N, 3) and their pixel counts, most common first."""
    px = rgba.reshape(-1, 4)
    px = px[px[:, 3] >= alpha_threshold][:, :3]
    if len(px) == 0:
        return np.zeros((0, 3), np.uint8), np.zeros((0,), np.int64)
    cols, counts = np.unique(px, axis=0, return_counts=True)
    order = np.argsort(-counts)
    return cols[order], counts[order]


def group_ramps(colors: np.ndarray, hue_gap: float = 28.0) -> list[list[int]]:
    """Group colors into ramps (indices into ``colors``), each sorted dark → light.

    Near-grays form one neutral ramp; chromatic colors are split wherever the hue wheel
    has a gap wider than ``hue_gap`` degrees.
    """
    if len(colors) == 0:
        return []
    lch = rgb_to_oklch(colors.astype(np.float64))
    idx = np.arange(len(colors))
    extreme = (lch[:, 0] > 0.85) | (lch[:, 0] < 0.25)
    is_gray = np.where(extreme, lch[:, 1] < FAINT_CHROMA, lch[:, 1] < ACHROMATIC_CHROMA)
    neutral = idx[is_gray]
    chroma = idx[~is_gray]
    ramps: list[list[int]] = []
    if len(chroma):
        order = chroma[np.argsort(lch[chroma, 2])]
        hues = lch[order, 2]
        gaps = np.diff(np.concatenate([hues, hues[:1] + 360.0]))
        if len(order) == 1:
            groups = [list(order)]
        else:
            start = int(np.argmax(gaps)) + 1  # begin after the widest gap
            rot = np.roll(order, -start)
            rot_gaps = np.roll(gaps, -start)
            groups, cur = [], [int(rot[0])]
            for i in range(1, len(rot)):
                if rot_gaps[i - 1] > hue_gap:
                    groups.append(cur)
                    cur = []
                cur.append(int(rot[i]))
            groups.append(cur)
        ramps.extend(groups)
    if len(neutral):
        ramps.append([int(i) for i in neutral])
    return [sorted(r, key=lambda i: lch[i, 0]) for r in ramps]


def ramp_stats(colors: np.ndarray, ramp: list[int]) -> dict:
    lch = rgb_to_oklch(colors[ramp].astype(np.float64))
    dark, light = lch[0], lch[-1]
    chromatic = bool(np.mean(lch[:, 1]) >= ACHROMATIC_CHROMA)
    shift = hue_delta(dark[2], light[2]) if chromatic and len(ramp) > 1 else 0.0
    return {
        "colors": [rgb_to_hex(c) for c in colors[ramp]],
        "steps": len(ramp),
        "lightness_span": round(float(light[0] - dark[0]), 3),
        "hue_shift_deg": round(float(shift), 1),
        "chromatic": chromatic,
    }


def describe_palette(rgba: np.ndarray) -> dict:
    cols, counts = extract_colors(rgba)
    ramps = group_ramps(cols)
    stats = [ramp_stats(cols, r) for r in ramps]
    flat = [s for s in stats if s["chromatic"] and s["steps"] >= 3 and abs(s["hue_shift_deg"]) < 8]
    return {
        "color_count": int(len(cols)),
        "ramps": stats,
        "flat_ramps": len(flat),
        "top_colors": [{"hex": rgb_to_hex(c), "pixels": int(n)} for c, n in zip(cols[:12], counts[:12])],
    }


# ---------------------------------------------------------------- building

def _rotate_toward(h: float, target: float, amount: float) -> float:
    """Rotate hue ``h`` toward ``target`` by at most ``amount`` degrees."""
    d = hue_delta(h, target)
    return (h + math.copysign(min(abs(d), amount), d)) % 360.0


def _fit_gamut(l: float, c: float, h: float) -> tuple[int, int, int]:
    """Convert OKLCH to sRGB, reducing chroma until the color is in gamut."""
    for _ in range(60):
        if oklab_in_gamut(oklch_to_oklab(np.array([l, c, h]))):
            break
        c *= 0.92
    rgb = np.clip(oklch_to_rgb(np.array([l, c, h])), 0, 255)
    return tuple(int(round(v)) for v in rgb)


def make_ramp(
    base: str,
    steps: int = 5,
    hue_shift: float = 25.0,
    l_min: float = 0.22,
    l_max: float = 0.93,
) -> Palette:
    """A hue-shifted ramp through ``base``: shadows drift cool, highlights drift warm."""
    steps = max(2, int(steps))
    L0, C0, H0 = rgb_to_oklch(np.array(hex_to_rgb(base), dtype=np.float64))
    ls = np.linspace(l_min, l_max, steps)
    i0 = int(np.argmin(np.abs(ls - L0)))
    ls[i0] = L0
    # keep strictly increasing lightness around the base
    for i in range(i0 - 1, -1, -1):
        ls[i] = min(ls[i], ls[i + 1] - 0.04)
    for i in range(i0 + 1, steps):
        ls[i] = max(ls[i], ls[i - 1] + 0.04)
    ls = np.clip(ls, 0.05, 0.99)
    colors = []
    for i, L in enumerate(ls):
        if i == i0:
            colors.append(hex_to_rgb(base))
            continue
        # t: 0 at the base, 1 at the lightest (above) or darkest (below) step
        if i > i0:
            t = (i - i0) / max(1, steps - 1 - i0)
        else:
            t = (i0 - i) / max(1, i0)
        if C0 < ACHROMATIC_CHROMA:  # gray base stays neutral
            colors.append(_fit_gamut(L, C0, H0))
            continue
        if i > i0:
            h = _rotate_toward(H0, WARM_HUE, hue_shift * t)
            c = C0 * (1.0 - 0.55 * t**1.5)
        else:
            h = _rotate_toward(H0, COOL_HUE, hue_shift * t)
            c = C0 * (1.0 - 0.30 * t)
        colors.append(_fit_gamut(L, max(c, 0.0), h))
    return Palette(colors, name=f"ramp {base}", source="make_ramp")


# ---------------------------------------------------------------- applying

def nearest_indices(rgb: np.ndarray, palette: Palette, chunk: int = 65536) -> np.ndarray:
    """Index of the perceptually nearest palette color for each RGB row."""
    pal_lab = rgb_to_oklab(palette.array.astype(np.float64))
    flat = rgb.reshape(-1, 3).astype(np.float64)
    out = np.empty(len(flat), dtype=np.int64)
    for s in range(0, len(flat), chunk):
        lab = rgb_to_oklab(flat[s : s + chunk])
        d = ((lab[:, None, :] - pal_lab[None, :, :]) ** 2).sum(-1)
        out[s : s + chunk] = np.argmin(d, axis=1)
    return out.reshape(rgb.shape[:-1])


_BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float64) / 16.0


def apply_palette(
    rgba: np.ndarray,
    palette: Palette,
    dither: str = "none",
    alpha_threshold: int = 128,
) -> np.ndarray:
    """Lock an image to ``palette``. Alpha becomes binary (pixel art has no partial alpha)."""
    h, w = rgba.shape[:2]
    out = np.zeros_like(rgba)
    opaque = rgba[..., 3] >= alpha_threshold
    rgb = rgba[..., :3].astype(np.float64)
    if dither != "none":
        pal_l = np.sort(rgb_to_oklab(palette.array.astype(np.float64))[:, 0])
        step = float(np.median(np.diff(pal_l))) if len(pal_l) > 1 else 0.05
        lab = rgb_to_oklab(rgb)
        yy, xx = np.mgrid[0:h, 0:w]
        lab[..., 0] += (_BAYER4[yy % 4, xx % 4] - 0.5) * step
        pal_lab = rgb_to_oklab(palette.array.astype(np.float64))
        d = ((lab[..., None, :] - pal_lab[None, None, :, :]) ** 2).sum(-1)
        idx = np.argmin(d, axis=-1)
    else:
        idx = nearest_indices(rgb, palette)
    out[..., :3] = palette.array[idx]
    out[..., 3] = np.where(opaque, 255, 0)
    out[~opaque, :3] = 0
    return out


def swap_palette(rgba: np.ndarray, src: Palette, dst: Palette) -> np.ndarray:
    """Recolor by index: each pixel's nearest ``src`` color becomes the same index in ``dst``.

    Palettes of equal length map one-to-one (the classic enemy-recolor swap). Otherwise
    both palettes are ordered dark → light and matched by relative lightness rank.
    """
    opaque = rgba[..., 3] > 0
    idx = nearest_indices(rgba[..., :3], src)
    if len(src) == len(dst):
        mapping = np.arange(len(src))
        dst_arr = dst.array
    else:
        src_order = np.argsort(rgb_to_oklab(src.array.astype(np.float64))[:, 0])
        dst_sorted = dst.array[np.argsort(rgb_to_oklab(dst.array.astype(np.float64))[:, 0])]
        rank = np.empty(len(src), dtype=np.float64)
        rank[src_order] = np.linspace(0, 1, len(src))
        mapping = np.round(rank * (len(dst) - 1)).astype(np.int64)
        dst_arr = dst_sorted
    out = rgba.copy()
    out[..., :3] = np.where(opaque[..., None], dst_arr[mapping[idx]], rgba[..., :3])
    return out


# ---------------------------------------------------------------- visuals

def swatch_image(rows: list[tuple[str, list[str]]], cell: int = 28) -> Image.Image:
    """Swatch rows, e.g. [("ramp 1", ["#112233", ...]), ...], with hex labels."""
    f = font(11)
    label_w = 70
    width = label_w + max((len(c) for _, c in rows), default=1) * (cell + 4) + 8
    height = len(rows) * (cell + 18) + 6
    im = Image.new("RGB", (max(width, 160), max(height, 40)), (30, 31, 36))
    d = ImageDraw.Draw(im)
    y = 4
    for label, colors in rows:
        d.text((4, y + cell // 2 - 6), label[:10], fill=(200, 200, 210), font=f)
        x = label_w
        for hx in colors:
            d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=hex_to_rgb(hx))
            d.text((x, y + cell + 2), hx.lstrip("#")[:6], fill=(150, 152, 160), font=font(9))
            x += cell + 4
        y += cell + 18
    return im
