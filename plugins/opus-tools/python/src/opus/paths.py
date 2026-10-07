"""Where projects live and where tool outputs go.

Outputs are written under ``<project>/.opus/out/<tool>/``. The ``.opus`` folder gets a
``.gdignore`` so Godot never imports our previews and reports as game assets.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

BIBLE_NAME = "opus.project.yaml"
PROJECT_MARKERS = (BIBLE_NAME, "project.godot")


def find_project_root(start: str | os.PathLike | None = None) -> Path | None:
    """Walk up from ``start`` (or $OPUS_PROJECT_DIR, or the cwd) to a project marker."""
    origin = start or os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()
    p = Path(origin).expanduser().resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    for d in (p, *p.parents):
        if any((d / m).exists() for m in PROJECT_MARKERS):
            return d
    return None


def opus_dir(base: Path) -> Path:
    d = base / ".opus"
    d.mkdir(parents=True, exist_ok=True)
    marker = d / ".gdignore"
    if not marker.exists():
        marker.touch()
    return d


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return s[:60] or "out"


def output_path(tool: str, stem: str, suffix: str = ".png", near: str | os.PathLike | None = None) -> Path:
    """A fresh, timestamped output path for ``tool``.

    Lives in the project's ``.opus/out/<tool>/`` when ``near`` is inside a project,
    otherwise in a ``.opus/out/<tool>/`` folder next to ``near`` (or the cwd).
    """
    root = find_project_root(near)
    if root is None:
        if near is not None:
            n = Path(near).expanduser().resolve()
            root = n.parent if (n.is_file() or not n.exists()) else n
        else:
            root = Path.cwd()
    out_dir = opus_dir(root) / "out" / tool
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{_slug(stem)}_{stamp}{suffix}"
    n = 1
    while path.exists():
        n += 1
        path = out_dir / f"{_slug(stem)}_{stamp}_{n}{suffix}"
    return path


def cache_dir(name: str, near: str | os.PathLike | None = None) -> Path:
    root = find_project_root(near) or Path.cwd()
    d = opus_dir(root) / "cache" / name
    d.mkdir(parents=True, exist_ok=True)
    return d
