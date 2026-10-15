"""Body Blockout: rigged, canon-proportioned starting bodies for characters and creatures.

Blender builds the body (see ``opus_bl/body.py``); this module picks the output paths and
renders a Look Dev Sheet so Claude sees the result in the same call.
"""

from __future__ import annotations

from pathlib import Path

from opus.blender.runner import run_task
from opus.paths import output_path

ARCHETYPES = {
    "humanoid": ["realistic", "heroic", "stylized", "chibi"],
    "quadruped": ["dog", "horse", "cat"],
    "dragon": ["western"],
}
DEFAULT_PRESET = {"humanoid": "realistic", "quadruped": "dog", "dragon": "western"}


def body_blockout(
    archetype: str = "humanoid",
    preset: str = "",
    height: float = 0.0,
    pose: str = "A",
    target_tris: int = 10000,
    out: str | Path | None = None,
    glb: bool = False,
    sheet: bool = True,
    timeout: int = 900,
) -> tuple[Path | None, dict]:
    """Build a blockout .blend (and optionally a .glb). Returns (lookdev sheet or None, report)."""
    if archetype not in ARCHETYPES:
        raise ValueError(f"archetype must be one of {sorted(ARCHETYPES)}")
    preset = preset or DEFAULT_PRESET[archetype]
    if preset not in ARCHETYPES[archetype]:
        raise ValueError(f"{archetype} presets: {ARCHETYPES[archetype]}")
    if pose.upper() not in ("A", "T"):
        raise ValueError("pose must be A or T")
    blend = Path(out).expanduser().resolve() if out else output_path("body", f"{archetype}_{preset}", suffix=".blend")
    if blend.suffix.lower() != ".blend":
        blend = blend.with_suffix(".blend")
    rep = run_task(
        "body",
        {
            "archetype": archetype, "preset": preset, "height": float(height or 0), "pose": pose,
            "target_tris": int(target_tris), "out_blend": str(blend),
            "out_glb": str(blend.with_suffix(".glb")) if glb else "",
        },
        timeout=timeout,
    )
    sheet_path = None
    if sheet:
        from opus.threed.lookdev import lookdev_sheet

        sheet_path, _ = lookdev_sheet(blend, out=blend.with_name(blend.stem + "_sheet.jpg"), timeout=timeout)
        rep["sheet"] = str(sheet_path)
    return sheet_path, rep
