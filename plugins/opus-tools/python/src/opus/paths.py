"""Where projects live and where tool outputs go.

Outputs are written under ``<project>/.opus/out/<tool>/``. The ``.opus`` folder gets a
``.gdignore`` so Godot never imports our previews and reports as game assets.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from pathlib import Path

BIBLE_NAME = "opus.project.yaml"
PROJECT_MARKERS = (BIBLE_NAME, "project.godot")


def plugin_root() -> Path:
    """The plugin folder (holds ``python/``, ``blender/``, ``data/``, ``skills/``)."""
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    """Committed fact tables and licence data (``<plugin>/data``)."""
    return plugin_root() / "data"


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


def project_base(near: str | os.PathLike | None = None) -> Path:
    """Where a project's ledgers live: the project root containing ``near``; else
    $OPUS_PROJECT_DIR when ``near`` lies inside it (a Unity or Unreal project has no marker
    before ``bible init``); else ``near`` itself (its folder when it is a file), else the cwd."""
    root = find_project_root(near)
    if root is not None:
        return root
    env = os.environ.get("OPUS_PROJECT_DIR")
    p = Path(near or env or os.getcwd()).expanduser().resolve()
    if env:
        e = Path(env).expanduser().resolve()
        if p == e or e in p.parents:
            return e
    return p.parent if p.is_file() else p


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


def _base(near: str | os.PathLike | None) -> Path:
    """The project root, else the folder of ``near``, else the cwd."""
    root = find_project_root(near)
    if root is None:
        if near is not None:
            n = Path(near).expanduser().resolve()
            root = n.parent if (n.is_file() or not n.exists()) else n
        else:
            root = Path.cwd()
    return root


def output_path(tool: str, stem: str, suffix: str = ".png", near: str | os.PathLike | None = None) -> Path:
    """A fresh, timestamped output path for ``tool``, reserved on disk (created empty) so a
    parallel call in the same second gets ``_2``, ``_3`` ... instead of the same file.

    Lives in the project's ``.opus/out/<tool>/`` when ``near`` is inside a project,
    otherwise in a ``.opus/out/<tool>/`` folder next to ``near`` (or the cwd).
    """
    out_dir = opus_dir(_base(near)) / "out" / tool
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    n = 1
    while True:
        path = out_dir / (f"{_slug(stem)}_{stamp}{suffix}" if n == 1 else f"{_slug(stem)}_{stamp}_{n}{suffix}")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            n += 1


def cache_dir(name: str, near: str | os.PathLike | None = None) -> Path:
    """A fresh work folder for one call, ``.opus/cache/<name>/<time>-<pid>-<4 hex>/``, never
    shared with a parallel call."""
    d = opus_dir(_base(near)) / "cache" / name
    d.mkdir(parents=True, exist_ok=True)
    while True:
        run = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{secrets.token_hex(2)}"
        try:
            run.mkdir(exist_ok=False)
            return run
        except FileExistsError:
            continue
