"""Synthetic sprites with known properties, for tests and demos."""

from __future__ import annotations

import numpy as np

OUTLINE = (34, 28, 48, 255)
SHADOW = (60, 92, 140, 255)
BASE = (84, 140, 196, 255)
LIGHT = (150, 196, 230, 255)
HIGHLIGHT = (222, 240, 250, 255)


def blob(size: int = 32, light: str = "top-left") -> np.ndarray:
    """A round, outlined, directionally lit blob: clean pixel art."""
    img = np.zeros((size, size, 4), np.uint8)
    c = (size - 1) / 2.0
    r = size * 0.42
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(yy - c, xx - c)
    inside = d <= r
    img[inside] = BASE
    # light from the top-left: brighter where (-x - y) is large
    lx, ly = (-1, -1) if light == "top-left" else (1, 1)
    proj = ((xx - c) * lx + (yy - c) * ly) / (r * 1.4142)
    img[inside & (proj > 0.25)] = LIGHT
    img[inside & (proj > 0.55)] = HIGHLIGHT
    img[inside & (proj < -0.35)] = SHADOW
    ring = inside & (d > r - 1.0)
    img[ring] = OUTLINE
    return img


def pillow_blob(size: int = 32) -> np.ndarray:
    """Same shape, but shaded by distance from the edge (pillow shading)."""
    img = np.zeros((size, size, 4), np.uint8)
    c = (size - 1) / 2.0
    r = size * 0.42
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(yy - c, xx - c)
    inside = d <= r
    img[inside] = SHADOW
    img[inside & (d < r * 0.7)] = BASE
    img[inside & (d < r * 0.4)] = LIGHT
    img[inside & (d < r * 0.15)] = HIGHLIGHT
    img[inside & (d > r - 1.0)] = OUTLINE
    return img


def with_defects(img: np.ndarray) -> np.ndarray:
    """Add one stray pixel, one orphan, and one semi-transparent pixel."""
    out = img.copy()
    out[1, 1] = (255, 0, 0, 255)  # stray: isolated in transparency
    h, w = out.shape[:2]
    out[h // 2, w // 2] = (250, 20, 200, 255)  # orphan inside the body
    out[h // 2 + 3, w // 2 - 3] = (84, 140, 196, 128)  # semi-alpha
    return out


def tileable(size: int = 16) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    v = (np.sin(2 * np.pi * xx / size) + np.cos(2 * np.pi * yy / size)) * 0.5
    img = np.zeros((size, size, 4), np.uint8)
    img[..., 3] = 255
    img[..., 1] = (120 + 60 * v).astype(np.uint8)
    img[..., 0] = 60
    img[..., 2] = 50
    return img


def ramp_tile(size: int = 16) -> np.ndarray:
    """Not tileable: a horizontal gradient jumps at the wrap."""
    img = np.zeros((size, size, 4), np.uint8)
    img[..., 3] = 255
    img[..., 0] = np.linspace(20, 230, size).astype(np.uint8)[None, :]
    img[..., 1] = 90
    img[..., 2] = 60
    return img
