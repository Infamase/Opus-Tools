"""Sprite Inspector: Claude's eyes for pixel art.

One call produces a labeled contact sheet (zoomed pixels with a grid, an issues overlay,
actual-size readability checks, silhouette, value, palette ramps, plus tile or animation
views) and a JSON report with plain-language warnings.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from opus import imaging as im
from opus.paths import output_path
from opus.pixel import analysis as an
from opus.pixel.color import rgb_to_hex
from opus.pixel.palette import Palette, describe_palette, extract_colors, load_palette, swatch_image

BACKGROUNDS = {"light": (232, 232, 236), "mid": (127, 127, 132), "dark": (28, 28, 32)}

ISSUE_COLORS = {
    "stray": (255, 40, 40),
    "orphan": (255, 150, 0),
    "elbow": (0, 220, 255),
    "semi_alpha": (255, 0, 255),
    "off_palette": (255, 240, 0),
}


def _tint(rgb: np.ndarray, mask: np.ndarray, k: int, color, strength: float = 0.65) -> np.ndarray:
    """Tint flagged native pixels on a zoomed image (used when there are too many boxes)."""
    big = im.upscale(mask[..., None], k)[..., 0]
    out = rgb.astype(np.float32)
    out[big] = out[big] * (1 - strength) + np.array(color, np.float32) * strength
    return out.astype(np.uint8)


def _zoom_view(native: np.ndarray, target: int) -> tuple[np.ndarray, int]:
    h, w = native.shape[:2]
    k = im.zoom_to_fit(h, w, target)
    big = im.upscale(native, k)
    rgb = im.over(big, im.checkerboard(big.shape[0], big.shape[1], cell=max(4, k * 2)))
    return im.draw_grid(rgb, k), k


def _issue_view(native: np.ndarray, masks: dict[str, np.ndarray], target: int) -> Image.Image:
    rgb, k = _zoom_view(native, target)
    rgb = (rgb.astype(np.float32) * 0.55 + 255 * 0.45 * 0.35).astype(np.uint8)  # dim so marks pop
    for name, mask in masks.items():
        if mask is None or not mask.any():
            continue
        color = ISSUE_COLORS[name]
        if mask.sum() > 1500 or k < 4:
            rgb = _tint(rgb, mask, k, color)
        else:
            rgb = im.highlight(rgb, mask, k, color, width=max(2, k // 4))
    return im.to_image(rgb)


def _actual_size_panel(native: np.ndarray, bg, scale: int = 1, pad: int = 12, min_w: int = 84) -> Image.Image:
    sprite = im.upscale(native, scale)
    h, w = sprite.shape[:2]
    cw = max(w + 2 * pad, min_w)
    canvas = np.zeros((h + 2 * pad, cw, 3), np.uint8)
    canvas[...] = bg
    x0 = (cw - w) // 2
    canvas[pad : pad + h, x0 : x0 + w] = im.over(sprite, canvas[pad : pad + h, x0 : x0 + w])
    return im.to_image(canvas)


def _silhouette(native: np.ndarray, target: int) -> Image.Image:
    h, w = native.shape[:2]
    k = im.zoom_to_fit(h, w, target)
    sil = np.where(native[..., 3:4] > 0, 0, 255).astype(np.uint8).repeat(3, axis=2)
    return im.to_image(im.upscale(sil, k))


def _value(native: np.ndarray, target: int) -> Image.Image:
    h, w = native.shape[:2]
    k = im.zoom_to_fit(h, w, target)
    L = np.clip(an.lightness_map(native) * 255.0, 0, 255).astype(np.uint8)
    gray = np.stack([L, L, L, native[..., 3]], axis=-1)
    big = im.upscale(gray, k)
    return im.to_image(im.over(big, im.checkerboard(big.shape[0], big.shape[1], cell=max(4, k * 2))))


def _tile_view(native: np.ndarray, target: int) -> Image.Image:
    rep = np.tile(native, (3, 3, 1))
    h, w = rep.shape[:2]
    k = im.zoom_to_fit(h, w, target)
    big = im.upscale(rep, k)
    rgb = im.over(big, (127, 127, 132))
    # faint markers at the tile borders
    th, tw = native.shape[0] * k, native.shape[1] * k
    for i in (1, 2):
        rgb[i * th - 1 : i * th, :, :] = (rgb[i * th - 1 : i * th, :, :] * 0.7).astype(np.uint8)
        rgb[:, i * tw - 1 : i * tw, :] = (rgb[:, i * tw - 1 : i * tw, :] * 0.7).astype(np.uint8)
    return im.to_image(rgb)


def _frames_views(frames: list[np.ndarray], width: int) -> list[im.Tile]:
    fh, fw = frames[0].shape[:2]
    n = len(frames)
    k = max(1, min(16, (width - 10 * n) // max(1, n * fw)))
    strip = []
    for f in frames:
        big = im.upscale(f, k)
        strip.append(im.over(big, im.checkerboard(big.shape[0], big.shape[1], cell=max(4, k * 2))))
    gap = np.full((fh * k, 6, 3), 30, np.uint8)
    row = np.concatenate([x for f in strip for x in (f, gap)][:-1], axis=1)
    tiles = [im.Tile(im.to_image(row), f"{n} frames, zoom x{k}")]
    # onion skin: all frames layered, later frames more opaque
    kk = im.zoom_to_fit(fh, fw, 260)
    acc = np.full((fh * kk, fw * kk, 3), 245, np.float32)
    for i, f in enumerate(frames):
        a = (f[..., 3:4].astype(np.float32) / 255.0) * (0.25 + 0.6 * (i + 1) / n)
        big_rgb = im.upscale(f[..., :3].astype(np.float32), kk)
        big_a = im.upscale(a, kk)
        acc = acc * (1 - big_a) + big_rgb * big_a
    tiles.append(im.Tile(im.to_image(acc.astype(np.uint8)), "onion skin"))
    # where pixels change between consecutive frames (including the loop back)
    heat = np.zeros((fh, fw), np.float32)
    for a, b in zip(frames, frames[1:] + frames[:1]):
        heat += np.any(a != b, axis=-1)
    heat = heat / max(1, n)
    hm = np.stack([heat * 255, heat * 120, 40 + heat * 0], axis=-1).astype(np.uint8)
    tiles.append(im.Tile(im.to_image(im.upscale(hm, kk)), "change heatmap"))
    return tiles


def _palette_check(native: np.ndarray, pal: Palette) -> tuple[dict, np.ndarray]:
    opaque = native[..., 3] > 0
    rgb = native[..., :3].astype(np.uint32)
    keys = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    pal_arr = pal.array.astype(np.uint32)
    pal_keys = (pal_arr[:, 0] << 16) | (pal_arr[:, 1] << 8) | pal_arr[:, 2]
    off = opaque & ~np.isin(keys, pal_keys)
    off_cols, off_counts = extract_colors(np.where(off[..., None], native, 0))
    return {
        "palette": pal.name or pal.source,
        "palette_size": len(pal),
        "off_palette_pixels": int(off.sum()),
        "off_palette_colors": [rgb_to_hex(c) for c in off_cols[:16]],
    }, off


def inspect_sprite(
    path: str | Path,
    mode: str = "sprite",
    frame_width: int = 0,
    frame_height: int = 0,
    palette=None,
    light: str = "top-left",
    max_colors: int = 0,
    game_background: str | None = None,
    out: str | Path | None = None,
) -> tuple[Path, dict]:
    """Inspect a sprite, tile, or sprite sheet. Returns (sheet_png_path, report)."""
    path = Path(path)
    raw = im.load_rgba(path)
    native, k = an.to_native(raw)
    h, w = native.shape[:2]
    if mode not in ("sprite", "tile", "sheet"):
        raise ValueError("mode must be 'sprite', 'tile', or 'sheet'")
    fw, fh = (frame_width // k or 0), (frame_height // k or 0)
    if mode == "sheet" and not (fw and fh):
        raise ValueError("sheet mode needs frame_width and frame_height (in image pixels)")

    pal = load_palette(palette)
    warnings: list[str] = []
    report: dict = {
        "file": str(path),
        "size": [int(raw.shape[1]), int(raw.shape[0])],
        "native_size": [int(w), int(h)],
        "upscale_factor": int(k),
        "mode": mode,
    }
    if k > 1:
        warnings.append(f"Image is a clean x{k} export; analyzed at native {w}x{h}.")

    colors = describe_palette(native)
    report["colors"] = colors
    if max_colors and colors["color_count"] > max_colors:
        warnings.append(f"{colors['color_count']} colors, over the budget of {max_colors}.")
    if colors["flat_ramps"]:
        warnings.append(
            f"{colors['flat_ramps']} color ramp(s) have almost no hue shift; shifting shadows "
            "cooler and highlights warmer usually reads richer."
        )

    semi = (native[..., 3] > 0) & (native[..., 3] < 255)
    strays, orphans = an.single_pixels(native)
    orphans &= ~semi  # report partial alpha once, as alpha
    line = an.dark_line_mask(native)
    elbows, clumps = an.jaggy_elbows(line)
    edge = an.boundary_mask(native)
    opaque_n = int((native[..., 3] > 0).sum())
    outline_cov = float((edge & line).sum() / max(1, edge.sum()))
    report["alpha"] = {"semi_transparent_pixels": int(semi.sum())}
    report["single_pixels"] = {
        "strays": int(strays.sum()),
        "orphans": int(orphans.sum()),
        "orphan_percent": round(100.0 * orphans.sum() / max(1, opaque_n), 2),
    }
    report["line_art"] = {
        "outline_coverage": round(outline_cov, 2),
        "jaggy_elbows": int(elbows.sum()),
        "clumps_2x2": int(clumps.sum()),
        "line_pixels": int(line.sum()),
    }
    if semi.any():
        warnings.append(f"{int(semi.sum())} semi-transparent pixels; pixel art usually wants binary alpha.")
    if strays.any():
        warnings.append(f"{int(strays.sum())} stray pixel(s) floating outside the sprite (red).")
    if report["single_pixels"]["orphan_percent"] > 1.5:
        warnings.append(
            f"{report['single_pixels']['orphan_percent']}% of pixels are isolated single colors "
            "(orange): noise, typical of AI output or over-detailed shading."
        )
    if elbows.sum() > max(3, 0.04 * max(1, line.sum())):
        warnings.append(f"{int(elbows.sum())} jaggy elbows in the line art (cyan): doubled corners on curves.")
    if 0.35 < outline_cov < 0.85:
        warnings.append(
            f"Outline covers {outline_cov:.0%} of the silhouette: fine if it's a deliberate selective "
            "outline, otherwise make it consistent."
        )
    if colors["color_count"] > 256 or report["single_pixels"]["orphan_percent"] > 10:
        warnings.append("This doesn't look like clean pixel art (too many colors or noise). Run pixel_cleanup.")

    off_mask = None
    if pal is not None:
        report["palette_check"], off_mask = _palette_check(native, pal)
        if report["palette_check"]["off_palette_pixels"]:
            warnings.append(
                f"{report['palette_check']['off_palette_pixels']} pixels use colors outside the "
                f"project palette (yellow). Lock it with palette_apply."
            )

    shading = an.shading_report(native, light)
    report["shading"] = shading
    if shading.get("pillow_shading_likely"):
        warnings.append(
            "Pillow shading likely: lightness follows the distance from the outline, not the "
            f"{light} light direction."
        )

    bgs = dict(BACKGROUNDS)
    if game_background:
        from opus.pixel.color import hex_to_rgb

        bgs["game"] = hex_to_rgb(game_background)
    report["contrast"] = an.contrast_report(native, bgs)
    for name, c in report["contrast"].items():
        if c["silhouette_edge_gap"] < 0.08:
            warnings.append(f"Silhouette edge nearly matches the {name} background; it may vanish there.")

    # ---------------- sheet
    sheet = im.Sheet(
        title=f"Sprite Inspector · {path.name}",
        subtitle=f"native {w}x{h} px · upscale x{k} · {colors['color_count']} colors · mode {mode}",
    )
    zoom_rgb, zk = _zoom_view(native, 560)
    issues = _issue_view(
        native,
        {"semi_alpha": semi, "off_palette": off_mask, "orphan": orphans, "elbow": elbows, "stray": strays},
        560,
    )
    sheet.add_row(
        "Pixels",
        [
            im.Tile(im.to_image(zoom_rgb), f"zoom x{zk} with pixel grid"),
            im.Tile(issues, "issues", "red stray · orange orphan · cyan elbow · magenta alpha · yellow off-palette"),
        ],
    )
    readability = [im.Tile(_actual_size_panel(native, bg), f"1x {name}") for name, bg in bgs.items()]
    if max(h, w) * 2 <= 300:
        readability.append(im.Tile(_actual_size_panel(native, bgs["mid"], 2), "2x mid"))
    readability += [im.Tile(_silhouette(native, 200), "silhouette"), im.Tile(_value(native, 200), "value")]
    sheet.add_row("Readability", readability)
    cols_arr, _ = extract_colors(native)
    ramp_rows = [(f"ramp {i + 1}", r["colors"]) for i, r in enumerate(colors["ramps"][:10])]
    pal_tiles = [im.Tile(swatch_image(ramp_rows or [("none", [])]), "ramps (dark -> light)")]
    if pal is not None:
        pal_tiles.append(im.Tile(swatch_image([("project", pal.hex()[:40])]), "project palette"))
    sheet.add_row("Palette", pal_tiles)

    if mode == "tile":
        report["tile"] = an.tile_seams(native)
        if report["tile"]["seams_visible"]:
            warnings.append(
                "Tile seams are visible: the wrap-around edge differs much more than the interior "
                f"(x{report['tile']['horizontal_seam_ratio']} horizontal, x{report['tile']['vertical_seam_ratio']} vertical)."
            )
        sheet.add_row("Tiling 3x3", [im.Tile(_tile_view(native, 480), "repeated")])
    elif mode == "sheet":
        frames = an.split_frames(native, fw, fh)
        report["animation"] = an.frame_report(frames)
        a = report["animation"]
        if a.get("colors_not_in_every_frame"):
            warnings.append(f"{a['colors_not_in_every_frame']} color(s) appear in only some frames (possible flicker).")
        if a.get("frames", 0) > 1:
            sheet.add_row("Animation", _frames_views(frames, 1400))

    report["warnings"] = warnings
    out_path = Path(out) if out else output_path("sprite_inspect", path.stem, near=path)
    rendered = sheet.render()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(out_path)
    report["sheet"] = str(out_path)
    return out_path, report
