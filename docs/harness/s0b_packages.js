export const meta = {
  name: 's0b-packages',
  description: 'S0b fan-out: build the given work packages from docs/S0B_DESIGN.md in isolated worktrees',
  phases: [{ title: 'Build', detail: 'one agent per work package, own worktree' }],
}

const SP = '/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad'
const BL = SP + '/blender/blender-5.2.2-linux-x64/blender'
const TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01CboCT4d2rpV2PoC5XN7UW6'

const NAMES = {
  F: 'WP-F — Data: fetch, tables, profiles',
  A: 'WP-A — Spec language, dims, templates, bible',
  B: 'WP-B — Compiler core',
  E: 'WP-E — Blender emit, finish, read-back, consistency task, export',
  C: 'WP-C — Raster, preview, consistency metrics',
  D: 'WP-D — Gates, defects, calibration',
  G: 'WP-G — spec_edit, acceptance, archive, joint solve, ledger',
  H: 'WP-H — CI, doctor, docs, A/B kit, mesh_lint / model_report additions',
}

const SCHEMA = {
  type: 'object',
  properties: {
    sha: { type: 'string' }, branch: { type: 'string' }, worktree: { type: 'string' },
    summary: { type: 'string' },
    exit_evidence: { type: 'array', items: { type: 'string' } },
    depends_on_unmerged: { type: 'array', items: { type: 'string' } },
    tests: { type: 'string' },
    open_issues: { type: 'array', items: { type: 'string' } },
    notes_for_integrator: { type: 'string' },
  },
  required: ['sha', 'branch', 'worktree', 'summary', 'exit_evidence', 'tests', 'open_issues'],
}

const pkgs = args || []
const out = await parallel(pkgs.map(k => () => agent(`You build one work package of sprint S0b (the spec compiler core, v0.5) of Opus Tools, in the git worktree that is your current working directory (repo Infamase/Opus-Tools; plugin code under plugins/opus-tools/). Opus Tools is a Claude Code plugin that helps Claude make game assets with headless Blender 5.2 for Unreal/Godot/Unity on the user's Windows PC.

Your package: ${NAMES[k]}.

The design is docs/S0B_DESIGN.md. Read ALL of it (long; do it), including the "WP0 implementation notes" at the end, which record decisions made when the shared contracts were written. WP0 (the contracts, stubs, fixtures, tools registry, CLI and MCP wiring) is already committed in your worktree; code against it exactly and do not edit WP0-owned files, except where §17 says your package takes over a stub (e.g. your tools/*.py module). Build your package exactly as §17 specifies: the files it owns, its tests and its exit. The broader design is docs/OVERHAUL.md (read the sections your package touches). Research digests with sources: ${SP}/research/*.md.

Other packages are being built in parallel worktrees and are merged afterwards in the order WP0 → F → A → B → E → C → D → G → H. Where your exit needs a package that is not in your worktree, use WP0's fixtures and stand-ins as §17 says, make your tests pass against them, and list in depends_on_unmerged which exit checks can only be confirmed after the merge (the integrator re-runs them).

Environment:
- Headless Blender 5.2.2: prefix commands that run Blender or Blender tests with OPUS_BLENDER=${BL}.
- Tests: cd plugins/opus-tools/python && OPUS_BLENDER=${BL} uv run --group dev pytest -q <tests>. Keep pytest -m "not blender" green; Blender tests behind the blender marker. 4 CPUs are shared with other package builders: run targeted tests while iterating and the full suite once at the end; re-run an unrelated failure once before concluding.
- Network goes through an HTTPS proxy (museum APIs, Wikidata, Wikipedia, Blender/Godot downloads are reachable). Downloads go to a cache under ${SP}/s0b/cache/ (never committed).
- Windows is the target: pathlib, explicit encodings, list-form subprocess.
- Probes and scratch under ${SP}/s0b/${k}/.

Conventions: match the surrounding code (comment density, naming, idiom). No new dependencies beyond what WP0 put in pyproject. Do not edit README.md, PLAN.md, docs/OVERHAUL.md or other packages' files unless §17 gives them to you. If you find a real defect in a WP0 contract, do not edit the contract: work around it minimally and describe it in notes_for_integrator.

When done: commit in this worktree (git add -A; git commit) with a message whose last two lines are exactly:
${TRAILER}
Do not push. Report: sha, branch, absolute worktree path, summary, exit evidence with measured numbers, depends_on_unmerged, test counts, open issues, notes for the integrator.`, { label: 'wp-' + k, phase: 'Build', schema: SCHEMA, isolation: 'worktree' })
  .then(r => r ? { pkg: k, ...r } : null)))

return out.filter(Boolean)
