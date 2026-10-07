# Opus Tools — Game Plan

**Mission:** give Claude the senses, building blocks, raw material, and quality gates it
needs to produce good **3D models**, **sound**, and **animation** for Blender + Godot 4
games — packaged as one install on the game-dev PC that works in every project.

Status: planning draft v0.1 (2026-10-07). Nothing is built yet.

---

## 1. Diagnosis — why Claude's output is weak today

| Gap | What it causes |
|---|---|
| **Claude can't perceive what it makes.** It writes a Blender script and never sees the mesh, writes DSP code and never hears it, keys an animation and never watches it. | Floating/intersecting parts, wrong proportions, clicks and clipping, foot sliding and pops all go unnoticed. |
| **The authoring interface is too low-level.** Raw `bpy` vertex math, raw sample buffers, raw keyframe values. | "Primitive soup" models, sine-and-noise sound effects, linear robotic motion. Claude is strong at structure and composition, weak at holding coordinates and curves in its head. |
| **It starts from nothing.** Real artists start from reference, libraries, recordings, scans, and mocap. | Everything is synthetic programmer-art. Organic shapes, natural sounds, and human motion suffer most. |
| **No craft memory.** Budgets, conventions, and recipes are re-derived every session; there is no record of what the user liked. | Inconsistent style across a game's assets; the same mistakes repeat. |
| **Blender → Godot pipeline traps.** | Procedural materials vanish on export; wrong scale/axes/origins; missing loop flags; un-randomized sounds; clips never wired into an `AnimationTree`. |

The single biggest lever is the first gap. The suite **closes the loop**: every *make* tool
is paired with a *perceive* tool and a rubric, so Claude iterates
**make → render/analyze → critique → fix** before the user ever sees the asset.

## 2. Design principles

1. **Perceive before shipping.** No generator without a matching inspector. Inspectors
   return images Claude can look at (contact sheets, spectrograms, motion strips) plus
   numeric reports with pass/fail thresholds.
2. **Semantic building blocks over raw numbers.** Parameterized, craft-aware builders
   (bevels, profiles, layers, envelopes, poses, easing) with good defaults baked in. Assets
   are *recipes* (code + params + seed), so variations and fixes are re-runs, not re-dos.
3. **Start from real material.** CC0 libraries, real recordings, mocap and (optionally)
   generative models are inputs; Claude's job shifts toward selecting, kitbashing,
   processing, cleaning up and integrating — which it is good at.
4. **Engine-native end state.** "Done" means imported and wired in Godot (import options,
   collision, randomizers, buses, AnimationTree) and verified with an in-engine capture.
5. **The user is the final judge — cheaply.** Taste calls (especially audio, which Claude
   cannot hear) go through a fast audition/rating board; ratings are saved as taste notes.
6. **One project bible.** Every tool reads a per-project style/budget file so assets stay
   consistent.
7. **Provenance from day one.** Every asset records source, license and author;
   non-commercial material is flagged; credits are generated.
8. **Swappable AI backends.** Generative models churn monthly; they sit behind stable
   interfaces, and the core stays fully useful with no GPU at all.
9. **Testable headlessly.** Everything runs from a CLI against headless Blender/Godot, so
   it can be built and regression-tested in cloud sessions and CI before it reaches the PC.

## 3. Architecture

```
 ┌──────────────────────── Claude (Claude Code on the dev PC) ─────────────────────────┐
 │  Skills: craft knowledge, workflows, rubrics      Critic subagents (fresh eyes)      │
 └──────────────┬───────────────────────────────────────────┬───────────────────────────┘
                │ MCP tools (return images + JSON)          │ `opus` CLI via Bash
 ┌──────────────▼───────────────────────────────────────────▼───────────────────────────┐
 │                          opus core  (Python, managed by uv)                          │
 │  senses : look-dev sheet · audio inspector · motion inspector · in-engine capture    │
 │  craft  : shape kit · material lab/bake · sound forge/synth · keyframe director      │
 │  gates  : mesh lint · rig lint · loudness/loop checks · motion diagnostics           │
 │  sources: asset/SFX/motion librarians · generative backends · provenance ledger      │
 └───────┬─────────────────────────┬──────────────────────────┬─────────────────────────┘
         │                         │                          │
  Blender (headless `-b`     Godot 4 (headless import,   Audio engine (numpy/scipy,
  or live addon socket)      editor plugin, Movie Maker   plugin host for VST3 synths
                             capture)                     and effects)
```

- **Delivery.** This repo becomes a Claude Code **plugin marketplace**. On the PC:
  `/plugin marketplace add Infamase/Opus-Tools`, then `/plugin install opus-tools@opus-tools`.
  Skills, subagents and MCP servers are then available in every project. The plugin's
  `userConfig` asks once for the Blender and Godot executable paths, the library folder,
  and any API keys (stored as sensitive).
- **Where it runs.** Full support (skills + local MCP servers that launch `blender.exe` /
  `godot.exe`) is in the **Claude Code CLI** and the **desktop app's Code tab**; Cowork only
  when the session runs locally. Plain chat surfaces load the skills but ignore local MCP
  servers, so the hands-and-senses half is unavailable there.
- **Skills** carry the craft: workflows, rubrics, recipes, Godot conventions. They load on
  demand (SKILL.md under ~500 lines, details in reference files), so a big library is cheap.
- **MCP servers** (Python, stdio, launched with `uv`) are the hands and senses for Blender,
  Godot and audio. Tool results can carry images, so renders and spectrograms come straight
  back to Claude. Long renders need a raised per-server tool timeout.
- **`opus` CLI** exposes the same functions for batch work and CI; Claude Code's Read tool
  can view the PNGs it writes.
- **Blender side:** a small addon for the live bridge (local socket) plus modules that run
  under headless `blender -b`. Anything that runs *inside* Blender depends only on `bpy` +
  `numpy` (Blender's bundled Python); everything else lives in the uv environment.
- **Godot side:** `addons/opus/` — editor plugin (live bridge, import post-processors,
  AnimationTree builder) plus runtime helpers (game feel, procedural animation, audio).
  Headless import/validation; Movie Maker mode for deterministic in-engine frame captures.
- **Per project:** `opus.project.yaml` (the bible) and `.opus/` (provenance ledger,
  ratings, caches).

Proposed repo layout:

```
Opus-Tools/
├── .claude-plugin/marketplace.json
├── plugins/
│   ├── opus-tools/                  # main plugin — works on any PC, no GPU needed
│   │   ├── .claude-plugin/plugin.json   # userConfig: blender/godot paths, library dir
│   │   ├── .mcp.json                # opus-blender, opus-godot, opus-audio servers
│   │   ├── skills/                  # project-bible, modeling, materials, sound-design,
│   │   │                            # music, animation, rigging, godot-pipeline, critique
│   │   ├── agents/                  # art / audio / animation director critics
│   │   ├── python/                  # opus core package, CLI, MCP servers
│   │   ├── blender/                 # addon + in-Blender modules (bpy + numpy only)
│   │   └── godot/addons/opus/       # copied into a game by `opus godot init`
│   └── opus-gen/                    # optional plugin: GPU/API generative backends
├── evals/                           # benchmark tasks, baseline + scored results
├── tests/                           # headless Blender/Godot/audio tests, golden images
└── install/                         # Windows setup + `opus doctor`
```

## 4. Tool catalog

Priority: **P0** foundation · **P1** biggest quality wins · **P2** strong upgrades ·
**P3** optional, GPU- or API-dependent.

### 4.0 Foundation

| Tool | What it does | Pri |
|---|---|---|
| **Blender Bridge** | Run scripts headless or in the user's open Blender; query the scene (objects, dimensions, tri counts, modifiers, materials, rigs); checkpoints; versioned `.blend` saves; `.glb` export. | P0 |
| **Godot Bridge** | Headless import and run; read errors/logs; inspect and edit scenes; write `.import` options; capture frames from a running scene for in-engine checks. | P0 |
| **Project Bible** | `opus.project.yaml`: art style, palette, shape language, reference board, tri/texture/bone budgets, texel density, loudness targets per sound category, animation fps and "feel", naming rules. Created by a short interview skill; read by every tool. | P0 |
| **Provenance Ledger** | Sidecar record per asset (source, license, author, generator + model version); generates `CREDITS.md`; blocks non-commercial material in commercial projects. | P0 |
| **Installer + `opus doctor`** | Windows setup (uv env, Blender addon, optional library downloads) and a health check of every integration. | P0 |
| **Eval suite** | Fixed benchmark tasks per domain, produced before/after each tool and rated blind — tells us which tools actually move quality. | P0 |

### 4.1 3D models

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Look Dev Sheet** | can't see it | One call → labeled contact sheet: front/side/back/top + ¾ perspective; clay/matcap (form); wireframe (topology density); solid silhouette (shape readability); face orientation (flipped normals); UV checker; 1.8 m human silhouette + 1 m grid for scale. Optional side-by-side with a reference, and a **gameplay-distance view** at the on-screen size the asset will really have. Laid out to fit Claude's image-input resolution so nothing gets downscaled into mush. | P1 |
| **Mesh Lint** | not game-ready | Non-manifold/loose geometry, flipped normals, zero-area faces, n-gons on deforming meshes, unapplied transforms, origin placement, intersecting/floating parts, tri budget, UV presence/overlap/bounds, texel-density consistency, material count, texture sizes, naming. JSON + heatmap render + safe auto-fixes. | P1 |
| **Shape Kit** | primitive soup | Python modeling library of semantic, parameterized builders: beveled primitives, lathe from profiles, sweep/loft/pipe along curves, inset/extrude/panel lines, booleans with cleanup + weighted normals, mirror/array/radial, taper/bend/twist/lattice, organic blobs (skin modifier/metaballs/SDF → remesh), scatter, grid-snapped modular kits, and generators (rocks, trees, crates, barrels, buildings, furniture, weapons). Every asset is a recipe function + params + seed → instant variations. Style presets: low-poly flat, stylized, PBR-realistic, PS1-retro, voxel. | P1 |
| **Material Lab + Bake** | flat colors; procedural materials lost on export | Procedural material graphs (wood, metal, stone, fabric, plastic, toon) with curvature/AO-driven wear and grime; one-call **bake to Godot-ready PBR** (albedo, ORM, normal) at the bible's texel density; high→low normal/AO bakes; palette-atlas workflow for low-poly; trim sheets; Godot material setup (StandardMaterial3D or toon shader). | P1 |
| **Asset Librarian** | starting from nothing | Downloads and indexes CC0 packs; renders thumbnails; text + image search via embeddings; returns a candidate contact sheet; imports with provenance; kitbash parts out of library meshes. | P1 |
| **Godot Import Pipeline** | export traps | glTF export presets; Godot import hints (`-col`, `-convcolonly`, `-navmesh`, `-loop`, …); writes `.import` options (LODs, shadow meshes, collision, materials); post-import scripts; then an in-engine capture in the game's own lighting. | P1 |
| **Blueprint & Match** | wrong proportions | Reference images or the user's sketches behind orthographic cameras; silhouette-overlap score (IoU) per view between render and reference, so "proportions look right" becomes a number. | P2 |
| **Lineup Render** | style drift | Renders the new asset next to already-approved assets at the same scale and lighting to catch scale, style and detail-density mismatches. | P2 |
| **Godot Look Presets** | assets look flat in-engine | WorldEnvironment, light rig, tonemapping, SSAO/SSIL, glow and fog presets per art style; applied to the game and used by every in-engine capture, so assets are judged under the light they ship in. | P2 |
| **Gen3D + Cleanup** | organic shapes | Concept image (sketch, reference or generated) → image-to-3D model → automated cleanup: scale/orient, remove floaters, remesh/decimate to budget, UVs, texture re-bake, LODs → Mesh Lint → Godot. Raw AI meshes are not game-ready; the cleanup stage is the value. | P3 |
| **Gen Texture** | bland surfaces | Tileable PBR textures, decals and concept sheets from an image model → derived normal/roughness maps → Material Lab. | P3 |

### 4.2 Sound

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Audio Inspector** ("ears") | can't hear it | Image of waveform + log-frequency spectrogram + loudness curve; report of duration, peak/true peak, LUFS, crest factor, DC offset, clipping, head/tail silence, attack/decay, spectral centroid/rolloff/flatness, pitch, onsets, stereo phase, noise floor, clicks and **loop-seam** continuity. A-vs-B and vs-reference comparison. Optional ML listeners: text-audio similarity ("how much does this sound like *heavy wooden door slam*?") and a captioner that describes the sound in words. | P1 |
| **SFX Library** | synthetic-only sound | Indexes royalty-free libraries and the user's own recordings with metadata + audio embeddings; text search; candidates with spectrograms; license tracking. | P1 |
| **Sound Forge** | thin, unprocessed sound | Declarative sound recipes: layers (library sample, synth or generated), each with trim/pitch/stretch/reverse/fades/EQ/saturation/transient shaping; bus processing (glue compression, convolution reverb with real impulse responses, limiter); normalized to the bible's category loudness. This is how sound designers work: layer and process real sources. | P1 |
| **Godot Audio Packager** | machine-gun repetition; uneven levels | Renders N variations; picks WAV vs Ogg Vorbis; writes loop settings with zero-crossing-snapped loop points; generates `AudioStreamRandomizer` resources; bus layout (Master/Music/SFX/UI/Ambience/Voice) with per-zone reverb buses; 3D attenuation presets. | P1 |
| **Synth Engine + Recipe Book** | beeps and white noise | For what synthesis does well — UI, retro, sci-fi, magic, whooshes, engines, weather/ambience beds — and impacts via **modal synthesis** (wood/metal/glass resonances). Backed by a real synth hosted headlessly + DSP; the recipe book stores known-good parameter ranges per category. | P2 |
| **Mix Check** | inconsistent mix | Project-wide loudness consistency per category, outliers, frequency masking between sounds that commonly play together. | P2 |
| **Music Studio** | simplistic music | Structured score (sections, chord progressions, parts, drum patterns) → MIDI → rendered with good free instruments → mix/master chain → loop-perfect export (render two passes, keep the second so reverb tails wrap) → stems for adaptive music in Godot (`AudioStreamInteractive` / `AudioStreamSynchronized`). Theory lint (ranges, voice leading). | P2 |
| **Gen Audio** | complex natural SFX; voices | Text-to-SFX model as one more *source* for the Forge (generate → layer/process → inspect); TTS for character barks + voice processing (radio, robot, monster). | P3 |

### 4.3 Animation

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Motion Inspector** ("eyes for motion") | can't watch it | Frame contact sheet from two cameras with onion skins and motion trails (hands, feet, head, root); curve plots (root height, foot heights/speeds, key joint angles); GIF/MP4 for the user. Diagnostics: **foot sliding**, ground penetration, joint-limit violations and knee flips, self-intersection, pops (velocity/jerk spikes), loop-seam continuity (pose and velocity), balance (center of mass vs support), arc smoothness, key-spacing chart. | P1 |
| **Rig Doctor** | broken deformation | Rig templates whose bone names match Godot's `SkeletonProfileHumanoid` (so Godot's retargeting just works) plus quadruped/bird/tail/tentacle/mechanical templates; auto-rig + automatic weights + weight transfer; **deformation test** — extreme poses (arms up, squat, twist) rendered as a contact sheet, candy-wrap and volume-loss flags; weight lint (≤4 influences, normalized, unweighted verts, symmetry). | P1 |
| **Motion Library + Retargeter** | hand-keyed humans | Indexes licensed motion sets (CC0 libraries, CMU mocap, Mixamo clips the user downloads, …); text search with preview strips; retargets onto the project's rigs; clip tools: trim, loop-fix (blend tail into head), speed, in-place ↔ root motion, mirror, additive layers. | P1 |
| **Godot Animation Wiring** | clips that feel bad in-game | Builds `AnimationTree` state machines and blend spaces from a spec (locomotion by velocity, one-shots, crossfades, root motion); runtime procedural layers: foot IK on slopes, look-at, spring bones (hair, tails, capes), lean into turns, partial-ragdoll hit reactions; **game-feel library** (easing presets, squash/stretch on landing, hit-stop, camera shake). Often the biggest perceived quality gain per hour of work. | P1 |
| **Keyframe Director** | linear, weightless motion | Animation DSL: Claude authors semantic poses, IK targets and timing ("anticipate 4f, strike 2f, overshoot 15 %, settle 6f"); the 12 principles are automatic passes — slow-in/out, anticipation, overshoot/settle, follow-through and overlap down bone chains, arcs, baked secondary motion, squash & stretch. Procedural cycle generators (walk/run/sneak/idle/fly/swim) with planted-foot IK and stride/bounce/weight/mood parameters. Best for creatures, props, machines, doors, chests and UI. | P2 |
| **Animation Events** | SFX/VFX out of sync | Uses Motion Inspector analysis to place method/audio tracks automatically: footsteps at foot contacts, whooshes at weapon peak velocity, impacts at contact frames; attack frame data (startup/active/recovery). | P2 |
| **Lip Sync** | dead faces in dialogue | Viseme timing from voice lines → shape-key / blend-shape tracks. | P3 |
| **Sim Bake** | stiff cloth, fake destruction | Blender cloth/rigid/soft-body sims baked to keyframes, shape keys or vertex-animation textures for Godot. | P3 |
| **Mocap from video / text** | unique human actions | The user films an action on a phone → video-to-motion model → cleanup (foot lock, smoothing, loop) → retarget → Motion Inspector. Text-to-motion models for drafts. | P3 |

### 4.4 Cross-cutting

| Tool | What it does | Pri |
|---|---|---|
| **Critic subagents** | Fresh-context art, audio and animation "directors" that judge inspector output against the bible and rubrics, so Claude isn't grading its own homework. They compare candidates pairwise (A vs B), which is more reliable than absolute scores. | P1 |
| **Audition Board** | Local page to compare variants (audio players, turntable GIFs, playblasts), pick winners and leave notes; results land in `.opus/ratings` and are summarized into taste notes in the bible. | P1 |
| **Recipe memory** | Approved assets save their recipe + parameters to the project (or global) recipe book for reuse. | P2 |

## 5. Measuring progress — the eval suite

A fixed set of benchmark tasks, produced once **before** any tool exists (baseline) and
again after each phase. The user rates old-vs-new pairs blind on the Audition Board;
automated metrics and "iterations to acceptable" are tracked alongside.

| Domain | Benchmark tasks | Automated metrics |
|---|---|---|
| 3D | Stylized wooden barrel · sci-fi crate with panel lines · low-poly pine trees ×3 variants · modular medieval house kit (wall, door, window, corner, roof) · stylized goblin character, rig-ready | Mesh Lint pass rate, tri budget adherence, silhouette IoU vs reference |
| Sound | UI set (hover, click, confirm, cancel, error) · sword swing + metal hit ×6 variations · footsteps on grass/stone/wood ×4 each · medium explosion · 30 s seamless rain loop · 60 s menu music loop | Loudness deviation from target, clipping/clicks, loop-seam error, variation spread |
| Animation | Treasure chest opening · goblin idle/walk/run · sword attack with anticipation and follow-through · quadruped walk cycle · door slam with secondary wobble · in-game third-person locomotion with blend space and foot IK on a slope | Foot slide (cm), ground penetration, pops, loop-seam error |

## 6. Third-party building blocks

_Pending: research on current models, libraries and licenses (late 2026) is in progress._

## 7. Roadmap

| Phase | Builds | Exit criteria |
|---|---|---|
| **0 · Foundation** | Plugin + marketplace skeleton, `userConfig`, Blender Bridge, Godot Bridge, Project Bible, Provenance Ledger, installer, eval baseline. | From any Godot project on the PC, Claude runs a Blender script (headless and live), imports the result into Godot and gets an in-engine capture back. Baseline eval outputs recorded. |
| **1 · Senses** | Look Dev Sheet, Mesh Lint, Audio Inspector, Motion Inspector, Audition Board, critic subagents. | Every asset type has a perceive step with numeric checks; eval tasks re-run with the loop. |
| **2 · Quick wins** | Asset Librarian, SFX Library + basic Forge, Motion Library + humanoid retarget, Godot Import Pipeline, Audio Packager, Animation Wiring + game-feel library. | Eval tasks show a clear blind-rated improvement in all three domains. |
| **3 · Craft** | Shape Kit, Material Lab + Bake, full Sound Forge + Synth Recipe Book, Rig Doctor, Keyframe Director, Animation Events. | Procedural props/environments and stylized animation pass lint and critic review without hand fixes. |
| **4 · Generative** | `opus-gen`: Gen3D + cleanup, Gen Audio, auto-rig and mocap models — sized to the PC's GPU or to paid APIs. | Each backend sits behind the common interface and passes the same gates. |
| **5 · Depth** | Music Studio, Mix Check, Lip Sync, Sim Bake, recipe memory, Blueprint & Match, Lineup Render. | — |

## 8. Honest limits

- **Claude will never hear.** Spectrograms, metrics and ML listeners catch technical faults
  and gross mismatches; the final taste call on audio stays with the user. The Audition
  Board makes that a 30-second job.
- **Organic sculpting purely in code stays limited.** For characters and creatures the
  realistic paths are library bases + kitbashing, image-to-3D + cleanup, or a quick user
  blockout with Claude doing the technical pipeline. Hard-surface props, architecture,
  environments and stylized low-poly are where procedural code gets genuinely good.
- **Hand-keyed human locomotion won't match mocap.** Humans → library/mocap + retarget +
  in-engine procedural layers. Creatures, props, machines and cartoony actions → Keyframe
  Director.
- **Generative models** vary in quality, need VRAM, and many carry non-commercial or
  region-restricted licenses. They are optional backends, never the foundation.
- **Disk:** full SFX bundles and asset libraries run to tens of GB.

## 9. Open questions

1. PC specs: OS, GPU and VRAM, RAM, free disk space.
2. Blender and Godot versions; Godot renderer (Forward+ / Mobile / Compatibility).
3. Usual art styles and camera (first-person, third-person, top-down, …).
4. Will the games be sold? (Rules out non-commercial models and data.)
5. Budget for paid APIs, or local-only?
6. Which Claude surface on the PC: Claude Code CLI, the desktop app's Code tab, or desktop chat?
7. How much in the loop the user wants to be (audition checkpoints per asset vs per batch).
8. Which domain hurts most — where to start.
