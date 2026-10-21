# Downloads

This repo holds code only. Everything big is listed here for you to download yourself,
when its phase arrives. `opus doctor` reports what's installed and what's missing.

Sizes marked "check page" haven't been verified yet; they get filled in before each phase.

For 3D models and animation, the full list of data packs (measured tables, mocap, CC0
bodies and kits, elevation data) is in [docs/OVERHAUL.md](docs/OVERHAUL.md) §7.2. They are
fetched sprint by sprint with `data_fetch`, which records each pack's licence. No
generative model is used for 3D or animation.

## Needed now (Phase 0–1)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| **uv** | Runs the toolkit's Python and installs its few dependencies automatically | small | MIT / Apache-2.0 | `winget install --id=astral-sh.uv -e` ([docs](https://docs.astral.sh/uv/getting-started/installation/)) |
| Blender 5.2 LTS | Look Dev Sheet and Mesh Lint run in it headlessly | already installed | GPL | — |
| Godot 4.7.2 | Engine-side tools (from Phase 2) | already installed | MIT | — |

## Later phases: don't download yet

### Local AI hub (2D and audio only; pending your decision on 2D)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| ComfyUI (Windows portable or Desktop) | One local server for the image and audio models below; the toolkit drives it over HTTP | check page | GPL-3.0 | [comfy.org/download](https://www.comfy.org/download) |

### Pixel art (Phase 2; the image models wait on your decision about 2D generation)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Z-Image-Turbo | Local image model; fits in 16 GB | check page | Apache-2.0 | [Hugging Face](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo) |
| FLUX.2 [klein] 4B | Alternative image model with multi-reference editing (on-model characters) | ~13 GB | Apache-2.0 | [Hugging Face](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) |
| Pixel-art LoRAs | Push those models toward pixel art | small | Apache-2.0 | [Z-Image](https://huggingface.co/tarn59/pixel_art_style_lora_z_image_turbo) · [klein](https://huggingface.co/Limbicnation/pixel-art-lora) |
| PixelLab *(paid, optional)* | 4/8-direction characters, animation, tilesets; API + MCP | $5–50 / month | commercial service | [pixellab.ai](https://www.pixellab.ai) |

### 3D (Phase 2)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Human-made model and texture packs | Style references, lineups, kitbash parts, materials | per pack | Kenney, Poly Haven, ambientCG: CC0. KayKit: per page. Quaternius: QAL v1.0 (recorded per pack) | [Kenney](https://kenney.nl/assets) · [Quaternius](https://quaternius.com) · [KayKit](https://kaylousberg.itch.io) · [Poly Haven](https://polyhaven.com) · [ambientCG](https://ambientcg.com) |

### Animation (Phase 3)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Quaternius Universal Animation Library 1 & 2 | Humanoid animations ready for retargeting | per pack | recorded per pack from the page | [itch.io](https://quaternius.itch.io/universal-animation-library) |
| CMU, 100STYLE, ACCAD, Bandai Namco mocap | Clips, gait statistics, combat poses | per set | see docs/OVERHAUL.md §7.2 | fetched by `data_fetch` when S5 starts |
| Mixamo clips *(optional)* | More humanoid animations, manual download only | per clip | revocable preview terms | [mixamo.com](https://www.mixamo.com) |

### Sound (Phase 4)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Sonniss GDC 2026 bundle | Royalty-free recorded SFX to layer and process | 7.47 GB | Sonniss license (no AI training) | [sonniss.com](https://sonniss.com/gameaudiogdc) |
| Kenney audio packs | Small CC0 SFX sets | small | CC0 | [kenney.nl](https://kenney.nl/assets?q=audio) |
| Stable Audio 3 Medium, ACE-Step 1.5, Qwen3-TTS | Local SFX, music and voices | check page | Stability Community / MIT / Apache-2.0 | added when Phase 4 starts |

## Disk budget

You have about 100 GB free. The plan is to stay well under that. 3D and animation data
needs under 50 MB for the core tables, 5–10 GB for a typical library and at most about
15 GB with all of CMU and 100STYLE. Each phase adds only what that phase needs, and
`opus doctor` will show what's using the space.
