"""Degrade clean sprites the way AI image models and painting tools do."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter


def fake_pixel_art(native: np.ndarray, scale: float = 7.3, blur: float = 1.0, noise: float = 6.0,
                   jpeg: int = 80, background=(255, 255, 255), offset: int = 3, seed: int = 0) -> np.ndarray:
    """Non-integer upscale + blur + noise + JPEG + flat opaque background + border offset."""
    rng = np.random.default_rng(seed)
    h, w = native.shape[:2]
    big = Image.fromarray(native, "RGBA").resize((round(w * scale), round(h * scale)), Image.NEAREST)
    canvas = Image.new("RGBA", (big.width + 2 * offset, big.height + 2 * offset), (*background, 255))
    canvas.alpha_composite(big, (offset, offset))
    rgb = canvas.convert("RGB").filter(ImageFilter.GaussianBlur(blur))
    arr = np.array(rgb).astype(np.float32) + rng.normal(0, noise, (rgb.height, rgb.width, 3))
    rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=jpeg)
    return np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGBA"))
