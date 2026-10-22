export const meta = {
  name: 's0b-wp0-contracts',
  description: 'S0b WP0: shared contracts before fan-out, then an adversarial conformance review and fixes',
  phases: [
    { title: 'Build', detail: 'WP0 contracts, stubs, packaging, fixtures' },
    { title: 'Review', detail: 'conformance to S0B_DESIGN §4, §15, §16, §17 WP0' },
    { title: 'Fix', detail: 'apply confirmed findings' },
  ],
}

const SP = '/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad'
const BL = SP + '/blender/blender-5.2.2-linux-x64/blender'
const REPO = '/home/user/Opus-Tools'
const TRAILER = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01CboCT4d2rpV2PoC5XN7UW6'

const CONTEXT = `Opus Tools (repo ${REPO}, branch claude/game-dev-tools-plan-cbtolh, main checkout) is a Claude Code plugin that helps Claude make game assets with headless Blender 5.2 for Unreal/Godot/Unity on the user's Windows PC. Plugin code: plugins/opus-tools/. v0.4.1 is the current release. Sprint S0b (the spec compiler core, v0.5) is designed in docs/S0B_DESIGN.md, which was reviewed by three critics and revised; it builds on docs/OVERHAUL.md. Headless Blender: OPUS_BLENDER=${BL}. Tests: cd plugins/opus-tools/python && OPUS_BLENDER=${BL} uv run --group dev pytest -q (the full suite takes about 13 minutes; run targeted tests while iterating). The machine has 4 CPUs. Probes and scratch files go under ${SP}/s0b/. Do not touch ${SP}/v04 or ${SP}/evals.`

phase('Build')
const wp0 = await agent(`${CONTEXT}

You are the WP0 integrator for S0b. A previous WP0 attempt was cut off by a usage limit and left uncommitted work in the checkout (git status shows modified cli.py, mcp_server.py, runner.py, runs.py, entry.py, paths.py, pyproject/uv.lock, plugin.json, and new compile/, gates/, spec/, tools/, extras.py, data/gates/, data/schema/, .github/, .gitattributes). Treat it as an unreviewed draft: check each file against the design, keep what is right, fix or finish the rest. Read docs/S0B_DESIGN.md in full (it is long; read all of it, the contracts in §4 above all), then build WP0 exactly as §17 "WP0 — Contracts" specifies: every file it owns, written VERBATIM from the §4 contract code where the doc gives code (EvalMesh, the .npz exchange format, hashes, conventions and raster rules, fmath, expr grammar, measure, kinds, Finding contract and registry, resolved spec TypedDicts, extras), the six/eleven tools/*.py stubs and the tools registry, the CLI groups and MCP wiring of §4.9/§15 (the restructure of mcp_server.py and cli.py into opus/tools/* modules, keeping every existing v0.4.1 tool and CLI command working with the same names and arguments), the hooks in opus_bl/entry.py, blender/runner.py and runs.py, paths.safe_name, pyproject (pydantic direct dependency, ruff dev dependency, the optional extras of §16, version 0.5.0.dev0 or as the doc says) and uv.lock, .gitattributes, the .github/workflows/ci.yml stub, the JSON schemas, data/gates/profiles.json, and the tests and fixtures (tests/fixtures/s0b/) listed for WP0.

Where the doc is ambiguous or a detail turns out wrong when you implement it, choose the option most consistent with the rest of the doc, and record each such decision in a new section "WP0 implementation notes" at the end of docs/S0B_DESIGN.md (the other packages read it). Do not start any other package's work.

Exit (from §17): eval_hash(fixture_boxes()) stable across two processes and equal inside Blender (a script under tests/blender_scripts/); save_npz/load_npz round trips with frames, fields and extra; quads_to_tris output passes validate() and a reordered layout fails it; Finding JSON (with numpy scalars) validates against its schema; expr accepts §4.4 and rejects attribute access outside the whitelist, lambdas, subscripts and comparisons; project reproduces the §2 probe masks; registry rejects duplicates, armed() follows K8, load_checks tolerates a missing module; the stubs register and every CLI verb of §15 parses; log_if_open is a no-op without a run; ruff check clean (as configured); the import-rule AST test (compile and gates import only numpy/stdlib). The full existing suite must stay green (v0.4.1 has 271 passing tests). The CI stub cannot be run from here: write it, and say what the user must do if pushing it needs extra permission.

Commit in ${REPO} on the branch (message ends with exactly:
${TRAILER}
). Do not push. Report: sha, files created, test counts (full suite), the implementation-note decisions, and anything a later package must know.`, { label: 'wp0', phase: 'Build' })

phase('Review')
const REVIEW = { type: 'object', properties: { findings: { type: 'array', items: { type: 'object', properties: {
  file: { type: 'string' }, line: { type: 'integer' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
  summary: { type: 'string' }, failure_scenario: { type: 'string' }, evidence: { type: 'string' } },
  required: ['file', 'severity', 'summary', 'failure_scenario', 'evidence'] } } }, required: ['findings'] }
const reviews = await parallel([
  ['conformance', 'CONFORMANCE: compare every WP0 file with docs/S0B_DESIGN.md §4 (and §4.9, §4.10, §15, §16, §17 WP0) line by line: names, signatures, dtypes, units, frames, hash definitions, raster conventions, schema fields, error behaviour. Any deviation that would make a package built from the doc not fit (unless it is recorded in "WP0 implementation notes" with a sound reason) is a finding. Check that the WP0 implementation notes themselves are consistent with the rest of the doc.'],
  ['regression', 'REGRESSION AND ROBUSTNESS: the restructure of mcp_server.py and cli.py must keep every v0.4.1 MCP tool and CLI command with identical names, arguments and outputs (compare against git show HEAD~1 versions, start the MCP server over stdio and call a sample of old tools, run old CLI commands). Check the determinism claims (hash equality host vs Blender; run the Blender script), the import-rule test, Windows path handling (safe_name), and that the full suite is green.'],
].map(([k, lens]) => () => agent(`${CONTEXT}

Review the WP0 commit just made on the branch (git show --stat HEAD; git diff HEAD~1). Lens: ${lens}
Reproduce before reporting (probes under ${SP}/s0b/wp0_review/). Do not edit the repo. Report concrete problems with evidence; an empty list is fine.`, { label: 'review:' + k, phase: 'Review', schema: REVIEW }).then(r => ({ k, r }))))
const findings = reviews.filter(Boolean).flatMap(x => (x.r ? x.r.findings : []).map(f => ({ lens: x.k, ...f })))

let fix = null
if (findings.length) {
  phase('Fix')
  fix = await agent(`${CONTEXT}

Review findings on the WP0 commit (HEAD of the branch):
${findings.map((f, i) => i + ': ' + JSON.stringify(f)).join('\n')}

For each: reproduce; fix the ones that reproduce at the root cause (contract fixes must also update docs/S0B_DESIGN.md's WP0 implementation notes so the packages built from the doc stay consistent); reject the rest with a reason. Run the full suite. Commit once (message ends with exactly:
${TRAILER}
). Do not push. Report fixed, rejected, test counts and the final sha.`, { label: 'fix', phase: 'Fix' })
}
return { wp0, findings, fix }
