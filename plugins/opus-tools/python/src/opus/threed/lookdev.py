"""Look Dev Sheet: Claude's eyes for 3D models.

Blender renders the tiles headlessly; this module lays them out into one labeled sheet.
"""

from __future__ import annotations

import time
from pathlib import Path

from PIL import Image

from opus import imaging as im
from opus.blender.runner import run_task
from opus.paths import cache_dir, output_path

ROWS = [
    ("Shaded", "shaded", ["front", "right", "back", "top", "three_quarter"]),
    ("Form: clay + wireframe", "clay_wire", ["front", "right", "three_quarter"]),
    ("Diagnostics", None, [("silhouette", "front"), ("silhouette", "right"), ("normals", "three_quarter"),
                           ("uv", "three_quarter"), ("scale", "front")]),
]
NOTES = {
    ("normals", "three_quarter"): "faces: blue out, red flipped",
    ("uv", "three_quarter"): "UV checker (even squares = even density)",
    ("silhouette", "front"): "silhouette front",
    ("silhouette", "right"): "silhouette side",
}
VIEW_LABEL = {"three_quarter": "3/4"}


def _fmt_m(v: float) -> str:
    return f"{v * 100:.1f} cm" if v < 1 else f"{v:.2f} m"


def lookdev_sheet(
    path: str | Path,
    objects: list[str] | None = None,
    engine: str = "workbench",
    tile: int = 270,
    out: str | Path | None = None,
    timeout: int = 900,
) -> tuple[Path, dict]:
    """Render and compose the sheet for a .blend/.glb/.gltf/.fbx/.obj. Returns (png, report)."""
    path = Path(path).expanduser().resolve()
    if engine not in ("workbench", "eevee", "cycles"):
        raise ValueError("engine must be workbench, eevee, or cycles")
    work = cache_dir("lookdev", near=path) / f"{path.stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    t0 = time.time()
    res = run_task(
        "lookdev",
        {"path": str(path), "out_dir": str(work), "objects": objects or None, "engine": engine, "size": tile},
        timeout=timeout,
    )
    tiles = {(t["pass"], t["view"]): t["path"] for t in res["tiles"]}
    stats = res["stats"]
    size = stats["bounds"]["size_m"]
    totals = stats["totals"]
    ref = "1.8 m figure" if res["reference"] == "human_1.8m" else "10 cm cube"
    sheet = im.Sheet(
        title=f"Look Dev Sheet · {path.name}",
        subtitle=(
            f"W {_fmt_m(size[0])} x D {_fmt_m(size[1])} x H {_fmt_m(size[2])} · {totals['tris']:,} tris · "
            f"{totals['objects']} object(s) · {totals['materials']} material(s) · shaded with {engine}"
        ),
    )
    for label, pass_name, views in ROWS:
        row = []
        for v in views:
            p, view = (pass_name, v) if pass_name else v
            fp = tiles.get((p, view))
            if not fp or not Path(fp).exists():
                continue
            img = Image.open(fp).convert("RGB")
            title = NOTES.get((p, view)) or (
                f"scale vs {ref}, grid {res['grid_cell_m']:g} m" if p == "scale" else VIEW_LABEL.get(view, view)
            )
            row.append(im.Tile(img, title))
        sheet.add_row(label, row)
    out_path = Path(out) if out else output_path("lookdev", path.stem, suffix=".jpg", near=path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # renders are photographic: a high-quality JPEG is a third of the PNG size
    rendered = sheet.render()
    if out_path.suffix.lower() in (".jpg", ".jpeg"):
        rendered.save(out_path, quality=90, optimize=True)
    else:
        rendered.save(out_path)
    report = {
        "file": str(path),
        "sheet": str(out_path),
        "seconds": round(time.time() - t0, 1),
        "engine": engine,
        "dimensions_m": size,
        "totals": totals,
        "objects": [
            {k: o[k] for k in ("name", "tris", "ngons", "materials", "uv_maps", "scale", "dimensions", "modifiers")}
            for o in stats["objects"]
        ],
        "tiles_dir": str(work),
    }
    return out_path, report
