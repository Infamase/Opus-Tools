"""Color conversions used by the pixel tools.

Perceptual work (nearest-color matching, ramps, hue shift) happens in OKLab / OKLCH,
which tracks human lightness and hue far better than RGB distance.
"""

from __future__ import annotations

import numpy as np


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 8:  # RRGGBBAA: drop alpha
        s = s[:6]
    if len(s) != 6:
        raise ValueError(f"not a hex color: {value!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def rgb_to_hex(rgb) -> str:
    r, g, b = (int(round(float(c))) for c in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M1 = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_M2 = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
_M1_INV = np.linalg.inv(_M1)
_M2_INV = np.linalg.inv(_M2)


def rgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    """uint8 or 0-255 float RGB (..., 3) -> OKLab (..., 3)."""
    lin = srgb_to_linear(np.asarray(rgb, dtype=np.float64)[..., :3] / 255.0)
    lms = lin @ _M1.T
    return np.cbrt(lms) @ _M2.T


def oklab_to_rgb(lab: np.ndarray) -> np.ndarray:
    """OKLab (..., 3) -> 0-255 float RGB, clipped to gamut."""
    lms = (np.asarray(lab, dtype=np.float64) @ _M2_INV.T) ** 3
    lin = lms @ _M1_INV.T
    return linear_to_srgb(lin) * 255.0


def oklab_in_gamut(lab: np.ndarray, tol: float = 1e-4) -> np.ndarray:
    """True where an OKLab color maps inside the sRGB gamut (before any clipping)."""
    lms = (np.asarray(lab, dtype=np.float64) @ _M2_INV.T) ** 3
    lin = lms @ _M1_INV.T
    return np.all((lin >= -tol) & (lin <= 1 + tol), axis=-1)


def oklab_to_oklch(lab: np.ndarray) -> np.ndarray:
    lab = np.asarray(lab, dtype=np.float64)
    c = np.hypot(lab[..., 1], lab[..., 2])
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0
    return np.stack([lab[..., 0], c, h], axis=-1)


def oklch_to_oklab(lch: np.ndarray) -> np.ndarray:
    lch = np.asarray(lch, dtype=np.float64)
    h = np.radians(lch[..., 2])
    return np.stack([lch[..., 0], lch[..., 1] * np.cos(h), lch[..., 1] * np.sin(h)], axis=-1)


def rgb_to_oklch(rgb: np.ndarray) -> np.ndarray:
    return oklab_to_oklch(rgb_to_oklab(rgb))


def oklch_to_rgb(lch: np.ndarray) -> np.ndarray:
    return oklab_to_rgb(oklch_to_oklab(lch))


def lightness(rgb: np.ndarray) -> np.ndarray:
    """Perceptual lightness (OKLab L, 0..1) for (..., 3) RGB."""
    return rgb_to_oklab(rgb)[..., 0]


def hue_delta(a: float, b: float) -> float:
    """Signed shortest hue difference b - a in degrees, in (-180, 180]."""
    d = (b - a + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d
