---
name: pixel-art
description: Make, fix and review pixel art for Godot games (sprites, tiles, sprite sheets, icons, palettes) with the Opus pixel tools, which show every sprite up close. Use whenever creating or editing pixel art, cleaning up AI-generated pixel art, building palettes or color ramps, or judging a sprite's quality.
---

# Pixel art with Opus Tools

You can't see a sprite well by reading its pixels. Always look at it with `sprite_inspect`.

## The loop (every asset, every change)

1. Read the project bible first (`project_bible`): palette, `max_colors`, light direction,
   outline style, typical character height. If there is no bible, offer the `project-bible`
   skill before making more than a throwaway sprite.
2. Make or change the asset at **native resolution** (1 array cell = 1 art pixel).
3. Run `sprite_inspect` (mode `tile` for tiles, `sheet` with frame size for animations).
4. Look at the sheet image, especially the 1x readability views and the issues overlay.
   Fix every warning that matters, then inspect again.
5. Stop when the warnings are clean or deliberately accepted. Show the user the sheet and
   name anything you chose to keep (for example "single-pixel eye glints are intentional").

## Pick the route by asset type

| Asset | Route |
|---|---|
| Icons, items, UI frames, simple props, tiles, effects | Draw in code at native size with palette ramps, then inspect. |
| Hi-res characters, creatures, detailed props | Don't plot them pixel by pixel. Use AI image + `pixel_cleanup`, the user's sketch + `pixel_cleanup`, or (Phase 2) the 3D-to-pixel renderer. |
| AI or painted "pixel art" (blurry, off-grid, too many colors) | `pixel_cleanup`, then `sprite_inspect`. |
| Recolors (enemy variants, seasons) | `palette_swap` with equal-length palettes. |

## Craft rules

1. **One pixel scale.** Never resize by non-integer factors or mix pixel sizes ("mixels").
   Export at 1x; let Godot scale.
2. **Palette discipline.** 3–6 colors per material ramp. Build ramps with `palette_ramp`:
   shadows shift cool (toward blue/purple), highlights shift warm (toward yellow), and
   saturation peaks in the midtones. Stay inside the bible's color budget, and lock
   finished art with `palette_apply`.
3. **One light direction** (from the bible). Shade by form and planes. Darkening toward the
   outline everywhere is pillow shading; the inspector flags it.
4. **Clean lines.** Curves use consistent step lengths (1-1-2-2-3…), not irregular ones.
   No doubled corners (cyan elbows in the inspector) and no stray pixels.
5. **Outlines.** Use the darkest color of the local ramp, not pure black. At hi-res, consider
   selective outlining: lighter where light hits, darker on the shadow side.
6. **Anti-aliasing by hand, sparingly,** only on curve steps inside the sprite. Never
   anti-alias against transparency; game backgrounds vary.
7. **Dither sparingly,** in ordered patterns on large gradients. Random speckle is noise.
8. **Binary alpha.** No semi-transparent pixels in sprites.
9. **Readability first.** The silhouette must read at 1x on light, mid and dark backgrounds.
   Parts need value contrast, so check the grayscale view.
10. **Animation:** same palette in every frame, stable ground line for idles and walks,
    deliberate timing. Use smear frames for fast actions. Check with mode `sheet`.

## Reading the inspector

| Warning | Fix |
|---|---|
| stray / orphan pixels | delete or merge into the neighbor color, unless it's a deliberate glint |
| jaggy elbows | remove the corner pixel so the line steps diagonally |
| semi-transparent pixels | make them fully opaque or fully clear |
| off-palette / over budget | `palette_apply`, or merge near-duplicate colors |
| flat ramps | rebuild the ramp with `palette_ramp` (hue shift around 20–30°) |
| pillow shading | re-shade from the light direction: lit planes light, turned-away planes dark |
| silhouette vanishes on a background | darken the outline or add a rim of contrast |
| tile seams visible | make the right edge continue into the left, and the bottom into the top |
| colors appear in only some frames | unify the frames' palette (flicker) |

## Drawing in code

Build a numpy RGBA array at native size. Define the palette ramps first, draw with exact
integer coordinates (Bresenham-style lines, midpoint circles), shade with the bible's light
direction, save PNG at 1x, then inspect. Keep a small script per asset so variants are
re-runs (change a seed or the ramp, not the code).

## Godot import (until Godot Pixel Setup automates it)

Set the default texture filter to Nearest (Project Settings › Rendering › Textures › Canvas
Textures). Use lossless compression and no mipmaps for 2D sprites. Pixel-perfect games use
stretch mode `viewport` with integer scaling. Hi-res sprites with smooth motion use
`canvas_items`.

## Provenance

Record anything imported or generated with `ledger_record` (source, license, model), so
`make_credits` can build CREDITS.md.
