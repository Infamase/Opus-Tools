---
name: project-bible
description: Create or update a game's opus.project.yaml (art style, palette, budgets, cameras, feel) through a short interview, so every Opus tool and every asset stays consistent. Use when starting a new game project, when assets drift in style, or when the user states a lasting style rule or preference.
---

# Project bible

The bible is `opus.project.yaml` at the game's root, next to `project.godot`. Every Opus
tool reads it for defaults: palette, color budget, light direction, triangle budgets,
look-dev engine.

## Creating one

Ask everything in **one** message, with suggested defaults so the user can answer fast:

1. Art style(s): pixel, low-poly, HD (can mix, e.g. pixel sprites in a low-poly world)
2. Camera(s): first-person, third-person, top-down, side-scroller
3. Pixel art: palette (a Lospec name like `endesga-32`, a file, or "make one"), typical
   character height in pixels, outline style (dark, selective, none), light direction
4. 3D: target platform or performance feel, which sets the budgets (defaults are prop
   500/3000, character 8000, hero 20000 tris)
5. Animation feel (snappy, floaty, weighty) and frame rate
6. Any reference games or images for the look

Then call `project_bible` with `action: "init"`, edit the created file to match the
answers, and show the user the result.

## Keeping it alive

- When the user states a lasting preference ("outlines too thick", "I like chunkier
  proportions"), add a short line to `taste_notes` and follow it from then on.
- When a palette is created, save it as a `.hex` file in the project (`palette_ramp` with
  `save_as`, or write it) and point `pixel.palette` at it.
- Keep the file short. It holds rules, not a design document.
