# Opus Tools

A toolkit that makes Claude better at the things it's weakest at in game development:
**3D models, pixel art, animation and sound**. It targets Blender + Godot 4 projects and
installs once on the game-dev PC as a Claude Code plugin, so every project can use it.

The core idea is to give Claude ways to see what it makes. Every tool that creates
something is paired with one that renders or analyzes the result, so Claude can check and
fix its own work before handing it over.

See [PLAN.md](PLAN.md) for the full game plan and [DOWNLOADS.md](DOWNLOADS.md) for
optional large downloads. The repo holds code only.

## What's in v0.1

| Tool | What it does |
|---|---|
| `sprite_inspect` | Zoomed pixels with grid, issue overlay, 1x readability on light/mid/dark, silhouette, value, palette ramps, tile and animation views, plus a critique (strays, jaggies, partial alpha, off-palette colors, pillow shading, seams, flicker) |
| `pixel_cleanup` | Turns AI or painted "fake pixel art" into true pixel art: finds the real grid, removes the background, locks the palette, removes noise |
| `palette_ramp` / `palette_apply` / `palette_swap` | Hue-shifted ramps, palette locking (incl. Lospec palettes), recolors |
| `lookdev_sheet` | Renders a 3D model from every side in headless Blender: shaded, clay + wireframe, silhouettes, face orientation, UV checker, scale next to a 1.8 m figure |
| `mesh_lint` | Game-readiness check: flipped faces, non-manifold, loose/floating parts, UV problems, unapplied scale, budgets, bone weights |
| `project_bible` | Per-game style rules and budgets (`opus.project.yaml`) that every tool reads |
| `ledger_record` / `make_credits` | Where each asset came from and its license; generates CREDITS.md |
| `opus_doctor` | Checks Blender, Godot, GPU, ComfyUI and the project bible |

Plus skills (`pixel-art`, `3d-modeling`, `project-bible`) and an `art-director` reviewer
subagent.

## Install (Windows, Claude desktop app → Code tab)

1. Install **uv**: `winget install --id=astral-sh.uv -e`
2. In a Code tab session, add the marketplace and install the plugin:
   ```
   /plugin marketplace add Infamase/Opus-Tools
   /plugin install opus-tools@opus-tools
   ```
3. When asked, set **Blender executable** (for example
   `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`). Leave it empty to
   auto-detect. Godot and the library folder can stay empty for now.
4. Run `/reload-plugins` (or start a new session), then ask Claude to run `opus_doctor`.

The first start installs the Python dependencies into the plugin's data folder, which
takes a few seconds. If the `opus` server shows as failed in `/mcp`, reconnect it there.

Chat mode in the desktop app loads the skills but not plugin MCP servers. A desktop
extension (`.mcpb`) build for chat is planned.

## Try it

- "Inspect `art/hero.png` and fix what the inspector finds."
- "Clean up `ai/knight.png` into a 64-px sprite on our palette."
- "Make a 5-step hue-shifted ramp from #3a7d44 and save it as `palettes/grass.hex`."
- "Save the Blender file and show me a look-dev sheet of the barrel, then lint it as a
  prop_small."

## Development

```
cd plugins/opus-tools/python
uv run --group dev pytest           # Blender tests run when Blender is found (OPUS_BLENDER)
uv run opus doctor
claude plugin validate ../../..     # marketplace + plugin manifests
```
