"""Small image helpers shared by the inspectors: loading, zooming, labels, contact sheets.

Contact sheets are laid out to stay under ~1500 px on the long edge so they reach
Claude without being downscaled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MAX_SHEET_WIDTH = 1500

BG_SHEET = (30, 31, 36)
FG_TEXT = (230, 230, 235)
FG_DIM = (150, 152, 160)


def load_rgba(path: str | Path) -> np.ndarray:
    """Load any image as an (H, W, 4) uint8 array. Animated images use the first frame."""
    with Image.open(path) as im:
        im.seek(0)
        return np.array(im.convert("RGBA"))


def save_rgba(arr: np.ndarray, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.ascontiguousarray(arr.astype(np.uint8)), "RGBA").save(path)
    return path


def upscale(arr: np.ndarray, k: int) -> np.ndarray:
    """Nearest-neighbour integer upscale of an (H, W, C) array."""
    if k <= 1:
        return arr
    return np.repeat(np.repeat(arr, k, axis=0), k, axis=1)


def zoom_to_fit(h: int, w: int, target: int, max_zoom: int = 32) -> int:
    """Largest integer zoom that keeps the long edge within ``target`` px (at least 1)."""
    return max(1, min(max_zoom, target // max(h, w, 1)))


def checkerboard(h: int, w: int, cell: int = 8, c1=(200, 200, 205), c2=(160, 160, 168)) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    mask = ((yy // cell) + (xx // cell)) % 2 == 0
    out = np.empty((h, w, 3), dtype=np.uint8)
    out[mask] = c1
    out[~mask] = c2
    return out


def over(rgba: np.ndarray, bg: np.ndarray | tuple) -> np.ndarray:
    """Alpha-composite an RGBA array over an RGB background (array or solid color)."""
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    if not isinstance(bg, np.ndarray):
        bg = np.broadcast_to(np.array(bg, dtype=np.float32), rgba.shape[:2] + (3,))
    out = rgba[..., :3].astype(np.float32) * a + bg.astype(np.float32) * (1.0 - a)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def draw_grid(rgb: np.ndarray, k: int, color=(0, 0, 0), alpha: float = 0.18) -> np.ndarray:
    """Overlay a pixel grid on an image upscaled by ``k`` (only when cells are big enough)."""
    if k < 4:
        return rgb
    out = rgb.astype(np.float32).copy()
    col = np.array(color, dtype=np.float32)
    out[::k, :, :] = out[::k, :, :] * (1 - alpha) + col * alpha
    out[:, ::k, :] = out[:, ::k, :] * (1 - alpha) + col * alpha
    return out.astype(np.uint8)


def highlight(rgb_zoomed: np.ndarray, mask: np.ndarray, k: int, color, width: int = 2) -> np.ndarray:
    """Draw a hollow box around every True pixel of ``mask`` on a zoomed image."""
    im = Image.fromarray(rgb_zoomed)
    d = ImageDraw.Draw(im)
    ys, xs = np.nonzero(mask)
    w = max(1, min(width, k // 3))
    for y, x in zip(ys.tolist(), xs.tolist()):
        d.rectangle([x * k, y * k, (x + 1) * k - 1, (y + 1) * k - 1], outline=tuple(color), width=w)
    return np.array(im)


def fit_text(text: str, fnt, max_w: int) -> str:
    """Trim ``text`` so it fits in ``max_w`` pixels."""
    if not text or fnt.getlength(text) <= max_w:
        return text
    while text and fnt.getlength(text + "..") > max_w:
        text = text[:-1]
    return text + ".."


def font(size: int = 14) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


@dataclass
class Tile:
    image: Image.Image
    title: str = ""
    note: str = ""


@dataclass
class Sheet:
    """Rows of titled tiles rendered into one labeled image."""

    title: str
    subtitle: str = ""
    rows: list[tuple[str, list[Tile]]] = field(default_factory=list)
    pad: int = 10

    def add_row(self, label: str, tiles: list[Tile]) -> None:
        tiles = [t for t in tiles if t is not None]
        if tiles:
            self.rows.append((label, tiles))

    def render(self, max_width: int = MAX_SHEET_WIDTH) -> Image.Image:
        pad = self.pad
        f_title, f_row, f_tile = font(20), font(15), font(13)
        laid: list[tuple[str, list[tuple[Tile, Image.Image]]]] = []
        for label, tiles in self.rows:
            # shrink a row uniformly if it would overflow the sheet width
            total = sum(t.image.width for t in tiles) + pad * (len(tiles) + 1)
            scale = min(1.0, max_width / total) if total else 1.0
            scaled = []
            for t in tiles:
                im = t.image
                if scale < 1.0:
                    im = im.resize(
                        (max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                        Image.NEAREST,
                    )
                scaled.append((t, im))
            laid.append((label, scaled))
        width = max([pad * 2 + 400] + [
            sum(im.width for _, im in tiles) + pad * (len(tiles) + 1) for _, tiles in laid
        ])
        width = min(width, max_width)
        height = pad + 28 + (20 if self.subtitle else 0)
        for label, tiles in laid:
            height += 22 + max(im.height for _, im in tiles) + 34
        sheet = Image.new("RGB", (width, height), BG_SHEET)
        d = ImageDraw.Draw(sheet)
        y = pad
        d.text((pad, y), self.title, fill=FG_TEXT, font=f_title)
        y += 28
        if self.subtitle:
            d.text((pad, y), self.subtitle, fill=FG_DIM, font=f_tile)
            y += 20
        for label, tiles in laid:
            d.text((pad, y), label, fill=(255, 200, 90), font=f_row)
            y += 22
            x = pad
            row_h = max(im.height for _, im in tiles)
            for i, (t, im) in enumerate(tiles):
                sheet.paste(im, (x, y))
                # a label may run under the next tile's gap but never into the next tile
                room = im.width + pad - 2 if i < len(tiles) - 1 else width - x - pad
                if t.title:
                    d.text((x, y + im.height + 3), fit_text(t.title, f_tile, room), fill=FG_TEXT, font=f_tile)
                if t.note:
                    d.text((x, y + im.height + 18), fit_text(t.note, f_tile, room), fill=FG_DIM, font=f_tile)
                x += im.width + pad
            y += row_h + 34
        return sheet


def to_image(arr: np.ndarray) -> Image.Image:
    mode = "RGBA" if arr.ndim == 3 and arr.shape[2] == 4 else "RGB"
    return Image.fromarray(np.ascontiguousarray(arr.astype(np.uint8)), mode)


def boxed(img: Image.Image, border=(70, 72, 80)) -> Image.Image:
    out = Image.new("RGB", (img.width + 2, img.height + 2), border)
    out.paste(img.convert("RGB"), (1, 1))
    return out
