# Opus Tools — Game Plan

**Mission:** give Claude the senses, building blocks, raw material and quality gates it
needs to produce good **3D models**, **pixel art**, **animation** and **sound** for
games made with Blender and Unreal, Godot or Unity, packaged as one small install on the
game-dev PC that works in every project.

Status: plan v0.6 (2026-10-21). **v0.4.1 of the toolkit is built:** the Phase 0 core, the
Phase 1 "see it" tools for pixel art and 3D, Sprint 2's proportion and recognizability
tools, hands that hold things properly, the overhaul's S0a quick wins, and the fixes from
the v0.4 baseline, which ran in the cloud on the 24 eval tasks (see §7). The PC checks are
still to run.

**3D models and animation now follow [docs/OVERHAUL.md](docs/OVERHAUL.md)** (design v1.1,
from 9 research digests, 4 competing proposals and 6 reviews). It replaces every 3D and
animation section of this plan; those sections stay below for history, with the
generative-model routes removed. Pixel art and sound still follow this plan.

---

## 0. The setup this plan targets

| | |
|---|---|
| **PC** | Windows 10 · RTX 4070 Ti Super (16 GB VRAM) · 64 GB RAM · ~100 GB free disk |
| **Apps** | Blender 5.2 · Unreal (preferred engine) · Godot 4.7.2 · Unity, all with MCP servers connected to the Claude desktop app. The engine is picked per project. |
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
3. **Start from real material.** Human-made libraries, real recordings, mocap, measured
   data and the user's references are inputs. Generative models are excluded for 3D and
   animation (their published methods and data statistics may be used). Claude's job
   shifts toward structuring, selecting, kitbashing, processing and integrating, which it
   is good at.
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
8. **Stable interfaces sized to the PC.** Native packages and GPU accelerators sit behind
   optional extras with numpy fallbacks, so the core stays useful with no GPU at all.
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
 │  sources: asset/SFX/motion librarians · measured data tables · provenance ledger │
 └───────┬────────────────────────┬─────────────────────────┬───────────────────────┘
         │                        │                         │
  Blender 5.2 (your Blender  Godot 4.7 (your Godot    Optional local AI backends
  MCP, or headless `-b`)     MCP, headless import,    (2D image and audio only;
                             frame capture)           none for 3D or animation)
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

Repo layout (code only; items marked * are planned):

```
Opus-Tools/
├── .claude-plugin/marketplace.json
├── plugins/
│   ├── opus-tools/                  # main plugin: works on any PC, no GPU needed
│   │   ├── .claude-plugin/plugin.json   # userConfig: Blender/Godot paths, library dir
│   │   ├── .mcp.json                # the `opus` MCP server, run with uv
│   │   ├── skills/                  # pixel-art, 3d-modeling, project-bible (+ more later)
│   │   ├── agents/                  # art-director critic (+ animation/audio later)
│   │   ├── python/                  # opus core package, CLI, MCP server, tests
│   │   ├── blender/opus_bl/         # in-Blender modules (bpy + bmesh + numpy only)
│   │   └── godot/addons/opus/ *     # copied into a game by `opus godot init`
│   └── opus-gen/ *                  # optional plugin: 2D image and audio backends only
├── extensions/ *                    # .mcpb manifests for chat mode (bundles built by CI)
├── evals/ *                         # benchmark task specs and scores (no big files)
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
| **Engine Bridge** (was Godot Bridge; Unreal adapter first since v0.4) | Uses the engine MCPs already on the PC for editor control. For Godot: Adds the parts it probably lacks: headless `--import`, `.import` option writers, scene inspection, and deterministic frame capture (Movie Maker mode) for in-engine checks. | P0 |
| **Project Bible** | `opus.project.yaml`: art style, palette, pixel scale, shape language, reference board, tri/texture/bone budgets, texel density, loudness targets, animation fps and "feel", naming rules. Created by a short interview skill; read by every tool. | P0 |
| **Provenance Ledger** | Sidecar record per asset (source, license, author, generator + model version); generates `CREDITS.md`; flags anything that would block a public release. | P0 |
| **Downloads manifest** | `DOWNLOADS.md` lists every large optional download (model weights, asset and sound libraries, apps) with purpose, size, license, link and target folder. `opus doctor` checks what's installed and what's missing. | P0 |
| **Installer + `opus doctor`** | Windows setup (uv environment, plugin and extension install, Godot add-on) and a health check of every integration. | P0 |
| **Eval suite** | Fixed benchmark tasks per domain, produced before and after each tool and rated blind. Tells us which tools actually improve quality. | P0 |

### 4.1 3D models

*Superseded by [docs/OVERHAUL.md](docs/OVERHAUL.md); kept for history.*

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Look Dev Sheet** | can't see it | One call → labeled contact sheet: front/side/back/top + ¾ perspective; clay/matcap (form); wireframe (topology density); solid silhouette (shape readability); face orientation (flipped normals); UV checker; 1.8 m human silhouette + 1 m grid for scale. Optional side-by-side with a reference, and a **gameplay-distance view** at the on-screen size the asset will really have in each camera style. Laid out to fit Claude's image-input resolution. | P1 |
| **Mesh Lint** | not game-ready | Non-manifold/loose geometry, flipped normals, zero-area faces, n-gons on deforming meshes, unapplied transforms, origin placement, intersecting/floating parts, tri budget, UV presence/overlap/bounds, texel-density consistency, material count, texture sizes, naming. JSON + heatmap render + safe auto-fixes. | P1 |
| **Shape Kit** | primitive soup | Python modeling library of semantic, parameterized builders: beveled primitives, lathe from profiles, sweep/loft/pipe along curves, inset/extrude/panel lines, booleans with cleanup + weighted normals, mirror/array/radial, taper/bend/twist/lattice, organic blobs (skin modifier/metaballs/SDF → remesh), scatter, grid-snapped modular kits, and generators (rocks, trees, crates, barrels, buildings, furniture, weapons). Every asset is a recipe function + params + seed → instant variations. Style presets: low-poly flat, stylized, PBR-realistic, PS1-retro, voxel. | P1 |
| **Material Lab + Bake** | flat colors; procedural materials lost on export | Procedural material graphs (wood, metal, stone, fabric, plastic, toon) with curvature/AO-driven wear and grime; one-call **bake to Godot-ready PBR** (albedo, ORM, normal) at the bible's texel density; high→low normal/AO bakes; palette-atlas workflow for low-poly; trim sheets; Godot material setup (StandardMaterial3D or toon shader). | P1 |
| **Asset Librarian** | starting from nothing | Indexes CC0 packs downloaded per the manifest; renders thumbnails; text + image search via embeddings; returns a candidate contact sheet; imports with provenance; kitbash parts out of library meshes. | P1 |
| **Godot Import Pipeline** | export traps | glTF export presets; Godot import hints (`-col`, `-convcolonly`, `-navmesh`, `-loop`, …); writes `.import` options (LODs, shadow meshes, collision, materials); post-import scripts; then an in-engine capture in the game's own lighting. | P1 |
| **Godot Look Presets** | assets look flat in-engine | WorldEnvironment, light rig, tonemapping, SSAO/SSIL, glow and fog presets per art style; used by every in-engine capture, so assets are judged under the light they ship in. | P2 |
| **Blueprint & Match** | wrong proportions | Reference images or the user's sketches behind orthographic cameras; silhouette-overlap score (IoU) per view between render and reference. | P2 |
| **Lineup Render** | style drift | Renders the new asset next to already-approved assets at the same scale and lighting to catch scale, style and detail-density mismatches. | P3 |

### 4.1b 3D upgrades after testing v0.1

*Superseded by [docs/OVERHAUL.md](docs/OVERHAUL.md); kept for history.*

v0.1's Look Dev Sheet is a fixed set of views, and Shape Kit doesn't exist yet. These
additions target the two remaining gaps: *understanding* (Claude can't look closer, can't
tell which part is which, and judges depth and distance by eye) and *generation* (numbers
placed by hand, nothing for organic or HD shapes).

| Tool | Gap | What it does | Pri |
|---|---|---|---|
| **Look At** | fixed views | Render any part from any angle or distance on request (orbit, zoom, close-up of a named object), in the same lighting, so a doubt gets checked instead of guessed. | P1 |
| **Part Map** | can't tell parts apart | ID pass that paints each object or part a distinct color, with a legend of names, sizes and tri counts, linking the image to the scene graph. | P1 |
| **Dimensions & Measure** | distance by eye | Orthographic views with technical-drawing dimension lines, plus a measure tool for distances, clearances, angles and raycasts ("seat height?", "does a 1.8 m character fit through the door?"). | P1 |
| **Structure Report** | 3D read from 2D pictures | Text description of the model: part tree, a primitive fitted to each part (box, cylinder, sphere, capsule) with its fit error, which parts touch where, mirror-symmetry deviation, and center of mass vs footprint (will it tip?). Claude reasons best in text and numbers. | P1 |
| **Cross-sections** | hidden insides | Slice outlines at several heights and planes, like a CT scan: profiles, wall thickness, hollow interiors, buried geometry. | P2 |
| **Surface maps** | can't see edge quality | Curvature (are edges beveled?), thickness (paper-thin walls?) and depth renders. | P2 |
| **Iteration Diff** | "what changed?" | Previous and current version side by side, with changed regions highlighted. | P2 |
| **Shape Kit with sockets** | numbers placed by hand | Parts attach to named sockets ("handle on body.side at 60% height") instead of coordinates, so pieces can't float. Mirroring and default bevels are built in. | P1 |
| **Fit to Reference** | proportions guessed | Claude writes the structure as a parametric recipe; an optimizer tunes its numbers until the front and side silhouettes match the reference (IoU). Claude is good at structure, worse at exact numbers. | P1 |

**Feedback from using v0.1 (drives Sprint 2).** Proportions of HD humanoids, creatures
and dragons were often wrong, which meant guessing and re-guessing. Blocky models came
out better but generic: not very artistic, and not always recognizable as what they were
meant to be. Two causes: proportions were invented each time instead of taken from a
canon, and nothing tested whether the result *reads*. Sprint 2 (built, v0.2) answers both:

| Tool | What it does | Status |
|---|---|---|
| **Body Blockout** | Rigged, watertight starting bodies from proportion canons: humanoid realistic (7.5 heads), heroic (8), stylized (6), chibi (3); quadruped dog, horse, cat; western dragon with folding wings. Joints come from data, primitives are fused by voxel remesh, and the rig uses Unreal mannequin bone names. Reports landmark heights and limb lengths in meters to model to. | built |
| **Proportion Check** | Builds the canon bodies at the model's height and overlays silhouettes front and side (red = sticks out, blue = missing). Humanoids get landmark ratios (leg length, heads tall, shoulders, waist, hips) and limb bone ratios when rigged. `auto` says which canon the model actually resembles. | built |
| **Reference Match** | Silhouette IoU and per-height-band width differences against a concept or reference image, with background removal and automatic mirroring. This is the measuring half of Blueprint & Match and Fit to Reference. | built |
| **Look At** | Any angle, distance and render pass, framed on an object, collection or bone region (`hand_l`), with a focus pass that highlights it. | built |
| **Part Map + Structure Report** | Labeled part map (objects, or bone regions of a skinned body), and per part: size, shape class, long axis, bone length and girth; contacts and floating gaps; mirror symmetry; center of mass vs footprint; rig naming style. | built |
| **Blind Read** | Unlabeled silhouettes and clay views under a neutral file name, plus a prompt for a fresh reviewer subagent that must identify the model without being told what it is. | built |
| **Feature brief** (workflow) | The 3d-modeling skill now starts every model with 5–7 defining features, a proportion intent and a shape language, and ends with the blind read. | built |

**Unreal, Godot and Unity (all available with MCPs; Unreal preferred).** Blender stays the
modeling hub, since FBX and glTF go to every engine. The engines add eyes and ecosystems:

- **Engine Bridge, Unreal first.** One contract (import with correct settings, capture
  in-engine frames, report errors) with an Unreal adapter first, then Godot and Unity, so
  games in any of the three get the same checks. Blockout rigs already use Unreal
  mannequin names, so they retarget to UE animations.
- **Unreal** (Epic's in-editor Unreal MCP plugin, or community servers using Python remote
  execution):
  - Lumen "beauty" renders for HD assets.
  - Geometry Script from Python for simplify, UVs and bakes (AO, curvature, normals, and
    baking from render captures), as a second cleanup path.
  - MetaHuman: licence for use outside Unreal unverified, so not used.
- **Unity** (official Unity MCP in the AI Assistant package, open beta): ProBuilder for
  quick blockouts, and the Asset Store.

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

*Superseded by [docs/OVERHAUL.md](docs/OVERHAUL.md) §5; kept for history.*

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Motion Inspector** ("eyes for motion") | can't watch it | Frame contact sheet from two cameras with onion skins and motion trails (hands, feet, head, root); curve plots (root height, foot heights/speeds, key joint angles); GIF/MP4 for the user. Diagnostics: **foot sliding**, ground penetration, joint-limit violations and knee flips, self-intersection, pops (velocity/jerk spikes), loop-seam continuity (pose and velocity), balance (center of mass vs support), arc smoothness, key-spacing chart. | P1 |
| **Motion Library + Retargeter** | hand-keyed humans | Indexes motion sets downloaded per the manifest (CC0 libraries, CMU mocap, Mixamo clips, …); text search with preview strips; retargets onto the project's rigs using bundled bone maps for common skeletons (Mixamo, UE5 Mannequin, Rigify, SOMA); clip tools: trim, loop-fix (blend tail into head), speed, in-place ↔ root motion, mirror, additive layers. | P1 |
| **Godot Animation Wiring** | clips that feel bad in-game | Builds `AnimationTree` state machines and blend spaces from a spec (locomotion by velocity, one-shots, crossfades, root motion); runtime procedural layers built from Godot's own skeleton modifiers: foot IK on slopes, look-at, spring bones (hair, tails, capes), lean into turns, partial-ragdoll hit reactions; **game-feel library** (easing presets, squash/stretch on landing, hit-stop, camera shake). Often the biggest perceived quality gain per hour of work. | P1 |
| **Rig Doctor** | broken deformation | Game-ready rig templates (deform bones in one clean hierarchy, names matching Godot's `SkeletonProfileHumanoid` so Godot's retargeting just works) plus quadruped/bird/tail/tentacle/mechanical templates; auto-rig + automatic weights + weight transfer; **deformation test**: extreme poses (arms up, squat, twist) rendered as a contact sheet, with candy-wrap and volume-loss flags; weight lint (≤4 influences, normalized, unweighted verts, symmetry). | P1 |
| **Keyframe Director** | linear, weightless motion | Animation DSL: Claude authors semantic poses, IK targets and timing ("anticipate 4f, strike 2f, overshoot 15 %, settle 6f"), and the 12 principles are automatic passes: slow-in/out, anticipation, overshoot/settle, follow-through and overlap down bone chains, arcs, baked secondary motion, squash & stretch. Procedural cycle generators (walk/run/sneak/idle/fly/swim) with planted-foot IK and stride/bounce/weight/mood parameters. Best for creatures, props, machines, doors, chests and UI. | P2 |
| **Animation Events** | SFX/VFX out of sync | Uses Motion Inspector analysis to place method/audio tracks automatically: footsteps at foot contacts, whooshes at weapon peak velocity, impacts at contact frames; attack frame data (startup/active/recovery). | P2 |
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

**Generative models: none for 3D or animation.** The user's rule excludes them; their
published methods and data statistics may still be used (see docs/OVERHAUL.md). The 2D
image and audio models below are untouched until the user decides on them. If they stay,
`opus-gen` drives one ComfyUI install (it runs on Windows, streams large weights to fit
16 GB, and has a plain HTTP API) and every output passes the same inspectors as
hand-made assets.

"Fits 16 GB" below refers to the RTX 4070 Ti Super.

### 6.1 3D

| Need | Recommended | Notes and licenses |
|---|---|---|
| Live Blender control | The Blender MCP already on the PC; Opus's own Blender work runs headless and doesn't depend on which one. The official **Blender Lab MCP** (v1.0.3, GPL-3.0, needs Blender 5.1+) is the reference choice. | Don't run the community `mcp-for-blender` alongside it: both use port 9876, and the community one has telemetry on by default. |
| Blender version | **5.2 LTS** (supported until Jul 2028) | Scripts must follow the 5.x API: `use_nodes` is deprecated, the EEVEE engine id is `BLENDER_EEVEE`, and 5.2 moved Geometry Nodes modifier inputs to `mod.properties.inputs`. |
| Retopology | QuadriFlow (built in) → Instant Meshes (permissive, batch CLI, Windows binaries) → QRemeshify (GPL-3 Blender extension, cleanest quads) | Machine-learning retopology is still research-grade. |
| Human-made models and textures | Poly Haven (free API), ambientCG (API v3), Kenney, KayKit and Quaternius (bulk downloads), Poly Pizza (needs an API key) | Poly Haven, ambientCG and Kenney are CC0. KayKit and Quaternius licences are recorded per pack from a snapshot of the page at download time (Quaternius uses QAL v1.0, not CC0). Poly Pizza mixes CC0 and CC-BY, so the ledger stores attribution per model. The Poly Haven API requires a unique User-Agent and a credit line. |

### 6.2 Pixel art

| Need | Recommended | Notes and licenses |
|---|---|---|
| Local image models | **Z-Image-Turbo** (6B, Apache-2.0, fits 16 GB, 8 steps) or **FLUX.2 [klein] 4B** (Apache-2.0, ~13 GB, multi-reference editing for keeping characters on-model), each with a pixel-art LoRA (Apache-2.0); run through ComfyUI | Every output still goes through Pixel Cleanup. FLUX.2 klein 9B is FLUX Non-Commercial (fine here, with output review). Qwen-Image-2.1 makes native transparent PNGs but is research-only and needs CPU offload. |
| Sprite-sheet LoRAs | 4-direction walk sheets (32×32) for klein-4B; walk/attack/hurt sheets (32×48) for Qwen-Image-Edit | Quality unverified; test in the eval suite before relying on them. |
| Paid pixel-art services | **PixelLab** ($5–50/mo; API + hosted MCP; 4/8-direction characters, animation, inpainting, Wang/side-scroller/isometric tiles, about $0.06 per 8-direction character). Retro Diffusion (prepaid API + MCP; its Pixel Fixer endpoint is free). | No independent benchmark of animation consistency exists; vendors' own docs say frames often need cleanup. PixelLab caps reference images at 256 px. |
| Fake → true pixel art | **Pixel Cleanup** (ours; tested against degraded sprites, see §7). Fallbacks: proper-pixel-art (MIT; video mode keeps one grid and palette across frames), unfake (MIT), Pixel Snapper (MIT CLI). | On our test set, proper-pixel-art with defaults got 5/54 exact versus 39/54 for ours, and it pulls in OpenCV + PyAV. Revisit its video mode for animation frames. |
| 3D → pixel sprites | Our renderer in headless Blender: orthographic N-direction cameras, EEVEE film filter 0, Shader-to-RGB → color-ramp toon shading, outlines, palette lock. Reference implementations: BlenderSpriteGenerator (MIT), Godot Pixel Renderer (MIT, GUI). | For real-time 3D pixel art in Godot: Godot-3d-pixelart-demo (MIT) outline shader in a low-res SubViewport; Godot 4.7 has nearest-neighbor 3D scaling. |
| Pixel editors | Aseprite ($20; CLI `--batch` + Lua; compiling from source is allowed for personal use) with **aseprite-mcp** (MIT, 104 tools); Pixelorama (MIT; CLI export only) | Only matters if you hand-edit; the Pixel Editor Bridge is a late phase. |
| Tilesets and autotiling | Godot TileSet terrains (47-tile blob for corners + sides, 16 tiles for corners-only or sides-only), peering bits set by a headless `godot --script`; **TileMapDual** (MIT, dual-grid, 15 tiles instead of 47); Better Terrain (public domain) | Tileset Builder generates tiles plus a ready TileSet resource. |
| Godot pixel setup | Stretch mode `viewport` + integer scaling + Nearest filter for pixel-perfect games, `canvas_items` for hi-res sprites with smooth motion; PixelPerfectSmoother (MIT) for camera jitter; Sprite3D with Nearest + alpha cut for HD-2D | Normal maps for 2D lighting: Laigter (GPL-3, CLI) into a CanvasTexture. |
| Palettes | Lospec `.hex` downloads (the `palette_apply` tool accepts `lospec:<slug>`); our `palette_ramp` for hue-shifted ramps | Lospec has no official API; `.hex` URLs work. |
| Sprite animation from AI | *Suspended pending the user's decision on 2D generative models.* Was: Wan 2.2 image-to-video + a pixel-animate LoRA, then Pixel Cleanup frame by frame | The 3D → pixel route is the most consistent for many directions. |

### 6.3 Animation

| Need | Recommended | Notes and licenses |
|---|---|---|
| Motion libraries | **Quaternius Universal Animation Library 1 and 2** (licence recorded per pack at download; free editions ~45 clips each), **Kenney** (CC0), **CMU mocap** (free to use; the data itself can't be resold), **100STYLE** (CC BY 4.0), **ACCAD** (CC BY 3.0), **Bandai Namco** motion datasets (CC BY-NC: retarget, edit and ship in a free game with attribution), Mixamo (manual, optional input only, under revocable preview terms) | BONES-SEED is skipped: eligibility for an individual is unclear. LAFAN1 is CC BY-NC-ND, so it is excluded. The full data plan is docs/OVERHAUL.md §7. |
| Godot animation | Target **Godot 4.7**: BoneMap + `SkeletonProfileHumanoid` retargeting; AnimationTree; root motion; the `SkeletonModifier3D` family — `LookAtModifier3D` and `SpringBoneSimulator3D` (4.4), aim/copy constraints (4.5), the IK family `TwoBoneIK3D` / `FABRIK3D` / `CCDIK3D` / … with joint limits (4.6); `PhysicalBoneSimulator3D` ragdolls | Every runtime procedural layer in the plan is built into the engine; no plugins needed. |
| Blender animation API | Slotted Actions (since 4.4); `action.fcurves` was removed in 5.0 | Keyframe Director writes through channelbags. Many older scripts and add-ons break on 5.x. |
| Rigging and retargeting | Our own game-rig templates (deform bones in one hierarchy, Godot humanoid names); **GameRig** (GPL-2.0) to make Rigify rigs game-ready; **Retarget** extension (GPL-3.0, maintained Expy Kit fork, Blender 5.0+); Robust Weight Transfer (GPL-3.0); Auto-Rig Pro (paid; has Godot humanoid naming) | Rigify alone doesn't export the clean deform hierarchy Godot needs. The Rokoko add-on likely breaks on Blender 5.x and requires a sign-in. |

### 6.4 Sound

| Need | Recommended | Notes and licenses |
|---|---|---|
| Analysis and processing | librosa (ISC), pyloudnorm (MIT), numpy/scipy; **pedalboard** or **DawDreamer** (both GPL-3) for effects, VST3 hosting and MIDI rendering | The GPL covers the tools, not the audio they render. |
| Synths and instruments | Surge XT (GPL-3) and Vital (via the Vita Python bindings) hosted headlessly; **VSCO-2-CE** and **VCSL** (CC0 sample libraries); GeneralUser GS (SF2) rendered with FluidSynth | Vital's factory presets can't be redistributed, so we ship our own presets. |
| Sound libraries | **Sonniss GDC bundles** (royalty-free, no attribution; 2026 bundle is 7.5 GB), **Kenney** audio (CC0), **Freesound** (its API is free for non-commercial use like this; CC0, CC-BY and CC-BY-NC sounds are all fine here) | Sonniss license v2.0 bans using its sounds to develop, train or enhance AI, so they never go into generative models. Pixabay bans bulk downloads, so it can't be indexed. |
| Reverb impulse responses | Voxengo, EchoThief, OpenAIR (Creative Commons license per recording) | Real spaces for convolution reverb. |
| Critique models ("ears") | LAION-CLAP (CC0) or MS-CLAP (MIT) for text–audio match; **Meta Audiobox Aesthetics** (CC-BY-4.0) for production-quality scores; **MiDashengLM-7B** (Apache-2.0, 8-bit to fit) to describe sounds in words | Audio Flamingo 3 / AF-Next caption slightly better but are research-only and need 4–8-bit quantization. These benchmarks test recognizing sounds, not judging sound design. The Qwen3-Omni captioner is ~60 GB. |
| SFX generation, local | **Stable Audio 3 Medium** (≤6.5 GB; best listener scores for SFX in the only head-to-head, which Stability ran itself; native in ComfyUI); Stable Audio 3 Small-SFX (~2 GB) for quick drafts; **Woosh** (Sony, CC-BY-NC, rated above Small-SFX) as the runner-up; MOSS-SoundEffect v2 (Apache-2.0) | MMAudio (CC-BY-NC) is only worth it for syncing sound to video. TangoFlux is research-only and scored lowest. |
| Music generation, local | **ACE-Step 1.5** (MIT, Windows portable build, native in ComfyUI; on 16 GB use the 2B turbo model with the 0.6–1.7B language model); Magenta RealTime (instrumental, CC-BY-4.0 weights) | No local model produces seamless loops, so Music Studio loops them with DSP. YuE2 needs 24 GB; MusicGen is older. |
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
| **2 · Make it** (3D + pixel art) | 3D: see docs/OVERHAUL.md §9 (sprints S0a–S11). Pixel art: 3D → Pixel Renderer, Tileset Builder, Godot Pixel Setup, AI Pixel Pipeline (pending the 2D decision), Pixel Forge. | Blind-rated improvement on the 3D and pixel-art eval tasks. |
| **3 · Animation** | See docs/OVERHAUL.md §5 and §9. Sprite Animator stays here. | Animation eval tasks pass the motion checks, with a blind-rated improvement. |
| **4 · Sound** | Audio Inspector, SFX Library + Sound Forge, Godot Audio Packager, Gen Audio, Synth recipes. | Sound eval tasks pass loudness and loop checks, with a blind-rated improvement. |
| **5 · Depth** | Music Studio, Mix Check, Lip Sync, Sim Bake, Blueprint & Match, Lineup Render, recipe memory, Pixel Editor Bridge. | — |

### Progress

**v0.1: built and tested in the cloud (2026-10-07)**

- **Phase 0 core.** Plugin + marketplace (pass `claude plugin validate`); `userConfig` for
  Blender and Godot paths; the `opus` MCP server launched by uv from a lockfile (checked
  with the exact plugin launch command); project bible; provenance ledger + CREDITS.md;
  `opus doctor`; downloads manifest.
- **Phase 1, pixel art.**
  - Sprite Inspector.
  - Pixel Cleanup. On 54 deliberately degraded test sprites (non-integer upscales, blur,
    noise, JPEG, opaque backgrounds) it recovers 39 exactly. That includes every typical
    AI-art case (cells of 5.5–16 px, mild blur). Heavily blurred tiny cells safely report
    "no grid", and clean native art is never touched.
  - Palette Lab: ramps, apply (including `lospec:` palettes), swap.
- **Phase 1, 3D.** Look Dev Sheet: 14 renders in about 2–3 s with Workbench, including face orientation from front and back; EEVEE and
  Cycles are optional. Mesh Lint caught every planted defect in its test asset.
- **Skills and agents.** `pixel-art`, `3d-modeling` and `project-bible` skills, plus the
  `art-director` reviewer subagent.
- **Tests.** 36 tests covering:
  - pixel tools on synthetic sprites, including degraded "AI-style" ones;
  - Blender 5.2 integration;
  - the MCP server end to end over stdio.

**Not done yet:**

- Godot-side pieces: headless import and frame capture. This environment can't download
  Godot, so they need testing on the PC.
- The Audition Board.
- The eval baseline run.
- `.mcpb` desktop extensions for chat mode.
- Install testing on the real Windows PC.

**v0.2 (Sprint 2): proportions and recognizability (2026-10-16)**

- Body Blockout, Proportion Check, Reference Match, Look At, Part Map + Structure Report
  (`model_report`) and Blind Read, as MCP tools and `opus` CLI commands (see §4.1b).
- All eight blockout presets bind with heat weights; posing a bone moves only its side,
  and dragon wings fold with their finger bones.
- Proportion Check finds the right canon for each preset (silhouette IoU 0.98–1.0) and
  flags a deliberately distorted body: legs 15% short, head too big, about 5.6 heads tall
  instead of 7.5. Reference Match recovers a mirrored side view (IoU 0.97).
- The `3d-modeling` skill now runs a canon-first workflow with a feature brief and blind
  read, plus per-engine export notes (Unreal first). The `art-director` agent has a blind
  read mode.
- 61 tests (Blender integration included).

**v0.3: hands that hold things (2026-10-17)**

Feedback: in first-person work, held objects sat inside the palm or floated beside it.

- Blockout humans now have hands: palm, thumb ball and 15 finger bones per hand (Unreal
  names), meshed at finger resolution and skinned so no finger drags its neighbor.
- `grip_define` marks a grip on an object (handle axis fitted to a part, palm side, thumb
  end, trigger point; pistol-style grips get their palm side from the barrel axis and the
  hand). Saved as a `SOCKET_grip_*` empty, which Unreal imports as a socket.
- `grip_hold` seats the handle on the palm's skin (found by ray casting the skinned hand),
  then closes the fingers GraspIt-style: a finger's joints close together, each stops
  when the part it moves touches, the rest keep wrapping, and a last pass closes on the
  real skin. The thumb is solved last with its skin simulated as the rig would skin it,
  wrapping over the fingers. Index fingers curl, stay extended, or find the trigger.
  First-person hip and sights poses use two-bone IK with the elbow placed for the least
  wrist bend; a second hand can reach a second grip. Adds a `weapon_r`/`weapon_l` bone and
  a `Grip_*` action.
- `grip_check` grades any scene: palm and each finger touching, gap or depth in mm, body
  clipping, with contact-colored close-ups and the first-person view.
- Tested: club and pistol grips are "good grip" with every contact within about half a
  millimeter on four body presets and both hands; a handle pushed through the palm and one
  floating off it are both caught; the pistol's index lands on the trigger.

**Overhaul design (2026-10-21).** Feedback: 3D models and animation still took too much
trial and error. A research pass (17 agents: LLM-to-3D papers, per-category craft and
data, animation, design process) and a design pass (4 competing proposals, 3 judges,
3 reviews) produced [docs/OVERHAUL.md](docs/OVERHAUL.md). In short: Claude writes a typed
spec of parts, anchors and the game camera; every number in it comes from a sourced
table, a profile traced from human-made work, a solver or the user; numeric checks run
before any opinion; fixes edit the spec instead of regenerating; the camera sets the
detail level; and results are compared against human-made exemplars at game size.

**v0.4 (S0a): quick wins on v0.3 (2026-10-21)**

Six work packages, built in parallel and merged; numbers are from their test runs and the
integration run.

- **Game camera.** `opus.camera` holds the §2.2 formulas and six presets (Unreal third and
  first person at 1080p, Godot, Unity, top-down, orthographic side-scroller); the bible's
  `camera` section overrides them and holds the first-person view-model camera, which is
  never assumed (a labelled FALLBACK stands in). The tests reproduce every worked example in
  §2.2: hfov 90° → vfov 58.7°, 274 px/m at 3.5 m, 4 px = 14.6 mm there, a 1 cm LOD error
  switches at 12.8 m at 1440p.
- **`readability_check` v0** renders the part map at true game pixel size. A 1.8 m body
  with 52 bone parts at Unreal third person: 498 px tall at 3.5 m (493.7 expected), 115 at
  15 m (115.2), 43 at 40 m (43.2), all within 2%, with 0 unmatched part-map pixels; about 6 s
  per run. Floors stay soft until S3 calibrates them. `blind_read_sheet` gained `game_size`.
- **Mask mode** (AA off, FLAT, Standard, dither 0) for every silhouette, part-ID and focus
  pass: 0 blended pixels of 40,000 on the planted two-box test (old FLAT + AA: 843; old part
  map: 10,923).
- **Canon fixes from committed tables** (`data/tables/`: ANSUR II and Garland & Janis 1993,
  with `opus data build --tables`). Realistic foot 0.151 of stature (was 0.130; ANSUR male
  p5–p95 0.146–0.163), hand 0.105 (was 0.096; 0.103–0.117). MT/F measured on the rigs: dog
  0.437, cat 0.348, horse 0.806, equal to wolf, lion and horse (was 0.642, 0.530, 1.315);
  the horse has fetlock, pastern and hoof bones that bend the skin. Every preset is still
  its own closest canon, and the grip tests pass with the longer hand.
- **Signed distance and penetration** (`opus_bl/geom.py`): pseudonormal sign for closed
  meshes, winding number for open ones, welded seams and flipped or mirrored parts handled.
  Wrong signs: rotated cube 0 of 2,658 points (old 144), 30° wedge 0 (old 270), open box 0
  (old 45), inverted or mirrored cube 0 of 400 (old 400). A box pushed right through a 2 mm
  plate, invisible to vertex tests, is reported as "through", 11 mm deep. `model_report`
  lists penetrations; grip results are unchanged.
- **Critique protocol.** The `art-director` agent and the `3d-modeling` skill use 2–5
  yes/no checklist questions, both-order A/B with the incumbent, and a lineup beside
  human-made exemplars. `lineup_sheet` (height from the camera profile at a distance, or
  given) and `ab_sheet` make letter-only sheets in both orders with seeded order and no key
  in names or metadata.
- **Licences.** `data/licences.yaml` (45 SPDX and LicenseRef IDs with flags); the ledger
  records `licence_id`, `inputs` lineage, tools and exact attribution; `licence_check`
  enforces the bible's `commercial` and `publish_assets` policy. The six misfiring strings
  classify correctly (QAL → no-redistribute-as-asset, Copernicus → attribution, both
  "CC BY 4.0 … since 2026" → CC-BY-4.0, NVIDIA SCL → nc, the two permission phrases →
  unknown instead of nc). `LICENSE` (GPL-3.0), `THIRD_PARTY_NOTICES.md` and
  `data/LICENSES.md`, with a test that every table has an entry naming its licence.
- **Evals and run ledger.** 24 task specs in `evals/tasks/` (the 8 regression subjects plus
  16 category tasks) that validate against the v0.4 tools; `run_log` / `run_stats` and
  `opus eval list | validate | prompt | summarize | compare | tokens`.
- **Review fixes.** A review of S0a confirmed 27 findings (24 distinct problems); all are
  fixed, each with a test. Mask passes also switch the opened file's compositor and
  sequencer off and use the sRGB display (a glare or a P3 display made every part read
  "hidden"), linked duplicates get
  their own ID colors, and an undecodable part map now warns. Thin-plate sheets keep the
  solid's outward faces (a curved plate's concave side read as "through"), "behind a sheet"
  counts only from where the other part crosses that sheet (a clamp on both faces is a
  crossing), faces reversed against their neighbours are turned to agree, objects scaled to
  0 no longer crash `model_report` and `grip_check`, and a large open part sums distant
  clusters as dipoles (`grip_hold` on a 29k-triangle capless handle: 53 s → 7.7 s; v0.3
  3.2 s). Dog and cat front paws stand on the floor with the hind toes. Licences: older CC
  versions are listed, a version the table lacks stays unknown instead of becoming 4.0,
  restriction phrases beside a name ("CC BY, non-commercial use only") add their flags,
  "original work" and "facts" are no longer aliases, CMU mocap may not ship as an asset
  pack, and the ledger follows `OPUS_PROJECT_DIR` before `bible init`. Camera settings are
  checked ("orthographic" and "Horizontal" read right, flat or list distances apply, no
  ortho without `ortho_h`), MCP tools return their error messages, `proportion_check` is a
  soft eval check until S1 calibrates it, and the game-size blind read flags a FALLBACK
  view-model.
- **Tests.** 204 tests (67 in v0.3), Blender 5.2.2 integration included: 203 pass
  and 1 is skipped (the ANSUR rebuild, which passes when `OPUS_ANSUR_DIR` points at the CSVs).
  Integration added checks that every eval check's arguments exist on its MCP tool and that
  each table's licence ID matches its `data/LICENSES.md` entry.

**v0.4.1: fixes from the v0.4 baseline (2026-10-21)**

The v0.4 baseline ran in the cloud on a frozen copy of v0.4. Each of the 24 tasks got a
fresh builder session, and an independent grader then re-ran every hard check with its own
probes and one fresh judge ([evals/results/v0.4.md](evals/results/v0.4.md)). The builders'
notes on tool friction and the graders' blind spots became five fix groups. They were built
in parallel worktrees, each fix with a test that failed on v0.4, and then merged.

- **Baseline (v0.4), recorded in `evals/results/v0.4.json`.**
  - Acceptance: the grader accepted 22 of 24 tasks; the builders had accepted 23.
  - Medians: 2 iterations to a hard pass, 3 to accept, 2 judge rounds and 3.5 validator
    rejections. Wall-clock was 19.1 min, which is noisy because six sessions shared 4 CPUs.
    Tokens were 10.1 M input (cache reads included) and 6.0 k output.
  - The two failures:
    - `human_hd`, blind read: the fresh judge said "female character", which is not on
      the name list.
    - `peasant_outfit`, garment poke-through: 13 mm against a 1 mm limit, and no tool
      measures it yet.
  - 59 of the 105 validator rejections were `run_log` calls.
  - The summary comes from a corrected copy of the ledger: events that parallel sessions
    filed under the wrong run are moved or dropped, and a round logged before its blind
    read ran counts as failing (the results note lists every change).
- **CLI and MCP (CLI-1..6).**
  - `--json` on every report command.
  - Axis names (`+Z`, `-X`) and values that start with a dash.
  - The missing options: `--objects`; `hold --aim-axis/--index/--thumb`;
    `grip-define --start/--end/--thumb`; `lint --category`; `run-stats --run`.
  - Errors are one line with exit 2 instead of a traceback.
  - `run-log --help` lists every event's fields.
  - A sheet given no frame size is cut into square frames.
- **Run ledger, provenance and evals (RUN-1..2, LED-1..2, EVAL-1..2, BODY-1).**
  - An event with no run id is refused while several runs are open.
  - Field errors name the field and its kind, and findings must be check ids.
  - An unlicensed build points at `LicenseRef-Own-Work`, and `ledger_record` refuses
    missing paths.
  - Camera checks must run at the task's camera: seven specs gained `camera: godot_tp`.
  - `judge.py` takes comma-separated names and 1–5 questions.
  - Quadruped blockouts report the withers height.
- **Lint, penetration and grips (LINT-1..4, GEOM-1, GRIP-1..4).**
  - Normals are read in world space.
  - Imported glTF, FBX, OBJ and STL are welded before the checks. Eight eval exports now
    lint with 0 errors, and `wolf_trot.glb` takes 2.2 s instead of 31.6 s.
  - Props on a bone count as rigid.
  - Floating pieces are measured with the gap and the nearest piece: the goblin's tusks at
    7.5 mm, the knight's rerebraces at 4–4.8 mm.
  - Flush faces count as contact, so the house roof bays no longer report a 76.6 mm
    penetration.
  - Grips accept a prop skinned to the weapon bone, and body depth comes only from
    counted triangles.
  - `fp_ads` takes the eye-to-sight distance.
  - Appended rigs no longer duplicate materials.
- **Parts and render passes (REP-1..2, PARTS-1, LOOKDEV-1, RENDER-1..2, LOOK-1).**
  - `model_report` checks skinned meshes and loose islands for contacts and gaps, with a
    3 mm contact cap. It finds the wolf floater, the goblin's tusks and the knight's
    plates, with no false floaters on barrel, chest, house, woman or chibi.
  - Bone-parented and rigid-skinned meshes are object parts.
  - Penetrations are class `report`.
  - EEVEE lookdev finds its studio light, or falls back with a warning.
  - Shaded passes show vertex colours, and there is a true normals pass.
  - A bone target includes its child bones, and a hidden one gets a cutaway.
- **Sheets and paths (READ-1, BLIND-1, CAM-1, LOOK-2, PATH-1, REF-1, REP-3).**
  - Defining names match in any case or by prefix, and names that match nothing count.
  - Game-size silhouettes turn to the side that shows the most.
  - Levels with the camera inside the subject are flagged and left off blind sheets.
  - Look sheets never name the file.
  - Output paths and work folders are reserved per call.
  - References with alpha are composited over a light background.
  - `report["metrics"]` carries the eval metric names.
- **Integration.**
  - A `grade` event (`accepted`, `failed` check ids, `note`) records an independent
    grader's verdict, and the baseline's 24 grades are in its ledger. A graded run counts
    as accepted only when its last grade says so; `self_accepted` keeps the builder's
    verdict. The failed checks count in the failure histogram, and prose findings from
    v0.4 ledgers count as `(prose)`.
  - The house and dragon blind reads pass framing distances (20,40 and 25,60), because
    their default close and typical levels put the camera inside the subject.
  - Blockouts saved over a reserved output path leave no empty `.blend1`.
  - `model_report`'s text says penetrations are reported, not gated.
  - `lookdev_sheet` returns the render's warnings.
  - The suite hash goes from `b3208ab30cbd` to `c4c1e134168e`; the check ids are
    unchanged.
- **Review fixes.** A review of v0.4.1 against the eval assets and the baseline ledger:
  - Game-size silhouettes pick the view with the most area in square meters, not the most
    pixels: each overview tile is framed to its own span, so the rifle and the wolf were
    seen end-on.
  - An object resting on the floor no longer floats in `model_report`, as islands already
    didn't.
  - Ears, noses and horns on their own bones stay body in grip checks: a mesh on its own
    bone is a held prop only below a hand or a weapon bone, or on a bone with no parent.
  - Licence text that names no licence, and an own-work entry that lists its references,
    say to record `LicenseRef-Own-Work`. Provenance phrases stay out of the aliases.
  - `run_log` refuses a count where check ids go (`failed=2` from the CLI), `tokens` and
    `user_rejection` without a run id while another run is open, a grade on an open run or
    one that contradicts itself or the close, and a round with zero hard failures that
    lists findings. The protocol counts a hard check not run yet as failing.
  - `run_stats` takes the grade logged after the final close as the verdict, and a run
    whose grade failed a hard check has no hard pass.
  - The baseline summary was rebuilt from a corrected ledger (see above), and its note says
    which gates measure more in v0.4.1 (floating on knight, goblin and dragon) and that
    checklist judges could see the file name.
- **Tests.** There are 272 tests, up from 204 in v0.4. With Blender 5.2.2, 271 pass and 1 is
  skipped (the ANSUR rebuild). The integration run caught one clash between the groups: the
  roof-contact test predated `gap_mm` on contacts. It also caught a ledger test that expected
  an exception where the CLI now prints a one-line error. Both are fixed.
- **Still open:**
  - Running `grip_define` again on an existing grip name adds a `.001` socket instead of
    replacing it.
  - Seven `ue_tp_1080` specs rely on the default camera, not an explicit one.
  - Armour and clothing layers with designed stand-off gaps now raise `floating_part`
    warnings: 24 on the plate armour. They are warnings only.
  - `model_report` is slower on large rigs: 6.0 s on the knight against 1.9 s before.
  - Several probe checks depend on how the probe is written, which is for S0b to pin
    down (see the results note).

**Not done yet (needs the PC):** the [PC checks](docs/PC_CHECKS.md): install, doctor green,
every tool on Windows, and a 1.8 m blockout coming into Unreal 180 units tall.

**Next:** the overhaul's sprints, in order (docs/OVERHAUL.md §9):

1. **Finish S0a on the PC:** the PC checks. The v0.4 baseline is recorded (v0.4.1 above).
2. **S0b:** the spec compiler core, kept only if it beats the v0.4 baseline in a measured
   A/B test.
3. **S1–S11:** HD humans, creatures, design lock and appeal, weapons and first-person,
   motion, creature gaits and pixel rendering, clothing and armor, surfaces, landscapes
   and trees, then buildings, faces, hair and vehicles.
4. Pixel art and sound continue from this plan in between.

## 8. Honest limits

- **Claude will never hear.** Spectrograms, metrics and ML listeners catch technical faults
  and gross mismatches; the final taste call on audio stays with the user. The Audition
  Board makes that a 30-second job.
- **Organic sculpting purely in code stays limited.** Canon blockouts now get proportions
  and the rig right, but surface detail (faces, hands, musculature, scales) still comes
  from library bases (the CC0 MakeHuman body and its targets), kitbashing, bakes and
  CC0 materials, or sculpting over the blockout. Hard-surface props, architecture,
  environments and low-poly are where procedural code gets genuinely good. See
  docs/OVERHAUL.md §10 for what stays hard.
- **Hi-res pixel characters are hard to draw in code.** The realistic routes are 3D → pixel
  renders, AI generation + cleanup, or the user's sketches cleaned up by the pipeline.
  Procedural code is genuinely good for icons, UI, tiles and props.
- **Hand-keyed human locomotion won't match mocap.** Humans → library or mocap + retarget +
  in-engine procedural layers. Creatures, props, machines and cartoony actions → Keyframe
  Director.
- **Generative models** are not used for 3D or animation. The 2D image and audio ones
  vary in quality, are capped by 16 GB of VRAM and some are research-only or
  region-restricted; they're optional backends, never the foundation.
- **Disk:** asset, sound and model downloads add up quickly; the manifest marks each one
  optional or recommended, with its size, so the ~100 GB budget is spent deliberately.

## 9. Open questions

1. Which MCP servers are connected for Blender and Godot (names or links)? Blender has an
   official one from Blender Lab and a popular community one; Godot has several community
   ones.
2. In the desktop app, do you work in regular chat or the Code tab? v0.1 installs as a
   plugin in the Code tab, which also gives Claude file access, a terminal and subagents.
   If you mostly use chat, the desktop-extension (`.mcpb`) build moves up the list.
3. What does "hi-res" pixel art mean for you: roughly how tall are characters (32, 64,
   128 px?), and are there games whose look you're aiming for?
4. Do you use a pixel editor (Aseprite, Pixelorama, LibreSprite, …)?
5. Does the no-generative-models rule also cover 2D: the image-model pixel pipeline
   (Z-Image, FLUX.2 klein, PixelLab) and AI sprite animation? Until you decide, those stay
   in the plan but aren't built. (`pixel_cleanup` itself is classical code.)
