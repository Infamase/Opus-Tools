"""Hands that hold things: grip points on objects, a contact-driven grip solver, and a check
that measures where a hand sinks into or floats off what it holds.

Blender does the work (``opus_bl/grip.py``); this module picks paths and lays out sheets.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from PIL import Image

from opus import imaging as im
from opus.blender.runner import run_task
from opus.paths import cache_dir, output_path

LEGEND = "green = touching · red = inside the object · blue = held object"


def _axis(text: str) -> tuple[str, str] | None:
    """("+"/"-", "X"/"Y"/"Z") for an axis name such as +Z, -x or Y, else None."""
    m = re.fullmatch(r"\s*([+-]?)\s*([xyzXYZ])\s*", text)
    return (m.group(1) or "+", m.group(2).upper()) if m else None


def axis_name(value: str, name: str) -> str:
    """An object-local axis as the Blender side names it (+X ... -Z): accepts x, Y, -z."""
    if not value:
        return value
    ax = _axis(value)
    if ax is None:
        raise ValueError(f"{name}: give an axis such as +Z or -Y, not {value!r}")
    return ax[0] + ax[1]


def parse_vector(value, name: str, axes: bool = True) -> list[float] | None:
    """A point or direction as [x, y, z] from a list, "x,y,z" or (``axes``) an axis name such
    as +Z, -X or y. Empty or None gives None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    items = value
    if isinstance(value, str):
        ax = _axis(value) if axes else None
        if ax is not None:
            return [(1.0 if ax[0] == "+" else -1.0) if a == ax[1] else 0.0 for a in "XYZ"]
        items = [x for x in re.split(r"[,;\s]+", value.strip()) if x]
    try:
        vec = [float(x) for x in items]
    except (TypeError, ValueError):
        vec = []
    if len(vec) != 3:
        hint = "give an axis such as +Z or -X, or x,y,z" if axes else "give three numbers x,y,z"
        raise ValueError(f"{name}: {hint} (got {value!r})")
    return vec


def _sheet(title: str, subtitle: str, tiles: list[dict], out: Path, row_label: str) -> Path:
    sheet = im.Sheet(title=title, subtitle=subtitle)
    close = [t for t in tiles if not t["label"].startswith("first-person")]
    fp = [t for t in tiles if t["label"].startswith("first-person")]
    for i in range(0, len(close), 4):
        sheet.add_row(row_label if i == 0 else "", [im.Tile(Image.open(t["path"]).convert("RGB"), t["label"]) for t in close[i : i + 4]])
    if fp:
        sheet.add_row("What the player sees", [im.Tile(Image.open(t["path"]).convert("RGB"), t["label"]) for t in fp])
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.render().save(out, quality=90)
    return out


def grip_define(
    path: str | Path,
    object: str,
    name: str = "main",
    part: str = "",
    start: list | None = None,
    end: list | None = None,
    palm_side: list | None = None,
    up: list | None = None,
    center: float = 0.5,
    style: str = "power",
    index: str = "curl",
    thumb: str = "wrap",
    trigger: list | None = None,
    point_axis: str = "",
    hand: str = "r",
    out_blend: str | Path | None = None,
    timeout: int = 600,
) -> tuple[Path, dict]:
    """Add a grip (SOCKET_grip_<name> empty) to an object and render it for checking.

    Points and directions are lists, "x,y,z" or axis names (+Z, -X); see ``parse_vector``."""
    start, end, palm_side, up, trigger = (parse_vector(v, k) for k, v in (
        ("start", start), ("end", end), ("palm_side", palm_side), ("up", up), ("trigger", trigger)))
    point_axis = axis_name(point_axis, "point_axis")
    path = Path(path).expanduser().resolve()
    work = cache_dir("grip", near=path) / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    rep = run_task(
        "grip_define",
        {"path": str(path), "object": object, "name": name, "part": part, "start": start, "end": end,
         "palm_side": palm_side, "up": up, "center": center, "style": style, "index": index, "thumb": thumb,
         "trigger": trigger, "point_axis": point_axis, "hand": hand,
         "out_blend": str(out_blend) if out_blend else "", "out_dir": str(work)},
        timeout=timeout,
    )
    out = output_path("grip", f"{path.stem}_{name}", suffix=".jpg", near=path)
    sub = (f"handle {rep['length'] * 100:.1f} cm long, radius {rep['radius'] * 100:.1f} cm · "
           f"index {rep['index']}, thumb {rep['thumb']}, for the {'right' if hand == 'r' else 'left'} hand")
    sheet = _sheet(f"Grip · {rep['object']} · {rep['grip']}", sub + " · blue axis, red = palm side, green = thumb end, yellow = trigger",
                   rep.pop("tiles"), out, "Grip")
    rep["sheet"] = str(sheet)
    return sheet, rep


def grip_hold(
    rig: str | Path,
    object_path: str | Path | None = None,
    object: str = "",
    grip: str = "",
    side: str = "r",
    pose: str = "rest",
    move: str = "object",
    aim_axis: str = "-Y",
    offset: list | None = None,
    index: str = "",
    thumb: str = "",
    out_blend: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Put an object in a rigged hand and close the fingers on it. Returns (sheet, report).

    ``offset`` is three numbers, a list or "forward,right,down"; ``aim_axis`` an axis name."""
    offset = parse_vector(offset, "offset", axes=False)
    aim_axis = axis_name(aim_axis, "aim_axis")
    rig = Path(rig).expanduser().resolve()
    work = cache_dir("grip", near=rig) / f"hold_{time.strftime('%Y%m%d-%H%M%S')}"
    rep = run_task(
        "grip_hold",
        {"rig_path": str(rig), "object_path": str(Path(object_path).expanduser().resolve()) if object_path else "",
         "object": object, "grip": grip, "side": side, "pose": pose, "move": move, "aim_axis": aim_axis,
         "offset": offset, "index": index, "thumb": thumb, "out_blend": str(out_blend) if out_blend else "",
         "out_dir": str(work)},
        timeout=timeout,
    )
    out = output_path("grip", f"{rig.stem}_holding_{rep['object']}", suffix=".jpg", near=rig)
    sub = f"{rep['contact']['verdict']} · {LEGEND}"
    sheet = _sheet(f"Hold · {rep['object']} in the {'right' if side == 'r' else 'left'} hand", sub,
                   rep.pop("tiles"), out, "Close-ups")
    rep["sheet"] = str(sheet)
    return sheet, rep


def grip_check(
    path: str | Path,
    side: str = "r",
    object: str = "",
    fp: bool = False,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Measure and show how a hand holds an object in any rigged scene."""
    path = Path(path).expanduser().resolve()
    work = cache_dir("grip", near=path) / f"check_{time.strftime('%Y%m%d-%H%M%S')}"
    rep = run_task("grip_check", {"path": str(path), "side": side, "object": object, "out_dir": str(work), "fp": fp},
                   timeout=timeout)
    tiles = []
    for sd, entry in rep["sides"].items():
        word = "right" if sd == "r" else "left"
        for t in entry.pop("tiles", []):
            tiles.append({**t, "label": t["label"] if t["label"].startswith("first-person") else f"{word}: {t['label']}"})
    out = output_path("grip", f"{path.stem}_check", suffix=".jpg", near=path)
    verdicts = ", ".join(f"{'right' if s == 'r' else 'left'} {e['contact']['verdict']}" for s, e in rep["sides"].items())
    sheet = _sheet(f"Grip Check · {path.name}", f"{verdicts} · {LEGEND}", tiles, out, "Close-ups")
    rep["sheet"] = str(sheet)
    return sheet, rep
