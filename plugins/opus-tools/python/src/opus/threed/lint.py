"""Mesh Lint: game-readiness checks (run inside Blender), summarized for Claude."""

from __future__ import annotations

from pathlib import Path

from opus.blender.runner import run_task


def mesh_lint(
    path: str | Path,
    objects: list[str] | None = None,
    budget_tris: int = 0,
    deforming: bool | None = None,
    timeout: int = 600,
) -> dict:
    """Lint a .blend/.glb/.gltf/.fbx/.obj. ``deforming`` forces character rules (default: auto)."""
    path = Path(path).expanduser().resolve()
    report = run_task(
        "lint",
        {"path": str(path), "objects": objects or None, "budget_tris": int(budget_tris or 0), "deforming": deforming},
        timeout=timeout,
    )
    report["text"] = summarize(report)
    return report


def summarize(report: dict) -> str:
    s = report["summary"]
    head = (
        f"{'GAME-READY' if report['game_ready'] else 'NOT game-ready'}: {s['error']} error(s), "
        f"{s['warning']} warning(s), {s['info']} note(s) · {report['total_tris']:,} tris"
    )
    if report.get("budget_tris"):
        head += f" (budget {report['budget_tris']:,})"
    lines = [head]
    for f in report["findings"]:
        lines.append(f"- [{f['severity']}] {f['object']}: {f['message']}")
    return "\n".join(lines)
