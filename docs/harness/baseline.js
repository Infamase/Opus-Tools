export const meta = {
  name: 'eval-baseline-v04',
  description: 'Run eval tasks on frozen v0.4 in fresh builder sessions, then grade every hard check independently',
  phases: [
    { title: 'Build', detail: 'one fresh session per task, following the eval protocol' },
    { title: 'Grade', detail: 'independent re-check of every hard check' },
  ],
}

const SP = '/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad'
const BL = SP + '/blender/blender-5.2.2-linux-x64/blender'
const V04 = SP + '/v04'
const PROJ = SP + '/evals/v0.4'
const LABEL = 'v0.4'
const OPUS = `uv run --project ${V04}/plugins/opus-tools/python opus`

const ENV = `Environment (a Linux cloud stand-in for the user's Windows PC):
- Work only in ${PROJ}/<task id>/ (create it). The eval project root is ${PROJ} (it holds opus.project.yaml; the run ledger goes to ${PROJ}/.opus/runs/). Never read or touch other tasks' folders.
- Opus Tools v0.4 is installed. The MCP tools named in the protocol are the same functions as this CLI: ${OPUS} <command> (see "${OPUS} --help" and "<command> --help"). Prefix every command with OPUS_BLENDER=${BL} OPUS_PROJECT_DIR=${PROJ}. MCP name -> CLI: run_log -> run-log, run_stats -> run-stats, mesh_lint -> lint, model_report -> report, proportion_check -> proportion, reference_match -> refmatch, blind_read_sheet -> blind, readability_check -> readability, look_at -> look, lookdev_sheet -> lookdev, body_blockout -> body, grip_define -> grip-define, grip_hold -> hold, grip_check -> grip-check, sprite_inspect -> inspect, pixel_cleanup -> cleanup, palette_ramp -> ramp, lineup_sheet -> lineup, ab_sheet -> ab, project_bible -> bible. Tools with no CLI command (palette_apply, palette_swap, ledger_record) may be called through the Python API: ${V04}/plugins/opus-tools/python/src/opus (uv run --project ... python -c ...).
- Blender 5.2.2 headless for your own scripts: ${BL} -b --factory-startup --python <script.py> -- <args>. Write scripts in your task folder.
- The plugin's skills load when relevant: read ${V04}/plugins/opus-tools/skills/3d-modeling/SKILL.md now and follow it as a loaded skill (and ${V04}/plugins/opus-tools/skills/pixel-art/SKILL.md for sprite work).
- Where the protocol says "a fresh art-director subagent", run: python3 ${V04}/evals/judge.py blind --image <sheet> --prompt-file <file holding the prompt the blind tool printed> --names "<the protocol's accepted names>" --log ${PROJ}/<task id>/judges.jsonl  (or: judge.py checklist --image <render> [--image ...] --question "..." [--question ...] --log ...; or judge.py letter for lineup or A/B sheets). It starts a separate fresh session that sees only the renamed images and the questions. Use its JSON verdict; do not second-guess it.
- Treat Opus Tools as installed software: do not read its source, its tests, docs/, PLAN.md, the evals/ specs or README, or anything else in ${V04} beyond the two skill files, the art-director agent file and --help output.
- The user is not available. If you would ask them something the brief does not answer, it is "your call": decide and note it.
- Network: an HTTPS proxy is configured; references (PhyloPic, Wikimedia, lospec palettes) can be downloaded into refs/ in your task folder.`

const BUILD_SCHEMA = {
  type: 'object',
  properties: {
    task: { type: 'string' }, run_id: { type: 'string' },
    status: { type: 'string', enum: ['accepted', 'abandoned'] },
    rounds: { type: 'integer' }, judge_rounds: { type: 'integer' }, validator_rejections: { type: 'integer' },
    minutes: { type: 'number' },
    final_files: { type: 'array', items: { type: 'string' } },
    values: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['task', 'status', 'rounds', 'final_files', 'values', 'notes'],
}
const GRADE_SCHEMA = {
  type: 'object',
  properties: {
    task: { type: 'string' },
    accepted_by_grader: { type: 'boolean' },
    checks: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, class: { type: 'string' }, value: { type: 'string' }, pass: { type: 'boolean' }, how: { type: 'string' } },
      required: ['id', 'class', 'value', 'pass', 'how'] } },
    discrepancies: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['task', 'accepted_by_grader', 'checks', 'discrepancies', 'notes'],
}

const tasks = args || []
log(`baseline ${LABEL}: ${tasks.join(', ')}`)

const results = await pipeline(tasks,
  id => agent(`You are a fresh Claude Code session on a game developer's PC. The user has the Opus Tools v0.4 plugin installed and has just sent the message below (it ends with an eval protocol, which you follow exactly). The user's label for this run is "${LABEL}".

${ENV}

The user's message is the output of this command; run it first and treat its text as the message:
  cd ${V04}/plugins/opus-tools/python && uv run opus eval prompt ${id}

Work the way a careful session would: plan, build, check with the tools, fix, and log every event the protocol asks for with run-log (--dir ${PROJ} if the command needs it). Respect the caps (10 check rounds, 2 judge rounds without a pass, 90 minutes from your run_start; check the clock with date). Finish with accept or abandon logged.

Report: task id, the run id from the ledger, accepted or abandoned, check rounds, judge rounds, validator rejections, minutes, the final asset files (absolute paths), the values string you logged, and short notes (what was hard, which tools helped or got in the way, any "your call" decisions).`, { label: `build:${id}`, phase: 'Build', schema: BUILD_SCHEMA }),
  (built, id) => agent(`You grade one eval run independently. Task: ${id}. The task spec is ${V04}/evals/tasks/${id}.yaml (read it; "accepted" means every check with class: hard passes). The builder session's final files are in ${PROJ}/${id}/ and it reported:
${JSON.stringify(built)}

${ENV.replace('Work only in', 'Read the builder\'s files in').replace('(create it)', '')}
You MAY read the task spec YAML (that is your job here), but still not the tool source.

Re-run EVERY hard check yourself on the final asset files, with the exact tool and arguments in the spec (the CLI equivalents above). For probe checks, write your own probe scripts from each check's "measure" text (in ${PROJ}/${id}/_grader/); never reuse the builder's probes. For blind-read and checklist hard checks make exactly one fresh judge.py call each, with --log ${PROJ}/${id}/_grader/judges.jsonl. Also run the soft checks once and record them. Never modify the builder's files: copy anything a tool would write into ${PROJ}/${id}/_grader/ first. Do not log anything to the run ledger.

Report per check: id, class, measured value, pass, and how you measured it; accepted_by_grader (true only if every hard check passes); discrepancies between your results and the builder's claims; notes.`, { label: `grade:${id}`, phase: 'Grade', schema: GRADE_SCHEMA })
    .then(g => ({ id, built, graded: g })))

return results.filter(Boolean)
