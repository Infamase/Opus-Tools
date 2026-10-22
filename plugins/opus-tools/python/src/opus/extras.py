"""Optional extras (docs/S0B_DESIGN.md §4.10, §16): heavy libraries imported lazily, with a message
that says which extra to install when one is missing."""

from __future__ import annotations

import importlib
from types import ModuleType

# extra -> the distributions it installs and the modules they provide (pyproject optional-dependencies)
EXTRAS: dict[str, dict[str, tuple[str, ...]]] = {
    "feq": {"packages": ("PyGEL3D",), "modules": ("pygel3d",)},
    "terrain": {"packages": ("fastscapelib", "pydelatin", "numba"), "modules": ("fastscapelib", "pydelatin", "numba")},
    "hulls": {"packages": ("coacd",), "modules": ("coacd",)},
    "uv": {"packages": ("xatlas",), "modules": ("xatlas",)},
    "ref": {"packages": ("opencv-python-headless",), "modules": ("cv2",)},
    "gpu": {"packages": ("cupy-cuda12x",), "modules": ("cupy",)},
    "lod": {"packages": ("pyfqmr",), "modules": ("pyfqmr",)},
}


def require(extra: str, module: str) -> ModuleType:
    """Import ``module`` (lazily, at the call) or raise ValueError("install opus[<extra>]: …")."""
    if extra not in EXTRAS:
        raise ValueError(f"unknown extra {extra!r}; extras: {sorted(EXTRAS)}")
    try:
        return importlib.import_module(module)
    except ImportError as e:
        pkgs = " ".join(EXTRAS[extra]["packages"])
        raise ValueError(f"install opus[{extra}]: {module} is not importable ({e}); from the plugin's python/ "
                         f"folder run `uv sync --extra {extra}` (installs {pkgs})") from None


def available(extra: str) -> dict[str, str | None]:
    """{module: version or None} for each module of ``extra`` (None = not importable)."""
    out: dict[str, str | None] = {}
    for module in EXTRAS[extra]["modules"]:
        try:
            m = importlib.import_module(module)
            out[module] = str(getattr(m, "__version__", "") or "installed")
        except Exception:  # an extra that fails to import for any reason is not available
            out[module] = None
    return out
