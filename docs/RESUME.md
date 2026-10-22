# Where the overhaul stopped, and how to resume

Paused on 2026-10-22 at the user's request, during sprint S0b (the spec compiler core).

## Done and pushed

| Step | Where |
|---|---|
| Overhaul design for 3D models and animation | `docs/OVERHAUL.md` |
| v0.4 (S0a quick wins) and v0.4.1 (36 fixes found by the baseline) | `PLAN.md` §7 Progress |
| v0.4 baseline: 24 eval tasks in fresh sessions, each re-checked by an independent grader | `evals/results/v0.4.md`, `evals/results/v0.4.json` |
| S0b technical design, revised after three critic reviews | `docs/S0B_DESIGN.md` |

## In progress: S0b WP0 (shared contracts)

The last commit holds a **WP0 draft that has not been reviewed** (commit message starts with "WIP").
It contains the `compile/`, `gates/`, `spec/`, `tools/` packages, `extras.py`, the schemas,
`data/gates/profiles.json`, the CI stub, `.gitattributes`, and edits to `cli.py`, `mcp_server.py`,
`runner.py`, `runs.py`, `entry.py`, `paths.py`, `pyproject.toml` and `uv.lock`.

Test status of the draft: the full suite gives **270 passed, 1 failed, 1 skipped** (the skip is the
ANSUR rebuild, as before). Every v0.4.1 tool still passes its tests. The one failure is
`test_mcp.py::test_server_lists_tools_and_returns_images`: the server now also lists the new S0b
tool stubs (`spec_build`, `dims_resolve`, `export_asset`, ...), and the test's `EXPECTED` set has
not been updated yet. That update is part of WP0's unfinished test work.

Still missing from WP0 (S0B_DESIGN §17):
- the fixtures in `tests/fixtures/s0b/` and WP0's tests (`test_contracts`, `test_import_rules`,
  `test_tools_s0b`, the `EXPECTED` update in `test_mcp`, the Blender hash script);
- the "WP0 implementation notes" section at the end of `docs/S0B_DESIGN.md`;
- the conformance and regression reviews.

## Resume in this order

1. **Finish WP0.** Run `docs/harness/s0b_wp0.js` as a workflow. Its builder prompt already says to
   treat the existing WP0 files as an unreviewed draft. It then runs two reviews (design conformance;
   no v0.4.1 regressions) and a fix step.
2. **Build the eight packages** with `docs/harness/s0b_packages.js`, one workflow per group of
   packages, for example `["F","A","B"]`, `["E","C","D"]` and `["G","H"]`. Each package builds in its
   own git worktree.
3. **Integrate:** merge in the order F → A → B → E → C → D → G → H and run each package's exit test
   after its merge. Then do the integration phase (S0B_DESIGN §17): goldens, `armed.json`, and the
   A/B entry gate.
4. **A/B (S0B_DESIGN §19):** the six props (sword, axe, round shield, chest, barrel, chair), run with
   v0.4.1 against S0b using the same harness as the baseline (`docs/harness/baseline.js`,
   `evals/judge.py`, an independent grader per run). The v0.4 baseline measured v0.4.0; the A arm
   should be re-run on v0.4.1, so the only difference between arms is the compiler.

## Before resuming in a new cloud session

The scratch folder of this session (headless Blender, the frozen v0.4 copy, the baseline's asset
files) does not survive. To set it up again:
- Download Blender 5.2.2 for Linux into a scratch folder and set `OPUS_BLENDER` to its `blender`.
- The scripts in `docs/harness/` use this session's absolute scratch paths
  (`/tmp/claude-0/.../scratchpad`). Point the `SP` constant at the new scratch folder.
- To freeze a version for an eval arm: `git worktree add --detach <scratch>/v041 <commit>`, then
  `uv sync` in its `plugins/opus-tools/python`.

## Decisions waiting on the user

1. Does the no-generative-models rule also cover 2D (image-model pixel art with Z-Image, FLUX or
   PixelLab, and AI sprite animation)? Until answered, those stay in the plan but are not built.
2. A/B size: 3 runs per prop per arm as designed (about 42 builder sessions plus graders), or 2 to
   save usage (a noisier comparison).

## Usage note

Agent work in this session hit the account's usage limits three times, the weekly one last. One baseline
builder session took about 5–20 M input tokens (mostly cache reads), and a full
build-plus-review sprint about 10–20 M. Plan the S0b packages and the A/B around the limit
windows.
