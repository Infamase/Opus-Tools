"""Run one Opus task inside Blender and write a JSON result.

    blender -b --factory-startup --python-exit-code 1 --python entry.py -- args.json result.json

``args.json`` holds {"task": name, ...keyword arguments}. The result file always gets
written, with {"ok": true, "result": ...} or {"ok": false, "error": ..., "traceback": ...}.

Task modules are imported lazily, only for the task that runs, so a missing or broken module
breaks only its own tasks. ``$OPUS_HOST_SRC`` (set by ``opus.blender.runner.run_task`` to the
plugin's ``python/src``) is appended to ``sys.path``, so tasks can import the numpy-only host
packages (``opus.compile``, ``opus.gates.finding``) inside Blender.
"""

import importlib
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HOST_SRC = os.environ.get("OPUS_HOST_SRC", "")
if _HOST_SRC and _HOST_SRC not in sys.path:
    sys.path.append(_HOST_SRC)

# task -> (opus_bl module, function)
TASKS = {
    "lookdev": ("lookdev", "run"), "lint": ("lint", "run"), "stats": ("assets", "stats_task"), "body": ("body", "build"),
    "views": ("inspect3d", "views"), "report": ("inspect3d", "report"), "silhouettes": ("inspect3d", "silhouettes"),
    "grip_define": ("grip", "define"), "grip_hold": ("grip", "hold"), "grip_check": ("grip", "check"),
    "readability": ("readability", "render"),
    # spec compiler (S0b); each module arrives with its work package
    "spec_emit": ("emit", "run"), "spec_readback": ("readback", "run"), "spec_consistency": ("consistency", "run"),
    "spec_export": ("export", "run"), "spec_eval_hash": ("compile_eval", "run"), "raster_tie": ("raster_tie", "run"),
}


def _task(name: str):
    if name not in TASKS:
        raise ValueError(f"unknown task {name!r}; known: {sorted(TASKS)}")
    module, fn = TASKS[name]
    try:
        mod = importlib.import_module(f"opus_bl.{module}")
    except ModuleNotFoundError as e:
        if e.name != f"opus_bl.{module}":
            raise
        raise ValueError(f"task {name!r} is not built yet (opus_bl/{module}.py is missing)") from None
    return getattr(mod, fn)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) < 2:
        raise SystemExit("usage: entry.py -- args.json result.json")
    args_path, result_path = argv[0], argv[1]
    try:
        with open(args_path, encoding="utf-8") as f:
            args = json.load(f)
        task = args.pop("task")
        payload = {"ok": True, "result": _task(task)(**args)}
    except Exception as e:  # report everything back to the caller
        payload = {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, default=str)


main()
