# Opus Tools — Game Plan

**Mission:** give Claude the senses, building blocks, raw material and quality gates it
needs to produce good **3D models**, **pixel art**, **animation** and **sound** for
Blender + Godot 4 games, packaged as one small install on the game-dev PC that works in
every project.

Status: planning draft v0.2 (2026-10-07). Nothing is built yet.

---

## 0. The setup this plan targets

| | |
|---|---|
| **PC** | Windows 10 · RTX 4070 Ti Super (16 GB VRAM) · 64 GB RAM · ~100 GB free disk |
| **Apps** | Blender 5.2 · Godot 4.7.2 · MCP servers for both already connected to the Claude desktop app |
| **Art styles** | Hi-res pixel art, low-poly 3D, HD 3D |
| **Camera views** | First-person, third-person, top-down, side-scroller |
| **Licensing** | Personal games shared free with friends, never sold, so non-commercial licenses are fine |
| **Spending** | Local first; affordable paid services are OK |
| **Priorities** | 1. 3D models and pixel art · 2. animation · 3. sound |
| **Repo** | Code only, kept small. Model weights, asset and sound libraries, and apps are listed in a downloads manifest for manual download, never committed. |

## 1. Diagnosis — why Claude's output is weak today

| Gap | What it causes |
|---|---|
| **Claude can't perceive what it makes.** It writes a Blender script and never sees the mesh, plots pixels and never sees the sprite up close, keys an animation and never watches it, writes DSP code and never hears it. | Floating parts and wrong proportions; jaggies, stray pixels and muddy shading; foot sliding and pops; clicks and clipping. All of it goes unnoticed. |
| **The authoring interface is too low-level.** Raw `bpy` vertex math, raw pixel coordinates, raw keyframe values, raw sample buffers. | "Primitive soup" models, blobby code-drawn sprites, linear robotic motion, sine-and-noise sound effects. Claude is strong at structure and composition, weak at holding coordinates and curves in its head. |
| **It starts from nothing.** Real artists start from reference, libraries, recordings, scans and mocap. | Everything looks like programmer art. Organic shapes, detailed characters, human motion and natural sounds suffer most. |
| **No craft memory.** Budgets, palettes, conventions and recipes are re-derived every session; there is no record of what the user liked. | Inconsistent style across a game's assets; the same mistakes repeat. |
| **Pipeline traps between Blender, image tools and Godot.** | Procedural materials vanish on export; wrong scale, axes or origins; blurry filtered sprites and jittery pixel cameras; missing loop flags; clips never wired into an `AnimationTree`. |

The single biggest lever is the first gap. The suite **closes the loop**: every *make* tool
is paired with a *perceive* tool and a rubric, so Claude iterates
**make → render/analyze → critique → fix** before the user ever sees the asset.

## 2. Design principles

1. **Perceive before shipping.** No generator without a matching inspector. Inspectors
   return images Claude can look at (contact sheets, zoomed pixel grids, spectrograms,
   motion strips) plus numeric reports with pass/fail thresholds.
2. **Semantic building blocks over raw numbers.** Parameterized, craft-aware builders
   (bevels, profiles, palette ramps, layers, envelopes, poses, easing) with good defaults.
   Assets are *recipes* (code + params + seed), so variations and fixes are re-runs.
3. **Start from real material.** CC0 libraries, real recordings, mocap and generative
   models are inputs; Claude's job shifts toward selecting, kitbashing, processing,
   cleaning up and integrating, which it is good at.
4. **Engine-native end state.** "Done" means imported and wired in Godot (import options,
   collision, tilesets, randomizers, buses, AnimationTree) and verified with an in-engine
   capture.
5. **The user is the final judge — cheaply.** Taste calls go through a fast audition and
   rating board; ratings are saved as taste notes.
6. **One project bible.** Every tool reads a per-project style and budget file, so assets
   stay consistent.
7. **Provenance from day one.** Every asset records its source, license and author. That
   produces credits for the friends' build and an exact list of what to replace if a game
   ever goes public.
8. **Swappable AI backends, sized to the GPU.** Generative models churn monthly; they sit
   behind stable interfaces, and the core stays useful with no GPU at all.
9. **MCP-first, small repo.** Every capability is an MCP tool, so it works from the
   desktop app. The repo holds code only; big downloads are listed, never committed.
10. **Testable headlessly.** Everything runs against headless Blender and Godot, so it can
    be built and regression-tested in cloud sessions and CI before it reaches the PC.

## 3. Architecture

```
 ┌───────────────────── Claude (desktop app: Code tab or chat) ─────────────────────┐
 │  Skills: craft knowledge, workflows, rubrics     Critic subagents (fresh eyes)   │
 └──────────────┬───────────────────────────────────────────────────────────────────┘
                │ MCP tools (return images + JSON)
 ┌──────────────▼───────────────────────────────────────────────────────────────────┐
 │                         opus core  (Python, managed by uv)                       │
 │  senses : look-dev sheet · sprite inspector · motion inspector · audio inspector │
 │  craft  : shape kit · material lab · pixel forge · 3D→pixel · keyframe director  │
 │  gates  : mesh lint · pixel lint · rig lint · motion diagnostics · loudness      │
 │  sources: asset/SFX/motion librarians · generative backends · provenance ledger  │
 └───────┬────────────────────────┬─────────────────────────┬───────────────────────┘
         │                        │                         │
  Blender 5.2 (your Blender  Godot 4.7 (your Godot    Local AI backends
  MCP, or headless `-b`)     MCP, headless import,    (image, 3D, motion, audio
                             frame capture)           models on the 16 GB GPU)
```

- **How it reaches Claude in the desktop app.**
  - **Code tab (recommended for asset work):** install this repo as a Claude Code plugin
    (`/plugin marketplace add Infamase/Opus-Tools`, then `/plugin install
    opus-tools@opus-tools`). That brings skills, subagents and our MCP servers, plus
    Claude's own file access and terminal. The plugin's `userConfig` asks once for paths
    and API keys.
  - **Chat:** the same skills load there, but MCP servers bundled inside a plugin don't.
    Chat runs local MCP servers only as desktop extensions, so CI also builds our servers
    as `.mcpb` desktop extensions (installed under Settings > Extensions) and publishes
    them on GitHub Releases, outside the repo. Chat has no local file access beyond what
    those tools return.
- **Works alongside the MCP servers already on the PC.** Our in-Blender modules run through
  any Blender MCP that executes Python, or through a plain `blender -b` runner. Godot
  editor control stays with the existing Godot MCP; we add headless import, `.import`
  writers and frame capture as our own small server.
- **Skills** carry the craft: workflows, rubrics, recipes, Godot conventions. They load on
  demand (each SKILL.md under ~500 lines, details in reference files).
- **MCP servers** (Python, stdio, run with `uv`) return images directly, so renders, pixel
  zooms and spectrograms come straight back to Claude. Long renders need a raised tool
  timeout. An `opus` CLI exposes the same functions for CI and batch jobs.
- **Blender side:** code that runs *inside* Blender depends only on `bpy` + `numpy`
  (Blender's bundled Python) and follows the 5.x API.
- **Godot side:** `addons/opus/` holds editor helpers (import post-processors, TileSet and
  AnimationTree builders) and runtime helpers (game feel, procedural animation,
  pixel-perfect camera, audio). Movie Maker mode gives deterministic in-engine frame
  captures.
- **Per project:** `opus.project.yaml` (the bible) and `.opus/` (provenance ledger,
  ratings, caches).
- **License:** GPL-3.0 by default. Blender add-on code must be GPL-compatible anyway, and
  the best audio libraries are GPL. The assets the tools produce are unaffected.

Proposed repo layout (code only):

```
Opus-Tools/
├── .claude-plugin/marketplace.json
├── plugins/
│   ├── opus-tools/                  # main plugin: works on any PC, no GPU needed
│   │   ├── .claude-plugin/plugin.json   # userConfig: paths, library dir, API keys
│   │   ├── .mcp.json                # opus-blender, opus-pixel, opus-godot,
│   │   │                            # opus-audio, opus-assets servers
│   │   ├── skills/                  # project-bible, modeling, materials, pixel-art,
│   │   │                            # tilesets, animation, rigging, sound-design,
│   │   │                            # godot-pipeline, critique
│   │   ├── agents/                  # art / animation / audio director critics
│   │   ├── python/                  # opus core package, CLI, MCP servers
│   │   ├── blender/                 # in-Blender modules (bpy + numpy only)
│   │   └── godot/addons/opus/       # copied into a game by `opus godot init`
│   └── opus-gen/                    # optional plugin: local AI backends + paid APIs
├── extensions/                      # .mcpb manifests (bundles are built by CI)
├── evals/                           # benchmark task specs and scores (no big files)
├── tests/                           # headless tests, small golden images
├── install/                         # Windows setup + `opus doctor`
└── DOWNLOADS.md                     # every big download: link, size, license, target
```

## 4. Tool catalog

Priority (**P0** foundation · **P1** biggest quality wins · **P2** strong upgrades ·
**P3** nice to have) is ranked within each domain. The roadmap orders the domains by the
user's priorities.

### 4.0 Foundation

| Tool | What it does | Pri |
|---|---|---|
| **Blender Bridge** | Uses the Blender MCP already on the PC for live control; our in-Blender modules run through its Python execution. Adds checkpoints and versioned `.blend` saves (MCP servers run generated code unguarded), `.glb` export presets, and a plain `blender -b` runner for batch jobs and CI. | P0 |
| **Godot Bridge** | Uses the Godot MCP already on the PC for editor control. Adds the parts it probably lacks: headless `--import`, `.import` option writers, scene inspection, and deterministic frame capture (Movie Maker mode) for in-engine checks. | P0 |
| **Project Bible** | `opus.project.yaml`: art style, palette, pixel scale, shape language, reference board, tri/texture/bone budgets, texel density, loudness targets, animation fps and "feel", naming rules. Created by a short interview skill; read by every tool. | P0 |
| **Provenance Ledger** | Sidecar record per asset (source, license, author, generator + model version); generates `CREDITS.md`; flags anything that would block a public release. | P0 |
| **Downloads manifest** | `DOWNLOADS.md` lists every large optional download (model weights, asset and sound libraries, apps) with purpose, size, license, link and target folder. `opus doctor` checks what's installed and what's missing. | P0 |
| **Installer + `opus doctor`** | Windows setup (uv environment, plugin and extension install, Godot add-on) and a health check of every integration. | P0 |
| **Eval suite** | Fixed benchmark tasks per domain, produced before and after each tool and rated blind. Tells us which tools actually improve quality. | P0 |

### 4.1 3D models

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Look Dev Sheet** | can't see it | One call → labeled contact sheet: front/side/back/top + ¾ perspective; clay/matcap (form); wireframe (topology density); solid silhouette (shape readability); face orientation (flipped normals); UV checker; 1.8 m human silhouette + 1 m grid for scale. Optional side-by-side with a reference, and a **gameplay-distance view** at the on-screen size the asset will really have in each camera style. Laid out to fit Claude's image-input resolution. | P1 |
| **Mesh Lint** | not game-ready | Non-manifold/loose geometry, flipped normals, zero-area faces, n-gons on deforming meshes, unapplied transforms, origin placement, intersecting/floating parts, tri budget, UV presence/overlap/bounds, texel-density consistency, material count, texture sizes, naming. JSON + heatmap render + safe auto-fixes. | P1 |
| **Shape Kit** | primitive soup | Python modeling library of semantic, parameterized builders: beveled primitives, lathe from profiles, sweep/loft/pipe along curves, inset/extrude/panel lines, booleans with cleanup + weighted normals, mirror/array/radial, taper/bend/twist/lattice, organic blobs (skin modifier/metaballs/SDF → remesh), scatter, grid-snapped modular kits, and generators (rocks, trees, crates, barrels, buildings, furniture, weapons). Every asset is a recipe function + params + seed → instant variations. Style presets: low-poly flat, stylized, PBR-realistic, PS1-retro, voxel. | P1 |
| **Material Lab + Bake** | flat colors; procedural materials lost on export | Procedural material graphs (wood, metal, stone, fabric, plastic, toon) with curvature/AO-driven wear and grime; one-call **bake to Godot-ready PBR** (albedo, ORM, normal) at the bible's texel density; high→low normal/AO bakes; palette-atlas workflow for low-poly; trim sheets; Godot material setup (StandardMaterial3D or toon shader). | P1 |
| **Asset Librarian** | starting from nothing | Indexes CC0 packs downloaded per the manifest; renders thumbnails; text + image search via embeddings; returns a candidate contact sheet; imports with provenance; kitbash parts out of library meshes. | P1 |
| **Godot Import Pipeline** | export traps | glTF export presets; Godot import hints (`-col`, `-convcolonly`, `-navmesh`, `-loop`, …); writes `.import` options (LODs, shadow meshes, collision, materials); post-import scripts; then an in-engine capture in the game's own lighting. | P1 |
| **Gen3D + Cleanup** | HD organic shapes | Concept image (sketch, reference, or generated) → local image-to-3D model sized to 16 GB, or an affordable paid API → automated cleanup: scale/orient, remove floaters, remesh/decimate to budget, UVs, texture re-bake, LODs → Mesh Lint → Godot. Raw AI meshes aren't game-ready; the cleanup is the value. | P1 |
| **Gen Texture** | bland surfaces | Tileable PBR materials and decals from a local image model, plus **mesh texturing**: paint a whole untextured model (for example a Shape Kit build) from a prompt or reference, then bake to UVs. | P2 |
| **Godot Look Presets** | assets look flat in-engine | WorldEnvironment, light rig, tonemapping, SSAO/SSIL, glow and fog presets per art style; used by every in-engine capture, so assets are judged under the light they ship in. | P2 |
| **Blueprint & Match** | wrong proportions | Reference images or the user's sketches behind orthographic cameras; silhouette-overlap score (IoU) per view between render and reference. | P2 |
| **Lineup Render** | style drift | Renders the new asset next to already-approved assets at the same scale and lighting to catch scale, style and detail-density mismatches. | P3 |

### 4.2 Pixel art

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Sprite Inspector** ("pixel eyes") | can't see the pixels | Integer-zoom view with a pixel grid, plus 1× and in-game-scale previews on light, dark and in-game backgrounds; silhouette and grayscale-value views; palette report (color count, ramps, hue shift). Lint: orphan pixels, jaggies, doubled lines, banding, pillow shading, mixed pixel sizes ("mixels"), stray semi-transparent pixels, inconsistent outlines, colors over budget. Tiles get a 3×3 repeat view to expose seams; animations get an onion-skin strip and a frame-to-frame difference map. | P1 |
| **Pixel Cleanup** | AI "fake pixel art" | Finds the real pixel grid in AI or painted output, downsamples to true resolution, snaps colors to the project palette, removes noise and orphan pixels, and fixes alpha and outlines. Turns generated images into usable sprites. | P1 |
| **Palette Lab** | muddy, inconsistent color | Builds hue-shifted color ramps, imports Lospec palettes, locks every asset to the game's palette, and makes palette-swap variants (enemy recolors, seasons). | P1 |
| **3D → Pixel Renderer** | detailed characters with many animations | Renders 3D models and animations to pixel sprite sheets: orthographic camera, 4/8/16 directions, stepped toon lighting, outline pass, palette lock, no anti-aliasing, one pixel scale everywhere. Exports sheets plus Godot `SpriteFrames`. This is the technique Dead Cells used, and it turns every 3D and animation tool into a pixel-art tool too. | P1 |
| **Tileset Builder** | seams, broken autotiling | Seamless tiles and terrain transitions in standard autotile layouts; generates Godot `TileSet` resources with terrain peering bits already set; seam checks. | P1 |
| **Godot Pixel Setup** | blurry sprites, jittery cameras | Pixel-perfect project settings (stretch mode, integer scaling, nearest filtering, pixel snapping), jitter-free camera follow, normal maps for 2D lighting, and HD-2D setups (pixel sprites in 3D scenes with pixel-friendly post-processing). | P1 |
| **AI Pixel Pipeline** | detail code can't draw | Local image model with a pixel-art LoRA on the 16 GB GPU, or an affordable paid pixel-art service → Pixel Cleanup → Sprite Inspector. Can start from Pixel Forge blockouts or 3D renders (image-to-image) to keep characters on-model. | P1 |
| **Pixel Forge** | blobby code-drawn sprites | Procedural sprite language: pixel-perfect lines, curves and shapes; light-direction shading through palette ramps; selective outlines; dithering; symmetry; layers. Generators for icons and items, props, UI frames (9-slice) and simple tiles. Every sprite is a recipe → instant variants. | P2 |
| **Sprite Animator** | stiff or inconsistent frames | Frame-by-frame key poses + in-betweens, smear frames, sub-pixel motion and per-frame timing; skeletal cut-out rigs (Godot `Skeleton2D`) for hi-res sprites; or the 3D → Pixel route for complex motion. Packs sheets and builds `SpriteFrames` / `AnimationPlayer` tracks. | P2 |
| **Pixel Editor Bridge** | hand touch-ups | Round-trips with the user's pixel editor (e.g. Aseprite's command line and Lua scripting): read and write layers, tags and slices, so hand edits flow back into the pipeline. | P3 |

### 4.3 Animation

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Motion Inspector** ("eyes for motion") | can't watch it | Frame contact sheet from two cameras with onion skins and motion trails (hands, feet, head, root); curve plots (root height, foot heights/speeds, key joint angles); GIF/MP4 for the user. Diagnostics: **foot sliding**, ground penetration, joint-limit violations and knee flips, self-intersection, pops (velocity/jerk spikes), loop-seam continuity (pose and velocity), balance (center of mass vs support), arc smoothness, key-spacing chart. | P1 |
| **Motion Library + Retargeter** | hand-keyed humans | Indexes motion sets downloaded per the manifest (CC0 libraries, CMU mocap, Mixamo clips, …); text search with preview strips; retargets onto the project's rigs using bundled bone maps for common skeletons (Mixamo, UE5 Mannequin, Rigify, SOMA); clip tools: trim, loop-fix (blend tail into head), speed, in-place ↔ root motion, mirror, additive layers. | P1 |
| **Godot Animation Wiring** | clips that feel bad in-game | Builds `AnimationTree` state machines and blend spaces from a spec (locomotion by velocity, one-shots, crossfades, root motion); runtime procedural layers built from Godot's own skeleton modifiers: foot IK on slopes, look-at, spring bones (hair, tails, capes), lean into turns, partial-ragdoll hit reactions; **game-feel library** (easing presets, squash/stretch on landing, hit-stop, camera shake). Often the biggest perceived quality gain per hour of work. | P1 |
| **Rig Doctor** | broken deformation | Game-ready rig templates (deform bones in one clean hierarchy, names matching Godot's `SkeletonProfileHumanoid` so Godot's retargeting just works) plus quadruped/bird/tail/tentacle/mechanical templates; auto-rig + automatic weights + weight transfer; **deformation test**: extreme poses (arms up, squat, twist) rendered as a contact sheet, with candy-wrap and volume-loss flags; weight lint (≤4 influences, normalized, unweighted verts, symmetry). | P1 |
| **Keyframe Director** | linear, weightless motion | Animation DSL: Claude authors semantic poses, IK targets and timing ("anticipate 4f, strike 2f, overshoot 15 %, settle 6f"), and the 12 principles are automatic passes: slow-in/out, anticipation, overshoot/settle, follow-through and overlap down bone chains, arcs, baked secondary motion, squash & stretch. Procedural cycle generators (walk/run/sneak/idle/fly/swim) with planted-foot IK and stride/bounce/weight/mood parameters. Best for creatures, props, machines, doors, chests and UI. | P2 |
| **Animation Events** | SFX/VFX out of sync | Uses Motion Inspector analysis to place method/audio tracks automatically: footsteps at foot contacts, whooshes at weapon peak velocity, impacts at contact frames; attack frame data (startup/active/recovery). | P2 |
| **Mocap from video / text** | unique human actions | The user films an action on a phone → video-to-motion model → cleanup (foot lock, smoothing, loop) → retarget → Motion Inspector. Text-to-motion models for drafts. | P2 |
| **Lip Sync** | dead faces in dialogue | Viseme timing from voice lines → shape-key / blend-shape tracks. | P3 |
| **Sim Bake** | stiff cloth, fake destruction | Blender cloth/rigid/soft-body sims baked to keyframes, shape keys or vertex-animation textures for Godot. | P3 |

Sprite animation lives in §4.2 (Sprite Animator and 3D → Pixel Renderer).

### 4.4 Sound

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Audio Inspector** ("ears") | can't hear it | Image of waveform + log-frequency spectrogram + loudness curve; report of duration, peak/true peak, LUFS, crest factor, DC offset, clipping, head/tail silence, attack/decay, spectral centroid/rolloff/flatness, pitch, onsets, stereo phase, noise floor, clicks and **loop-seam** continuity. A-vs-B and vs-reference comparison. Optional ML listeners: a text–audio match score ("how much does this sound like *heavy wooden door slam*?"), a production-quality score, and a captioner that describes the sound in words. | P1 |
| **SFX Library** | synthetic-only sound | Indexes royalty-free libraries (downloaded per the manifest) and the user's own recordings with metadata + audio embeddings; text search; candidates with spectrograms; license tracking. | P1 |
| **Sound Forge** | thin, unprocessed sound | Declarative sound recipes: layers (library sample, synth or generated), each with trim/pitch/stretch/reverse/fades/EQ/saturation/transient shaping; bus processing (glue compression, convolution reverb with real impulse responses, limiter); normalized to the bible's category loudness. This is how sound designers work: layer and process real sources. | P1 |
| **Godot Audio Packager** | machine-gun repetition; uneven levels | Renders N variations; picks WAV vs Ogg Vorbis; writes loop settings with zero-crossing-snapped loop points; generates `AudioStreamRandomizer` resources; bus layout (Master/Music/SFX/UI/Ambience/Voice) with per-zone reverb buses; 3D attenuation presets. | P1 |
| **Gen Audio** | complex natural SFX; voices | Local text-to-SFX model as one more *source* for the Forge (generate → layer/process → inspect); TTS for character barks with emotion control + voice processing (radio, robot, monster). | P2 |
| **Synth Engine + Recipe Book** | beeps and white noise | For what synthesis does well — UI, retro, sci-fi, magic, whooshes, engines, weather/ambience beds — and impacts via **modal synthesis** (wood/metal/glass resonances). Backed by a real synth hosted headlessly + DSP; the recipe book stores known-good parameter ranges per category. | P2 |
| **Music Studio** | simplistic music | Structured score (sections, chord progressions, parts, drum patterns) → MIDI → rendered with good free instruments → mix/master chain → loop-perfect export (render two passes, keep the second so reverb tails wrap) → stems for adaptive music in Godot (`AudioStreamInteractive` / `AudioStreamSynchronized`). Theory lint (ranges, voice leading). | P2 |
| **Mix Check** | inconsistent mix | Project-wide loudness consistency per category, outliers, frequency masking between sounds that commonly play together. | P3 |

### 4.5 Cross-cutting

| Tool | What it does | Pri |
|---|---|---|
| **Critic subagents** | Fresh-context art, animation and audio "directors" that judge inspector output against the bible and rubrics, so Claude isn't grading its own homework. They compare candidates pairwise (A vs B), which is more reliable than absolute scores. | P1 |
| **Audition Board** | Local page to compare variants (sprites, turntable GIFs, playblasts, audio players), pick winners and leave notes; results land in `.opus/ratings` and are summarized into taste notes in the bible. | P1 |
| **Recipe memory** | Approved assets save their recipe + parameters to the project (or global) recipe book for reuse. | P2 |

## 5. Measuring progress — the eval suite

A fixed set of benchmark tasks, produced once **before** any tool exists (baseline) and
again after each phase. The user rates old-vs-new pairs blind on the Audition Board;
automated metrics and "iterations to acceptable" are tracked alongside. Only task specs and
scores live in the repo; outputs stay on the PC.

| Domain | Benchmark tasks | Automated metrics |
|---|---|---|
| 3D | Stylized wooden barrel · sci-fi crate with panel lines · low-poly pine trees ×3 variants · modular medieval house kit (wall, door, window, corner, roof) · HD treasure chest with PBR textures · stylized goblin character, rig-ready | Mesh Lint pass rate, tri budget adherence, silhouette IoU vs reference |
| Pixel art | Hi-res hero sprite (side view) with idle and walk cycle · 16-icon item set (potions, weapons, gems) · grass/dirt/stone terrain tileset that autotiles in Godot · 3-layer parallax forest background · 8-direction top-down character rendered from a 3D model · HD-2D test scene (pixel character in a low-poly 3D room) | Palette adherence, orphan/jaggy counts, pixel-grid consistency, tile seam error, frame-to-frame consistency |
| Animation | Treasure chest opening · goblin idle/walk/run · sword attack with anticipation and follow-through · quadruped walk cycle · door slam with secondary wobble · in-game third-person locomotion with blend space and foot IK on a slope | Foot slide (cm), ground penetration, pops, loop-seam error |
| Sound | UI set (hover, click, confirm, cancel, error) · sword swing + metal hit ×6 variations · footsteps on grass/stone/wood ×4 each · medium explosion · 30 s seamless rain loop · 60 s menu music loop | Loudness deviation from target, clipping/clicks, loop-seam error, variation spread |

## 6. Third-party building blocks

Snapshot as of October 2026, checked against repos, license files and official docs. This
field moves monthly, so re-verify before building on any of it.

Licensing for these games: they're personal and never sold, so non-commercial (NC)
licenses are fine. Three things are still flagged: **research-only** licenses (strictly,
they don't cover making a game, even a free one), **Tencent's territory exclusion** (its
models can't be used in the EU, UK or South Korea), and anything that would need replacing
if a game ever went public. The Provenance Ledger tracks all three.

_Being revised for the 16 GB GPU and the relaxed licensing; pixel-art tools are being
researched._

### 6.1 3D

| Need | Recommended | Notes and licenses |
|---|---|---|
| Live Blender control | The Blender MCP already on the PC. The official **Blender Lab MCP** (v1.0.3, GPL-3.0, needs Blender 5.1+) is the reference choice. | Don't run the community `mcp-for-blender` alongside it: both use port 9876, and the community one has telemetry on by default. |
| Blender version | **5.2 LTS** (supported until Jul 2028) | Scripts must follow the 5.x API: `use_nodes` is deprecated, the EEVEE engine id is `BLENDER_EEVEE`, and 5.2 moved Geometry Nodes modifier inputs to `mod.properties.inputs`. |
| Retopology | QuadriFlow (built in) → Instant Meshes (permissive, batch CLI, Windows binaries) → QRemeshify (GPL-3 Blender extension, cleanest quads) | Machine-learning retopology is still research-grade. |
| CC0 models and textures | Poly Haven (free API), ambientCG (API v3), Kenney, Quaternius and KayKit (bulk downloads), Poly Pizza (needs an API key) | All CC0 except Poly Pizza, which mixes CC0 and CC-BY, so the ledger stores attribution per model. The Poly Haven API requires a unique User-Agent. |
| Image-to-3D, local | **TripoSG** (MIT, ~8 GB, untextured; our bake pipeline adds textures); **TRELLIS.2** (MIT, PBR output, 24 GB at full size); Hunyuan3D 2.x (shape from 6–10 GB). The Modly desktop app runs several of these on Windows. | TRELLIS's GLB export uses nvdiffrast, which is research-only. Hunyuan3D carries Tencent's territory exclusion. SAM 3D needs 32 GB and Linux and outputs splats. |
| Image-to-3D, paid | **Meshy**: API from $20/mo; smart topology (100–15k faces), quads, PBR, rigging. **Tripo**: face limits, quad and low-poly modes, auto-rig with Mixamo bone names, official Godot plugin. **Rodin Gen-2.5**: quads, PBR; API needs the $120/mo plan. | Meshy's free-plan output is CC BY 4.0. |

### 6.2 Pixel art

_Research in progress._

### 6.3 Animation

| Need | Recommended | Notes and licenses |
|---|---|---|
| Motion libraries | **Quaternius Universal Animation Library 1 and 2** (CC0; free editions ~45 clips each, paid editions 120–130+), **Kenney** (CC0), **CMU mocap** (free to use; the data itself can't be resold), **100STYLE** (CC BY 4.0), **Bandai Namco** motion datasets (CC BY-NC), Mixamo (free in games, manual download only) | **BONES-SEED** has 142k mocap clips, free with attribution for anyone under $1M annual revenue. LAFAN1 is CC BY-NC-ND (no adapted versions may be shared). |
| Godot animation | Target **Godot 4.7**: BoneMap + `SkeletonProfileHumanoid` retargeting; AnimationTree; root motion; the `SkeletonModifier3D` family — `LookAtModifier3D` and `SpringBoneSimulator3D` (4.4), aim/copy constraints (4.5), the IK family `TwoBoneIK3D` / `FABRIK3D` / `CCDIK3D` / … with joint limits (4.6); `PhysicalBoneSimulator3D` ragdolls | Every runtime procedural layer in the plan is built into the engine; no plugins needed. |
| Blender animation API | Slotted Actions (since 4.4); `action.fcurves` was removed in 5.0 | Keyframe Director writes through channelbags. Many older scripts and add-ons break on 5.x. |
| Rigging and retargeting | Our own game-rig templates (deform bones in one hierarchy, Godot humanoid names); **GameRig** (GPL-2.0) to make Rigify rigs game-ready; **Retarget** extension (GPL-3.0, maintained Expy Kit fork, Blender 5.0+); Robust Weight Transfer (GPL-3.0); Auto-Rig Pro (paid; has Godot humanoid naming) | Rigify alone doesn't export the clean deform hierarchy Godot needs. The Rokoko add-on likely breaks on Blender 5.x and requires a sign-in. |
| Auto-rig models | **UniRig** (MIT, ≥8 GB), **SkinTokens** (MIT, ≥14 GB; UniRig's successor), **Puppeteer** (Apache-2.0; skeleton, skinning and video-guided animation) | RigAnything is non-commercial. |
| Text-to-motion | **NVIDIA Kimodo-SOMA** (clips up to 10 s; text plus pose and path constraints; BVH export; under 3 GB VRAM with the text encoder on CPU; Linux-first, Windows via Docker) | Needs the gated Llama 3 8B text encoder. Its model card admits foot skating, which our foot-lock cleanup targets. HY-Motion needs 24 GB+ and carries Tencent's territory exclusion. |
| Video-to-motion | **SAM 3D Body** (outputs Meta's Apache-2.0 MHR body model, no SMPL) + SAM-Body4D (MIT) for video; FreeMoCap (AGPL, multi-webcam); QuickMagic (paid) | Pipelines that need SMPL/SMPL-X model files (GVHMR, WHAM, PromptHMR) depend on those licenses' terms. |

### 6.4 Sound

| Need | Recommended | Notes and licenses |
|---|---|---|
| Analysis and processing | librosa (ISC), pyloudnorm (MIT), numpy/scipy; **pedalboard** or **DawDreamer** (both GPL-3) for effects, VST3 hosting and MIDI rendering | The GPL covers the tools, not the audio they render. |
| Synths and instruments | Surge XT (GPL-3) and Vital (via the Vita Python bindings) hosted headlessly; **VSCO-2-CE** and **VCSL** (CC0 sample libraries); GeneralUser GS (SF2) rendered with FluidSynth | Vital's factory presets can't be redistributed, so we ship our own presets. |
| Sound libraries | **Sonniss GDC bundles** (royalty-free, no attribution; 2026 bundle is 7.5 GB), **Kenney** audio (CC0), **Freesound** (its API is free for non-commercial use like this; CC0, CC-BY and CC-BY-NC sounds are all fine here) | Sonniss license v2.0 bans using its sounds to develop, train or enhance AI, so they never go into generative models. Pixabay bans bulk downloads, so it can't be indexed. |
| Reverb impulse responses | Voxengo, EchoThief, OpenAIR (Creative Commons license per recording) | Real spaces for convolution reverb. |
| Critique models ("ears") | LAION-CLAP (CC0) or MS-CLAP (MIT) for text–audio match; **Meta Audiobox Aesthetics** (CC-BY-4.0) for production-quality scores; **MiDashengLM-7B** (Apache-2.0) to describe sounds in words | The Qwen3-Omni captioner is ~60 GB, too big for 16 GB. |
| SFX generation, local | **Stable Audio 3 Small-SFX** (~2 GB VRAM, up to 2 min, 44.1 kHz stereo; free under $1M revenue, registration required); **MOSS-SoundEffect v2** (Apache-2.0, 48 kHz, up to 30 s) | Non-commercial alternatives (MMAudio, Woosh, AudioX) are now allowed; to be compared. TangoFlux is research-only. |
| Music generation, local | **ACE-Step 1.5** (MIT, 4–20 GB VRAM, Windows package); Magenta RealTime (instrumental, CC-BY-4.0 weights) | No local model produces seamless loops, so Music Studio loops them with DSP. |
| Voice (TTS) | **Qwen3-TTS** (Apache-2.0: design a voice from a text description, emotion instructions, cloning from 3 s); Chatterbox (MIT, watermarked), Dia (Apache-2.0, English only), Kokoro (Apache-2.0, no emotion control) | |
| Paid APIs | ElevenLabs Sound Effects (up to 30 s, loop option, from the $6 plan) | |
| Godot audio | Target **Godot 4.7** | `AudioStreamRandomizer` (pitch in semitones since 4.6); `AudioStreamInteractive` / `AudioStreamPlaylist` / `AudioStreamSynchronized` since 4.3, with beat- and bar-synced transitions; WAV and Ogg loop settings at import. |

## 7. Roadmap

Ordered by the user's priorities (3D and pixel art first, then animation, then sound) and
by dependency (checking tools before making tools, since every making tool is tested with
them).

| Phase | Builds | Exit criteria |
|---|---|---|
| **0 · Foundation** | Plugin skeleton + desktop-app packaging, hook-up to the existing Blender and Godot MCPs, Project Bible, Provenance Ledger, downloads manifest + `opus doctor`, eval baseline. | From any project, Claude runs our in-Blender code through the Blender MCP, captures a frame from Godot, and reads the bible. Baseline outputs for the 3D and pixel-art eval tasks recorded. |
| **1 · See it** (3D + pixel art) | Look Dev Sheet, Mesh Lint, Sprite Inspector, Pixel Cleanup, Palette Lab, Audition Board, critic subagents. | Every 3D and pixel asset is checked with images and numbers before the user sees it. |
| **2 · Make it** (3D + pixel art) | Shape Kit, Material Lab + Bake, Asset Librarian, Godot Import Pipeline, Gen3D + Cleanup, Gen Texture, Godot Look Presets · 3D → Pixel Renderer, Tileset Builder, Godot Pixel Setup, AI Pixel Pipeline, Pixel Forge. | Blind-rated improvement on the 3D and pixel-art eval tasks. |
| **3 · Animation** | Motion Inspector, Motion Library + Retargeter, Godot Animation Wiring + game feel, Rig Doctor, Sprite Animator, Keyframe Director, Animation Events, mocap from video/text. | Animation eval tasks pass the motion checks, with a blind-rated improvement. |
| **4 · Sound** | Audio Inspector, SFX Library + Sound Forge, Godot Audio Packager, Gen Audio, Synth recipes. | Sound eval tasks pass loudness and loop checks, with a blind-rated improvement. |
| **5 · Depth** | Music Studio, Mix Check, Lip Sync, Sim Bake, Blueprint & Match, Lineup Render, recipe memory, Pixel Editor Bridge. | — |

## 8. Honest limits

- **Claude will never hear.** Spectrograms, metrics and ML listeners catch technical faults
  and gross mismatches; the final taste call on audio stays with the user. The Audition
  Board makes that a 30-second job.
- **Organic sculpting purely in code stays limited.** For HD characters and creatures the
  realistic paths are library bases + kitbashing, image-to-3D + cleanup, or a quick user
  blockout with Claude doing the technical pipeline. Hard-surface props, architecture,
  environments and low-poly are where procedural code gets genuinely good.
- **Hi-res pixel characters are hard to draw in code.** The realistic routes are 3D → pixel
  renders, AI generation + cleanup, or the user's sketches cleaned up by the pipeline.
  Procedural code is genuinely good for icons, UI, tiles and props.
- **Hand-keyed human locomotion won't match mocap.** Humans → library or mocap + retarget +
  in-engine procedural layers. Creatures, props, machines and cartoony actions → Keyframe
  Director.
- **Generative models** vary in quality and are capped by 16 GB of VRAM. Some licenses are
  research-only or region-restricted. They're optional backends, never the foundation.
- **Disk:** asset, sound and model downloads add up quickly; the manifest marks each one
  optional or recommended, with its size, so the ~100 GB budget is spent deliberately.

## 9. Open questions

1. Which MCP servers are connected for Blender and Godot (names or links)? Blender has an
   official one from Blender Lab and a popular community one; Godot has several community
   ones.
2. In the desktop app, do you work in regular chat or the Code tab? The Code tab gives
   Claude file access, a terminal and subagents, which most of these tools assume. Chat
   works too if every tool ships as a desktop extension.
3. What does "hi-res" pixel art mean for you: roughly how tall are characters (32, 64,
   128 px?), and are there games whose look you're aiming for?
4. Do you use a pixel editor (Aseprite, Pixelorama, LibreSprite, …)?
5. If you or your friends are in the EU, UK or South Korea, Tencent's models (Hunyuan3D,
   HY-Motion) are off the table. Let me know if that applies.
