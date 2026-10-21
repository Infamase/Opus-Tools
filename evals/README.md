# Eval suite

24 fixed asset tasks that measure how much trial and error it takes Claude, with Opus Tools,
to get an asset right. **v0.4 is the baseline.** Every later sprint runs the same tasks and is
compared with it (docs/OVERHAUL.md §1 and §9).

The measures come from the run ledger: iterations to a hard pass, validator rejections, judge
rounds, tokens and wall-clock per asset. Taste is measured separately, by the user's blind A/B.

Only task specs (`tasks/*.yaml`), score summaries (`results/<label>.json`) and a short note on
each set (`results/<label>.md`) are committed. Assets, renders, references, ledgers and
transcripts stay on the PC; `.gitignore` here keeps everything else out. The v0.4 baseline is
`results/v0.4.json`, with `results/v0.4.md`.

## The tasks

| Group | Tasks |
|---|---|
| Regression subjects (8) | `knight`, `goblin`, `wolf`, `dragon`, `chest`, `barrel`, `house`, `sword` |
| Characters | `human_hd` (HD human), `chibi_lowpoly` (stylized, low-poly, chibi) |
| Clothing, armor | `peasant_outfit`, `plate_armor` |
| Weapons | `fp_rifle` (first person, two-handed hold), `axe`, `round_shield` |
| Props | `chair` |
| Creatures | `horse` (quadruped), `crow` (flyer, pixel sprites rendered from 3D) |
| Landscape, foliage | `forest_valley`, `pine_trees` |
| Animation | `walk_cycle`, `wolf_trot`, `sword_attack`, `chest_open` |

S3 judges blind reads and the user's A/B on the 8 regression subjects. S0b's A/B uses `sword`,
`axe`, `round_shield`, `chest`, `barrel` and `chair`.

```
opus eval list               # the tasks
opus eval validate           # every spec, plus the suite's coverage
opus eval prompt knight      # what to paste into a fresh session
```

Run these from `plugins/opus-tools/python` in a clone (`uv run opus eval ...`). A marketplace
install carries only the plugin folder; set `OPUS_EVALS_DIR` to a clone's `evals` folder there.

## A task spec

| Field | Meaning |
|---|---|
| `id`, `title` | The file is `tasks/<id>.yaml` |
| `category` | character, clothing, armor, weapon, prop, building, creature, landscape, foliage, animation |
| `regression` | `true` for the 8 regression subjects |
| `covers` | Coverage tags such as `hd_human`, `chibi`, `first_person`, `two_handed`, `quadruped`, `flyer`, `walk_cycle` |
| `brief` | What the user would type. Pasted verbatim |
| `style` | `lowpoly`, `hd`, or `pixel` (rendered from 3D) |
| `engine` | `unreal` by default, some `godot` |
| `camera` | An `opus.camera` profile and the distances in m it is checked at (`sprite_px` for pixel tasks) |
| `references` | `[]`, or CC0 and public-domain URLs. Downloaded into the eval project's `refs/` when needed, never committed |
| `budgets` | Triangles, materials, bones, texture size, frames |
| `accept` | The checks. **Accepted means every `hard` check passes** |
| `score` | The fields recorded for the run: the 10 ledger fields below plus the task's own |

A check is `{id, tool, args, metric, op, value, class}`, plus `names` for a blind read,
`questions` for a checklist, `measure` for a probe, and an optional `note`. `op` is one of
`==`, `!=`, `<=`, `>=`, `<`, `>`, `between [low, high]` or `in [...]`. Quote YAML values that
contain commas inside `{...}`; the validator rejects the stray keys an unquoted comma makes.

Classes follow §2.5: `hard` blocks acceptance; `soft` is recorded (readability floors,
`proportion_check` until it is percentile-based in S1, and other uncalibrated heuristics stay
soft); `report` is only reported.

Checks use only tools that exist in v0.4:

| Tool | Metrics |
|---|---|
| `mesh_lint` | `errors` (error findings), `findings` (one code's count, `args.code`), `tris` |
| `model_report` | From `report["metrics"]`: `floating_parts`, `penetrations` (entries in its penetrations list), `on_floor`, `com_over_footprint`, `symmetric`, `rig_style`, `width_m` (X), `length_m` (Y), `height_m` (Z), `longest_m`. `missing_contacts` (parts that should touch and don't) is the number of pairs the check's `note` requires that are absent from `report["contacts"]` |
| `proportion_check` | `closest_canon`, `unintended_findings` (findings the brief does not declare as stylization) |
| `reference_match` | `iou`, against the task's first reference |
| `readability_check` | `defining_under_floor` (defining parts under the pixel floor, gone, or not found: any `defining` entry whose status is not `ok`, including names in `defining_not_found`), `subject_px` |
| `blind_read_sheet` | `top1_names_subject`: a fresh judge's top guess is one of `names` |
| `grip_check` | `verdict` (`good grip`), `body_clipping_verts` |
| `sprite_inspect` | `semi_transparent_pixels`, `strays`, `off_palette_pixels`, `color_count`, `jaggy_elbows`, `colors_not_in_every_frame` |
| `art_director` | `checklist_no`: No or Unclear answers to 2–5 yes/no questions |
| `probe` | A short Blender script for what no v0.4 tool measures yet (foot skate, loop seams, hinges, grid seams); `measure` says how |

## Running a set

1. Make one eval project outside the repo, for example `D:\opus-evals\v0.4`, and run
   `project_bible init` there. Each task's assets go in a subfolder named after the task.
2. Use the same model and plugin version for the whole set. For each task, start a fresh
   Claude Code session in the eval project and paste `opus eval prompt <id>`, adding the label
   ("label v0.4"). The prompt is the brief followed by the protocol: Claude logs `run_start`,
   an `iteration` after every round of hard checks, each `judge_round` and
   `validator_rejection`, and `accept` or `abandon`.
3. Don't steer. If Claude asks something the brief doesn't answer, reply "your call".
4. Judges (blind reads, checklists) are fresh `art-director` subagents that see only the sheet
   and the questions, never file names or the brief. "Unclear" counts as No.
5. Caps: 10 check rounds, 2 judge rounds without a pass, 90 minutes. Then `abandon`.
6. Tokens: `opus eval tokens <session transcripts> --log --run <run id> --dir <eval project>`.
   Transcripts are under `%USERPROFILE%\.claude\projects\<eval project folder name>\`; input
   counts fresh, cache-write and cache-read tokens.
7. `opus eval summarize v0.4 --runs D:\opus-evals\v0.4` writes `results/v0.4.json`. Commit that
   file and a short `results/v0.4.md` note (per-task table, failures, anything that skews the
   numbers); nothing else from the run.

### Without a desktop session (cloud or batch)

`judge.py` stands in for the fresh art-director subagent. Each call starts a new headless
`claude -p` session in an empty folder holding only the images, renamed `image1.png`, ...,
with the art-director instructions appended and no MCP servers, settings or file names:

```
python evals/judge.py blind --image <sheet> --prompt-file <prompt> --names "wolf|dog" --log judges.jsonl
python evals/judge.py checklist --image <render> --question "..." --question "..."
python evals/judge.py letter --image <lineup or A/B sheet> --prompt-file <prompt>
```

It prints the verdict (`top1_names_subject`, `checklist_no` or the letter) with the judge's
token usage. A cloud run freezes the plugin at the label's commit (a git worktree), gives each
task a fresh builder session and then an independent grader that re-runs every hard check
with its own probes; the grader's verdict decides `accepted`. Log it for the builder's run:

```
opus run-log grade accepted=false "failed=blind_read" "note=fresh judge: female character" --run <run id> --dir <eval project>
```

`failed` lists the hard check ids the grader failed; they count in the failure histogram.

## Scoring

Per run, from the ledger (`<project>/.opus/runs/<date>.jsonl`):

| Field | Meaning |
|---|---|
| `accepted` | Every hard check passed within the caps: the run closed with `accept` and, when it has a `grade`, the last grade accepts it (`self_accepted` is the builder's own accept) |
| `iterations_to_hard_pass` | The first check round with no hard failure |
| `iterations_to_accept` | Check rounds when accepted |
| `hard_fail_count_first` | Hard failures in the first round |
| `validator_rejections` | Rejected tool calls in v0.4; `spec_validate` rejections from S0b on |
| `judge_rounds`, `user_rejections` | Counted per run |
| `wall_clock_s` | From `run_start` to `accept` (or to the last event) |
| `tokens_input`, `tokens_output` | From the session transcripts |

A task's own score fields (`blind_read_top1`, `grip_verdict`, `foot_skate_cm`, ...) go in the
`values` of the accept or abandon event. Summaries keep the median of numbers and a count per
answer for anything else.

A summary holds medians per task and overall, a histogram of failing checks and rejections,
the suite hash, tool versions and models. A run that never reached a hard pass counts as worse
than any number, and a median that lands on one is `null`. No paths or assets go into it.

## Comparing sprints

```
opus eval compare v0.4 s3
```

Per task, the median iterations to a hard pass in both result files, the tasks where the new
set is lower, higher or tied, and a one-sided sign test. Lower on 17 or more of 24 gives
p ≈ 0.03: the S3 exit and the §9 cut rule.
