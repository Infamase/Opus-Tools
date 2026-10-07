"""Find Blender and run an ``opus_bl`` task in it headlessly.

Blender is located from $OPUS_BLENDER (set by the plugin's ``blender_path`` option), then
PATH, then the standard install folders on Windows, macOS and Linux.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[4]
BLENDER_MODULES = Path(os.environ.get("OPUS_BLENDER_MODULES", PLUGIN_ROOT / "blender"))


class BlenderNotFound(RuntimeError):
    pass


class BlenderTaskError(RuntimeError):
    pass


def _version_key(path: str) -> tuple:
    nums = re.findall(r"(\d+)\.(\d+)", path)
    return tuple(int(n) for n in nums[-1]) if nums else (0, 0)


def find_blender() -> str:
    env = os.environ.get("OPUS_BLENDER", "").strip().strip('"')
    if env:
        if Path(env).is_file():
            return env
        raise BlenderNotFound(f"OPUS_BLENDER points to {env!r}, which doesn't exist.")
    found = shutil.which("blender")
    if found:
        return found
    patterns = [
        r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
        r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\Blender*\blender.exe"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
        os.path.expanduser("~/blender*/blender"),
        "/opt/blender*/blender",
    ]
    hits = [h for p in patterns for h in glob.glob(p)]
    if hits:
        return sorted(hits, key=_version_key)[-1]
    raise BlenderNotFound(
        "Blender not found. Set the plugin's blender_path option (or the OPUS_BLENDER "
        "environment variable) to blender.exe."
    )


def blender_version(blender: str | None = None) -> str:
    out = subprocess.run([blender or find_blender(), "--version"], capture_output=True, text=True, timeout=60)
    first = (out.stdout or out.stderr).strip().splitlines()
    return first[0] if first else "unknown"


def run_task(task: str, args: dict, timeout: int = 900) -> dict:
    """Run ``opus_bl`` task ``task`` with keyword ``args``; return its result dict."""
    blender = find_blender()
    entry = BLENDER_MODULES / "opus_bl" / "entry.py"
    with tempfile.TemporaryDirectory(prefix="opus_bl_") as tmp:
        args_path = Path(tmp) / "args.json"
        result_path = Path(tmp) / "result.json"
        args_path.write_text(json.dumps({"task": task, **args}), encoding="utf-8")
        cmd = [
            blender, "-b", "--factory-startup", "--python-exit-code", "1",
            "--python", str(entry), "--", str(args_path), str(result_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        if not result_path.exists():
            tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-25:])
            raise BlenderTaskError(f"Blender exited with code {proc.returncode} before writing a result:\n{tail}")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        raise BlenderTaskError(f"{payload.get('error')}\n{payload.get('traceback', '')}")
    return payload["result"]
