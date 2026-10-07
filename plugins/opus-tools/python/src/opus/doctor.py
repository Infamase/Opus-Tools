"""Health check: is every integration reachable from this machine?"""

from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

from opus import __version__
from opus.bible import load_bible
from opus.blender.runner import BlenderNotFound, blender_version, find_blender


def find_godot() -> str | None:
    env = os.environ.get("OPUS_GODOT", "").strip().strip('"')
    if env and os.path.isfile(env):
        return env
    for name in ("godot", "godot4", "Godot"):
        found = shutil.which(name)
        if found:
            return found
    hits = glob.glob(r"C:\Program Files\Godot*\Godot*.exe") + glob.glob(os.path.expanduser(r"~\Godot*\Godot*.exe"))
    hits = [h for h in hits if "console" not in h.lower()] or hits
    return sorted(hits)[-1] if hits else None


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001 - report, don't crash
        return f"error: {e}"


def doctor(project_dir: str | None = None) -> dict:
    checks: list[dict] = []

    def add(name, ok, detail, fix=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "fix": fix})

    add("python", sys.version_info >= (3, 11), f"{platform.python_version()} · opus-tools {__version__}")
    try:
        b = find_blender()
        add("blender", True, f"{blender_version(b)} at {b}")
    except BlenderNotFound as e:
        add("blender", False, str(e), "Set the plugin's blender_path option to blender.exe")
    g = find_godot()
    add("godot", bool(g), f"{_run([g, '--version'])} at {g}" if g else "not found",
        "" if g else "Set the plugin's godot_path option to the Godot executable (needed from Phase 2)")
    smi = shutil.which("nvidia-smi")
    add("gpu", bool(smi), _run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"]) if smi else "no NVIDIA GPU tools found",
        "" if smi else "Only needed for the optional AI backends")
    url = os.environ.get("OPUS_COMFYUI_URL", "http://127.0.0.1:8188")
    try:
        with urllib.request.urlopen(f"{url}/system_stats", timeout=2) as r:
            add("comfyui", r.status == 200, f"reachable at {url}")
    except Exception:  # noqa: BLE001
        add("comfyui", False, f"not running at {url}", "Optional: start ComfyUI to use local AI backends")
    bible = load_bible(project_dir)
    add("project_bible", bool(bible.get("_file")),
        bible.get("_file") or f"no opus.project.yaml found (project root: {bible.get('_root')})",
        "" if bible.get("_file") else "Run the project-bible skill or `opus bible init` in the game folder")
    required = {"python", "blender"}
    return {"ok": all(c["ok"] for c in checks if c["check"] in required), "checks": checks}


def format_report(rep: dict) -> str:
    lines = ["Opus doctor: " + ("ready" if rep["ok"] else "needs attention")]
    for c in rep["checks"]:
        mark = "OK " if c["ok"] else "-- "
        lines.append(f"{mark}{c['check']}: {c['detail']}" + (f"\n     fix: {c['fix']}" if c["fix"] and not c["ok"] else ""))
    return "\n".join(lines)
