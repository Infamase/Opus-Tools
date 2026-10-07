"""The Opus MCP server: Claude's senses and building blocks as tools.

Tools that look at something return an image (a labeled contact sheet) plus a compact JSON
report, so Claude can see the asset and read the numbers in one call. Defaults such as the
palette, light direction and triangle budgets come from the project's opus.project.yaml.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from opus import imaging as im
from opus.bible import init_bible, load_bible, resolve_palette_spec
from opus.doctor import doctor, format_report
from opus.ledger import license_flags, record, write_credits
from opus.paths import find_project_root, output_path

INSTRUCTIONS = """\
Opus Tools give you eyes for game assets. Use them in a loop: make or edit an asset, look at
it with an inspector, fix what the report and image show, and repeat before showing the user.
- Pixel art: sprite_inspect after every change; pixel_cleanup for AI or painted images;
  palette_apply / palette_ramp / palette_swap to keep colors on the project palette.
- 3D: lookdev_sheet to see a model from every side; mesh_lint before calling it game-ready.
- project_bible holds the project's style rules and budgets; read it before making assets.
Paths may be absolute or relative to the project folder.
"""

server = MCPServer("opus", instructions=INSTRUCTIONS)


def _path(p: str) -> Path:
    q = Path(p).expanduser()
    if not q.is_absolute():
        base = os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()
        q = Path(base) / q
    q = q.resolve()
    if not q.exists():
        raise FileNotFoundError(f"{q} does not exist")
    return q


def _json(data: dict) -> str:
    return json.dumps(data, indent=1, default=str)


def _before_after(before: Path, after_arr, title: str, out: Path) -> Path:
    src = im.load_rgba(before)
    k1 = im.zoom_to_fit(src.shape[0], src.shape[1], 520)
    k2 = im.zoom_to_fit(after_arr.shape[0], after_arr.shape[1], 520)
    a = im.over(im.upscale(src, k1), im.checkerboard(src.shape[0] * k1, src.shape[1] * k1, max(4, 2 * k1)))
    b = im.over(im.upscale(after_arr, k2), im.checkerboard(after_arr.shape[0] * k2, after_arr.shape[1] * k2, max(4, 2 * k2)))
    sheet = im.Sheet(title=title)
    sheet.add_row("Before / after", [im.Tile(im.to_image(a), "before"), im.Tile(im.to_image(b), "after")])
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.render().save(out)
    return out


# ---------------------------------------------------------------- pixel art

@server.tool(structured_output=False)
def sprite_inspect(
    path: str,
    mode: str = "sprite",
    frame_width: int = 0,
    frame_height: int = 0,
    palette: str = "",
    light: str = "",
    max_colors: int = 0,
) -> list:
    """Look at a sprite, tile or sprite sheet up close and get a pixel-art critique.

    Returns a contact sheet (zoomed pixels with grid, issue overlay, actual-size readability on
    light/mid/dark backgrounds, silhouette, value, palette ramps; plus a 3x3 tiling view in
    mode="tile" or frames/onion skin/change heatmap in mode="sheet") and a JSON report with
    warnings: stray and orphan pixels, jaggy line elbows, partial alpha, off-palette colors,
    color budget, pillow shading, flat ramps, low contrast, tile seams, frame flicker.
    mode: sprite | tile | sheet (sheet needs frame_width/frame_height in image pixels).
    palette/light/max_colors default to the project bible.
    """
    from opus.pixel.inspect import inspect_sprite

    p = _path(path)
    bible = load_bible(p)
    px = bible["pixel"]
    sheet, rep = inspect_sprite(
        p,
        mode=mode,
        frame_width=frame_width,
        frame_height=frame_height,
        palette=palette or resolve_palette_spec(bible) or None,
        light=light or px["light"],
        max_colors=max_colors or px["max_colors"],
        game_background=px.get("game_background") or None,
    )
    return [Image(path=sheet), _json(rep)]


@server.tool(structured_output=False)
def pixel_cleanup(
    path: str,
    palette: str = "",
    max_colors: int = 24,
    background: str = "auto",
    outline: str = "none",
    crop: bool = True,
    out_path: str = "",
) -> list:
    """Turn AI-generated or painted "fake pixel art" into true pixel art.

    Detects the real pixel grid (any cell size, even fractional), samples each cell, removes
    a flat background (background="auto" | "none" | "#hex"), locks colors to a palette (the
    project palette, a given one, or an automatic one of max_colors), makes alpha binary,
    removes stray/noise pixels, and optionally adds a 1-px outline ("dark" or "#hex").
    Clean native pixel art is left at its resolution. Returns a before/after image and a
    report; the cleaned PNG path is in report["clean"].
    """
    from opus.pixel.cleanup import cleanup

    p = _path(path)
    bible = load_bible(p)
    clean, preview, rep = cleanup(
        p,
        palette=palette or resolve_palette_spec(bible) or None,
        max_colors=max_colors,
        background=background,
        outline=outline,
        crop=crop,
        out=out_path or None,
    )
    return [Image(path=preview), _json(rep)]


@server.tool(structured_output=False)
def palette_ramp(base_color: str, steps: int = 5, hue_shift: float = 25.0, save_as: str = "") -> list:
    """Build a hue-shifted color ramp through base_color (shadows cooler, highlights warmer).

    Returns a swatch image and the hex colors. save_as writes a .hex palette file.
    """
    from opus.pixel.palette import make_ramp, save_hex, swatch_image

    ramp = make_ramp(base_color, steps=steps, hue_shift=hue_shift)
    out = output_path("palette", f"ramp_{base_color.strip('#')}")
    swatch_image([("ramp", ramp.hex())], cell=40).save(out)
    data = {"colors": ramp.hex()}
    if save_as:
        target = Path(save_as).expanduser()
        if not target.is_absolute():
            target = Path(os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()) / target
        data["saved"] = str(save_hex(ramp, target))
    return [Image(path=out), _json(data)]


@server.tool(structured_output=False)
def palette_apply(path: str, palette: str = "", dither: str = "none", out_path: str = "") -> list:
    """Lock an image to a palette (nearest perceptual color; dither="none" or "bayer4").

    palette: file (.hex/.gpl/.pal/.json/palette image), lospec:<slug>, or hex list; defaults to
    the project palette. Writes the result and returns a before/after image.
    """
    from opus.pixel.palette import apply_palette, load_palette

    p = _path(path)
    spec = palette or resolve_palette_spec(load_bible(p))
    pal = load_palette(spec)
    if pal is None:
        raise ValueError("no palette given and the project bible has none")
    out = apply_palette(im.load_rgba(p), pal, dither=dither)
    dest = Path(out_path) if out_path else output_path("palette", f"{p.stem}_paletted", near=p)
    im.save_rgba(out, dest)
    prev = _before_after(p, out, f"Palette apply · {p.name} · {pal.name or 'palette'} ({len(pal)} colors)",
                         dest.with_name(dest.stem + "_preview.png"))
    return [Image(path=prev), _json({"output": str(dest), "palette": pal.name or pal.source, "colors": len(pal)})]


@server.tool(structured_output=False)
def palette_swap(path: str, from_palette: str, to_palette: str, out_path: str = "") -> list:
    """Recolor a sprite from one palette to another by index (enemy variants, seasons).

    Equal-length palettes map color-for-color; otherwise colors are matched by lightness rank.
    """
    from opus.pixel.palette import load_palette, swap_palette

    p = _path(path)
    out = swap_palette(im.load_rgba(p), load_palette(from_palette), load_palette(to_palette))
    dest = Path(out_path) if out_path else output_path("palette", f"{p.stem}_swapped", near=p)
    im.save_rgba(out, dest)
    prev = _before_after(p, out, f"Palette swap · {p.name}", dest.with_name(dest.stem + "_preview.png"))
    return [Image(path=prev), _json({"output": str(dest)})]


# ---------------------------------------------------------------- 3D

@server.tool(structured_output=False)
def lookdev_sheet(path: str, objects: str = "", engine: str = "", tile: int = 270) -> list:
    """Render a 3D asset from every side in headless Blender and return one labeled sheet.

    Rows: shaded front/right/back/top/3-4; clay + wireframe (form and topology density);
    diagnostics: silhouettes, face orientation (blue out, red flipped), UV checker, and scale
    next to a 1.8 m figure (or 10 cm cube) on a measured grid. Report has dimensions, tri
    counts, materials and UV maps per object. Works on .blend/.glb/.gltf/.fbx/.obj; save the
    live Blender file first. objects: comma-separated object or collection names (default:
    all visible geometry). engine: workbench (fast) | eevee (true PBR look) | cycles.
    """
    from opus.threed.lookdev import lookdev_sheet as run

    p = _path(path)
    bible = load_bible(p)
    names = [s.strip() for s in objects.split(",") if s.strip()]
    sheet, rep = run(p, objects=names or None, engine=engine or bible["3d"]["lookdev_engine"], tile=tile)
    return [Image(path=sheet), _json(rep)]


@server.tool(structured_output=False)
def mesh_lint(path: str, objects: str = "", category: str = "", budget_tris: int = 0, deforming: str = "auto") -> str:
    """Check a 3D asset for game-readiness problems and say exactly what to fix.

    Errors: non-manifold edges, flipped faces / inside-out meshes, negative scale, missing UVs
    or texture files, over budget, n-gons and bad weights on deforming meshes. Warnings: loose
    and degenerate geometry, floating parts, unapplied scale, collapsed/overlapping UVs,
    uneven texel density, >4 bone influences, empty material slots. category picks the tri
    budget from the bible (prop_small, prop_large, environment_piece, character,
    hero_character) unless budget_tris is given. deforming: auto | true | false.
    """
    from opus.threed.lint import mesh_lint as run

    p = _path(path)
    budget = budget_tris
    if not budget and category:
        budgets = load_bible(p)["3d"]["budgets_tris"]
        if category not in budgets:
            raise ValueError(f"unknown category {category!r}; the bible has {sorted(budgets)}")
        budget = budgets[category]
    names = [s.strip() for s in objects.split(",") if s.strip()]
    flag = {"auto": None, "true": True, "false": False}.get(str(deforming).lower())
    rep = run(p, objects=names or None, budget_tris=budget, deforming=flag)
    text = rep.pop("text")
    return text + "\n\n" + _json(rep)


# ---------------------------------------------------------------- project

@server.tool(structured_output=False)
def project_bible(action: str = "show", project_dir: str = "", project: str = "", styles: str = "", cameras: str = "") -> str:
    """Show the project's style rules and budgets, or create opus.project.yaml (action="init").

    The bible lives next to project.godot. Read it before making assets so palettes, budgets
    and light direction stay consistent. init takes styles/cameras as comma-separated lists.
    """
    base = project_dir or os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()
    if action == "init":
        root = find_project_root(base) or Path(base)
        path = init_bible(
            root,
            project=project,
            styles=[s.strip() for s in styles.split(",") if s.strip()],
            cameras=[c.strip() for c in cameras.split(",") if c.strip()],
        )
        return f"Created {path}. Edit it to set the palette, budgets and feel."
    return _json(load_bible(base))


@server.tool(structured_output=False)
def ledger_record(
    asset: str,
    source: str,
    license: str = "",
    author: str = "",
    url: str = "",
    generator: str = "",
    model: str = "",
    notes: str = "",
) -> str:
    """Record where an asset came from (library, AI model, made by hand) and its license.

    Use for every imported or generated asset; credits and release checks are built from it.
    """
    return _json(record(str(_path(asset)), source, license, author, url, generator, model, notes))


@server.tool(structured_output=False)
def make_credits(project_dir: str = "") -> str:
    """Write CREDITS.md from the provenance ledger and list licenses that block a public release."""
    base = project_dir or os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()
    path = write_credits(base)
    return _json({"credits": str(path), "non_commercial_or_research_assets": license_flags(base)})


@server.tool(structured_output=False)
def opus_doctor(project_dir: str = "") -> str:
    """Check that Blender, Godot, the GPU, ComfyUI and the project bible are reachable."""
    return format_report(doctor(project_dir or None))


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
