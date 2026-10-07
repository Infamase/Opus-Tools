"""Run one Opus task inside Blender and write a JSON result.

    blender -b --factory-startup --python-exit-code 1 --python entry.py -- args.json result.json

``args.json`` holds {"task": name, ...keyword arguments}. The result file always gets
written, with {"ok": true, "result": ...} or {"ok": false, "error": ..., "traceback": ...}.
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(argv) < 2:
        raise SystemExit("usage: entry.py -- args.json result.json")
    args_path, result_path = argv[0], argv[1]
    try:
        with open(args_path, encoding="utf-8") as f:
            args = json.load(f)
        task = args.pop("task")
        from opus_bl import assets, lint, lookdev

        tasks = {"lookdev": lookdev.run, "lint": lint.run, "stats": assets.stats_task}
        if task not in tasks:
            raise ValueError(f"unknown task {task!r}; known: {sorted(tasks)}")
        payload = {"ok": True, "result": tasks[task](**args)}
    except Exception as e:  # report everything back to the caller
        payload = {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, default=str)


main()
