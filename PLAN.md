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
- **Blender side:** the official Blender Lab MCP server (add-on + stdio server; needs
  Blender 5.1+, target **5.2 LTS**) provides the live connection; our modules run inside
  Blender through it or under headless `blender -b`. Anything that runs *inside* Blender
  depends only on `bpy` + `numpy` (Blender's bundled Python) and follows the 5.x API.
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
│   │   ├── .mcp.json                # opus-blender (headless render/lint/bake),
│   │   │                            # opus-godot, opus-audio, opus-assets servers;
│   │   │                            # live Blender control = official Blender MCP
│   │   ├── skills/                  # project-bible, modeling, materials, sound-design,
│   │   │                            # music, animation, rigging, godot-pipeline, critique
│   │   ├── agents/                  # art / audio / animation director critics
│   │   ├── python/                  # opus core package, CLI, MCP servers
│   │   ├── blender/                 # in-Blender modules (bpy + numpy only)
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
| **Blender Bridge** | **Adopt the official Blender Lab MCP server** for live control (Python execution, scene/object summaries, screenshots, viewport renders, headless CLI tools, search over the bundled API docs). Add our own thin layer on top: checkpoints and versioned `.blend` saves (the official server runs generated code unguarded), loading our in-Blender modules, `.glb` export presets, and a plain `blender -b` runner for batch jobs and CI. | P0 |
| **Godot Bridge** | No official Godot MCP exists; community ones (e.g. Coding-Solo/godot-mcp, MIT: launch, run, debug output, scene edits — but no screenshots) are evaluated in Phase 0 and adopted for generic editor control if solid. We build the parts nobody covers: headless `--import`, `.import` option writers, scene inspection, and deterministic frame capture (Movie Maker mode) for in-engine checks. | P0 |
| **Project Bible** | `opus.project.yaml`: art style, palette, shape language, reference board, tri/texture/bone budgets, texel density, loudness targets per sound category, animation fps and "feel", naming rules. Created by a short interview skill; read by every tool. | P0 |
| **Provenance Ledger** | Sidecar record per asset (source, license, author, generator + model version); generates `CREDITS.md`; blocks non-commercial material in commercial projects. | P0 |
| **Installer + `opus doctor`** | Windows setup (uv env, official Blender MCP add-on, optional library downloads) and a health check of every integration. | P0 |
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
| **Audio Inspector** ("ears") | can't hear it | Image of waveform + log-frequency spectrogram + loudness curve; report of duration, peak/true peak, LUFS, crest factor, DC offset, clipping, head/tail silence, attack/decay, spectral centroid/rolloff/flatness, pitch, onsets, stereo phase, noise floor, clicks and **loop-seam** continuity. A-vs-B and vs-reference comparison. Optional ML listeners: a text–audio match score ("how much does this sound like *heavy wooden door slam*?"), a production-quality score, and a captioner that describes the sound in words. | P1 |
| **SFX Library** | synthetic-only sound | Indexes royalty-free libraries and the user's own recordings with metadata + audio embeddings; text search; candidates with spectrograms; license tracking. | P1 |
| **Sound Forge** | thin, unprocessed sound | Declarative sound recipes: layers (library sample, synth or generated), each with trim/pitch/stretch/reverse/fades/EQ/saturation/transient shaping; bus processing (glue compression, convolution reverb with real impulse responses, limiter); normalized to the bible's category loudness. This is how sound designers work: layer and process real sources. | P1 |
| **Godot Audio Packager** | machine-gun repetition; uneven levels | Renders N variations; picks WAV vs Ogg Vorbis; writes loop settings with zero-crossing-snapped loop points; generates `AudioStreamRandomizer` resources; bus layout (Master/Music/SFX/UI/Ambience/Voice) with per-zone reverb buses; 3D attenuation presets. | P1 |
| **Synth Engine + Recipe Book** | beeps and white noise | For what synthesis does well — UI, retro, sci-fi, magic, whooshes, engines, weather/ambience beds — and impacts via **modal synthesis** (wood/metal/glass resonances). Backed by a real synth hosted headlessly + DSP; the recipe book stores known-good parameter ranges per category. | P2 |
| **Mix Check** | inconsistent mix | Project-wide loudness consistency per category, outliers, frequency masking between sounds that commonly play together. | P2 |
| **Music Studio** | simplistic music | Structured score (sections, chord progressions, parts, drum patterns) → MIDI → rendered with good free instruments → mix/master chain → loop-perfect export (render two passes, keep the second so reverb tails wrap) → stems for adaptive music in Godot (`AudioStreamInteractive` / `AudioStreamSynchronized`). Theory lint (ranges, voice leading). | P2 |
| **Gen Audio** | complex natural SFX; voices | Text-to-SFX model as one more *source* for the Forge (generate → layer/process → inspect); TTS for character barks with emotion control + voice processing (radio, robot, monster). Current SFX models need only ~2 GB of VRAM, so this runs on almost any gaming GPU. | P2 |

### 4.3 Animation

| Tool | Fixes | What it does | Pri |
|---|---|---|---|
| **Motion Inspector** ("eyes for motion") | can't watch it | Frame contact sheet from two cameras with onion skins and motion trails (hands, feet, head, root); curve plots (root height, foot heights/speeds, key joint angles); GIF/MP4 for the user. Diagnostics: **foot sliding**, ground penetration, joint-limit violations and knee flips, self-intersection, pops (velocity/jerk spikes), loop-seam continuity (pose and velocity), balance (center of mass vs support), arc smoothness, key-spacing chart. | P1 |
| **Rig Doctor** | broken deformation | Game-ready rig templates (deform bones in one clean hierarchy, names matching Godot's `SkeletonProfileHumanoid` so Godot's retargeting just works) plus quadruped/bird/tail/tentacle/mechanical templates; auto-rig + automatic weights + weight transfer; **deformation test** — extreme poses (arms up, squat, twist) rendered as a contact sheet, candy-wrap and volume-loss flags; weight lint (≤4 influences, normalized, unweighted verts, symmetry). | P1 |
| **Motion Library + Retargeter** | hand-keyed humans | Indexes licensed motion sets (CC0 libraries, CMU mocap, Mixamo clips the user downloads, …); text search with preview strips; retargets onto the project's rigs using bundled bone maps for common skeletons (Mixamo, UE5 Mannequin, Rigify, SOMA); clip tools: trim, loop-fix (blend tail into head), speed, in-place ↔ root motion, mirror, additive layers. | P1 |
| **Godot Animation Wiring** | clips that feel bad in-game | Builds `AnimationTree` state machines and blend spaces from a spec (locomotion by velocity, one-shots, crossfades, root motion); runtime procedural layers built from Godot's own skeleton modifiers: foot IK on slopes, look-at, spring bones (hair, tails, capes), lean into turns, partial-ragdoll hit reactions; **game-feel library** (easing presets, squash/stretch on landing, hit-stop, camera shake). Often the biggest perceived quality gain per hour of work. | P1 |
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

Snapshot as of October 2026, checked against repos, license files and official docs.
This field moves monthly, so re-verify before building on any of it. License notes matter
if the games will be sold.

### 6.1 3D

| Need | Recommended | Notes and licenses |
|---|---|---|
| Live Blender control | Official **Blender Lab MCP** (v1.0.3) | GPL-3.0. That's fine because it runs as a separate process and our code doesn't link to it. Needs Blender 5.1+. Don't run the community `mcp-for-blender` alongside it: both use port 9876, and the community one has telemetry on by default. |
| Blender version | **5.2 LTS** (supported until Jul 2028) | Scripts must follow the 5.x API: `use_nodes` is deprecated, the EEVEE engine id is `BLENDER_EEVEE`, and 5.2 moved Geometry Nodes modifier inputs to `mod.properties.inputs`. |
| Retopology | QuadriFlow (built in) → Instant Meshes (permissive, batch CLI, Windows binaries) → QRemeshify (GPL-3 Blender extension, cleanest quads) | Machine-learning retopology is still research-grade. |
| CC0 models and textures | Poly Haven (free API), ambientCG (API v3), Kenney, Quaternius and KayKit (bulk downloads), Poly Pizza (needs an API key) | All CC0 except Poly Pizza, which mixes CC0 and CC-BY, so the ledger stores attribution per model. The Poly Haven API requires a unique User-Agent. |
| Image-to-3D, local | 8 GB GPU: **TripoSG** (MIT, untextured; our bake pipeline adds textures). 24 GB+: **TRELLIS.2** (MIT, PBR output). The Modly desktop app runs both on Windows. | ⚠ License traps. The default background removers (RMBG-1.4 and 2.0) are non-commercial. TRELLIS's GLB export uses nvdiffrast, which is research-only. Both have to be swapped out. Hunyuan3D 2.x forbids use in the EU, UK and South Korea. SAM 3D needs 32 GB and Linux, and outputs splats rather than game meshes. |
| Image-to-3D, paid | **Meshy**: API from $20/mo; smart topology (100–15k faces), quads, PBR, rigging. **Tripo**: face limits, quad and low-poly modes, auto-rig with Mixamo bone names, official Godot plugin. **Rodin Gen-2.5**: quads, PBR; API needs the $120/mo plan. | Check the output license for your plan; Meshy's free-plan output is CC BY 4.0. |

### 6.2 Sound

| Need | Recommended | Notes and licenses |
|---|---|---|
| Analysis and processing | librosa (ISC), pyloudnorm (MIT), numpy/scipy; **pedalboard** or **DawDreamer** (both GPL-3) for effects, VST3 hosting and MIDI rendering | The GPL covers the tools, not the audio they render. Importing them in-process means this toolkit should be GPL-3.0 too (open decision, see §9). |
| Synths and instruments | Surge XT (GPL-3) and Vital (via the Vita Python bindings) hosted headlessly; **VSCO-2-CE** and **VCSL** (CC0 sample libraries); GeneralUser GS (SF2, free for commercial use) rendered with FluidSynth | Vital's factory presets can't be redistributed, so we ship our own presets. |
| Sound libraries | **Sonniss GDC bundles** (royalty-free, no attribution; 2026 bundle is 7.5 GB), **Kenney** audio (CC0), Freesound (manual downloads, CC0/CC-BY only) | ⚠ Sonniss license v2.0 bans using its sounds to develop, train or enhance AI, so they never go into generative models. Freesound's API is free only for non-commercial use, and its NC-licensed sounds must be filtered out. Pixabay bans bulk downloads, so it can't be indexed. |
| Reverb impulse responses | Voxengo (commercial use OK), EchoThief, OpenAIR (Creative Commons license per recording) | Real spaces for convolution reverb. |
| Critique models ("ears") | LAION-CLAP (CC0) or MS-CLAP (MIT) for text–audio match; **Meta Audiobox Aesthetics** (CC-BY-4.0) for production-quality scores; **MiDashengLM-7B** (Apache-2.0) to describe sounds in words | Audio Flamingo is non-commercial. The Qwen3-Omni captioner is ~60 GB, too big for most PCs. |
| SFX generation, local | **Stable Audio 3 Small-SFX** (~2 GB VRAM, up to 2 min, 44.1 kHz stereo; free commercial use under $1M annual revenue, registration required); **MOSS-SoundEffect v2** (Apache-2.0, 48 kHz, up to 30 s) | ⚠ Non-commercial, so avoid: MMAudio, TangoFlux, AudioX, ThinkSound, Woosh. HunyuanVideo-Foley carries Tencent's EU/UK/South Korea exclusion. |
| Music generation, local | **ACE-Step 1.5** (MIT, outputs usable commercially, 4–20 GB VRAM, Windows package); Magenta RealTime (instrumental, CC-BY-4.0 weights) | No local model produces seamless loops, so Music Studio loops them with DSP. MusicGen and YuE2 are non-commercial. |
| Voice (TTS) | **Qwen3-TTS** (Apache-2.0: design a voice from a text description, emotion instructions, cloning from 3 s); Chatterbox (MIT, watermarked), Dia (Apache-2.0, English only), Kokoro (Apache-2.0, no emotion control) | |
| Paid APIs | ElevenLabs Sound Effects (up to 30 s, loop option; commercial use from the $6 plan) | ⚠ Eleven Music's self-serve plans exclude monetized games, which need an Enterprise plan. |
| Godot audio | Target **Godot 4.7** (current stable) | `AudioStreamRandomizer` (pitch in semitones since 4.6); `AudioStreamInteractive` / `AudioStreamPlaylist` / `AudioStreamSynchronized` since 4.3, with beat- and bar-synced transitions; WAV and Ogg loop settings at import. |

### 6.3 Animation

| Need | Recommended | Notes and licenses |
|---|---|---|
| Motion libraries | **Quaternius Universal Animation Library 1 and 2** (CC0; free editions ~45 clips each, paid editions 120–130+), **Kenney** (CC0), **CMU mocap** (allowed in commercial products, but the data can't be resold), **100STYLE** (CC BY 4.0), Mixamo (free in games, no redistribution of raw files, manual download only) | **BONES-SEED** has 142k mocap clips, usable in commercial products by companies under $1M annual revenue, with attribution. ⚠ LAFAN1 and Bandai Namco are non-commercial. |
| Godot animation | Target **Godot 4.7**: BoneMap + `SkeletonProfileHumanoid` retargeting; AnimationTree; root motion; the `SkeletonModifier3D` family — `LookAtModifier3D` and `SpringBoneSimulator3D` (4.4), aim/copy constraints (4.5), the IK family `TwoBoneIK3D` / `FABRIK3D` / `CCDIK3D` / … with joint limits (4.6); `PhysicalBoneSimulator3D` ragdolls | Every runtime procedural layer in the plan is now built into the engine; no plugins needed. |
| Blender animation API | Slotted Actions (since 4.4); `action.fcurves` was removed in 5.0 | Keyframe Director writes through channelbags. Many older scripts and add-ons break on 5.x. |
| Rigging and retargeting | Our own game-rig templates (deform bones in one hierarchy, Godot humanoid names); **GameRig** (GPL-2.0) to make Rigify rigs game-ready; **Retarget** extension (GPL-3.0, maintained Expy Kit fork, Blender 5.0+); Robust Weight Transfer (GPL-3.0); Auto-Rig Pro (paid; has Godot humanoid naming) | Rigify alone doesn't export the clean deform hierarchy Godot needs. The Rokoko add-on likely breaks on Blender 5.x and requires a sign-in. |
| Auto-rig models | **UniRig** (MIT, ≥8 GB), **SkinTokens** (MIT, ≥14 GB; UniRig's successor), **Puppeteer** (Apache-2.0; skeleton, skinning and video-guided animation) | ⚠ Avoid RigAnything (non-commercial) and Make-It-Animatable (trained on Mixamo data, which Adobe forbids for machine learning). |
| Text-to-motion | **NVIDIA Kimodo-SOMA** (commercial use worldwide; clips up to 10 s; text plus pose and path constraints; BVH export; under 3 GB VRAM with the text encoder on CPU; Linux-first, Windows via Docker) | Needs the gated Llama 3 8B text encoder. Its model card admits foot skating, which our foot-lock cleanup targets. ⚠ HY-Motion's license bans using its output in the EU, UK and South Korea. MoMask, MDM and T2M-GPT weights are trained on AMASS, so they're non-commercial. |
| Video-to-motion | **SAM 3D Body** (commercial use OK; outputs Meta's Apache-2.0 MHR body model, no SMPL) + SAM-Body4D (MIT) for video; FreeMoCap (AGPL, multi-webcam); QuickMagic (commercial use from $14.90/mo) | ⚠ Anything that needs SMPL/SMPL-X model files (GVHMR, WHAM, PromptHMR) is non-commercial without a paid Meshcapade license. |

## 7. Roadmap

Phases follow dependencies, not just priority. The senses come first because every later
tool is tested with them, so a few P1 tools (Shape Kit, Material Lab, Rig Doctor) land in
Phase 3.

| Phase | Builds | Exit criteria |
|---|---|---|
| **0 · Foundation** | Plugin + marketplace skeleton, `userConfig`, Blender Bridge, Godot Bridge, Project Bible, Provenance Ledger, installer, eval baseline. | From any Godot project on the PC, Claude runs a Blender script (headless and live), imports the result into Godot and gets an in-engine capture back. Baseline eval outputs recorded. |
| **1 · Senses** | Look Dev Sheet, Mesh Lint, Audio Inspector, Motion Inspector, Audition Board, critic subagents. | Every asset type has a perceive step with numeric checks; eval tasks re-run with the loop. |
| **2 · Quick wins** | Asset Librarian, SFX Library + basic Forge, Motion Library + humanoid retarget, Godot Import Pipeline, Godot Look Presets, Audio Packager, Animation Wiring + game-feel library. | Eval tasks show a clear blind-rated improvement in all three domains. |
| **3 · Craft** | Shape Kit, Material Lab + Bake, full Sound Forge + Synth Recipe Book, Gen Audio (SFX + voice; cheap to run), Rig Doctor, Keyframe Director, Animation Events. | Procedural props/environments and stylized animation pass lint and critic review without hand fixes. |
| **4 · Generative** | `opus-gen`: Gen3D + cleanup, Gen Texture, auto-rig and mocap models — sized to the PC's GPU or to paid APIs. | Each backend sits behind the common interface and passes the same gates. |
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
2. Blender and Godot versions (the plan targets Blender 5.2 LTS and Godot 4.7); Godot
   renderer (Forward+ / Mobile / Compatibility).
3. Usual art styles and camera (first-person, third-person, top-down, …).
4. Will the games be sold? (Rules out non-commercial models and data.)
5. Budget for paid APIs, or local-only?
6. Which Claude surface on the PC: Claude Code CLI, the desktop app's Code tab, or desktop chat?
7. How much in the loop the user wants to be (audition checkpoints per asset vs per batch).
8. Which domain hurts most — where to start.
9. License for this toolkit: GPL-3.0 (simplest, since the best audio libraries are GPL),
   or MIT with every GPL tool kept in a separate process. Either way, the assets it
   produces are unaffected.
