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
- 3D: start characters and creatures from body_blockout (canon proportions + rig), not from
  guesses. Check bodies with proportion_check, concept fidelity with reference_match, and
  recognizability with blind_read_sheet. look_at shows any angle or part up close;
  model_report labels parts and measures them; lookdev_sheet shows every side; mesh_lint
  before calling anything game-ready.
- readability_check renders the part map at the game camera's true pixel size and flags thin defining parts.
- Hands holding things (first person especially): grip_define marks the handle, grip_hold
  puts it in the hand and closes the fingers on it, grip_check measures any held object.
  Never place held objects by eye.
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


def _names(objects: str) -> list[str] | None:
    return [s.strip() for s in objects.split(",") if s.strip()] or None


@server.tool(structured_output=False)
def body_blockout(
    archetype: str = "humanoid",
    preset: str = "",
    height: float = 0.0,
    pose: str = "A",
    target_tris: int = 10000,
    out_path: str = "",
    glb: bool = False,
) -> list:
    """Build a rigged, canon-proportioned body to model on, instead of guessing proportions.

    archetype/preset: humanoid realistic (7.5 heads) | heroic (8) | stylized (6) | chibi (3);
    quadruped dog | horse | cat; dragon western. height in meters (default 1.8 m humanoid,
    1.0 m chibi, the animal's real size). pose: A or T. Returns a Look Dev Sheet and a report
    with landmarks_m (chin, shoulder, waist, crotch, knee heights, limb lengths, widths) and
    joints_m. The rig uses Unreal mannequin bone names (pelvis, spine_01, upperarm_l, thigh_l)
    so it retargets in Unreal's IK Retargeter and maps to Godot/Unity humanoid profiles.
    Sculpt, kitbash or shrinkwrap the final model over it, then run proportion_check.
    """
    from opus.threed.body import body_blockout as run

    dest = None
    if out_path:
        dest = Path(out_path).expanduser()
        if not dest.is_absolute():
            dest = Path(os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()) / dest
    sheet, rep = run(archetype, preset, height, pose, target_tris, out=dest, glb=glb)
    return [Image(path=sheet), _json(rep)]


@server.tool(structured_output=False)
def look_at(
    path: str,
    views: str = "three_quarter",
    render_pass: str = "clay",
    target: str = "",
    zoom: float = 1.0,
    isolate: bool = False,
    ortho: bool = False,
    objects: str = "",
) -> list:
    """Look at a 3D asset (or one part of it) from any angle, on demand.

    views: comma-separated names (front, right, back, left, top, bottom, three_quarter,
    three_quarter_back) or "azimuth,elevation" pairs separated by ";" (e.g. "30,15; 200,40";
    azimuth 0 = front, 90 = right side). render_pass: clay | shaded | wire | silhouette |
    normals | parts (labeled part map) | focus (target in orange, rest gray). target: an
    object, collection, or bone name (a skinned body splits into bone regions such as hand_l)
    to frame; zoom > 1 moves closer; isolate hides everything else.
    """
    from opus.threed.understand import look_at as run

    if ";" in views or any(ch.isdigit() for ch in views.split(",")[0]):
        parsed = [v.strip() for v in views.split(";") if v.strip()]
    else:
        parsed = [v.strip() for v in views.split(",") if v.strip()]
    sheet, rep = run(_path(path), views=parsed, pass_=render_pass, target=target, zoom=zoom, isolate=isolate,
                     ortho=ortho, objects=_names(objects))
    return [Image(path=sheet), _json(rep)]


@server.tool(structured_output=False)
def model_report(path: str, objects: str = "") -> list:
    """Understand a 3D asset's structure: a labeled part map plus measurements.

    Parts are objects, or bone regions of a skinned body. Per part: size, shape class
    (rod/limb, slab, box, sphere-like...), long axis, bone length and girth. Also contacts and
    floating gaps between parts, mirror symmetry (and which parts break it), whether the
    center of mass sits over the footprint, and the rig's naming style.
    """
    from opus.threed.understand import model_report as run

    sheet, rep = run(_path(path), objects=_names(objects))
    text = rep.pop("text")
    return [Image(path=sheet), text + "\n\n" + _json(rep)]


@server.tool(structured_output=False)
def proportion_check(path: str, archetype: str = "humanoid", preset: str = "auto", pose: str = "auto", objects: str = "") -> list:
    """Measure a character's or creature's proportions against canon bodies at its height.

    Builds the canon blockouts (preset auto = all presets of the archetype, closest wins, or
    name one: realistic, heroic, stylized, chibi; dog, horse, cat; western) and overlays
    silhouettes front and side: red = the model sticks out, blue = the canon has volume the
    model lacks. Humanoids also get landmark ratios (leg length, head size and heads-tall,
    shoulders, waist, hips) and limb bone ratios when rigged. Use after every major change to
    a body until there are no findings you didn't intend (stylization is a choice, not an error).
    """
    from opus.threed.proportion import proportion_check as run

    sheet, rep = run(_path(path), archetype=archetype, preset=preset, pose=pose, objects=_names(objects))
    text = rep.pop("text")
    return [Image(path=sheet), text + "\n\n" + _json(rep)]


@server.tool(structured_output=False)
def reference_match(path: str, reference: str, view: str = "front", humanoid: bool = False, objects: str = "") -> list:
    """Compare the model's silhouette with a concept or reference image (front/side/back).

    Removes the image background (alpha, or the border color), scales both to the same
    height with feet aligned, mirrors the reference if that fits better, and reports IoU and
    the height bands where the model is wider or narrower. humanoid=true adds landmark
    comparisons (legs, head, shoulders...). view: front | back | right | left.
    """
    from opus.threed.proportion import reference_match as run

    sheet, rep = run(_path(path), _path(reference), view=view, humanoid=humanoid, objects=_names(objects))
    text = rep.pop("text")
    return [Image(path=sheet), text + "\n\n" + _json(rep)]


@server.tool(structured_output=False)
def blind_read_sheet(path: str, objects: str = "", game_size: bool = False, camera: str = "", distances: str = "") -> str:
    """Make an unlabeled silhouette + clay sheet for a blind recognizability test.

    Hand the returned prompt to a fresh subagent (e.g. the art-director agent) WITHOUT saying
    what the model is supposed to be. If its top guess isn't the intended subject, the
    defining features aren't reading yet. Compare its feature list with your feature brief.
    game_size=true adds the silhouette and clay at TRUE game pixel size (nearest-upscaled) for
    a camera profile (default: the bible's) at its distances, or at ``distances`` in meters.
    """
    from opus.threed.understand import blind_read_sheet as run

    sheet, prompt = run(_path(path), objects=_names(objects), game_size=game_size, camera=camera, distances=_floats(distances))
    return f"Blind-read sheet: {sheet}\n\nPrompt for a fresh reviewer (do not add what the model is):\n{prompt}"


@server.tool(structured_output=False)
def readability_check(
    path: str,
    camera: str = "",
    distances: str = "",
    defining: str = "",
    view: str = "",
    floor_px: float = 2.0,
    objects: str = "",
) -> list:
    """Will the asset read in the game? Renders its part map at TRUE game pixel size: the camera
    profile's FOV and resolution at each distance, cropped to the subject, no anti-aliasing.

    camera: a profile (default: the bible's camera.profile; presets ue_tp_1080, ue_fp_1080,
    godot_tp, unity_tp, topdown, sidescroller; "viewmodel" = the first-person view-model camera,
    flagged as a FALLBACK when the bible has none). distances: meters, comma-separated
    (default: the profile's close, typical, far). defining: the feature brief's 5-7 defining
    parts (part, bone or object names); those under floor_px wide, or gone, get warnings.
    view: front, right, three_quarter... or "azimuth,elevation" (default: the profile's).
    Per distance: the game-size image (nearest-upscaled), its part map, and visible px, min
    width and extent per part; the subject's height vs Johnson's criteria; a squint view.
    Floors are SOFT warnings until calibrated. Full per-part data: report["all_parts"].
    """
    from opus.threed.understand import readability_check as run

    sheet, rep = run(_path(path), camera=camera, distances=_floats(distances), defining=_names(defining), view=view,
                     floor_px=floor_px, objects=_names(objects))
    text = rep.pop("text")
    return [Image(path=sheet), text + "\n\n" + _json(rep)]


# ---------------------------------------------------------------- holding things

def _floats(text: str) -> list | None:
    return [float(x) for x in text.replace(";", ",").split(",") if x.strip()] if text.strip() else None


@server.tool(structured_output=False)
def grip_define(
    path: str,
    object: str,
    name: str = "main",
    part: str = "",
    start: str = "",
    end: str = "",
    palm_side: str = "",
    up: str = "",
    center: float = 0.5,
    style: str = "power",
    index: str = "curl",
    thumb: str = "wrap",
    trigger: str = "",
    point_axis: str = "",
    hand: str = "r",
) -> list:
    """Mark where and how a hand holds an object: a grip saved as an empty named
    SOCKET_grip_<name> on the object (Unreal's FBX import turns it into a socket; Godot and
    Unity get a node). Saves into the .blend (a .glb/.fbx gets a <name>_grips.blend).

    The handle axis is fitted to ``part`` (an object, e.g. the grip or handle mesh) or given
    as world-space ``start``/``end`` points "x,y,z". ``up``: direction toward the end the
    thumb points to (blade, slide, hammer head), default +Z. ``palm_side``: direction from
    the handle toward the palm; for pistol-style grips give ``point_axis`` instead (the
    object's local axis that points along the forearm, e.g. -Y for a barrel) and ``hand``.
    ``center`` (0-1) slides the hand along the handle. style: power | pistol. index: curl |
    trigger | extended; ``trigger`` is the trigger's front point "x,y,z". thumb: wrap | along.
    Returns a render: blue axis, red arrow = palm side, green = thumb end, yellow = trigger.
    """
    from opus.threed.grip import grip_define as run

    sheet, rep = run(_path(path), object, name, part, _floats(start), _floats(end), _floats(palm_side), _floats(up),
                     center, style, index, thumb, _floats(trigger), point_axis, hand)
    return [Image(path=sheet), _json(rep)]


@server.tool(structured_output=False)
def grip_hold(
    rig: str,
    object_path: str = "",
    object: str = "",
    grip: str = "",
    side: str = "r",
    pose: str = "rest",
    move: str = "object",
    aim_axis: str = "-Y",
    offset: str = "",
    index: str = "",
    thumb: str = "",
    out_path: str = "",
) -> list:
    """Put an object with a grip into a rigged hand so it sits right: the handle against the
    palm's skin, every finger closed until it touches (never inside), the thumb wrapped, the
    index on the trigger if the grip says so. Works on Unreal-, Mixamo-, Rigify- and
    humanoid-named rigs with finger bones (body_blockout humans have them).

    side: r | l. pose: rest (arm untouched) | front | fp_hip (first-person hip position; the
    object's ``aim_axis`` points forward; ``offset`` "forward,right,down" in m from the eye,
    default 0.5,0.2,0.18; long guns sit closer, e.g. 0.1,0.15,0.25) | fp_ads (needs an empty
    named SOCKET_sight on the object). move: object (bring it to the hand; adds a
    weapon_r/weapon_l bone and parents the object to it) | hand (reach this hand to an object
    already placed, e.g. the support hand on a rifle's handguard: run it on the saved file
    with object_path empty). Keys the pose as a Grip_* action and saves a new .blend.
    Returns close-ups colored by contact plus a measured report: palm and each finger
    touching / gap mm / inside mm, body clipping, aim_vs_hand_deg, wrist_bend_deg.
    """
    from opus.threed.grip import grip_hold as run

    dest = None
    if out_path:
        dest = Path(out_path).expanduser()
        if not dest.is_absolute():
            dest = Path(os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()) / dest
    sheet, rep = run(_path(rig), _path(object_path) if object_path else None, object, grip, side, pose, move, aim_axis,
                     _floats(offset), index, thumb, dest)
    text = rep.pop("text")
    return [Image(path=sheet), text + "\n\n" + _json(rep)]


@server.tool(structured_output=False)
def grip_check(path: str, side: str = "r", object: str = "", fp: bool = False) -> list:
    """Check how hands hold things in any rigged scene, however it was made: for the palm and
    each finger, touching, the gap in mm, or how deep it sinks into the object, plus any
    place the object passes through the body. side: r | l | both. object: the held object
    (default: the one nearest the palm). fp: also render the first-person view from the eyes.
    """
    from opus.threed.grip import grip_check as run

    sheet, rep = run(_path(path), side, object, fp)
    text = rep.pop("text")
    return [Image(path=sheet), text + "\n\n" + _json(rep)]


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
    from opus.bible import camera_profile

    bible = load_bible(base)
    for key, name in (("camera_active", ""), ("camera_viewmodel", "viewmodel")):
        try:  # the resolved camera and its derived numbers (px/m, smallest features, texel density)
            bible[key] = camera_profile(bible, name).summary()
        except ValueError as e:
            bible[key] = {"error": str(e)}
    return _json(bible)


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
