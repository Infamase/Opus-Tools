# Downloads

This repo holds code only. Everything big is listed here for you to download yourself,
when its phase arrives. `opus doctor` reports what's installed and what's missing.

Sizes marked "check page" haven't been verified yet; they get filled in before each phase.

## Needed now (Phase 0–1)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| **uv** | Runs the toolkit's Python and installs its few dependencies automatically | small | MIT / Apache-2.0 | `winget install --id=astral-sh.uv -e` ([docs](https://docs.astral.sh/uv/getting-started/installation/)) |
| Blender 5.2 LTS | Look Dev Sheet and Mesh Lint run in it headlessly | already installed | GPL | — |
| Godot 4.7.2 | Engine-side tools (from Phase 2) | already installed | MIT | — |

## Later phases: don't download yet

### Local AI hub (Phase 2+)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| ComfyUI (Windows portable or Desktop) | One local server for the image, 3D, motion and audio models below; the toolkit drives it over HTTP | check page | GPL-3.0 | [comfy.org/download](https://www.comfy.org/download) |

### Pixel art (Phase 2)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Z-Image-Turbo | Local image model; fits in 16 GB | check page | Apache-2.0 | [Hugging Face](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo) |
| FLUX.2 [klein] 4B | Alternative image model with multi-reference editing (on-model characters) | ~13 GB | Apache-2.0 | [Hugging Face](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) |
| Pixel-art LoRAs | Push those models toward pixel art | small | Apache-2.0 | [Z-Image](https://huggingface.co/tarn59/pixel_art_style_lora_z_image_turbo) · [klein](https://huggingface.co/Limbicnation/pixel-art-lora) |
| PixelLab *(paid, optional)* | 4/8-direction characters, animation, tilesets; API + MCP | $5–50 / month | commercial service | [pixellab.ai](https://www.pixellab.ai) |

### 3D (Phase 2)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| trellis.cpp (TRELLIS.2) | Image-to-3D on a 16 GB card, Windows CUDA builds | check page | MIT | [GitHub](https://github.com/pwilkin/trellis.cpp) |
| CC0 model and texture packs | Starting points and kitbash parts | per pack | CC0 | [Kenney](https://kenney.nl/assets) · [Quaternius](https://quaternius.com) · [KayKit](https://kaylousberg.itch.io) · [Poly Haven](https://polyhaven.com) · [ambientCG](https://ambientcg.com) |

### Animation (Phase 3)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Quaternius Universal Animation Library 1 & 2 | Humanoid animations ready for retargeting | per pack | CC0 | [itch.io](https://quaternius.itch.io/universal-animation-library) |
| Mixamo clips | More humanoid animations (manual download) | per clip | free to use in games | [mixamo.com](https://www.mixamo.com) |
| Motion models via ComfyUI (Kimodo, SAM 3D Body) | Text-to-motion; motion capture from phone video | check page | NVIDIA Open Model / SAM License | added when Phase 3 starts |

### Sound (Phase 4)

| What | Why | Size | License | Get it |
|---|---|---|---|---|
| Sonniss GDC 2026 bundle | Royalty-free recorded SFX to layer and process | 7.47 GB | Sonniss license (no AI training) | [sonniss.com](https://sonniss.com/gameaudiogdc) |
| Kenney audio packs | Small CC0 SFX sets | small | CC0 | [kenney.nl](https://kenney.nl/assets?q=audio) |
| Stable Audio 3 Medium, ACE-Step 1.5, Qwen3-TTS | Local SFX, music and voices | check page | Stability Community / MIT / Apache-2.0 | added when Phase 4 starts |

## Disk budget

You have about 100 GB free. The plan is to stay well under that: the AI hub and models
take the most, libraries much less. Each phase adds only what that phase needs, and
`opus doctor` will show what's using the space.
