# Opus Tools

A toolkit that makes Claude better at the things it's weakest at in game development:
**3D models, pixel art, animation and sound**. It targets Blender with Unreal, Godot or
Unity, and installs once on the game-dev PC as a Claude Code plugin, so every project can
use it.

The core idea is to give Claude ways to see what it makes. Every tool that creates
something is paired with one that renders or analyzes the result, so Claude can check and
fix its own work before handing it over.

See [PLAN.md](PLAN.md) for the full game plan and [DOWNLOADS.md](DOWNLOADS.md) for
optional large downloads. The repo holds code only.

## What's in v0.4

v0.4 (sprint S0a of the [overhaul](docs/OVERHAUL.md)) adds game-camera readability, judge
sheets for a blind review protocol, licence IDs in the provenance ledger and a run ledger
for the eval suite, and fixes canons and measurements in the v0.3 tools.

| Tool | What it does | v0.4 |
|---|---|---|
| `readability_check` | Renders the part map at the game camera's true pixel size (profile FOV and resolution, close / typical / far distances, no anti-aliasing): subject height against Johnson's criteria, min width per part, warnings for defining parts under 2 px or gone, a squint view; `viewmodel` camera for first person | new |
| `lineup_sheet` | The asset beside 2–3 human-made exemplars, cut out and scaled to the same game height (or the height the camera profile gives at a distance), letters only, in both orders for two fresh judges | new |
| `ab_sheet` | Blind A/B pair of two versions in both orders, at game size or large; a candidate wins only when both orders pick it | new |
| `licence_check` | What in the ledger blocks export under the bible's policy (`commercial`, `publish_assets`), with the reason and the input responsible; classifies a licence string to its ID | new |
| `run_log` / `run_stats` | Run ledger per asset (check rounds, judge rounds, rejections, tokens, accept) and its stats: iterations to a hard pass, wall-clock, failing checks | new |
| `body_blockout` | Rigged, canon-proportioned starting bodies: humanoid (realistic, heroic, stylized, chibi), quadruped (dog, horse, cat), western dragon. Unreal mannequin bone names; reports landmark heights and limb lengths to model to | hand 0.82 and foot 1.15 head-units from ANSUR II; dog, cat and horse hind legs from Garland & Janis MT/F; horse fetlock, pastern and hoof |
| `proportion_check` | Overlays a model's front and side silhouettes on canon bodies built at its height; reports leg length, heads tall, shoulder/waist/hip widths and limb bone ratios | hand bone compared |
| `reference_match` | Silhouette match against a concept or reference image: IoU plus where the model is too wide or narrow | |
| `look_at` | Any angle, zoom and render pass, framed on an object or a bone region such as `hand_l` | mask mode: exact part colours, no blended edges |
| `model_report` | Labeled part map plus measurements: shapes, contacts, floating parts, penetrations, symmetry, balance, rig style | penetrations with depth, including parts pushed through thin plates; touching faces stay contacts |
| `blind_read_sheet` | Unlabeled silhouettes for a fresh reviewer to identify, to test whether a model reads as what it should be | `game_size`: silhouette and clay at true game pixel size |
| `grip_define` | Marks how an object is held: handle axis, palm side, thumb end, trigger point (a `SOCKET_grip_*` empty that becomes an Unreal socket) | |
| `grip_hold` | Puts the object in a rigged hand: handle seated on the palm skin, every finger closed until it touches, thumb wrapped, index on the trigger; first-person poses and two-handed holds; adds a `weapon_r` bone and a grip pose action | robust signed distance |
| `grip_check` | Measures any hand holding anything: palm and each finger touching, gap or depth inside in mm, and where the object clips the body | also catches the object crossing the body between vertices |
| `sprite_inspect` | Zoomed pixels with grid, issue overlay, 1x readability on light/mid/dark, silhouette, value, palette ramps, tile and animation views, plus a critique (strays, jaggies, partial alpha, off-palette colors, pillow shading, seams, flicker) | |
| `pixel_cleanup` | Turns AI or painted "fake pixel art" into true pixel art: finds the real grid, removes the background, locks the palette, removes noise | |
| `palette_ramp` / `palette_apply` / `palette_swap` | Hue-shifted ramps, palette locking (incl. Lospec palettes), recolors | |
| `lookdev_sheet` | Renders a 3D model from every side in headless Blender: shaded, clay + wireframe, silhouettes, face orientation, UV checker, scale next to a 1.8 m figure | mask mode for silhouettes |
| `mesh_lint` | Game-readiness check: flipped faces, non-manifold, loose/floating parts, UV problems, unapplied scale, budgets, bone weights | |
| `project_bible` | Per-game style rules and budgets (`opus.project.yaml`) that every tool reads | camera profiles and view-model camera with derived px/m; licence policy keys |
| `ledger_record` / `make_credits` | Where each asset came from and its licence; generates CREDITS.md | SPDX / LicenseRef IDs with flags, `inputs` lineage, tools, exact attribution strings; free text matched on whole names only (restriction phrases beside a name add their flags) |
| `opus_doctor` | Checks Blender, Godot, GPU, ComfyUI (optional, 2D and audio only) and the project bible | |

The 24-task eval suite lives in [evals/](evals/README.md) (`opus eval list | validate |
prompt | summarize | compare`), and [docs/PC_CHECKS.md](docs/PC_CHECKS.md) is the
10-minute check to run on the game-dev PC after an update. Data tables under
`plugins/opus-tools/data/` are listed with their sources in its `LICENSES.md`.

Plus skills (`pixel-art`, `3d-modeling`, `project-bible`) and an `art-director` reviewer
subagent that reviews 3D work by yes/no checklist, blind read, lineup and both-order A/B.

### Changes in 0.4.1

These fixes come from the v0.4 baseline run ([evals/results/v0.4.md](evals/results/v0.4.md)):
22 of 24 eval tasks were accepted by an independent grader, with a median of 2 iterations to
a hard pass.

- **Floating parts and contacts on skinned and imported assets.** `model_report` and
  `mesh_lint` now find floating islands and gaps on skinned meshes, giving the gap in mm and
  the nearest part. Penetrations are reported but no longer gate a check, and faces that
  only touch count as contacts.
- **Lint on shipped files.** glTF, FBX, OBJ and STL imports are welded before lint runs, so
  exports no longer raise false "faces point inward" errors. Rotated objects no longer raise
  false flipped normals, and props parented to a bone count as rigid.
- **Readability.** `readability_check` matches defining names in any case or by prefix,
  and names that match nothing count against the check. A camera inside the subject is
  flagged, and blind sheets leave those views out. Game-size silhouettes turn to the side
  that shows the most.
- **Grips and look.** `grip_check` accepts props skinned to the weapon bone. A `look_at`
  bone target includes the bone's fingers, and a hidden one gets a cutaway. The normals and
  vertex-colour passes are correct.
- **Command line and run ledger.** Every report command takes `--json`. Values that start
  with a dash and axis names such as `+Z` work. Errors are one line instead of a traceback.
  `run-log --help` lists every field. An event without a run id is refused when several
  runs are open, and a `grade` event records an independent grader's verdict.
- **Output paths.** Each call gets its own output path, so parallel calls never share files.

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

## Updating

Refreshing the marketplace only downloads the new catalog; the installed plugin stays on
its old version until you update it, then restart. In a terminal (PowerShell):

```
claude plugin marketplace update opus-tools
claude plugin update opus-tools@opus-tools
```

Then fully quit and reopen the desktop app (or start a new session) so the new version
and its MCP tools load. `claude plugin list` shows the installed version. If an update
still won't apply, reinstall: `claude plugin uninstall opus-tools@opus-tools`, then
`claude plugin install opus-tools@opus-tools`. Reinstalling clears the plugin's settings,
so set the Blender path again afterwards.

Chat mode in the desktop app loads the skills but not plugin MCP servers. A desktop
extension (`.mcpb`) build for chat is planned.

## Try it

- "Inspect `art/hero.png` and fix what the inspector finds."
- "Clean up `ai/knight.png` into a 64-px sprite on our palette."
- "Make a 5-step hue-shifted ramp from #3a7d44 and save it as `palettes/grass.hex`."
- "Save the Blender file and show me a look-dev sheet of the barrel, then lint it as a
  prop_small."
- "Make a heroic knight for Unreal: start from a body blockout, check proportions, and do a
  blind read before showing me."
- "Compare `dragon.blend` with `concept/dragon_side.png` from the side."
- "Put `pistol.blend` in the hero's right hand for first person, index on the trigger, and
  show me what the player sees."
- "Will the goblin read at 15 m in our third-person camera? Check the club and the ears."
- "Line the chest up against these two Kenney chests at game size and ask two judges."
- "Record `textures/rock.png` as CC0 from ambientCG and `models/cart.glb` as CC BY 4.0 from
  Poly Pizza, then tell me if anything blocks a commercial release."

## Development

```
cd plugins/opus-tools/python
uv run --group dev pytest           # Blender tests run when Blender is found (OPUS_BLENDER)
uv run opus doctor
uv run opus eval validate           # the 24 eval task specs
claude plugin validate ../../..     # marketplace + plugin manifests
```
