# S0b design: compiler core (v0.5)

Status: technical design, revision 2 (2026-10-21), after three reviews (completeness, interfaces,
feasibility); the review log at the end lists every point and what was done. Governing document:
[OVERHAUL.md](OVERHAUL.md) (§9 row S0b). This document is what 8 implementation agents build from in
parallel worktrees. Where it and OVERHAUL differ, OVERHAUL sets the goals and this document sets the
interfaces; §0 lists every deliberate deviation and the decisions the user must take before WP0.

How to use it:
- **WP0 (the contract commit, §4) lands first**, made by the integrator verbatim from §4. Every work
  package branches from it. Nobody edits a contract file in a package branch; a needed change goes to
  the integrator, who amends WP0 and tells every package.
- Each package owns the files listed for it in §17 and nothing else. Two packages never edit one file.
  WP0 creates some files as stubs that a package then owns (§17 says which).
- Exits are of two kinds: a **package exit** a package meets on its own branch (rebased on the merges
  before it), and an **integration exit** that needs later packages and runs in the integration phase
  after the last merge (§17).
- Numbers that came from a probe are marked **(probed)**; §2 lists the probes.

---

## 0. Key decisions

| # | Decision | Why |
|---|---|---|
| K1 | **pydantic 2 becomes a direct host dependency, pinned `pydantic>=2.11,<3`** (2.13.5 is already in the venv through `mcp`). Only `opus.spec.model`, `schema`, `validate` and `templates` import it. `opus/spec/__init__.py` is empty and may never import anything. `opus.compile`, `opus.gates.{finding,registry,geom,t2}` import only the standard library, numpy, `opus.paths` and `opus.camera`, because Blender's Python must import them. An AST test enforces both rules (§3). | Blender 5.2.2 ships Python 3.13.13 + numpy 2.3.4 and no pydantic **(probed)**; a package `__init__` that imports pydantic breaks every submodule import in Blender **(probed by the interfaces review)** |
| K2 | The compiler consumes a **resolved spec**: a plain-JSON dict whose TypedDicts live in `opus/compile/resolved.py` (§4.8), produced by `dims_resolve`. Pydantic models never cross into compile. | K1; the compile is a pure function of one JSON file |
| K3 | **Determinism is promised per machine:** the same spec, seed and `tables_version` hash identically on the host and inside Blender on the same computer. Across machines only the resolved JSON is promised (to 1e-12 relative). Geometry code uses numpy only for `+ − × ÷`, `sqrt`, `abs`, `floor`/`ceil`/`rint`, `minimum`/`maximum`, comparisons, indexing and integer reductions; transcendentals and non-integer powers go through `math.*` on scalars (`fmath`); float reductions that feed geometry use `math.fsum`; no BLAS (`@`, `dot`, `einsum`, `linalg`). | `A @ R.T` differs between Blender's numpy 2.3.4 and the host's 2.5.3; under an AVX2-only dispatch `np.tan`, `arctan2`, `exp`, `log`, `power(x, 0.37)`, `cbrt` and `arccos` change bits while `sin`, `cos`, `sqrt`, sums and `math.*` do not **(probed twice)**; Windows numpy has no SVML and `math.*` uses UCRT |
| K4 | **One mesh object per part**, emitted with local vertices plus a world matrix. `geom_hash` covers part names, matrices, local vertices and triangles, float32-cast and quantized to 1e-6; `eval_hash` = `geom_hash` + anchors + sockets. Determinism compares `eval_hash` (host vs Blender evaluator); `emit_hash` compares `geom_hash` of the read-back with the evaluator's. | Blender stores float32; anchors cannot be read back from Blender |
| K5 | **Raster conventions pinned and verified against Workbench**: pixel centres at (i+0.5, j+0.5), y down, sensor fit VERTICAL, `ortho_scale` = visible height, `angle_y` = vfov, perspective-correct depth. Tie rule: left and bottom edges inclusive. The consistency gate shifts the camera by a fixed sub-pixel offset so exact ties are improbable on any GPU. | 0 mismatched pixels on 18 random triangles × 2 projections × 3 resolutions; tie rule measured on Mesa llvmpipe **(probed)**; the PC's NVIDIA backend may differ |
| K6 | Silhouettes use a **scanline-span rasterizer with back-face culling**; IDs and depth use spans expanded to pixels. An edge-function rasterizer stays as the reference in tests. | 4,333 silhouettes/min worst case (37k tris filling 256²) vs 142/min for bounding-box edge functions, identical masks **(probed)** |
| K7 | **All T1/T2 gate code is numpy and runs on the host** on the EvalMesh, and again on arrays read back from Blender after a build (OVERHAUL puts T2 in the worker, which arrives in S1; the same code moves there). T2 distances use a uniform grid hash over triangles, exact closest points and early exit; inside tests use +Z ray parity with the §4.2 tie rule. No winding-number brute force. | Grid hash: a 25k-triangle part builds in 0.06 s and a touching 25k/25k pair resolves in 0.01 s; brute-force winding numbers took 43 s for 4,000 samples × 25k triangles **(probed)** |
| K8 | **Arming.** Each registered check declares `needs_suite`. Exact checks (formats, names, references, licences, counts, hashes, round trips) have `needs_suite=False` and block from day one, each with a planted pass/fail unit test. Thresholded geometric checks have `needs_suite=True` and block only when `data/gates/armed.json` lists them, written from a passing `defect_inject` run. The runner stamps `armed` on every finding. | OVERHAUL §2.5: hard blocks once its recall test passes; formats block from day one |
| K9 | Two additions to the source vocabulary (§5.2): **`record`** (a measurement from a CC0 museum record) and **`profile` + `param`**. Records resolve from the committed CC0 table `museum_records` first (K17). An expression literal other than 0.5, 1 or 2 must carry `src`. | The A/B briefs cite Met records; `0.197*hand_length` needs a citation |
| K10 | **No booleans in S0b specs.** Holes come from lathe annulus profiles and extruded rings or U-profiles. `finish.boolean()` exists, with verification, for S2+. | MANIFOLD silently returns the base mesh unchanged when an operand is non-manifold; EXACT with an open operand leaves non-manifold edges **(probed)** |
| K11 | **Materials are named slots only in S0b** (surface arrives in S2). The user's blind A/B pairs are clay renders. | Otherwise the A/B measures colour, not the compiler |
| K12 | **Godot headless import runs in CI and on the PC** (`--headless --import`). The UE import script re-creates sockets and collision from the sidecar if the importer drops them. | Godot 4.7-stable imported our probe .glb headlessly in 8 s here **(probed)**; UE Interchange handling of `SOCKET_`/`UCX_` is unverified |
| K13 | MCP tools and CLI commands are added through **`opus/tools/<module>.py`**. WP0 registers all 11 tools with their final signatures as stubs and creates the shared CLI groups (`spec`, `gates`, `data`); packages fill in bodies. | Parallel worktrees; `argparse` refuses a second `spec` subparser **(probed)** |
| K14 | Spec templates (`spec_new`) contain **no number from an eval brief**; a test greps for them. One report-only `generic`-template session per prop measures how much the A/B depends on templates (§19). | The A/B must measure the compiler, not templates tuned to the briefs |
| K15 | **The A/B's primary measure is pre-registered with the user before WP0** (§19.4, decision U1). Proposed: grader-confirmed `iterations_to_accept`, 3 fresh sessions per prop per arm, with token and wall-clock guards. OVERHAUL's `iterations_to_hard_pass` stays a reported measure. | The v0.4 baseline already reaches a hard pass at iteration 1 on sword, chest and chair, so "fewer iterations to a hard pass on ≥5/6" cannot be met **(probed on the baseline ledger)** |
| K16 | Version 0.5.0 (`pyproject.toml`, `opus/__init__.py`, `plugin.json`). Spec files are `*.spec.json`; revisions and the Pareto archive live in `<project>/.opus/specs/<id>/`. | `runs.tool_version()` reads `plugin.json` |
| K17 | **Cited museum records are committed** as the CC0 fact table `data/tables/museum_records.json` (extracted measurements, never images), so specs resolve offline and in CI and records are covered by `tables_version`. The library cache is a fallback for records not committed. | CI never fetches; a re-fetched record must not change a hash silently |
| K18 | **Grip sockets are written in v0.4's `grip_define` format** (`SOCKET_grip_<name>` parented to the asset root, frame (x, handle axis, palm side), `opus_grip` JSON), so `grip_define`, `grip_hold` and `grip_check` work on compiled assets unchanged. | Otherwise `hold()` picks the compiled empty, has no radius and holds the sword crosswise **(probed by the completeness review)** |
| K19 | **Joint root parts carry their origin on the joint axis in the evaluator** (the matrix translation is the joint anchor point; local vertices are expressed from it). Emit uses evaluator matrices unchanged; export only joins. | One matrix for hash, .blend and export; the chest's hinge probe reads the .blend's lid origin |
| K20 | `opus.trace` (maintainer-only profile tracing) uses the `opus[ref]` extra (opencv-python-headless) for components, hole filling and contours. | Hand-written numpy versions are needless work; OVERHAUL already plans the extra |

**Deviations from OVERHAUL** (each also in the review log):
1. K9 adds `record` and `profile.param` sources; K10 removes booleans from the S0b spec surface.
2. S0b ships Nelder-Mead joint solves only (CMA-ES moves to S2 with `spec_fit`); the constraint sketch
   solver stays in S4 (`sketch` validates and reports `not_available`).
3. **Orientation** comes from anchor-frame mating, `spin` (0–3 quarter turns, a discrete structural
   choice written as a literal) and `orient` words for roots. Relations (`coaxial`, `parallel`,
   `perpendicular`) are checked, not solved; `along_tangent` arrives with `sweep` in S4.
4. **Free anchor positions:** `uvw` components and `@f` fractions may be the literals 0, 8 or 16
   (sixteenths: the bbox faces and centre, equivalent to named anchors); any other position must be a
   ratio dim (a `design` range, an expression or a template slot). Ratio dims are not snapped to the
   1/16 grid in S0b.
5. **`design` values:** until `spec_explore`/`spec_fit` exist (S2–S3), `spec_edit` may set a `design`
   dim's `value` inside its range only when `why` cites a finding key; each such edit is logged as a
   `design_pick` in `history` and the run ledger and counted in the A/B (OVERHAUL decision 16 reserves
   these values for explore, fit or the user).
6. Relation `tol_deg` may be a literal (a gate tolerance, as in OVERHAUL's own §2.1 example); the
   default comes from the gate profile.
7. T2 runs on the host (K7); the worker arrives in S1.
8. The A/B's primary measure (K15, §19.4) once the user signs it off.
9. Deferred items OVERHAUL lists for S0b, each with its sprint, are in §1.2 (the CI calibration corpus,
   the `organic` profile's self-overlap check, `mesh_lint` influences and kit grid).

**User decisions needed before WP0 starts** (also in the final report):
- **U1** — the A/B measure (§19.4). Recommended: `iterations_to_accept`. If declined, OVERHAUL's
  wording stands and the A/B cannot pass on sword, chest and chair, so the §18 fallback follows.
- **U2** — the token and wall-clock guards (S0b median ≤1.2× v0.4 per prop) as part of a win.
- **U3** — 36 more A/B sessions (12 v0.4, 18 S0b, 6 report-only `generic`): about 9 session-hours at the
  baseline's 10–20 minutes each, about 4.5 hours of wall-clock at concurrency 2, plus grading (§19.3).
- **U4** — CI: if pushing `.github/workflows/ci.yml` is refused for lack of the `workflow` permission,
  the user commits that file through the GitHub web UI (§16).

---

## 1. Scope

### 1.1 What S0b builds (every bullet of the §9 row, plus the S0b rows of OVERHAUL §8)

| OVERHAUL §9 bullet / §8.2 row | Delivered as | WP |
|---|---|---|
| Spec envelope + validator | `opus.spec` (pydantic models, JSON Schema, T0 rules), `spec_new` templates for 6 archetypes + generic | A |
| dims resolver + first fact tables (ANSUR, Oakeshott, Cleveland swords, Wikidata firearms, ADA) with LICENSES entries | `opus.dims`; tables `anthro_ansur2` v2, `oakeshott`, `museum_arms` (Cleveland + Met), `museum_records`, `firearms_wikidata`, `ada_2010`, `weapon_facts` | A, F |
| Anchor/graph solver | `opus.compile.solver`: attach (face, point), squeeze, reflect, translate, orient, radial and linear arrays | B |
| Evaluator contract for all kinds; numpy builders box, extrude, lathe, station_loft | `opus.compile.kinds` (kinds, levels per kind, `Proxy2D`, `frames`/`fields` containers, round-trip tests on stub kinds) + `opus.compile.evaluate` (assembly; other kinds raise `KindNotAvailable` with their sprint); builders box, superquadric, extrude, lathe, station_loft | WP0, B |
| Evaluator raster + blueprint sheet | `opus.compile.raster`, `opus.compile.views`, `opus.preview` | C |
| Profile library v0: ≥6 sword, axe and shield profiles traced from Cleveland/Met CC0 photos | `data/profiles/` (up to 13 variants in 7 families, 11 of them weapons) + `opus.trace` maintainer tool | F |
| Blender emitter + finish v1 via the one-shot runner | `opus_bl/emit.py`, `finish.py`, `readback.py` | E |
| Consistency gate v1 | `opus.gates.consistency` (host metrics) + `opus_bl/consistency.py` (renders, BVH depth) | C, E |
| Finding contract + T0–T2 + `spec_edit` (lexicographic) + run ledger | `opus.gates.*`, `opus.spec_edit`, `opus.accept`, `opus.runs` (`spec_round`, `design_pick` events) | WP0, D, G |
| Minimal `defect_inject` / `gate_calibrate` harness | `opus.gates.defects`, `inject`, `calibrate`; `data/gates/armed.json`, `noise.json` | D |
| CI workflow (Workbench and CPU) | `.github/workflows/ci.yml` (host on Linux and Windows, Blender, licences, Godot import) | WP0 stub, H |
| FBX/glTF export presets + Blender round trip + UE import script and checklist | `opus_bl/export.py`, `opus.export`, `data/engine/` templates | E |
| `data_fetch` (manifest, `--from-file`, snapshots, lineage) | `opus.data_fetch`, `data/packs.yaml` | F |
| Optional-extras packaging | `[project.optional-dependencies]`, `opus.extras`, doctor report | WP0, H |
| §8.2 `mesh_lint` (S0b part) | MANIFOLD readiness (closed 2-manifold per object), custom-normal check, gate-profile awareness; existing keys and thresholds unchanged | H |
| §8.2 `model_report` (S0b part) | `findings` in the finding contract for gaps, contacts and penetrations; existing keys unchanged | H |
| §8.2 `project_bible` | `weapon_scale`, `gravity_mult`, `style_mult`, texel-density rule (stored for S2), gate profiles, `twist_policy` (stored for S1), rating budget | A |
| §8.2 `ledger_record` / `make_credits` | `spec_build` lineage inputs and tool tags; export policy; `sa` licence stamp and CREDITS.md entries at export | E |
| §8.2 `opus_doctor` | extras smoke tests, per-pack status and size, Blender numpy version, fill rule per GPU | H |

Also in S0b, because the exits need them: `spec_new` templates, the 3d-modeling skill update, the S0b PC
checklist, the A/B kit and its entry gate (§19.0), `post_eval` handling after a build (§11.6).

### 1.2 What S0b defers

| Deferred | To | Note |
|---|---|---|
| Persistent worker | S1 | One-shot runner (~0.8 s Blender start-up, probed) |
| visual_hull, sweep, `along_tangent` | S4 | |
| inflate, sdf_body, facet_loft, creature_cage | S2 | `Proxy2D`, `frames` and `fields` containers exist now (§4.5, §7.1) |
| Constraint sketch solver (`sketch` source) | S4 | Validates; compile reports `not_available` |
| Relation solving (orientation from relations) | S4 | S0b checks relations (deviation 3) |
| Fullers and lenticular-with-fuller sections, `lib:point.*` | S4 | Blades use a superellipse section with exponent `blade_n` |
| `spec_explore`, `spec_fit`, CMA-ES, `critique_pack` | S3, S2 | `design` values resolve by seed, by the Nelder-Mead joint solve, or by a finding-cited `spec_edit` (deviation 5) |
| Surface: palette atlas, PBR values, bakes | S2 | Named material slots and analytic UVs only. `palette_roles` entries are stored and syntax-checked; `palette` sources resolve in S2 |
| CI calibration corpus (Kenney/KayKit CC0 snapshot) | S2 | S0b has no soft gate to promote; its hard gates arm on generated fixtures (OVERHAUL §2.5: "generator outputs built to pass") |
| `organic` gate profile's self-overlap check | S2 | The profile entry exists in `data/gates/profiles.json`; no S0b kind uses it |
| `mesh_lint` influences and kit grid | S1, S10 | |
| CoACD hulls | S4 | One convex hull per part (`bmesh.ops.convex_hull`) |
| `ref_extract(profile)` for users | S4 | `opus.trace` is maintainer-only in S0b |
| Rigs; `post_eval` kinds (SDF, cloth) | S1, S2, S7 | S0b handles `post_eval` parts of assemblies (§11.6) |
| Unity adapter verification | S8 | Preset exists, unverified |
| T2b defect suite (planted Blender-side shifts) | S1 | Consistency checks stay unarmed (report in effect); the exit test asserts them (§9.3) |

### 1.3 Exit criteria and how each is tested

All tests named here are integration exits unless §17 names them as a package's exit; they run in the
integration phase on the merged tree and then on every CI run.

| Exit criterion (§9) | Test | Runs in |
|---|---|---|
| Same spec + seed + `tables_version` → identical quantized hash, host and Blender | `test_determinism.py`: the 6 A/B specs × seeds {0,1,7}: `eval_hash` on the host equals `eval_hash` computed inside Blender (`spec_eval_hash` task) in the same job; `geom_hash` of the read-back of the emitted (unfinished) mesh equals the evaluator's. `test_golden_resolved.py`: the resolved JSON equals the committed golden to 1e-12 relative (every host job, Linux and Windows). Hash goldens are never asserted across machines; the Windows job reports any difference as a warning. | CI (blender job; host jobs); PC checklist item 2 (Windows, NVIDIA) |
| Single-triangle projection convention test | `test_raster.py::test_single_triangle_blender`: ortho and perspective, 97×64 and 64×97, plus the 8×8 tie case, against a Workbench mask render (`raster_tie` task) | CI; PC item 2 records the tie rule seen on the GPU |
| 5 specs × 4 views: IoU ≥0.99, per-part boundary p95 ≤0.5 px, depth p95 ≤1 game px | `test_consistency.py` on the 6 A/B specs × views front, right, top (ortho) and three_quarter (perspective), stage `emitted` (§9.6), with the hidden-part rule | CI |
| ≥200 numpy silhouette evals/min (one view, 256², ≤12 parts) | `test_perf.py::test_silhouette_throughput`: `evaluate(level="fit")` + `raster.silhouette` at 256² for each A/B spec, 50 iterations; min over specs ≥200/min (expected ≥1,000). Asserted when `OPUS_PERF_ASSERT=1` (CI), logged otherwise | CI (marker `perf`) |
| 6-part anchored prop survives 3 random dial edits with 0 gaps and 0 floating parts | `test_spec_edit.py::test_random_dial_edits` (§10.6): chest (12 parts) and chair (11 parts), 20 seeds × 3 edits; each edit's **candidate** (`dry_run`) has 0 failing `contact_gap`, `floating`, `anchor_error`; ≥95% of in-bounds edits are accepted (rejections listed); a negative control with propagation disabled must fail | CI |
| `defect_inject`: contact, floating, manifold, sheet, naming ≥95% recall (≥99% at 2×), 0 failures on clean fixtures | `test_defects.py` (package) + `opus gates inject all --fixtures ab6 --check-armed` (§9.7), recall reported per family, spec and placement mode; the clean set includes Blender read-backs | CI (blender job) |
| CI green | `.github/workflows/ci.yml` | GitHub |
| A/B against v0.4 on 6 props | §19, after the entry gate (§19.0) | cloud runs + user (≤20 min) |
| PC: Godot headless import of the exported .glb | CI job `godot` and PC item 3: `Godot_v4.7-stable_win64_console.exe --headless --path <proj> --import`, then `-s check_import.gd` | CI + PC |
| PC: UE import checklist | `docs/PC_CHECKS_S0B.md` item 4 | PC only |

**PC-only:** the UE import checklist, the user's blind pairs, and the Windows/NVIDIA runs of the
determinism hash, the tie rule and the Godot import (they also run on Linux in CI).

---

## 2. Probe evidence

Probes are in `/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad/s0b_design/` (Blender 5.2.2 LTS, Linux, Mesa llvmpipe;
4 CPUs). The reviewers' probes are in its `critic/` and `critic/feas/` folders, the revision's in `rev/`.

| Probe | Result | Used in |
|---|---|---|
| Versions (`ver.py`) | Blender Python 3.13.13, numpy 2.3.4; host uv venv Python 3.13.16, numpy 2.5.3, pydantic 2.13.5, jsonschema 4.26 | K1 |
| Bitwise determinism (`det_probe.py`, `critic/feas/det2.py`) | Same CPU path: host and Blender agree on everything except `A @ R.T`. With AVX-512 masked (`NPY_DISABLE_CPU_FEATURES`): `np.tan`, `arctan2`, `exp`, `log`, `power(x, 0.37)`, `cbrt`, `arccos` change bits; `sin`, `cos`, `sqrt`, `hypot`, `power(x, 2)`, sums, `cumsum`, `cross`, `interp` and `math.*` do not | K3, §4.3 |
| Projection (`proj_host.py`, `proj_bl.py`) | 0 mismatched pixels (IDs and silhouettes): 3 parts × 6 triangles, ortho and perspective, 97×64, 64×97, 128×128, Workbench mask mode | K5, §4.2 |
| Tie rule (`tie_host.py`, `fill_rule.py`) | A pixel centre on an edge is inside when the edge's inward normal has nx > 0, or nx = 0 and ny < 0 (image y down): left and bottom edges. Reproduced exactly in numpy. GPU: OpenGL 4.5, Mesa 25.2.8 llvmpipe | §4.2 |
| Raster speed (`raster_bench.py`, `span_bench.py`) | Edge function, bbox pairs: 142/min worst case; spans + culling: 4,333/min worst case, 21k/min on a 4.5k-triangle sword; masks identical | K6 |
| T2 distances (`rev/t2_grid_bench.py`) | Grid hash (cell = max(4·tol, diag/64)) + vectorized Ericson closest point, ≤4,000 samples, early exit: grid build 0.009 s (2.9k tris) / 0.06 s (25k); touching 25k/25k pair 0.009 s; 5 mm near miss 0.013 s; hoop wrapped round a 23k-tri barrel 0.04 s. Brute-force generalized winding number (`critic/feas/gwn_bench.py`): 43 s for 4,000 samples × 25k tris | K7, §9.4 |
| Mesh emission (`api_probe.py`) | `foreach_set` 0.021 s vs `from_pydata` 0.061 s for 12.8k verts / 25k tris; vertex order preserved; `validate()` returns False when nothing was fixed, True when it fixed something (also with `loop_start` only, `critic/feas/api_bl.py`) | §11.1 |
| Quad layout (`critic/quad_probe_bl.py`) | Read-back of quads split (a,b,c),(a,c,d) reproduces the evaluator's triangles only when mates are adjacent in that order; a builder emitting all first halves then all second halves hashes differently | §4.5 |
| Stamps | `VertexGroup` refuses ID properties (TypeError). Objects keep `opus_part` through glTF (`export_extras`) and FBX (`use_custom_props`) re-import; FBX returns array stamps as strings (`"[1.0000001, …"`) | §11.1, §12.2 |
| Modifiers (`api_probe.py`, `uv_probe.py`, `critic/feas/api_bl.py`) | Bevel `face_strength_mode='FSTR_AFFECTED'`, `miter_outer='MITER_ARC'`, `harden_normals`; Weighted Normal `keep_sharp`, `use_face_influence`, `weight`, `mode`; Triangulate `keep_custom_normals`; attributes `bevel_weight_edge`, `sharp_edge`, `sharp_face`; `Mesh.set_sharp_from_angle`; UV `foreach_set("vector")`; Bevel `limit_method='WEIGHT'` reads `bevel_weight_edge`; the evaluated mesh has custom normals | §11.2 |
| Bevel triangle growth (`critic/bevel_tris_probe.py`) | Box 12 → 108 tris; a 14-sided, 56-station lathe leg 1,592 → 2,208 with 11 flagged rings (+56 per ring) | §9.3 `budget_tris`, §11.2 |
| Booleans (`bool_probe.py`, `critic/feas/api_bl.py`) | MANIFOLD with a non-manifold operand returns the base mesh unchanged and raises nothing (it prints "Cannot execute, object(s) 'B' have non-manifold geometry"); EXACT computes but leaves 6 non-manifold edges | K10, §11.2 |
| UE join (`critic/feas/join_bl.py`) | `object.join` keeps only the active object's modifier stack: per-part Bevel widths are lost. `bpy.data.meshes.new_from_object(obj_eval, preserve_all_data_layers=True)` per part, then join, keeps them and the custom normals | §12.1 |
| Grip sockets (`critic/grip_collide_probe.py`) | A compiled `SOCKET_grip_main` parented to `grip_C` survives `grip_define(object=root)`, which then writes `SOCKET_grip_main.001`; `hold()` takes the first one, which has no radius | K18 |
| Export (`api_probe.py`, `critic/feas/api_bl.py`) | glTF export 0.99 s; every glTF/FBX kwarg used in §12 accepted; re-import keeps object names, stamps and `SOCKET_` empties with their parents | §12 |
| Godot (`gdproj/`) | Godot 4.7-stable Linux, `--headless --import` 8 s; `blade_C` → MeshInstance3D, AABB (0.04, 1.0, 0.04) (Z-up → Y-up), `SOCKET_grip_main` → Node3D. Exit prints benign leak `ERROR:` lines | K12, §12.4 |
| Exchange (`npz_bl.py`) | `.npz` written by numpy 2.5.3 loads in Blender with `allow_pickle=False`; 128² BVH ray casts 0.025 s; a 2048² Workbench mask render 1.0 s, 128² BVH grid over 12 objects 0.27 s (`critic/feas/render_bl.py`) | §4.5, §11.4 |
| CLI groups (`critic/probe_argparse.py`) | A second `add_parser("spec")` on one subparsers object raises `ArgumentError: conflicting subparser: spec` (Python 3.13.16) | K13, §4.9 |
| Imports (`critic/probe_import*.py`) | An `opus/spec/__init__.py` importing pydantic makes `import opus.spec.resolved` fail in Blender ("No module named 'pydantic'") | K1 |
| Baseline ledger (read-only `runs.run_summaries`, 2026-10-21 09:00) | v0.4 `iterations_to_hard_pass`: sword 1, axe 2, round_shield 2, chest 1, barrel 2, chair 1; `iterations_to_accept`: 2, 2, 2, 3, 3, 2; wall-clock 571–1,181 s; tokens not yet logged | K15, §19 |
| Start-up | one-shot Blender run 0.76–0.84 s | §11 |

**Network, 2026-10-21, through the proxy.**
- Cleveland Open Access API 200: 511 CC0 sword records, 500 with structured `dimensions` (metres);
  none has a pommel dimension and 2 have a blade width. `q=shield` also returns a parade sword, a
  halberd, a hauberk and a rifle; `q=boss` a curb bit and a katar.
- Met: `v1/search` returns 410 ("retired"); `v1.1/search` 200 (4,639 hits for "sword"; 100 ids by
  default, up to 500 per page with `limit`/`offset`); `v1/objects/<id>` 200; `v1.1/objects` 404. Most
  Met sizes are in the `dimensions` string, not structured `measurements`. 23367: blade length 81.28 cm,
  overall 102.24 cm, blade thickness 0.64 cm, greatest blade width 8.89 cm, greatest width 23.5 cm,
  1.673 kg; its quillon tips sit about 2.2 cm toward the blade from the bar (arched). 15292: 92.7 ×
  58.4 × 42.5 cm. Public-domain early medieval shield bosses: 22635 (Ø 19.99 cm, H 16 cm; DT257906 is
  a near-side view; 35771 is the same boss with its grip), 472596 (Ø 19.05 cm, D 8.89 cm), 472597
  (Ø 17.78 cm, D 8.89 cm; 24905 lists both). `q=shield boss` also returns 8 horse "Bit boss" objects.
  Loose pommels 29117 (5.2 cm) and 32799 (6.7 cm) give sizes only in the string.
- Wikidata SPARQL 200 (729 rows for 592 firearm items with a psn-normalized length; per-item duplicates).
- Wikipedia raw wikitext 200 with revision ids; "Viking shield" is a redirect to "Viking Age arms and
  armour#Shields", which gives diameters (45–120 cm, most 75–90 cm) but no board thickness or boss size;
  "Oakeshott typology" gives only the grip length for type XIV and says XIV crosses are "generally…
  curved".
- **Albion's typology article returns 404 on every URL variant** (the first draft's "200" was a
  "Page not found" page served with status 200; the feasibility reviewer saved a live copy from an
  unrecorded URL). `oakeshott` is Wikipedia-only unless WP-F finds the live URL (§14.1).
- access-board.gov/ada 200; ANSUR II CSVs 200 (sha256 as in §13.1); Blender 5.2.2 tarball + `.sha256`
  200; Godot 4.7-stable zip 200 (sha256 matches); CMA image CDN 200.
- `api.github.com` direct: 403 here; `gh api repos/Infamase/Opus-Tools` works (public repo) but
  `.../actions/permissions` gets proxy 403; the GitHub MCP `actions_list` works (§16).

---

## 3. Architecture and module layout

```
spec.json ──spec_validate(T0)──► dims_resolve ──► resolved.json ──evaluate(level)──► EvalMesh
   ▲  (pydantic, host)              (host)          (plain dict)     (numpy; host or Blender)
   │                                                                     │
spec_edit ◄── findings ◄── gates T1/T2 (numpy, host) ◄───────────────────┤
   │                                     ▲                              raster ──► spec_preview (blueprint, masks, T1 lint)
   │                                     │ read-back .npz (emitted, finished)
   └──► spec_build ──► .npz ──run_task──► Blender: emit → read back → finish → save .blend → read back → export
                                         └─ spec_consistency: Workbench ID masks + BVH depth ──► T2b (host metrics)
```

**Import rules** (`tests/test_import_rules.py`, WP0). It imports each numpy-only module with `pydantic`,
`yaml`, `PIL` and `mcp` blocked in `sys.modules`, and walks its AST:
- numpy-only modules: `opus.paths`, `opus.camera`, `opus.compile.*`, `opus.gates.finding`,
  `opus.gates.registry`, `opus.gates.geom`, `opus.gates.t2`;
- `opus/spec/__init__.py` contains no import statement;
- in `opus.compile.*`, `opus.gates.geom` and `opus.gates.t2`: no `ast.MatMult`; no attribute named
  `dot`, `matmul`, `einsum`, `tensordot`, `inner`, `outer` or `linalg`; no numpy transcendental
  (`np.sin`, `cos`, `tan`, `arcsin`, `arccos`, `arctan`, `arctan2`, `exp`, `expm1`, `log*`, `power`,
  `float_power`, `cbrt`, `hypot`, `sinh`, `cosh`, `tanh`) — those go through `fmath`;
- `@dataclass`, `@property` and strings containing `@` are not flagged (decorators are `ast` nodes of
  another kind), which the first draft's grep would have done.

### Module tree (new files; owner in brackets)

```
python/src/opus/
  spec/__init__.py            [WP0] empty; never imports (K1)
  spec/model.py               [A]  pydantic models (§5)
  spec/schema.py              [A]  JSON Schema export → data/schema/opus.asset.1.schema.json
  spec/validate.py            [A]  T0 rules → Findings
  spec/templates.py           [A]  spec_new
  dims.py                     [A]  dims_resolve, wielders, tables_version, lock
  compile/__init__.py         [WP0] empty
  compile/resolved.py         [WP0] ResolvedSpec TypedDicts (§4.8)
  compile/evalmesh.py         [WP0] EvalMesh, PartInfo, Anchor, hashes, npz, quads, fixtures (§4.5)
  compile/conventions.py      [WP0] frames, names, anchor grammar, views, RasterCamera, project (§4.1-4.2)
  compile/fmath.py            [WP0] deterministic math (§4.3)
  compile/expr.py             [WP0] expression evaluator (§4.4)
  compile/measure.py          [WP0] sheet measures shared by builders and gates (§4.6)
  compile/kinds.py            [WP0] KINDS, LEVELS, KindNotAvailable, Proxy2D (§7.1)
  compile/evaluate.py         [B]  evaluate(resolved, level, ppm)
  compile/solver.py           [B]  anchor/graph solver
  compile/profiles.py         [B]  profile JSON → polylines; prim families
  compile/triangulate.py      [B]  polygon-with-holes ear clipping
  compile/uv.py               [B]  analytic UVs + shelf pack
  compile/builders/{box,superquadric,extrude,lathe,station_loft}.py   [B]
  compile/raster.py           [C]  silhouette, id_depth (spans), reference edge-function raster
  compile/views.py            [C]  view cameras, framing, consistency resolution, game camera
  preview.py                  [C]  blueprint sheet (PIL; host only)
  gates/__init__.py           [WP0] empty
  gates/finding.py            [WP0] Finding, Target, Fix (§4.7)
  gates/registry.py           [WP0] CheckSpec, REGISTRY, GateContext, armed(), CHECK_MODULES, profiles (§4.7)
  gates/runner.py             [D]  tiered runner
  gates/t0.py                 [D]  registers the T0 rules (calls spec.validate lazily)
  gates/t1.py, t2.py, geom.py [D]  numpy checks (Blender-importable)
  gates/defects.py, inject.py, calibrate.py   [D]
  gates/consistency.py        [C]  T1 feature_px_game, T2b metrics and orchestration, finish_delta_px
  gates/built.py              [E]  emit_hash, export_round_trip, licence_blocked
  spec_edit.py, accept.py, optim.py           [G]
  build.py                    [E]  spec_build orchestration (host)
  export.py                   [E]  export_asset (host)
  data_fetch.py, trace.py     [F]
  extras.py                   [WP0] require(extra, module) lazy import helper
  tools/__init__.py           [WP0] register_all, add_cli_all, run_cli
  tools/spec.py [A], preview.py [C], build.py [E], check.py [D], edit.py [G], data.py [F]   (WP0 stubs)
blender/opus_bl/
  emit.py, finish.py, readback.py, consistency.py, export.py   [E]
  grip.py                     [E]  handle_props() extracted from define(); define's output unchanged
  compile_eval.py             [B]  runs opus.compile.evaluate inside Blender, returns the hashes
  raster_tie.py               [C]  single-triangle and tie renders
  entry.py                    [WP0 adds task names; lazy imports]
  lint.py, inspect3d.py       [H]  mesh_lint / model_report additions (additive only)
data/
  schema/{finding,opus.resolved.1,opus.profile.1}.schema.json [WP0]; opus.asset.1.schema.json [A]
  gates/profiles.json [WP0]; gates/{armed.json,noise.json,calibration/} [D]
  templates/*.spec.json [A]; tables/*.json [F]; profiles/*.json, profiles/trace.yaml [F]; packs.yaml [F]
  engine/* [E]; errors.json [E]
.github/workflows/ci.yml [WP0 stub, then H]; .gitattributes [WP0]; docs/PC_CHECKS_S0B.md [H]
tests/conftest.py, test_import_rules.py, test_contracts.py, test_tools_s0b.py, test_mcp.py (EXPECTED),
  fixtures/s0b/ [WP0]
```

Changes to the first draft's layout, and why: the resolved-spec TypedDicts moved from `opus/spec/` to
`opus/compile/` (K1); `measure.py` and `kinds.py` are contracts because B and D both use them;
`GateContext` and the profile thresholds are contracts because C, D, E and G build contexts; T2b
finish checks belong to C and built-asset checks to E, so every check has one owner (§9.3).

Existing files changed: `bible.py` [A], `tables.py` [F], `runs.py` [WP0 hooks, then G],
`blender/runner.py` [WP0 env hook, then E], `doctor.py` [H], `opus_bl/lint.py`, `opus_bl/inspect3d.py`
[H], `skills/3d-modeling/SKILL.md`, `README.md`, `evals/README.md` [H], `data/LICENSES.md` [F],
`DOWNLOADS.md` [F], `paths.py` (`safe_name`) [WP0], and only in WP0: `mcp_server.py`, `cli.py`,
`pyproject.toml`, `uv.lock`, `opus/__init__.py`, `.claude-plugin/plugin.json`, `tests/test_mcp.py`.

---

## 4. Shared contracts (WP0)

WP0 writes these files exactly as specified, with tests in `tests/test_contracts.py`, and commits them
before fan-out. Code shown is normative; prose around it fills in what the code elides.

### 4.1 Frames, sides, names, anchors (`compile/conventions.py`)

- World: metres, **+Z up, −Y front, +X = the object's left**. An object faces −Y; seen in the front
  view its left side appears on the viewer's right.
- Sides: `L` = +X, `R` = −X, `F` = −Y, `B` = +Y, `C` = on the centre plane.
- Part names: `NAME_RE = r"^(?P<role>[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)*)_(?P<side>[LRCFB])(?P<index>\d{2})?$"`,
  e.g. `blade_C`, `leg_front_L`, `stave_C07`. `ground` is a reserved virtual part (the z = 0 plane;
  anchor `ground:top_c` at the origin, n = +Z, t = +X).
- Reserved prefixes, never valid part names: `UCX_ UBX_ USP_ UCP_ SOCKET_ SM_ ground`.
- **Canonical builder frames.** Builders work in a fixed local frame: box and superquadric centred;
  extrude with the profile in local XY (u → x, v → y) extruded along local Z, centred; lathe and
  station_loft with the axis on local +Z from 0. The `plane` (extrude) and `axis` (lathe, loft)
  parameters become a fixed proper rotation `R_b` folded into the part's matrix:

  | Param | `R_b` (where canonical x, y, z go) |
  |---|---|
  | extrude `XY`; lathe/loft `z` | identity |
  | extrude `XZ` | x → +X, y → +Z, z → −Y |
  | extrude `YZ` | x → −Y, y → +Z, z → −X |
  | lathe/loft `x` | x → −Z, y → +Y, z → +X |
  | lathe/loft `y` | x → +X, y → −Z, z → +Y |

  `verts_local` and builder anchors are in the canonical frame; `PartInfo.matrix` maps canonical
  local → world and includes `R_b`. Every sheet measure (§4.6) is taken in the canonical frame.
- **Anchor frame:** point **p**, unit normal **n** (frame z), unit tangent **t** (frame x, t ⟂ n),
  frame y = n × t.
- **Placement** (`R(M)` is the rotation part of a matrix, `Rot(a, θ)` a rotation about world axis a):
  - *face* (attach default): target rotation `R_t = Rot(n_p, 90°·spin) · R_p · Rx(180°)` and target point
    `p_t = p_p + offset·n_p`, where (p_p, R_p) is the parent's anchor frame in world; the child matrix is
    `M_c = [R_t | p_t] · F_c⁻¹` with F_c the child's anchor frame in its canonical frame. So child t =
    parent t, child n = −parent n, then `spin` quarter turns counter-clockwise about the parent's n.
  - *point*: `R(M_c) = R(M_p) · Rz(90°·spin) · R_b(child)`; translation such that the child's anchor
    point lands on `p_p + offset·n_p`.
  - *translate*: point mode with the child's anchor at `p_p + b₁·t_p + b₂·(n_p × t_p) + b₃·n_p` for
    `"by": [b₁, b₂, b₃]` (dims, or the literal 0).
  - *squeeze*: the child's length param is set to |P₂ − P₁| between the two target points; its local
    axis through its two self anchors runs P₁ → P₂, roll from the `from` part's t.
  - *orient* (roots only): `M = ORIENT[word] · R_b`, `ORIENT = {"up": I, "front": Z→−Y (Rx +90°),
    "back": Z→+Y, "left": Z→+X, "right": Z→−X, "down": Z→−Z}`. With no placement key: identity at the
    origin.
  - *reflect*: with S the world mirror through the plane (yz, xz or xy) and its `through` point (default
    the world origin at solve time) and `S_l = diag(−1, 1, 1)` the canonical-local x mirror:
    `M' = S · M_src · S_l` (a proper rotation), `verts_local' = S_l · verts_local`, winding reversed.
    Anchor names on a reflected part are evaluated on its own (mirrored) canonical geometry; nothing is
    renamed.
  - *arrays*: the declared part is a template expanded into copies `<name><NN>` (NN = 01…n; the
    template name itself is not a part). Radial: copy k is `Rot(axis, 2πk/n + 2π·phase) · M_template`
    about the attach parent's canonical z axis in world; linear: n copies spaced over `span` along the
    parent frame's x, y or z, centred on the template's placement.
- **Joint roots (K19):** after placement, a part named as a joint's `part` is re-origined: its matrix
  translation becomes the joint anchor's world point and `verts_local`, its local anchors and its mate
  points are shifted by the inverse (rotation unchanged). Its descendants are unaffected.
- **Anchor grammar** (`ANCHOR_RE`, `BUILDER_ANCHORS`, `builder_anchor_names(builder, profile=None)`):
  ```
  ref        := part ":" anchor                       # split at the first ":"
  anchor     := static | fam "@" frac | "uvw:" c "," c "," c | profile_anchor
  static     := top_c | bottom_c | front_c | back_c | left_c | right_c | top_back | top_front
              | bottom_back | bottom_front | rim_+x | rim_-x | rim_+y | rim_-y | inner_c | inner_corner
  fam        := section_x | section_y | section_z | ring | side_+x | side_-x | side_+y | side_-y
  frac       := "0/16" | "8/16" | "16/16" | dim_name        # a ratio dim in [0, 1]
  c          := "0" | "8" | "16" | dim_name                  # sixteenths, or a ratio dim
  ```
  `BUILDER_ANCHORS` lists which statics and families each builder has (§5.4); `profile_anchor` names come
  from the resolved profile's `anchors`. `EvalMesh.anchors` keys are the literal spec strings
  (`"haft_C:ring@head_s"`); values are the evaluated world frames.

### 4.2 Raster conventions (`compile/conventions.py`)

```python
VIEWS = {"front": (0.0, 0.0), "right": (90.0, 0.0), "back": (180.0, 0.0), "left": (270.0, 0.0),
         "top": (0.0, 90.0), "bottom": (0.0, -90.0), "three_quarter": (38.66, 26.6),
         "three_quarter_back": (218.66, 26.6)}   # (azimuth, elevation) in degrees = opus_bl.inspect3d.NAMED_VIEWS
PSEUDO_VIEWS = ("game",)    # the camera profile's own view at d_typical (views.game_camera)
LEVELS = ("close", "typical", "far")                       # = opus.camera.LEVELS
# direction from the target to the camera, as opus_bl.inspect3d.aim: d = (sin az cos el, -cos az cos el, sin el)
TIE_RULE = "left+bottom"    # probed on Mesa llvmpipe 25.2.8 (OpenGL 4.5)
JITTER_PX = (0.137, 0.291)  # anti-tie camera shift for consistency renders (x right, y down)

@dataclass(frozen=True)
class RasterCamera:
    projection: str          # "persp" | "ortho"
    width: int               # full-frame pixels
    height: int
    vfov_deg: float = 0.0    # persp only; sensor fit VERTICAL (Blender: data.angle_y)
    ortho_h: float = 0.0     # ortho only: visible world height in m (Blender: ortho_scale)
    view: tuple[float, ...] = IDENTITY16   # row-major world -> camera; camera looks down -Z, +Y up, +X right
    crop: tuple[int, int, int, int] | None = None   # (x0, y0, w, h) in full-frame pixels, y down
    near: float = 1e-3
    far: float = 1e4
    def ppm(self, depth: float | None = None) -> float: ...   # ortho: H/ortho_h; persp: (H/2)/tan(vfov/2)/depth
    def out_shape(self) -> tuple[int, int]: ...                # (h, w) of the crop, else (height, width)
    def to_dict(self) -> dict: ...
    @staticmethod
    def from_dict(d: dict) -> "RasterCamera": ...

def look_view(target, d, distance) -> tuple[float, ...]:
    """Camera at target + d*distance looking at target. x_cam = normalize(cross(-d, up)), y_cam =
    cross(x_cam, -d), z_cam = d, with up = +Z; for |d.z| > 0.999 up = +Y (top view: image up = +Y)."""

def project(cam: RasterCamera, P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """World points (N,3) -> pixel x (right), pixel y (down) in crop coordinates, depth (m, > 0 in front).
    c = apply(view, P); depth = -c_z
    ortho: k = H/ortho_h; x = W/2 + c_x*k - x0; y = H/2 - c_y*k - y0
    persp: f = (H/2)/tan(vfov/2); x = W/2 + f*c_x/depth - x0; y = H/2 - f*c_y/depth - y0"""
```

- Pixel (i, j) has its centre at (i + 0.5, j + 0.5); row 0 is the top row.
- A pixel is covered when its centre is strictly inside a triangle, or on an edge whose inward normal
  (in image coordinates) has nx > 0, or nx = 0 and ny < 0. In span form: a row's centre y is covered when
  y_min < y ≤ y_max, and a pixel centre x when x_left ≤ x < x_right.
- Depth is view-space distance along −Z_cam, interpolated perspective-correctly (1/z for persp).
- Blender side (`opus_bl`): `cam.matrix_world = inverse(view)`, `data.sensor_fit = 'VERTICAL'`,
  `data.angle_y = radians(vfov)` or `data.type = 'ORTHO'; data.ortho_scale = ortho_h`, no shift,
  `resolution_x/y = width/height`, `resolution_percentage = 100`, `render.filepath` absolute (a relative
  path fails, probed), mask mode from `opus_bl.lookdev.mask_mode(color_type="OBJECT")`. A crop sets
  `use_border = use_crop_to_border = True`, `border_min_x = x0/W`, `border_max_x = (x0+w)/W`,
  `border_min_y = 1 − (y0+h)/H`, `border_max_y = 1 − y0/H` (Blender's border is bottom-up).

### 4.3 Determinism (`compile/fmath.py`)

```python
def apply(M, P):           # M: 16-tuple row-major, P: (N,3) float64 -> (N,3); explicit:
    # x' = M0*x + M1*y + M2*z + M3, y' = M4*x + ..., z' = M8*x + ...  (no matmul)
def compose(A, B) -> tuple # 4x4 product in pure Python floats, fixed summation order
def invert_rigid(M) -> tuple
def rot_axis(axis, quarter_turns) -> tuple   # exact 0/±1 entries
def rot_about(axis_vec, angle) -> tuple      # math.cos/math.sin on scalars
def ring_table(K: int, n: float, phase: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Superellipse ring: cx_k = sgn(cos θk)|cos θk|^(2/n), sy_k = sgn(sin θk)|sin θk|^(2/n),
    θk = 2πk/K + phase, computed with math.cos/math.sin/math.pow on scalars, cached."""
def spow(x, y)             # elementwise x**y via math.pow (arrays: list comprehension; ≤ a few thousand values)
def fsum(a) -> float       # math.fsum over a float64 array
def seeded_uniform(seed: int, key: str, lo: float, hi: float) -> float:
    """random.Random(int.from_bytes(sha256(f"{seed}:{key}".encode()).digest()[:8], "little")).random()
    scaled to [lo, hi]. One stream per key, so adding a dimension never moves another."""
```

Rules for `opus.compile`, `opus.gates.geom` and `opus.gates.t2` (K3; enforced by the AST test of §3):
numpy only for arithmetic, `sqrt`, `abs`, `floor`/`ceil`/`rint`, `minimum`/`maximum`, comparisons,
indexing, sorting, `bincount`/`cumsum` on integers and `cross`; transcendentals and non-integer powers via
`fmath`; float reductions that feed geometry via `fmath.fsum`.

### 4.4 Expressions (`compile/expr.py`)

Grammar: a Python expression parsed with `ast.parse(mode="eval")`, allowing only

| Node | Allowed |
|---|---|
| Constant | int, float (validator: a literal other than 0.5, 1, 2 requires the dim's `src`, §5.2) |
| Name | dim names; `s` (station 0..1, station-loft params only); `pi` |
| Attribute | `wielder.<measure>`, `camera.ppm_close`, `ppm_typical`, `ppm_far`, `bevel_close` (flattened to dotted keys) |
| BinOp | `+ - * / **` (`**` → `fmath.spow`) |
| UnaryOp | `+ -` |
| Call | `min max clamp(x,a,b) lerp(a,b,t) sqrt abs floor ceil` |

```python
class ExprError(ValueError): ...
def names(text: str) -> set[str]                       # dotted names used
def evaluate(text: str, env: Mapping[str, float | np.ndarray]) -> float | np.ndarray
```

### 4.5 EvalMesh, exchange file and hashes (`compile/evalmesh.py`)

```python
FORMAT = "opus.evalmesh/1"
Q = 1e-6
EDGE_SHARP, EDGE_BEVEL, EDGE_CUTTING, EDGE_SEAM = 1, 2, 4, 8

@dataclass
class Anchor:
    p: tuple[float, float, float]                 # point (m)
    n: tuple[float, float, float]                 # unit normal (frame z)
    t: tuple[float, float, float]                 # unit tangent (frame x)
    attrs: dict[str, float] = field(default_factory=dict)  # radius | a, b, n | w, h, d

@dataclass
class Mate:                        # one placement contact, re-checkable from matrices (anchor_error)
    part: str                      # the other part ("ground" allowed)
    kind: str                      # "attach" | "squeeze" | "translate" | "contact" (relation; no points)
    self_anchor: str = ""; other_anchor: str = ""          # names, for messages
    p_self: tuple | None = None    # this part's anchor point, canonical local
    p_other: tuple | None = None   # the other part's anchor point (+ offset·n), its canonical local
    xf: tuple | None = None        # 16 floats applied to the other's world point (reflect mirror, array turn)

@dataclass
class PartInfo:
    name: str
    src: str                       # JSON pointer into the spec, e.g. "/parts/2"
    builder: str                   # box | superquadric | extrude | lathe | station_loft | fixture
    v0: int; v1: int; t0: int; t1: int        # slices of verts / tris
    matrix: tuple[float, ...]      # 16 floats row-major, canonical local -> world (includes R_b)
    material: str = ""
    parent: str | None = None      # placement parent ("ground" allowed); reflect: the source's parent's
                                   # mirror partner if it has one, else the same parent; array copy: the template's
    mates: list[Mate] = field(default_factory=list)
    mirror_of: str | None = None   # reflect source
    array_of: str | None = None    # array template name
    joint: dict | None = None      # joint root only: {"name","type":"revolute|prismatic","origin":[3],"axis":[3],"limits_deg":[2]} world
    joint_root: str | None = None  # name of the joint whose subtree holds this part
    closed: bool = True            # closed 2-manifold by construction
    post_eval: bool = False
    measures: dict[str, dict] = field(default_factory=dict)  # key -> {"spec": float | None, "built": float} (§4.6)
    deps: tuple[str, ...] = ()     # transitive closure of dims and parts this part depends on (§10.2)

@dataclass
class EvalMesh:
    verts_local: np.ndarray        # (V,3) float64, canonical frames
    verts: np.ndarray              # (V,3) float64 = fmath.apply(part.matrix, verts_local) per part
    tris: np.ndarray               # (T,3) int32, CCW seen from outside; parts never share vertices
    part_id: np.ndarray            # (T,) int16
    uv: np.ndarray                 # (T,3,2) float32 corner UVs
    edge_flags: np.ndarray         # (T,3) uint8; edge k joins tris[:,k] and tris[:,(k+1)%3]
    quad_mate: np.ndarray          # (T,) int32: the other triangle of a quad, -1 if none (canonical form below)
    parts: list[PartInfo]
    anchors: dict[str, Anchor]     # "part:anchor" (literal spec strings) -> world frame; placements, sockets, joints
    sockets: dict[str, dict]       # name -> {"ref": "part:anchor"} | {"grip", "center", "palm", "up", "hand"} (§5.5, §11.1)
    relations: list[dict]          # expanded: reflect-mirrored and array-expanded copies of the spec's relations
    source: dict                   # {"spec_id","rev","seed","tables_version","level","evaluator","kind",
                                   #  "origin_offset": [x, y, z] applied by the origin rule}
    extra: dict = field(default_factory=dict)     # JSON; read-backs: {"objects","stamps","socket_empties"}
    fields: dict[str, np.ndarray] = field(default_factory=dict)  # named arrays (heightfields, SDF grids; S2+)
    frames: np.ndarray | None = None              # (F, P, 16) per-part world matrices per frame (motion, joints)

    def part(self, name) -> PartInfo
    def bounds(self) -> tuple[np.ndarray, np.ndarray]
    def validate(self) -> list[str]
        # shapes and dtypes; part slices contiguous and covering; ids in range; unit n/t, |t·n| < 1e-9;
        # quads canonical: for quad_mate[i] = j >= 0, either j == i+1 (i is the first half) or j == i-1;
        # first half (a,b,c), second half (a,c,d): tris[j,0] == tris[i,0] and tris[j,1] == tris[i,2];
        # mates reference existing parts; frames (if any) shaped (F, len(parts), 16)

def quads_to_tris(quads: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(Q,4) quads [a,b,c,d] -> (2Q,3) tris [(a,b,c),(a,c,d)] interleaved, and quad_mate. Every builder uses it."""

def geom_hash(m: EvalMesh) -> str:
    def q(a):
        return np.rint(np.asarray(a, np.float32).astype(np.float64) / Q).astype("<i8").tobytes()
    h = hashlib.sha256(FORMAT.encode() + b"\0")
    for p in sorted(m.parts, key=lambda p: p.name.encode()):
        h.update(p.name.encode() + b"\0")
        h.update(q(p.matrix))
        h.update(q(m.verts_local[p.v0:p.v1]))
        h.update((m.tris[p.t0:p.t1] - p.v0).astype("<i4").tobytes())
    return h.hexdigest()

def eval_hash(m: EvalMesh) -> str:
    """geom_hash, then anchors (sorted keys: key, q(p, n, t)) and sockets (sorted, canonical JSON)."""

def part_hash(m: EvalMesh, name: str, root_frame: bool = True) -> str
    # geom recipe for one part plus its anchors (keys "name:..."); root_frame subtracts
    # source["origin_offset"] from the matrix translation AND from those anchor points, so re-centring
    # the asset after an edit does not count as a change (locality, §10.2)
def save_npz(m: EvalMesh, path) -> None
def load_npz(path) -> EvalMesh                  # with np.load(path, allow_pickle=False) as z: ... (closes the file; Windows)
def fixture_boxes() -> EvalMesh                 # base_C 0.4x0.4x0.1 on ground, post_C 0.1x0.1x0.5 on it,
                                                # top_C 0.3x0.3x0.05 on that; anchors top_c/bottom_c; sockets {"top": {"ref": "top_C:top_c"}}
```

**`.npz` exchange** (host ↔ Blender, both directions): arrays `verts_local` (float64), `verts`
(float64), `tris` (int32), `part_id` (int16), `uv` (float32), `edge_flags` (uint8), `quad_mate`
(int32), optional `frames` (float64) and `field_<name>`, and `meta`: a uint8 array holding UTF-8 JSON
`{"format": FORMAT, "source", "parts": [PartInfo as dict], "anchors", "sockets", "relations", "extra"}`.
No object arrays; always `allow_pickle=False`. Files are written to `cache_dir("spec_build")` and closed
before Blender starts. Read-back files set `source.level` to `"emitted"` or `"finished"`, copy `parts`
(mates, measures, deps), `anchors`, `sockets` and `relations` from the emit `.npz`, take matrices from
the `opus_matrix` stamps and put `{"objects": [...], "stamps": {...}, "socket_empties": {...}}` in
`extra`. A quad read back from Blender is split (a,b,c),(a,c,d) in polygon order, which reproduces the
evaluator's triangle order because builders emit quads only through `quads_to_tris`.

### 4.6 Sheet measures (`compile/measure.py`)

Builders record measures; T1 re-measures; both call these functions, in the part's canonical frame
(§4.1), on `verts_local` and part-local triangles.

```python
MEASURE_RE = r"^(extent_[xyzuv]|depth|radius_max|(width_at|thick_at|circ_d):(0|1|0\.\d+))$"
def measure(verts_local: np.ndarray, tris_local: np.ndarray, key: str) -> float
def section(verts_local, tris_local, f: float) -> list[np.ndarray]   # closed loops of the plane z = z0 + f·(z1 − z0)
def tess_bound(key: str, builder: str, params: dict, K: int) -> float # allowed |built − spec| from tessellation
```

| Key | Definition |
|---|---|
| `extent_x`, `extent_y`, `extent_z` | ptp of the local coordinate |
| `extent_u`, `extent_v`, `depth` | extrude only: `extent_x`, `extent_y`, `extent_z` |
| `radius_max` | max √(x² + y²) |
| `width_at:f`, `thick_at:f` | x-extent and y-extent of the section at height fraction f |
| `circ_d:f` | perimeter of the section's outer loop (largest perimeter) / π |

`PartInfo.measures[key] = {"spec": analytic value from the params (None when there is none), "built":
measure(...) on the builder's output}`. Builders assert |built − spec| ≤ `tess_bound` (1e-9 relative
for extents and for widths at stations; an inscribed K-gon's factor K·sin(π/K)/π for `circ_d`; the
linear-interpolation bound between stations). Station-loft K is a multiple of 4 so `width_at` and
`thick_at` are exact at stations. A dim's `measure` names a part: `"grip_C:circ_d:0.5"`.

### 4.7 Finding contract and registry (`gates/finding.py`, `gates/registry.py`, `data/schema/finding.schema.json`)

```python
CLASSES = ("hard", "soft", "report")
TIERS = ("T0", "T1", "T2", "T2b", "T3", "T4", "T5", "T6")
FAMILIES = ("contact", "floating", "manifold", "sheet", "naming", "relation", "overlap", "consistency")

@dataclass
class Target:
    part: str | None = None; other: str | None = None; view: str | None = None; path: str | None = None
    bone: str | None = None; frames: list | None = None; pose: str | None = None; cell: list | None = None

@dataclass
class Fix:
    spec_path: str | None          # JSON pointer that fixes it
    suggest: str                   # one line, imperative
    dial_unit: str | None = None   # "m" | "ratio" | "deg" | "count" | "anchor" | "name"

@dataclass
class Finding:
    gate: str                      # the calling tool ("spec_check", "spec_validate", "spec_build", "export_asset")
    check: str                     # registry id, e.g. "contact_gap"
    klass: str                     # JSON key "class"
    tier: str
    target: Target
    value: float | int | str | bool | None
    expected: str                  # "<=0.002" | ">=0.99" | "==0" | "in[0.9,1.1]" | "true"
    unit: str                      # "m" | "px" | "deg" | "count" | "ratio" | ""
    noise_tol: float               # ε for spec_edit (§10.3); 0 for exact checks
    passed: bool                   # JSON key "pass"; a NaN value never passes
    family: str | None = None      # stamped by the runner from the registry
    armed: bool = True             # stamped by the runner from armed(); False: reports, never blocks
    evidence: str | None = None    # path to an image or npz
    fix: Fix | None = None
    message: str = ""

    def key(self) -> tuple: return (self.check, self.target.part, self.target.other, self.target.view)
    def blocking(self) -> bool: return self.klass == "hard" and self.armed and not self.passed
    def magnitude(self) -> float:
        """0 when passed. "<=x": (v-x)/max(|x|,1e-9); ">=x": (x-v)/max(|x|,1e-9); "in[a,b]": distance
        outside /(b-a); "==x" numeric: |v-x|/max(|x|,1); booleans, strings, None: 1."""
    def to_json(self) -> dict      # numpy scalars -> Python (np.bool_ -> bool, np.integer -> int,
                                   # np.floating -> float); NaN/inf -> None; validates against the schema in tests
    @staticmethod
    def from_json(d) -> "Finding"

@dataclass(frozen=True)
class CheckSpec:
    check: str; tier: str; klass: str; family: str | None
    scope: str                     # "asset" | "part" | "pair"
    stages: tuple[str, ...]        # of "spec", "eval", "emitted", "finished" (read-backs), "export"
    needs_suite: bool              # True: blocks only once armed.json arms it (K8)
    owner: str                     # "A" | "C" | "D" | "E"
    fn: Callable[["GateContext"], list[Finding]]
    profiles: tuple[str, ...] = ("cad_clean", "kitbash", "organic")

REGISTRY: dict[str, CheckSpec] = {}
CHECK_MODULES = ("opus.gates.t0", "opus.gates.t1", "opus.gates.t2", "opus.gates.consistency", "opus.gates.built")
def register(spec: CheckSpec) -> None          # a duplicate id raises ValueError
def load_checks() -> dict[str, str]            # imports CHECK_MODULES; {module: error} for those that fail;
                                               # the runner adds one report-class not_available finding per failed module
def armed(check: str) -> bool                  # not needs_suite, or data/gates/armed.json[check]["armed"]
def gate_profiles() -> dict                    # data/gates/profiles.json (§9.2)

@dataclass
class GateContext:
    resolved: dict                 # ResolvedSpec
    mesh: EvalMesh                 # evaluator mesh, or the mesh under test (defects)
    spec: dict | None = None
    emitted: EvalMesh | None = None   # read-back before finishing
    built: EvalMesh | None = None     # finished read-back
    profile: dict = field(default_factory=dict)   # = resolved["gates"]
    parts: set[str] | None = None  # local re-run scope; None = all
    evidence_dir: Path | None = None
    blend: Path | None = None
    readback_npz: Path | None = None
    run_task: Callable[[str, dict], dict] | None = None   # injectable Blender runner (tests pass a fake)
    gate: str = "spec_check"       # copied into Finding.gate
```

JSON form (OVERHAUL §2.5 plus `tier`, `family`, `armed`, `message`):
`{"gate","check","class","tier","target":{...},"value","expected","unit","noise_tol","pass","family","armed","evidence","fix":{"spec_path","suggest","dial_unit"},"message"}`.
The same failure has the same `key()` whichever tool reports it.

### 4.8 Resolved spec (`compile/resolved.py`, `data/schema/opus.resolved.1.schema.json`)

```python
class RDim(TypedDict):
    value: float; min: float; max: float
    unit: str        # "m" | "ratio" | "deg" | "count" | "kg"
    src: str         # human-readable provenance
    tag: str         # measured | derived | recalled | user | design
    kind: str        # table | record | range | expr | profile | user | design
    path: str        # "/dims/<name>"
    licence_id: str | None
    measure: NotRequired[str]          # "<part>:<measure key>" (§4.6)
    tol: NotRequired[float]            # relative tolerance for dim_measure
    int: NotRequired[bool]
    sanity: NotRequired[list[float]]   # resolved [lo, hi]

class RCamera(TypedDict):
    name: str; projection: str; vfov_deg: float; ortho_h: float; res_w: int; res_h: int
    d_close: float; d_typical: float; d_far: float; near_m: float; scale: float
    view: str; elevation_deg: float; viewmodel: bool    # viewmodel picks contact_fp_m (§9.2)

class RFeature(TypedDict):
    rank: int; id: str; parts: list[str]; views: list[str]; min_px: float

class RPart(TypedDict):
    name: str; src: str
    builder: NotRequired[str]      # absent for reflect parts
    params: NotRequired[dict]      # dim name, expr string, "@<attr>", "auto", preset word, profile key
    place: dict | None             # {"attach"|"squeeze"|"translate"|"reflect": {...}} | {"orient": word}; None = root at origin
    array: dict | None             # {"radial": {...}} | {"linear": {...}}
    material: str
    edges: dict                    # {"cutting": "sharp", ...}
    post_eval: bool

class ResolvedSpec(TypedDict):
    resolved: str                  # "opus.resolved/1"
    id: str; rev: int; kind: str; category: str; style: str; seed: int; tables_version: str
    camera: RCamera; origin: str   # "bottom_center" | "socket:<name>" | "none"
    wielder: dict[str, float]      # "wielder.hand_length" -> m; {} without a wielder
    features: list[RFeature]
    dims: dict[str, RDim]
    profiles: dict[str, dict]      # literal param string -> that one resolved variant (§14.2)
    parts: list[RPart]
    relations: list[dict]          # as written; EvalMesh.relations holds the expansion
    sockets: dict[str, dict]       # name -> {"ref": "part:anchor"} | {"grip": part, "center": float, "palm": word, "up": word, "hand": "r|l"}
    joints: dict[str, dict]        # name -> {"part", "type", "anchor", "axis", "limits_deg": [lo, hi]}
    gates: dict                    # merged thresholds: profiles.json < bible < spec overrides (§9.2)
    provenance: dict               # §5.1
```

### 4.9 Tools, CLI groups, Blender tasks, run-ledger hooks

```python
# opus/tools/__init__.py
MODULES = ("spec", "preview", "build", "check", "edit", "data")
GROUPS = {"spec": "spec_cmd", "gates": "gates_cmd", "data": "data_cmd"}   # group -> argparse dest
def register_all(tool) -> None         # for m in MODULES: import opus.tools.<m>; m.register(tool)
def add_cli_all(sub) -> dict           # creates each group once: sub.add_parser(g).add_subparsers(dest=GROUPS[g],
                                       # required=True); then m.add_cli(sub, groups) for every module
def run_cli(args) -> int | None        # the first m.run_cli(args) that returns an int (exit code); None = not ours
```

Each module defines `register(tool)`, `add_cli(sub, groups)` and `run_cli(args) -> int | None`. WP0
writes the six modules as stubs registering **all 11 tools with their final §15 signatures**; each stub
raises `ValueError("<tool> is not built yet (WP-x)")`. Packages replace bodies only, importing their code
lazily inside the tool (the existing `mcp_server` pattern). `tests/test_mcp.py`'s `EXPECTED` gains the 11
names once, in WP0. Verbs per module: `spec` group — `new`, `validate`, `resolve` (A), `preview` (C),
`build` (E), `check` (D), `edit` (G); `gates` group — `inject`, `calibrate`, `fixtures` (D); `data`
group — `fetch`, `build`, `list` (F; WP0 moves the existing `opus data build` here unchanged); top-level
`dims` (A) and `export` (E). `cli.main` calls `tools.run_cli(args)` before its own dispatch and returns
its code; `mcp_server.py` calls `tools.register_all(_tool)` after `run_stats`.

`entry.py` gains lazily imported tasks: `spec_emit` (emit.run), `spec_readback` (readback.run),
`spec_consistency` (consistency.run), `spec_export` (export.run), `spec_eval_hash` (compile_eval.run),
`raster_tie` (raster_tie.run). `runner.run_task` sets `OPUS_HOST_SRC` (= `python/src`) in Blender's
environment and `entry.py` appends it to `sys.path`, so Blender imports `opus.compile`.

**Run ledger hooks** (`runs.py`, WP0; WP-G owns the file afterwards):
- `EVENTS["spec_round"] = {"n": int, "tier": str, "hard_fail_count": int, "findings": dict, "outcome":
  str, "rev": int, "tool": str}` (outcome `checked` | `accepted` | `rejected` | `built`) and
  `EVENTS["design_pick"] = {"dim": str, "value": float, "finding": str, "rev": int}`.
- `log_if_open(event, near=None, **fields) -> dict | None`: logs into the open run, or returns None
  when there is none (tools never fail for lack of a run); for `spec_round` it assigns `n` = the run's
  previous `spec_round` count + 1 when not given.
- `findings_counts(findings: list[dict]) -> dict[str, int]`: failing blocking findings counted by check.
- Who logs what: `spec_check` one `spec_round` per call (`checked`); `spec_edit` one per call (`accepted`
  or `rejected`; its internal re-gate does not log again) plus one `design_pick` per picked design value;
  `spec_build` one (`built`); `spec_validate` one `validator_rejection` per hard T0 finding (other tools
  running T0 do not log rejections again).
- `compare(..., tasks: list[str] | None = None)`; CLI `opus eval compare --tasks a,b,c --metric
  iterations_to_accept` (`metric` already exists as a parameter). There is no token tie-break.

### 4.10 Packaging, repository hygiene and fixtures in WP0

- `pyproject.toml`: version 0.5.0; dependency `pydantic>=2.11,<3`; extras `feq = ["PyGEL3D"]`,
  `terrain = ["fastscapelib", "pydelatin", "numba"]`, `hulls = ["coacd"]`, `uv = ["xatlas"]`,
  `ref = ["opencv-python-headless"]`, `gpu = ["cupy-cuda12x"]`, `lod = ["pyfqmr"]`; dev dependency
  `ruff` pinned to an exact version, `[tool.ruff]` (py313, line length 120, default rules + `PLW1514`
  unspecified-encoding); WP0 fixes the existing ruff errors (7 with default rules, per the review).
  Pytest markers `blender`, `perf`, `network` (never in CI), `integration`. `uv lock` refreshed; note
  that numba and cupy cap `numpy<2.6`, which the universal lock applies to the core environment (it
  resolves to 2.5.3 today, probed). psutil, scipy and scikit-image join the core when first used (S1, S1, S3).
- `.claude-plugin/plugin.json` and `opus/__init__.py` → 0.5.0.
- `.gitattributes`: `* text=auto eol=lf`; `*.png *.jpg *.npz *.glb *.fbx *.blend binary`.
- `extras.py`: `require(extra: str, module: str)` imports lazily or raises `ValueError("install opus[<extra>]: …")`.
- `paths.safe_name(id) -> str`: characters outside `[A-Za-z0-9._-]` → `_` (so `met:23367` →
  `met_23367`; a `:` in a Windows file name silently writes an NTFS alternate stream), Windows device
  names (CON, PRN, AUX, NUL, COM1–9, LPT1–9) get a `_` suffix, trailing dots and spaces are dropped. Every
  path built from an id uses it. Every text read and write passes `encoding=` (ruff `PLW1514`).
- `tests/conftest.py`: tests that need Blender get the `blender` marker automatically (including the
  existing `skipif` ones, which the CI blender job otherwise never selects); `integration` tests skip
  unless every package is present.
- `tests/fixtures/s0b/`:
  - `resolved_box3.json` (three boxes stacked by face attach); `resolved_mixed.json` (every builder and
    every placement mode: face attach with spin and offset, point attach, translate, squeeze, orient,
    reflect in yz, xz and xy, radial and linear arrays, `@radius`, `@profile`, a profile anchor);
    `resolved_joint.json` (a joint root with re-origin and a subtree, quads, a squeeze, a grip socket);
  - `ab6/<id>.spec.json`: the six Appendix A specs verbatim (their resolved goldens are added in the
    integration phase, §17);
  - `profiles/*.json`: synthetic stand-ins with the real ids, in the §14.2 schema;
  - `tables/*.json`: stand-ins for `oakeshott`, `museum_arms`, `museum_records` (holding the real record
    values of §2), `weapon_facts`, `ada_2010` and `anthro_ansur2` v2 (with `measures_mm`);
  - `raster/`: the §2 probe cases `case0–5` (.json + .png) and the tie case;
  - `evalmesh_box3.npz` (`fixture_boxes()`), `readback_box3.npz` (with `extra`: objects, stamps, socket empties);
  - stub-kind round trips: an EvalMesh with `frames` and a `field_*` array; a `Proxy2D` JSON.
- `data/gates/profiles.json` (§9.2), `data/schema/opus.profile.1.schema.json` (§14.2).
- CI stub: WP0 pushes a one-job `ci.yml` (host tests on ubuntu-24.04) and confirms a run through the
  GitHub MCP tools (§16) before fan-out.

---

## 5. Spec language in S0b

### 5.1 Envelope

Implemented and validated: `spec` ("opus.asset/1"), `kind`, `id` (`^[a-z][a-z0-9_]{1,63}$`), `rev` (≥1),
`parent_rev`, `category`, `style` (lowpoly | stylized | hd | pixel3d), `units` ("m"), `up` ("+Z"),
`front` ("-Y"), `camera` (bible profile id or inline profile), `template`, `tables_version`, `seed`
(int ≥0), `wielder`, `origin`, `features` (1–7 `{rank, id, parts, views, min_px}`; soft warning outside
5–7 for characters, 3–7 for props; views from §4.2 plus `game`), `shape_language`, `size_tiers`,
`palette_roles` (stored and syntax-checked; colours apply from S2), `must_avoid`, `dims`, the kind body
(`parts`, `relations`, `sockets`, `joints`, `materials` for `assembly`), `explore` (stored, unused until
S3), `gates`, `surface`, `lock`, `provenance`, `history`. Every other kind validates its envelope and an
open body; `spec_build` then reports `not_available` with the kind's sprint.

`provenance` is written by tools only: `{"tables": {name: version}, "profiles": {key: sha256},
"records": {ref: {"sha256", "committed": bool}}, "licences": [ids], "tools": {name: version}}`; T0
`schema` validates it and soft `provenance_edited` reports a hand edit (its hash in `lock` differs).

`wielder`: `"ansur2:<male|female>:p<5|50|95>"` or `{"preset": ..., "user": {"stature": 1.83}}`. It
provides `wielder.stature, hand_length, hand_breadth, popliteal_height, buttock_popliteal_length,
elbow_rest_height, thumbtip_reach` in metres (absolute bands from `anthro_ansur2` v2; `user` values
override and are logged).

### 5.2 Dimension sources

Every number lives in `dims`. Each entry is exactly one source form plus optional common keys `unit`
(default "m"), `doc`, `tol`, `measure`, `sanity`, `int`, `value` (a resolved pick, written only by
`spec_edit`, the user, or lock).

| Form | Example | Resolves to | Tag |
|---|---|---|---|
| table | `{"table": "oakeshott.types.XIV.grip_len", "pick": "value\|sample\|min\|max", "style_mult": 1.15}` | the fact's value (or seeded sample in [min, max]) × style_mult; z-score logged | the fact's tag |
| record | `{"record": "met:23367", "measure": "blade_len"}`; `{"record": "cma:1921.1252", "measure": "cross_w"}` | `museum_records.records.<safe_name(ref)>.<measure>` (committed, K17); else the library cache; measure keys are the parser's canonical keys (§14.1) | measured |
| range | `{"range": [0.0020, 0.0022], "src": "replica distal taper, Albion spec sheets"}` | seeded uniform sample | recalled (warnings only) |
| expr | `{"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005, NIOSH"}` | evaluated; `src` required for a literal other than 0.5, 1, 2 | weakest input tag |
| profile | `{"profile": "lib:cross.straight#cma:1923.1121", "param": "aspect"}` | the profile variant's parameter | the profile's tag |
| user | `{"user": 0.9}` | the value; logged | user |
| design | `{"design": [0.9, 1.3], "unit": "ratio"}` | `value` if set, else seeded sample; T0 soft `design_unresolved` | design |
| sketch | `{"sketch": [...]}` | — | T0 hard `not_available` (S4) |

`sanity`: a table ref or `"lo..hi"` (a literal band copied from the task, allowed only here); outside
it → soft `sanity_range`. `measure`: `"<part>:<key>"` (§4.6), checked by T1 `dim_measure` within `tol`.

### 5.3 Parts

```json
{"name": "<role_side[index]>",
 "build": {"<builder>": {"<param>": "<dim | expr | @attr | auto | preset | profile key>", ...}},
 "attach":    {"to": "<part|ground>", "at": "<anchor>", "self": "<anchor>", "mode": "face|point",
               "spin": 0, "offset": "<dim|expr>", "clearance": "<dim|expr>"},
 "squeeze":   {"from": "<part:anchor>", "to": "<part:anchor>", "self": ["<anchor>", "<anchor>"]},
 "translate": {"from": "<part:anchor>", "self": "<anchor>", "by": ["<dim|0>", "<dim|0>", "<dim|0>"]},
 "reflect":   {"of": "<part>", "plane": "yz|xz|xy", "through": "<part:anchor>"},
 "orient":    "up|front|back|left|right|down",
 "array":     {"radial": {"n": "<count dim>", "phase": "<frac>"}} | {"linear": {"n": "<count dim>", "axis": "x|y|z", "span": "<dim|expr>"}},
 "edges":     {"cutting": "sharp|bevel|smooth", "rims": "...", "all": "..."},
 "post_eval": false}
```

Exactly one of `attach`, `squeeze`, `translate`, `reflect`, `orient`, or none (a root at the origin).
Placement maths is §4.1. A reflected part is declared with its own name; its sides follow the plane
(T0 `reflect_sides`): `yz` swaps `_L`/`_R`, `xz` swaps `_F`/`_B`, `xy` keeps the side and needs a
different role or index. Reflected parts inherit the source's material and `edges`; relations naming the
source part are mirrored onto it in `EvalMesh.relations`.

**Literal numbers** are allowed only in `rev`, `seed`, `spin` (0–3), `features[]` (`rank`, `min_px`),
`shape_language`, `size_tiers`, `gates` overrides, relation `tol_deg`, joint closed limit `0`,
`translate.by` zeros, anchor sixteenths 0, 8 and 16 (§4.1 grammar), and inside `dims` source forms. In
any expression (dims or build params) the literals 0.5, 1 and 2 are free (half of a diameter, a
complement, both sides); any other literal needs the dim's `src` and is rejected in build params.

Preset words for `n` (section exponent): `diamond` 1, `lens` 1.5, `round` 2, `squircle` 4, `boxy` 8.

### 5.4 Builders, parameters and anchors

| Builder | Params | Canonical frame | Anchors (plus `uvw:a,b,c` on every builder: the canonical bbox point at fractions a, b, c along x, y, z; n = +z, t = +x) | Measures recorded |
|---|---|---|---|---|
| `box` | `sx sy sz` (`auto` allowed for squeeze) | centred bbox | face centres `top_c bottom_c front_c back_c left_c right_c` (left = +x; t = +x, left/right t = +y; attrs w, h of the face, d along n); edge midpoints `top_back top_front bottom_back bottom_front` (n outward-diagonal, t along the edge); `section_x@f`, `section_y@f`, `section_z@f` (attrs w, h of the cross-section) | `extent_x/y/z` |
| `superquadric` | `sx sy sz e1 e2` | centred | as box | `extent_x/y/z` |
| `extrude` | `profile` (an outline key or prim), `plane` XZ\|YZ\|XY (→ `R_b`), `len` (uniform scale so the profile's `ref` equals len), `h` (optional: rescales v to this extent; logged), `depth` (centred), prim params | profile in local XY, extruded along local Z | bbox faces; every profile anchor (point at mid-depth, n from the profile, t = local +Z); `inner_c`, `inner_corner` for prims | `extent_u`, `extent_v`, `depth` |
| `lathe` | `profile` (a radius curve or loop, or prim), prim params (`r`, `r_max`, `len`, `h`, `d`, ...), `axis` z\|x\|y (→ `R_b`), `segments` (count dim; default camera rule), `phase` | axis local +Z from 0 | `bottom_c`, `top_c` (n ∓z, t = +x), `ring@f` (on the axis at height fraction f; attrs `radius` = outer radius there), `rim_+x rim_-x rim_+y rim_-y` (outer surface at the max-radius height; n radial, t = +z) | `extent_z`, `radius_max`, `circ_d:f` for dims that name them |
| `station_loft` | `len`, `stations` ("auto" or count dim), `width_profile` + `w` (a = ½·w·v(s)) or `a`; `t` (b = ½·t) or `b`; `n` (preset, dim or expr of s); `axis` (→ `R_b`); `segments` | axis local +Z from 0 to len | `bottom_c`, `top_c`, `ring@f` (attrs a, b, n), `side_+x@f side_-x@f side_+y@f side_-y@f` (surface point, n outward, t = +z) | `extent_z`, `width_at:f`, `thick_at:f` for f in {0.1, 0.5, 0.9} and profile breakpoints, `circ_d:f` for dims that name them |

`@<attr>` in a param reads the attach target anchor's attribute (`@radius`, `@w`, `@h`, `@a`, `@b`);
`@profile` (lathe `band` only) copies the parent lathe's radius function over the band's height, plus
`clearance`.

**Tessellation** (`level="build"`; `level="fit"` uses the raster's own pixels per metre):
- Round sections: K = `camera.circle_segments(r_max, camera.ppm(d_close))`; style `lowpoly` caps K at 12
  and floors at 6 unless `segments` is given; station-loft K is rounded up to a multiple of 4.
- Profile curves (outlines, radius curves, width curves): `line` segments contribute their end points
  only; `arc` and `cubic` segments are subdivided by the sagitta rule at 0.5 px at d_close.
- Station lofts: stations at the profile breakpoints and the ends, plus uniform spacing (≤8 game px at
  d_close for hd, ≤24 px for lowpoly; 4–64 stations) **only over intervals where a(s), b(s) or n(s)
  varies**; a constant section uses its end stations only.
- A width or radius that reaches 0 at an end becomes a single apex vertex (no degenerate triangles);
  radius curves touching the axis become poles; seams are welded, so every part is a closed 2-manifold.
- Edge flags: `EDGE_SHARP|EDGE_BEVEL` on box edges, cap rims and profile corners whose tangent turns by
  ≥30° (tangent joins between segments are not corners); `cutting` = station-loft θ = 0 and π lines;
  `edges` in the spec rewrites flags per set.

**Profiles and prims.** Library keys: `lib:<family>.<name>#<variant>` (variant optional = the family
default). Primitive families (`prim:`) are geometric, have no provenance and take every parameter from
dims:

| Prim | Kind (§14.2) | Params |
|---|---|---|
| `rect` / `rect_ring` / `rect_u` | outline | `w h` / `w_in h_in wall` / `w_in h_in wall open: top\|bottom` (anchor `inner_c` = centre of the inner rectangle) |
| `angle_l` | outline | `leg wall`; inner corner at the origin (anchor `inner_corner`), legs along +u and +v, walls on the −v and −u sides |
| `circle` | outline | `d` |
| `axe_bearded` | outline | `edge_len eye_h eye_w neck_w head_len beard_drop` (eye block around `eye_c`; neck to an arced edge; a concave beard arc from the neck's lower side down to `beard_drop` below the eye); the A.2 fallback (§14.2) |
| `cylinder` / `disc` | radius_curve | `d len` / `r t` |
| `baluster` | radius_curve | `len r_max r_end_frac r_neck_frac bulb_s neck_s` (cubic segments through the foot, bulb, neck and top radii); the A.6 fallback |
| `annulus_slab` | radius_loop | `r_out r_in t` |
| `band` | radius_loop | `r_in` (or `@profile`), `w`, `t`, `clearance` |
| `dome_shell` | radius_loop | `d h wall flange` |
| `barrel_arc` | radius_curve | `h r_end r_mid` (circular arc through the three points, flat ends to the axis) |

### 5.5 Relations, sockets, joints

- Relations: `coaxial`, `parallel`, `perpendicular` (`{"a": "part[.axis]", "b": "...", "tol_deg"}`, axis
  default the canonical z, `tol_deg` default the profile's `angle_tol_deg`), `symmetric` (implied by
  `reflect`), `embedded` (`a` may interpenetrate `b`; mirrored automatically for reflect pairs),
  `contact` (`a` and `b` must touch though neither places the other).
- Sockets: `"tip": "blade_C:top_c"` → empty `SOCKET_tip` on that anchor. **Grip sockets** (name
  `grip_*`): `{"grip": "<part>", "center": "<frac>", "palm": "<axis word>", "up": "<axis word>",
  "hand": "r|l"}` with axis words `+x -x +y -y +z -z` (defaults 8/16, `+y`, `+z`, `r`) → a v0.4 grip
  (K18, §11.1): the handle runs along the part's canonical z axis, pointed so that d·up ≥ 0 as
  `grip_define`'s `up` hint does (d·X ≥ 0 when d ⟂ up).
- Joints: `{"lid": {"part": "lid_C", "type": "revolute", "anchor": "body_C:top_back", "axis": "t",
  "limits": [0, "lid_open_max"]}}` (limits in degrees for revolute, metres for prismatic). The joint
  moves the part and its placement descendants (the joint subtree: `PartInfo.joint_root`); the part's
  origin sits on the joint axis (K19).

### 5.6 T0 validator rules (`spec/validate.py`)

| Check | Class | Family | Rejects |
|---|---|---|---|
| `schema` | hard | — | JSON Schema violations, unknown keys |
| `units_frame` | hard | — | units ≠ m, up ≠ +Z, front ≠ −Y |
| `unsourced_number` | hard | — | a numeric literal outside the §5.3 places; an expression literal other than 0.5, 1, 2 without `src` |
| `free_anchor` | hard | — | an anchor sixteenth other than 0, 8 or 16 (use a ratio dim or a template slot) |
| `typed_colour` | hard | — | a hex or RGB value without a palette source |
| `name_format`, `name_duplicate`, `name_reserved` | hard | naming | §4.1 rules |
| `reflect_sides` | hard | naming | a reflect pair whose sides do not follow its plane (§5.3) |
| `unknown_ref` | hard | — | parts, anchors (`builder_anchor_names`), dims, profiles or tables that don't exist; ratio dims outside [0, 1] |
| `parent_cycle` | hard | — | cycles in attach/squeeze/translate/reflect or in expressions |
| `too_many_parts` | hard | — | >12 declared parts (array copies count once) |
| `table_range` | hard (soft if the fact is `recalled`) | — | a resolved value outside [min, max] × style_mult |
| `missing_licence` | hard | — | a table or profile without a `data/LICENSES.md` entry, or an unknown licence ID |
| `record_unavailable` | hard | — | a `record` in neither `museum_records` nor the library cache (and not fetchable when `OPUS_OFFLINE` is unset); a record that is not CC0 / public domain |
| `todo_unfilled` | hard | — | template placeholders left (`{"user": null}`) |
| `not_available` | hard | — | a kind, builder or source form from a later sprint |
| `design_unresolved` | soft | — | `design` dims without `value` |
| `sanity_range` | soft | — | outside `sanity` |
| `record_uncommitted` | soft | — | a record resolved from the library cache, not the committed table |
| `provenance_edited` | soft | — | `provenance` changed by hand |
| `tables_version_drift` | soft | — | the spec's `tables_version` ≠ current, unlocked |

All T0 checks are exact (`needs_suite=False`, K8). Feature pixel sizes need the evaluator, so they are
T1 (`feature_px_game`, §9.3) and `spec_validate` reports camera numbers only.

---

## 6. dims_resolve, tables_version, lock (`opus/dims.py`)

```python
def dims_resolve(spec: dict | str, wielder: str | dict | None = None, style: str | None = None,
                 seed: int | None = None, near=None) -> tuple[ResolvedSpec, list[Finding]]
def resolve_sheet(category: str, wielder=None, style="hd", seed=0) -> dict   # template dims only (the tool's category mode)
def lookup(ref: str) -> dict          # "oakeshott.types.XIV.grip_len" -> fact; dotted path from the table's top level
def record(ref: str, measure: str) -> dict   # museum_records first, then the library cache (§14.3)
def wielder_sheet(w) -> dict[str, RDim]
def tables_version() -> str           # "t-" + sha256 over sorted (relpath.as_posix(), bytes with CRLF->LF) of
                                      # data/tables/*.json and data/profiles/*.json, first 12 hex
def lock(spec: dict) -> dict          # writes spec["lock"] = {"tables_version", "dims": {name: value},
                                      # "profiles": {key: sha256}, "records": {ref: value}, "rev", "provenance_sha256"}
```

Order: wielder → tables/records/profile params/users/ranges/design (each with `seeded_uniform(seed,
"dims/<name>")`) → expressions in dependency order (cycle → `parent_cycle`) → style_mult → T0 range
checks → camera (bible profile with distances; `RCamera`) → profiles inlined (one variant per literal
key) → gate thresholds merged (`data/gates/profiles.json` < bible `gates` < spec `gates`) → parts copied
with params untouched. Units: mm, cm, in convert to m; `stature` units multiply by `wielder.stature`. A
locked spec uses the lock's values and reports `tables_version_drift` as soft. Conflicting sources for one
dim (a table and a record) are not allowed in one entry; tables store conflicts as [min, max].

---

## 7. Compiler (`opus.compile`)

### 7.1 Evaluator contract for every kind (`compile/kinds.py`, WP0)

```python
class KindNotAvailable(ValueError):           # a ValueError, so MCP shows its message to Claude
    def __init__(self, kind: str, sprint: str): ...
KINDS = {"assembly": "S0b", "body.human": "S1", "body.creature": "S2", "garment": "S7", "harness": "S7",
         "terrain": "S9", "tree": "S9", "building": "S10", "kit": "S10", "layout": "S10",
         "motion": "S5", "face": "S10", "hair": "S10"}
LEVELS = {"assembly": ("fit", "build"), "body.human": ("fit", "build"),
          "body.creature": ("proxy2d", "confirm", "build"), "garment": ("envelope", "build"),
          "harness": ("envelope", "build"), "terrain": ("heightfield", "build"), "tree": ("skeleton", "build"),
          "building": ("fit", "build"), "kit": ("fit", "build"), "layout": ("transforms",),
          "motion": ("frames",), "face": ("contract",), "hair": ("contract",)}
POST_EVAL_KINDS = {"garment", "harness", "tree", "face", "hair"}

@dataclass
class Prim2D:
    part: str; kind: str           # "ellipse" | "stadium" | "polygon"
    params: dict                   # centre, axes, angle | end points, radius | points

@dataclass
class Proxy2D:                     # body.creature level "proxy2d" (S2): projected primitives per view
    views: dict[str, list[Prim2D]]; smooth_k: float; source: dict
    def to_json(self) -> dict
    @staticmethod
    def from_json(d) -> "Proxy2D"
```

What each level returns: `proxy2d` → `Proxy2D`; `frames` and `transforms` → `EvalMesh` with `frames`
(F, P, 16); `heightfield` → `EvalMesh` with `fields["height"]` (and its grid triangles at `build`);
`skeleton` → `EvalMesh` with `fields["skeleton"]`; `contract` → `EvalMesh` without triangles and the
contract in `extra`; every other level → `EvalMesh` with triangles. WP0 tests round-trip each container
through `save_npz`/`load_npz` or JSON.

### 7.2 Assembly evaluator and solver (`evaluate.py`, `solver.py`, WP-B)

```python
def evaluate(resolved: ResolvedSpec, level: str = "build", ppm: float | None = None) -> EvalMesh | Proxy2D
    # kinds other than assembly raise KindNotAvailable(kind, KINDS[kind]); a level not in LEVELS[kind] raises ValueError
def build_part(rpart: RPart, env: dict, anchors_in: dict, level: str, ppm: float) -> LocalPart
@dataclass
class LocalPart:                      # builder output, canonical frame
    verts: np.ndarray; tris: np.ndarray; uv: np.ndarray; edge_flags: np.ndarray; quad_mate: np.ndarray
    anchors: dict[str, Anchor]        # canonical-local frames
    measures: dict[str, dict]         # §4.6
    R_b: tuple                        # §4.1
```

Solver:
1. Expand the declared parts into a DAG: edges from attach/squeeze/translate/reflect targets, `@`
   attributes, reflect sources and array templates. Topological order; ties by declaration order.
2. For each part in order: evaluate params (env = dims + wielder + camera; `s` arrays inside the loft),
   build in the canonical frame, then place (§4.1). Joint roots are re-origined (K19). Array copies are
   placed after their template. Reflect parts are generated as soon as their source is placed, before
   any part placed on them.
3. Record world anchors under their literal keys, `mates` (one per placement contact, mirrored or
   turned for reflect and array copies, plus `contact` relations), the expanded `relations`, and `deps`:
   the **transitive closure** of the dims a part's params, placement and array fields read (through
   expression inputs), its placement targets (attach or translate parent, both squeeze targets), `@`
   sources and reflect source, and their `deps`.
4. Origin: `bottom_center` translates everything so the bbox bottom centre is at the origin (skipped
   when a part attaches to `ground`); `socket:<name>` puts that socket at the origin. The translation is
   stored in `source["origin_offset"]`.
5. Assemble the EvalMesh: parts concatenated in solve order, `verts = fmath.apply(matrix, verts_local)`;
   `validate()` must return [].

A test-only keyword `evaluate(..., _freeze=incumbent)` keeps every non-root part's matrix from the
incumbent EvalMesh; the dial-edit negative control uses it (§10.6).

**UVs** (`uv.py`): analytic islands per builder in metres (box faces planar; lathe and loft (θ/2π ×
circumference, arc length); extrude caps planar, sides (perimeter, depth)), seam edges flagged, then one
deterministic shelf pack per asset into [0, 1] with uniform texel density and 2 px padding at 1024 px.
S2 replaces this with the surface plan.

---

## 8. Raster, views, preview (`opus.compile.raster`, `views`, `opus.preview`; WP-C)

```python
def silhouette(m: EvalMesh, cam: RasterCamera, parts: list[str] | None = None) -> np.ndarray     # out_shape bool
def id_depth(m: EvalMesh, cam: RasterCamera) -> tuple[np.ndarray, np.ndarray]                    # int16 (-1 bg), float32 depth (inf bg)
def raster_reference(m, cam) -> tuple[np.ndarray, np.ndarray]                                    # edge-function, tests only
def view_camera(view: str | tuple[float, float], lo, hi, res: int | tuple[int, int], projection="ortho",
                camera: RCamera | None = None, margin: float = 1.1, jitter: bool = False) -> RasterCamera
def game_camera(m, rcam: RCamera, level: str = "typical", view: str | None = None) -> RasterCamera
    # the profile's full frame (res_w x res_h, its vfov, its view and elevation at distance d_<level>),
    # cropped to the asset's projected bbox + 2 px, clamped to the frame
def consistency_resolution(m: EvalMesh, view) -> tuple[int, int]
    # (W, H), each a multiple of 128 and <= 2048: the smallest part's larger projected extent >= 10 px
```

- **Silhouette**: project, drop back faces of closed parts (keep a triangle when its outward normal faces
  the camera; with y down that is a negative x₁y₂ − x₂y₁ signed area) and edge-on ones, expand
  (triangle, row) pairs, intersect each row centre with the three edges, apply the tie rule, accumulate
  `+1/−1` at span ends with `np.bincount`, cumulative sum per row.
- **IDs and depth**: the same spans expanded to pixels, depth by perspective-correct barycentrics, nearest
  per pixel by `np.lexsort((depth, pixel))`; processed in chunks of ≤4M pixel pairs.
- Ortho framing: centre on the bbox centre; W and H from the projected bbox aspect; `ortho_h` so the
  bbox × margin fits both ways. Perspective framing: distance so the bbox fits the vfov.

**Blueprint sheet** (`preview.blueprint(m, resolved, out) -> Path`, PIL, host only): front, right,
back and top orthographic views at one scale, filled silhouette plus part outlines in ID colours;
horizontal landmark lines (each part's top and bottom) across all views; 0.1 m / 1 m grid; callouts with
each part's as-built size in metres; a 1.8 m figure drawn from ANSUR p50 male fractions; a three_quarter
view; game-size insets at d_typical and d_far (true pixels, ×4 nearest neighbour, labelled with pixel
heights); a footer with id, rev, seed, `tables_version` and `eval_hash`. Masks per view are saved as ID
PNGs. `spec_preview` also runs T1 `feature_px_game` (§9.3): per feature, the part's eroded width and
extent in game pixels at d_typical and d_far, plus the per-part size tiers (`size_m`, `px_close`,
`px_far`, `tier`) that the first draft put in `spec_validate`.

---

## 9. Gates (`opus.gates`)

### 9.1 Runner (`gates/runner.py`, WP-D)

```python
def run_gates(ctx: GateContext, tiers=("T0", "T1", "T2"), stop_at_first_hard=True) -> dict
# -> {"ok": bool, "stopped_at": tier|None, "hard_fail_count": int, "hard_magnitude": float,
#     "soft_score": float, "findings": [Finding.to_json()], "by_tier": {tier: {"n","hard_fail"}},
#     "unavailable": {module: error}}
```

The runner calls `registry.load_checks()` once, runs each registered check whose tier is requested,
whose profile list holds `ctx.profile["profile"]` and whose stages include an available mesh (`eval` =
`ctx.mesh`, `emitted` = `ctx.emitted`, `finished` = `ctx.built`; a check with no available stage is
skipped without a finding), and stamps `gate`,
`family` and `armed` on every finding. `ok` = no blocking finding. Part and pair checks honour
`ctx.parts` (the patched part, its placement descendants and its reflect partners); asset checks
(floating, budgets, grounded, symmetry, T2b) always run.

### 9.2 Gate profiles (`data/gates/profiles.json`, WP0; bible overrides, WP-A)

| Key | cad_clean | kitbash | organic |
|---|---|---|---|
| `contact_m` (third person) / `contact_fp_m` (view-model camera, `RCamera.viewmodel`) | 0.002 / 0.0005 | 0.004 / 0.001 | 0.002 / 0.0005 |
| `overlap_m` (undeclared interpenetration depth) | 0.0005 | warn only | — (self-overlap, S2) |
| `sheet_rel` / `sheet_abs_m` | 0.02 / 0.001 | 0.05 / 0.002 | 0.02 / 0.001 |
| `anchor_m` | 1e-6 | 1e-6 | 1e-6 |
| `angle_tol_deg` (relations without `tol_deg`) | 0.5 | 1.0 | 0.5 |
| `grounded_m` | 0.0005 | 0.001 | 0.0005 |
| manifold | per part, strict | per part, strict | single skin (S2) |
| consistency (all profiles) | IoU ≥0.99, boundary p95 ≤0.5 px, depth p95 ≤1 game px, min part 10 px, `finish_delta_px` 1 | | |

Bible additions (WP-A, `opus.project.yaml` and `bible.DEFAULTS`): `gates: {profile_by_style: {hd:
cad_clean, stylized: cad_clean, lowpoly: cad_clean, pixel3d: cad_clean}, profiles: {...overrides}}`,
`3d.weapon_scale: 1.0`, `3d.gravity_mult: 1.0`, `3d.style_mult: {}`, `3d.texel_density: "camera"`
(stored for S2), `allow_nc: true`, `rating_budget_min: 20`, `twist_policy: ""` (S1). A spec's `gates`
overrides are logged in `history`. `dims_resolve` writes the merged result to `resolved["gates"]`
(including `profile` and `hard.tris`), which is `GateContext.profile`.

### 9.3 Check catalogue (S0b)

`Suite` = `needs_suite` (K8): "no" checks are exact and block from day one, each with a planted unit
test; "yes" checks block once `armed.json` arms them.

| Check | Tier / stage | Class | Family | Suite | Owner | Measures |
|---|---|---|---|---|---|---|
| T0 rules (§5.6) | T0 / spec | §5.6 | §5.6 | no | A (registered by D's `t0.py`) | |
| `anchor_error` | T1 / eval | hard | contact | yes | D | per mate: \|M_self·p_self − xf·M_other·p_other\| ≤ `anchor_m` |
| `sheet_as_built` | T1 / eval, emitted | hard | sheet | yes | D | each `measures` key re-measured (§4.6) on the mesh under test vs `built`, within max(sheet_rel × value, sheet_abs_m); and \|built − spec\| ≤ `tess_bound` |
| `dim_measure` | T1 / eval, emitted | hard | sheet | yes | D | dims with `measure`: the named part's measure vs the dim's value within `tol` |
| `relation_angle` | T1 / eval | hard | relation | yes | D | coaxial / parallel / perpendicular within `tol_deg` (default `angle_tol_deg`) |
| `symmetry_pair` | T1 / eval, emitted | hard | naming | yes | D | reflect pairs mirror within `anchor_m`; `_L` centroid x > +ε, `_R` x < −ε |
| `budget_tris_est` | T1 / eval | soft | — | no | D | evaluator triangles + an estimate of bevel growth (2·segments per flagged edge + corner patches) within the budget |
| `feature_px_game` | T1 / eval | soft | — | no | C | §8 lint |
| `manifold` | T2 / eval, emitted, finished | hard | manifold | yes | D | per part: 0 boundary edges, 0 edges with ≠2 faces, consistent orientation, 0 triangles with area < 1e-12 m², signed volume > 0 |
| `shells` | T2 / eval, emitted, finished | hard | floating | yes | D | 1 connected shell per part |
| `contact_gap` | T2 / eval, emitted, finished | hard | contact | yes | D | each mate pair and `contact` relation: distance ≤ `contact_m` |
| `floating` | T2 / eval, emitted, finished | hard | floating | yes | D | the contact graph (parts and `ground`, edges at distance ≤ `contact_m`) is one component |
| `overlap` | T2 / eval, emitted, finished | hard | overlap | yes | D | undeclared pairs: max inside depth ≤ `overlap_m` |
| `grounded` | T2 / eval, emitted, finished | hard | contact | yes | D | assets attached to `ground`: min z ∈ [−grounded_m, +grounded_m] |
| `com_over_footprint` | T2 / eval | soft | — | no | D | volume centroid over the support hull (≥5% margin) |
| `budget_tris` | T2 / finished | hard | — | no | D | triangles of the finished read-back (= what v0.4 `mesh_lint` counts, Bevel included) within `gates.hard.tris` or the bible budget |
| `naming_built` | T2 / emitted, finished | hard | naming | no | D | Blender names = spec names (no `.001`), stamps present and valid (FBX string stamps parsed), `SOCKET_<name>` empties present |
| `consistency_iou`, `consistency_boundary`, `consistency_depth` | T2b / emitted | hard | consistency | yes (no S0b suite: never armed in S0b; `test_consistency.py` asserts them) | C | §9.6 |
| `finish_delta_px` | T2b / finished | report | — | no | C | per part, finished vs evaluator boundary at the game camera; >1 px marks the part `post_eval` |
| `emit_hash` | T2b / emitted | hard | — | no | E | `geom_hash(emitted read-back) == geom_hash(evaluator)`; on mismatch the first differing part is named |
| `export_round_trip` | export | hard | — | no | E | §12.2 |
| `licence_blocked` | export | hard | — | no | E | §12.3 |

A module of `CHECK_MODULES` that fails to import adds one report-class `not_available` finding (per
module), so a package can merge before the modules it calls. Sheet and symmetry checks do not run on
the finished stage, where bevels legitimately change widths near rims; `finish_delta_px` covers it.

### 9.4 T2 algorithms (`gates/geom.py`, numpy only)

- **Grid per part**: cell = max(4 × tolerance, bbox diagonal / 64); each triangle registered in the cells
  its bbox ± tolerance overlaps; sorted cell keys with `np.searchsorted` for queries (as `rev/t2_grid_bench.py`).
- **Samples**: vertices ∪ triangle centroids ∪ edge midpoints, stride-subsampled to ≤4,000
  (deterministic), keeping only those inside the other part's bbox expanded by the tolerance.
- **Pair distance**: candidate triangles from the other part's grid; exact closest points (Ericson 5.1.5,
  vectorized; the logic of `closest_on_triangles` in `opus_bl/geom.py`, re-implemented without bpy);
  both directions; chunks of 1,024 samples with **early exit** once a distance ≤ tolerance is found (a
  pass needs no more). A failing pair's exact value comes from an expanding search (cell size doubled
  until a candidate appears or the bbox is covered).
- **Contact graph** (`floating`): only pairs whose bboxes overlap after expansion by `contact_m`; an edge
  when the pair distance ≤ `contact_m`; a part touches `ground` when its min z ≤ `contact_m`.
- **Inside test** (`overlap`): a sample of A inside B's bbox with no B triangle within `overlap_m` is
  classified by +Z ray parity against B's triangles from an XY grid, with half-open edges by the §4.2
  tie rule so each crossing counts once; depth = distance to B's surface (expanding search); the value
  is the max over inside samples.
- **Edges and shells**: undirected edge keys `min*V + max` with `np.unique(return_counts)`, orientation
  by directed-edge pairing; shells by label propagation (as `opus_bl.geom._labels`).
- **Budget** (`test_gates_perf`, asserted under `OPUS_PERF_ASSERT=1`): T1 + T2 ≤1 s on each ab6 spec at
  level build; ≤2 s on a synthetic 12-part, 50k-triangle asset.

### 9.5 Defects (`gates/defects.py`)

Sizes are **resulting** sizes: a plant is made until the measured separation, depth or count equals the
stated size (±5%), so parts embedded in or wrapped round their parent are still eligible.

| Family | Defect | Size → 2× | Eligible targets | Expected check |
|---|---|---|---|---|
| contact | `offset_part`: translate the part (vertices and matrix) along the candidate direction (± each mate's parent normal, ±x, ±y, ±z) that reaches the size with the smallest move (bisection on [0, 1 m]); size = min distance to that mate's part | 3 mm → 6 mm | every part with a point-bearing mate (attach, squeeze, translate), reflect and array copies included; a plant that cannot reach the size within 1 m counts `ineligible` | `contact_gap` (`anchor_error` also fires) |
| contact | `lift_asset`: translate everything up by the size | 3 mm → 6 mm | specs with a `ground` attach (barrel, chair) | `grounded` |
| floating | `detach_part`: as `offset_part`, size = min distance to every other part and to ground | 5 mm → 10 mm | every part | `floating` |
| floating | `split_shell`: duplicate one part's shell displaced by 2× its size inside the same part | 1 shell → 2 | every part | `shells` |
| manifold | `delete_face`, `flip_face`, `unweld_seam` (duplicate one seam vertex), `degenerate` (collapse a triangle) | 1 element → 2 | every part | `manifold` |
| sheet | `scale_part` about the part's centroid, along its canonical z or radially in x and y | ×0.95 → ×0.90 (also ×0.85) | parts whose scaled measure is ≥40 mm (so ×0.95 exceeds `sheet_abs_m`) | `sheet_as_built` or `dim_measure` |
| relation | `tilt_part` about its first mate point | 2° → 4° | parts named in coaxial / parallel / perpendicular relations | `relation_angle` |
| naming | spec level: `rename_default` ("Cube.001"), `drop_side`, `duplicate_name`, `swap_side` (an `_L` name on the −X part of a pair); read-back level: object renamed to `<name>.001`, `strip_stamp`, `drop_socket` | 1 → 2 violations | every part; read-back defects on the read-back fixtures | `name_*`, `reflect_sides`, `symmetry_pair`, `naming_built` |
| overlap | `embed_part`: translate into the nearest undeclared neighbour until the max inside depth equals the size | 3 mm → 6 mm | parts with an undeclared neighbour within 10 mm | `overlap` |

```python
@dataclass(frozen=True)
class DefectSpec: family: str; kind: str; size: float; target: str | None = None
def inject(m: EvalMesh, spec: dict, d: DefectSpec, rng: random.Random) -> tuple[EvalMesh, dict, dict]
    # -> (mesh', spec', expected {"checks": [...], "family", "part", "mode"}); naming defects edit names,
    #    stamps or extra; a read-back defect needs a read-back mesh
```

Only the expected checks re-run on a plant, scoped to the planted part (`ctx.parts`), so a full run
takes minutes (§9.7).

### 9.6 Consistency gate v1 (T2b; host metrics WP-C, Blender task WP-E)

Stage `emitted` (exit test): finish modifiers disabled for rendering. Views: front, right and top
orthographic at `consistency_resolution` (W, H); three_quarter perspective at d_close with the spec
camera's vfov, square, at the smallest multiple of 128 (≤2048) where the smallest part spans ≥10 px. The
host builds each `RasterCamera` with `JITTER_PX` and rasterizes `id_depth`; Blender renders an ID mask
(mask mode, `id_colors`) and casts a 128×128 BVH depth grid at pixel centres x = i·kx + kx//2 + 0.5,
y = j·ky + ky//2 + 0.5 (kx = W/128, ky = H/128, integers), which the evaluator reads at pixel
(i·kx + kx//2, j·ky + ky//2).

Metrics: whole-object IoU ≥0.99; per part, symmetric boundary distance p95 ≤0.5 px (boundary pixels of
each mask, chunked brute-force nearest distances); depth: p95 of |z_blender − z_eval| over rays hitting
in both ≤ 1/ppm(d_close) m. **Hidden parts:** a part is scored in a view when it covers ≥20 px in the
evaluator mask; it fails (value inf) when it covers ≥20 px in one mask and <5 px in the other; below
20 px in both it is skipped there; a part scored in no view fails `consistency_boundary` as `unscored`.
A NaN never passes.

Stage `finished` (every build): the game camera at d_close at true size (cropped); per part, boundary
change between the evaluator and the finished mesh; >1 px → `finish_delta_px` report and `post_eval:
true` on that part in the read-back (§11.6).

Blender task `spec_consistency(blend, cameras: [RasterCamera dict], stage, out_dir)` →
`{"views": [{"camera": i, "id_png": path, "colors": {part: [r, g, b]}, "background": [r, g, b],
"depth_npz": path}]}`; colours are the 8-bit sRGB values the PNG holds (`readability.srgb8` of
`id_colors`, pairwise ≥10 apart per channel), decoded by exact match; the npz holds `depth` (float32,
128×128, inf for misses) and `hit` (bool).

### 9.7 defect_inject, gate_calibrate, noise (`inject.py`, `calibrate.py`)

```python
def defect_inject(gate: str = "all", fixtures: str = "ab6", seeds=range(8), sizes=(1, 2), n_per: int = 200,
                  check_armed: bool = False, write_armed: bool = False) -> dict
# per family: {"planted", "ineligible", "detected", "recall", "recall_2x", "clean_failures",
#              "by_spec": {...}, "by_mode": {...}, "misses": [first 10], "ok"}
# check_armed: the CLI exits 1 when an armed check's recall falls below 95% / 99% or a clean failure appears
def write_armed(report: dict, path=data_dir()/"gates"/"armed.json") -> None
def build_fixtures(fixtures: str = "ab6", seeds=range(3)) -> list[Path]   # Blender: emitted + finished read-backs, cached
def gate_calibrate(check: str, clean: list, planted: list, thresholds: list[float] | None = None,
                   noise: bool = False) -> dict
# -> {"check","n_clean","n_planted","recall","false_alarm_rate","threshold","table":[...],"promote","written"}
```

Fixtures `ab6` = the six A/B specs × seeds 0–7 at levels fit and build (96 evaluator meshes), plus the
`emitted` and `finished` read-backs of seeds 0–2 (36 meshes, built by `opus gates fixtures --build ab6`
in the blender job), plus the WP0 fixtures. Each family plants ≥200 defects per size (random targets
and kinds, seeded). Pass: recall ≥95% at the stated size, ≥99% at 2×, 0 clean failures (every T1/T2
check on every clean mesh; built-stage checks on the read-backs), `ineligible` <5%. `armed.json`:
`{"<check>": {"armed": true, "family", "recall", "recall_2x", "clean_failures": 0, "n", "date",
"commit"}}`, written in the integration phase from a passing run and re-verified by every CI run
(`--check-armed`). `gate_calibrate` sweeps a threshold over clean and planted sets and writes
`data/gates/calibration/<check>.json` (corpus sources and licence IDs, never assets). With `noise=True`
it re-measures a metric over 3 seeds or 3 render jitters and writes ε to `data/gates/noise.json`;
`noise_tol` is that ε where measured, else 2% of the band (OVERHAUL §2.6).

Cost: clean set about 2 minutes, plants about 3 minutes with §9.4's numbers, so the full run is part of
every blender CI job. If it ever exceeds 15 minutes, the push job runs 50 plants per family and a
scheduled nightly job runs the full set.

---

## 10. spec_edit (`opus/spec_edit.py`, `accept.py`, `optim.py`; WP-G)

### 10.1 Input

```python
def spec_edit(path: str, patch: list[dict] | None = None, edit: str = "", why: str = "",
              keep: list[str] | None = None, mode: str = "single", dials: list[str] | None = None,
              tag: str = "", dry_run: bool = False, by_user: bool = False, near=None) -> dict
```

- `patch`: RFC 6902 operations `replace`, `add`, `remove`, `test` on the spec.
- `edit` (seed-edit grammar, `;`-separated): `<dim> (=|*=|+=|-=) <number>`, `<dim>.style_mult = <n>`,
  `seed = <int>`. On a `table` dim, `*=` becomes `style_mult`; on `range` dims it sets `value` (clamped,
  the clamp reported); on `design` dims it sets `value` (clamped) only when `why` cites a finding key
  (`finding:<check>[:<part>]`) or `by_user=true`, and logs a `design_pick` (deviation 5); `user` dims
  refuse edits unless `by_user=true`; `expr` dims refuse edits (change their inputs).
- `why` is required. `keep`: relation indices to hold (default all). `tag="locked"` runs `lock()`.
- `dry_run`: steps 1–5 run and the candidate's findings are returned; nothing is written.

### 10.2 Steps

1. Apply to a copy (rev+1, parent_rev = rev); run T0. A new hard T0 failure rejects.
2. Resolve and evaluate the candidate.
3. **Locality**: allowed = parts whose `deps` (a transitive closure, §7.2) include a touched dim or part,
   their placement descendants, reflect partners and array copies. Every other part's
   `part_hash(root_frame=True)` must equal the incumbent's; otherwise reject with `edit_locality` naming
   the parts.
4. Re-gate: local checks on the allowed parts, asset checks always.
5. Label each finding by `key()`: improved, unchanged, regressed, new, resolved.
6. Accept by §10.3. Accepted: write the spec (history entry `{"rev","op","path","from","to","why"}` per
   change), keep `.opus/specs/<id>/rev_<n>.json`, update the archive. Rejected: the spec file is
   untouched; the candidate is saved as `rev_<n>.rejected.json`.
7. `runs.log_if_open("spec_round", ...)` (and `design_pick` per picked design value).

Returns `{"accepted", "rule": "<step that decided>", "rev", "diff": [...], "locality": {"touched",
"allowed", "changed", "violations"}, "findings": [... with "label"], "archive": [...], "coupled": [...],
"dry_run"}`.

### 10.3 Acceptance rule (`accept.py`)

```python
@dataclass(frozen=True)
class Score: hard_count: int; hard_mag: float; soft_score: float; new_hard: tuple[str, ...]
def score(findings: list[Finding], incumbent: list[Finding] | None) -> Score
def accept(cand: Score, inc: Score, eps: dict[str, float]) -> tuple[bool, str]
```

In order: (1) any armed hard check that passed in the incumbent fails now → reject; (2) fewer hard
failures → accept; (3) equal count: summed magnitude lower by more than ε (ε = Σ per-check `noise_tol`
normalized — from `data/gates/noise.json` where measured, else 2% of the band) → accept; (4) hard tie:
soft score (Σ weights × magnitude) lower, with each regressed soft check inside its band → accept; (5)
otherwise reject ("judge tie-break" is S3). Archive: up to 4 revisions non-dominated over (hard_count,
hard_mag, soft_score), JSON `.opus/specs/<id>/archive.json` `[{"rev","score","hash"}]`.

### 10.4 Coupled findings and joint solve (`optim.py`)

Coupled = two failing findings whose fix paths share a dependency, or that traded places over the last
2 rounds. `mode="joint"` with ≤3 `dials` (design/range dims or style_mults): Nelder-Mead in numpy
(`nelder_mead(f, x0, lo, hi, max_evals=60, seed)`), objective f = 1e6·hard_count + 1e3·hard_mag +
soft_score using host T1/T2 only; the best point then goes through §10.2 as one edit (a solver pick,
not Claude's: logged as `design_pick` with `finding` = the coupled keys).

### 10.5 Run ledger (`runs.py`)

WP0 adds the events and `log_if_open` (§4.9). WP-G adds `spec_rounds`, `spec_rounds_to_hard_pass` and
`design_picks` to `summarize_run`, `run_stats` and `summarize`. `iteration` stays a manual event with the
§19.4 definition, so both A/B arms count iterations the same way.

### 10.6 The dial-edit exit test (`test_spec_edit.py::test_random_dial_edits`, integration)

For chest and chair, 20 seeds × 3 sequential edits. Each edit picks a random editable dim (`design` or
`range` with an in-bounds new value, or a table dim's `style_mult` inside its band) and runs
`spec_edit(..., dry_run=True, by_user=True)`; the **candidate's** findings must hold 0 failing
`contact_gap`, `floating` and `anchor_error`, armed or not. The edit is then applied for real; ≥95% of
in-bounds edits must be accepted, and every rejection is listed with its rule. A negative control
re-runs 5 seeds with `_freeze` (§7.2), so children keep their old matrices; it must produce ≥1 failing
`contact_gap`, which proves the test can fail. A companion test perturbs each design dim of the six
specs and asserts that the parts whose `part_hash` changes are a subset of the dim's closure, equal to
it for ≥95% of dims.

---

## 11. Blender side (`opus_bl`; WP-E unless noted)

### 11.1 Emit (`emit.py`, task `spec_emit`)

`run(npz, out_blend, finish: dict, exports: list[str], stage_hash: bool = True) -> dict`:
- `read_factory_settings(use_empty=True)`; collection `opus:<id>`; root empty `<id>` with `opus_spec`,
  `opus_rev`, `opus_hash` (`eval_hash`).
- Per part: mesh via `vertices.add` + `foreach_set("co", float32)`, `loops`,
  `polygons.foreach_set("loop_start")` (a quad for each canonical `quad_mate` pair (a,b,c)+(a,c,d)
  emitted as [a,b,c,d], else a triangle), `update(calc_edges=True)`, `validate()` must return False; UV
  map `UVMap` via `uv.uv.foreach_set("vector")`; attributes `sharp_edge`, `bevel_weight_edge` from
  `edge_flags`; lowpoly → `sharp_face` all True, else `set_sharp_from_angle(angle=radians(30))` plus
  flagged edges.
- Object name = part name; `matrix_world` = `PartInfo.matrix` (joint roots already carry their origin on
  the axis, K19). Parents (keep transform): parts of a joint subtree → that joint's root object; every
  other part → the root empty.
- Stamps: `obj["opus_part"]`, `["opus_src"]`, `["opus_builder"]`, `["opus_joint"]`, `["opus_matrix"]`;
  vertex-group stamps (S1+) go in `obj["opus_vgroups"]` (JSON), because vertex groups have no ID
  properties (probed).
- Sockets: a plain socket → empty `SOCKET_<name>` parented to its part at the anchor frame, with
  `["opus_socket"]`. **A grip socket → v0.4's format (K18):** empty `SOCKET_grip_<name>` parented to
  the root empty `<id>`; handle axis d = the grip part's canonical +z in world, flipped so d·up ≥ 0
  (`grip.define`'s `up` hint; d·X ≥ 0 when d ⟂ up); palm side p = the `palm` word's world axis made perpendicular to d;
  frame columns (x = d × p, d, p) at the point on the axis at `center` of the part's z extent;
  `["opus_grip"]` = the JSON `grip.define` writes (`radius`, `palm_offset`, `length`, `style` "power",
  `index` "curl", `thumb` "wrap", `diagonal` 20, `hand`), computed by `grip.handle_props(part_obj, p0, p1,
  p, center)`, a helper WP-E extracts from `define` without changing `define`'s output (a test compares
  both on a fixture). So `grip_define(object=<id>)` replaces it instead of adding `.001`, and
  `grip_hold` finds a grip with a radius.
- Materials: one per material id, named as the id, neutral grey.
- Read back the unfinished mesh → `emit_hash`. Then `finish.apply`, save `.blend` (`compress=False`),
  write the finished read-back `.npz`, run exports. Returns `{"blend", "emit_hash", "readback_emitted",
  "readback_finished", "exports": {...}, "warnings"}`.

### 11.2 Finish v1 (`finish.py`)

Per part, as modifiers (non-destructive in the .blend, applied at export):

| Order | Modifier | Settings |
|---|---|---|
| 1 | Bevel | `limit_method='WEIGHT'` (weights from `EDGE_BEVEL`, 0 on `cutting`), `width = camera.bevel_width(ppm(d_close), thickness = part min extent)`, `segments` 1 (lowpoly) / 2 (hd) / 3 (view-model profile), `profile=0.5`, `use_clamp_overlap=True`, `harden_normals=True`, `face_strength_mode='FSTR_AFFECTED'`, `miter_outer='MITER_ARC'`. **Skipped for a part whose width × ppm(d_close) < 1 px** (a sub-pixel bevel is omitted, OVERHAUL §4.6 detail tiers) |
| 2 | Weighted Normal | `mode='FACE_AREA'`, `weight=50` (= plain area weighting), `keep_sharp=True`, `use_face_influence=True` |
| 3 | Triangulate | `quad_method='BEAUTY'`, `ngon_method='BEAUTY'`, `min_vertices=4`, `keep_custom_normals=True` |

`boolean(obj, cutter, op)`: requires both operands manifold (bmesh check) and runs MANIFOLD; verifies
that the volume changed when the bboxes overlap and that the result is manifold; otherwise runs EXACT
and verifies the result is manifold, else raises (an EXACT result with non-manifold edges is never
accepted); FLOAT never. Unused by S0b specs (K10).

### 11.3 Read-back (`readback.py`, task `spec_readback`)

Evaluated meshes per object. Stage `emitted` (finish modifiers disabled): polygons read back in order,
quads split (a,b,c),(a,c,d), so `geom_hash` compares like with like. Stage `finished`: `loop_triangles`
of the triangulated result. Local vertices float32 → float64; matrices from the `opus_matrix` stamps
(the 16 floats emitted, because Blender re-derives `matrix_world` from location, rotation and scale),
with `matrix_world` required to match within 1e-6 (else `emit_hash` fails naming the object); corner
UVs; `sharp_edge` → `EDGE_SHARP`; `parts`, `anchors`, `sockets`, `relations` copied from the emit `.npz`
(§4.5); `extra` = object names, stamps, socket empties (with their `opus_grip`). Output: an EvalMesh `.npz`.

### 11.4 Consistency (`consistency.py`, task `spec_consistency`)

Camera from the `RasterCamera` dict (§4.2, crop as a render border), mask mode with
`color_type="OBJECT"` and `id_colors(n)`, `render_aa='OFF'`; BVH per object (`BVHTree.FromObject(obj,
depsgraph)`), rays through the §9.6 grid pixel centres (persp: origin = camera, direction (x−W/2,
−(y−H/2), −f) rotated; ortho: origins on the image plane, direction −Z_cam), depth = view-space z. 128²
rays take ~0.03 s per object set (probed). `raster_tie.py` (WP-C): renders the single-triangle and 8×8
tie cases and the doctor's 16×16 fill-rule probe.

### 11.5 Traps (`data/errors.json`, matched against tracebacks and output by `runner.py`, hint appended)

| Pattern | Hint |
|---|---|
| `BLENDER_EEVEE_NEXT` | 5.x id is `BLENDER_EEVEE` |
| `solver.*FAST` | Boolean solvers are FLOAT, EXACT, MANIFOLD |
| `Cannot execute, object\(s\) .* have non-manifold geometry` | MANIFOLD skipped the operation (the result is the base mesh); use `finish.boolean` |
| `face_strength_mode.*AFFECTED` / `miter_outer.*ARC` | `FSTR_AFFECTED` / `MITER_ARC` |
| `id properties not supported for this type` | VertexGroup: store on the object (`opus_vgroups`) |
| `file_format` enum error | set `image_settings.media_type` first |
| `Couldn't create directory for file` | `render.filepath` must be absolute |
| `outdated internal index table` | call `ensure_lookup_table()` |
| `fcurves.ensure` / `channelbag` | S1+: slotted actions (`action_ensure_channelbag_for_slot`) |
| `WinError 32` | a file is still open: `with np.load(...) as z` and close files before Blender starts |

### 11.6 `post_eval` after a build (`opus/build.py`)

Parts the finished stage marks `post_eval` (`finish_delta_px` > 1 px) use the finished read-back's
arrays in every later T1/T2 check and preview of that build (`merge_post_eval(eval_mesh, finished,
parts)`). On a locked spec, `lock.post_eval = {part: {measure: built value}}` is written with a history
entry listing each as-built measure's change against the locked sheet.

---

## 12. Export (`opus_bl/export.py`, `opus/export.py`; WP-E)

### 12.1 Presets

| Engine | Format | Groups | Settings | Naming |
|---|---|---|---|---|
| `ue` | FBX | each part baked with `bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)` (its own finish stack applied), then the baked copies joined: `SM_<id>` (parts outside joint subtrees) and `SM_<id>_<joint>` per joint subtree, whose origin is the joint root's (on the axis); sockets re-parented to the joined meshes | `use_selection`, `object_types={'MESH','EMPTY'}`, `use_mesh_modifiers=False` (already baked), `mesh_smooth_type='FACE'`, `use_tspace=True`, `add_leaf_bones=False`, `use_custom_props=True`, `apply_unit_scale=True`, default axes | `UCX_SM_<id>_NN` (one convex hull per part, `bmesh.ops.convex_hull`), `SOCKET_<name>` empties |
| `godot` | glTF binary (.glb) | the same baked groups, named `<id>` and `<id>_<joint>`; the joint group parented under the main one | `export_format='GLB'`, `export_yup=True`, `export_apply=True`, `export_extras=True` | hull nodes `<group>-convcolonly`, `SOCKET_<name>` → Node3D |
| `unity` | FBX | as ue | as ue + `apply_scale_options='FBX_SCALE_UNITS'` | unverified until S8 |

`object.join` alone keeps only the active object's modifiers (probed), hence the per-part bake.

Sidecar `<id>.opus.json`: id, rev, `eval_hash`, engine, units, `axis_matrix` (the exporter's axis
conversion), `groups: [{"name", "parts", "bbox_m", "bbox_engine"}]` (bbox_engine = after `axis_matrix`
and unit scale), `bbox_uu` (ue), tris, materials, sockets `[{"name","part","pos_m","quat_wxyz",
"pos_engine","rot_engine"}]`, joints, licence (an `sa` licence id from the lineage, else
`LicenseRef-Own-Work`), flags union, files.

### 12.2 Round trip

Re-import each exported file into factory settings and compare: object and socket names (exact),
socket positions ≤0.1 mm, per-group bbox ≤0.1 mm, triangle counts equal, sorted quantized vertex sets
equal within 1e-5 m (after the format's axis conversion back); stamps parsed (FBX returns array stamps
as strings, probed). Failures → hard `export_round_trip`.

### 12.3 Licence policy

Before writing, `ledger.check` on the asset's lineage (§13.3) under the bible's policy; blocked flags
stop the export with `licence_blocked` findings. An `sa` flag stamps the output's licence (sidecar and
the export's ledger entry); `attribution` flags add the inputs' credits to `<project>/CREDITS.md`
through `make_credits`.

### 12.4 Engine-side files (MIT)

- `data/engine/ue_import.py.tmpl` → `<project>/Opus/ue/import_<id>.py`: MIT header; imports the FBX with
  `unreal.AssetImportTask` (`automated`, `replace_existing`, `save`, destination `/Game/Opus/<id>`) via
  `AssetToolsHelpers.get_asset_tools().import_asset_tasks`; then for each static mesh compares
  `get_bounding_box()` with the sidecar group's `bbox_engine` (±1 uu), adds missing sockets
  (`unreal.StaticMeshSocket`, `add_socket`), adds a box collision with
  `StaticMeshEditorSubsystem.add_simple_collisions` when none imported, and writes
  `Saved/Opus/<id>_import_report.json` plus PASS/FAIL lines in the Output Log. The API names are checked
  by checklist item 4.1 on the PC; a failing name is reported and fixed there.
- `data/engine/CHECKLIST_ue.md.tmpl` → `<project>/Opus/ue/CHECKLIST_<id>.md` (≤5 minutes per asset).
- Godot: no script; `godot --headless --path <proj> --import`, then
  `godot --headless --path <proj> -s tests/godot/check_import.gd` prints node names, classes and AABBs
  and compares them with the sidecars' `bbox_engine`; `ERROR: … leaked at exit` lines are ignored. On the
  PC the binary is `Godot_v4.7-stable_win64_console.exe`.

---

## 13. data_fetch (`opus/data_fetch.py`, `data/packs.yaml`; WP-F)

### 13.1 Manifest

```yaml
version: 1
packs:
  ansur2:
    title: ANSUR II public working databases
    kind: file            # file | zip | api | manual
    files:
      - {url: https://tools.openlab.psu.edu/publicData/ANSUR_II_MALE_Public.csv, path: ANSUR_II_MALE_Public.csv,
         sha256: 0547aea0170e5293de519389981135e75803f02e6d40c77ace740decc0caac64}
      - {url: https://tools.openlab.psu.edu/publicData/ANSUR_II_FEMALE_Public.csv, path: ANSUR_II_FEMALE_Public.csv,
         sha256: ed7e800aa97a4d42f8286b988be2fe1883a2e789588169db959864b707d1757a}
    licence_id: LicenseRef-US-Gov-Public-Release
    licence_page: https://www.openlab.psu.edu/ansur2/
    attribution: "Contains data derived from the 2012 U.S. Army Anthropometric Survey (ANSUR II) ..."
    target: tables/ansur2
  museum_records:
    kind: api             # on demand: data_fetch --record met:23367 | cma:1921.1252
    endpoints: {met_object: "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}",
                cma_object: "https://openaccess-api.clevelandart.org/api/artworks/{id}"}
    licence_id: CC0-1.0
    requires: {met: "isPublicDomain == true", cma: "share_license_status == CC0"}
    target: records
  met_arms:
    kind: api
    endpoints: {search: "https://collectionapi.metmuseum.org/public/collection/v1.1/search?q={q}&departmentId=4&limit=500&offset={offset}",
                object: "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"}
    paginate: true        # until a page returns fewer than 500 ids; the id list is snapshotted with its sha256
    licence_id: CC0-1.0
    target: met_arms
```

The Met's `v1/search` is retired (410) and `v1.1/objects` does not exist (404), so search and object
endpoints are named separately (probed). Packs in S0b: `ansur2`, `museum_records`, `cma_arms` (API query
snapshots), `met_arms`, `wikidata_firearms` (SPARQL snapshot), `wikipedia_facts` (raw wikitext by
revision id, fetched through `action=query&redirects=1&prop=revisions&rvprop=ids|content&rvslots=main`
so redirects such as "Viking shield" are followed), `albion_typology` (`kind: manual`: `--from-file`
only, because its URL returns 404), `ada_2010`, `cma_profile_images` and `met_profile_images` (the exact
image URLs of §14.2). `kind: manual` packs (itch.io, Albion) accept only `--from-file`. The CI calibration
corpus pack is S2 (§1.2).

### 13.2 Behaviour

```python
def data_fetch(pack: str = "", from_file: str = "", record: str = "", licence_page: str = "",
               list_packs: bool = False, library_dir: str = "") -> dict
# -> {"pack","dir","files":[{"path","sha256","size"}],"licence_id","flags","licence_json","status"}
```

- `library_dir` = `$OPUS_LIBRARY_DIR` (plugin `userConfig.library_dir`), else
  `%LOCALAPPDATA%/OpusTools/library` / `~/.local/share/opus-tools/library`. Layout
  `<library>/<pack>/<YYYYMMDD>/...`, `<library>/<pack>/LICENSE.json`, `<library>/index.json`. Every
  file and folder name made from an id goes through `paths.safe_name` (`met:23367` → `met_23367`).
- `OPUS_OFFLINE=1` (set in CI) makes every fetch fail fast with `status: "offline"`.
- Downloads stream to `<file>.part` with HTTP `Range` resume, then sha256; a mismatch deletes the file and
  fails. Packs with `sha256: null` (api snapshots) record the observed hash.
- Archives unpack into a fresh empty directory with path-traversal and symlink rejection; nothing is
  executed; `np.load` uses `allow_pickle=False` inside `with`; pickle formats are rejected; parsers of
  downloads run in `python -I`. All text I/O passes `encoding="utf-8"`.
- `LICENSE.json`: `{"pack","licence_id","flags","licence_url","snapshot_text" (page text, ≤200 KB),
  "snapshot_sha256","retrieved","source_urls","attribution"}`.
- `--from-file <zip> --pack <id> [--licence-page <url|html>]`: copies, hashes, checks against the
  manifest when it lists a hash, snapshots the page (or the saved HTML) with the date.
- User-Agent `OpusTools/<version> (+https://github.com/Infamase/Opus-Tools)`; no personal data in headers;
  throttled to 10 requests/s per host.

### 13.3 Lineage

`spec_build` records the built asset with `ledger.record(asset, source="opus spec_build <id> rev <n>",
licence_id="LicenseRef-Own-Work", inputs=[{"source": "table:<name>@<version>", "licence_id", "role":
"dims"}, {"source": "profile:<key>", "licence_id", "role": "profile"}, {"source": "record:met:23367",
"licence_id": "CC0-1.0", "role": "dims"}], tools=[{"name": "opus-tools", "licence_id":
"GPL-3.0-or-later"}])`. Flags come from `licences.yaml`; export applies the policy (§12.3).

---

## 14. Data acquisition (WP-F)

### 14.1 Tables (all committed under `data/tables/`, built by `opus data build --tables` from the cache)

Every value is `{value, min, max, unit, src, tag}` (existing `tables.fact`). `measured` = the number is
stated in the source (unit conversion allowed); `derived` = computed from measured values by a stated
rule (percentiles, ratios, merged ranges); `recalled` = not verified against a primary source (warnings
only; a test asserts recalled facts never produce a hard finding). A class or measure with fewer than 3
records is left out (a spec citing it gets `unknown_ref`, and its template uses a `design` range).

| Table | Source and access | Licence ID | Content (paths as dims use them) |
|---|---|---|---|
| `anthro_ansur2` v2 | ANSUR II CSVs (pack `ansur2`, sha256 above) | `LicenseRef-US-Gov-Public-Release` (existing entry) | adds `poplitealheight`, `buttockpopliteallength`, `elbowrestheight`, `thumbtipreach` ratios and a `measures_mm` block per sex (absolute p5/p50/p95 in mm) for stature, hand length and breadth, popliteal height, buttock–popliteal length, elbow rest height, thumb-tip reach. `sexes.<sex>.measures_mm.<name>` |
| `oakeshott` | Wikipedia "Oakeshott typology" raw wikitext (revision id stored); Albion's article only through `--from-file` (404 today) | `LicenseRef-Facts` (numbers only; no prose copied) | `types.<X..XXII>.{blade_len, grip_len, cross_len, fuller_frac}` where stated (XIV: `grip_len` only; the page's "crosses generally curved" is kept as a `note`); two sources disagreeing → value = midpoint, [min, max] spans both, tag derived |
| `museum_records` (K17) | the records cited by templates, the ab6 specs and profile specimens (met:23367, 15292, 22635, 472596, 472597; cma:1921.1252, 1923.1121, 1921.1253, 1916.1601, 1922.28), from pack `museum_records` | `CC0-1.0` | `records.<safe_name(ref)>.<key>` facts plus `meta: {ref, url, title, date, retrieved, raw_sha256, parser}`. Canonical keys: `overall_len, blade_len, blade_w, blade_t, cross_w, grip_len, pommel_w, head_h, edge_len, mass_kg, height, width, depth, diameter`; `src` holds the record's own label ("L. of blade") |
| `museum_arms` | Cleveland `GET /api/artworks/?type=Arms%20and%20Armor&q=<term>&cc0=1&limit=1000` (structured `dimensions`, m); Met v1.1 search, paginated, then v1 objects (`isPublicDomain` only): structured `measurements` when present, else the **`dimensions` string parser**; raw JSON cached as packs `cma_arms`, `met_arms` | `CC0-1.0` | `classes.<class>.<key>`. Class membership by an **objectName/title whitelist, a date window and the department**, never by search term: `sword_1300_1500` (Met objectName "Sword"; Cleveland titles `^(Sword\|Arming Sword\|Longsword\|Hand-and-a-half Sword)`; 1300–1500), `axe_1000_1600` ("Axe", "Battle Axe", "Axe head"; not halberd, pole, ceremonial), `shield_boss_early` ("Shield boss", "Shield Boss (Umbo)", "Two shield bosses", "Shield boss and grip"; 300–1100 CE). Duplicates merge (one object listed by several records, e.g. 22635 and 35771, or 24905 and 472596/7). n ≥ 5: robust p5/p50/p95 after median ± 3 MAD; 3 ≤ n < 5: observed range, value = median; `src` lists n and record ids. Today `shield_boss_early.diameter` has n = 3 (17.78–19.99 cm) |
| `firearms_wikidata` | Wikidata SPARQL, items reached by `(wdt:P31 or wdt:P279)/wdt:P279*` from `wd:Q12796` with `p:P2043/psn:P2043/wikibase:quantityAmount` (length), optional P2067 mass, P2048 height, P2049 width, all psn-normalized (query text stored); duplicate rows per item aggregated (median; disagreement → [min, max]); class QIDs for pistol, rifle, carbine, shotgun resolved by label at build | `CC0-1.0` | `items.<qid>.{label, len, mass, height, width}` and `classes.<class>.{len, mass, height, width}` percentiles; query text and response sha256 in `source` |
| `ada_2010` | 2010 ADA Standards, `https://www.access-board.gov/ada/` | `LicenseRef-US-Gov-PD` | `work_surface_h` 902.3 (28–34 in), `door_clear_w_min` 404.2.3 (32 in), `reach_forward_high/low` 308.2, `riser_h` 504.2 (4–7 in), `tread_d_min` 504.2 (11 in), `handrail_h` 505.4 (34–38 in), `seat_h_toilet` 604.4; tag measured, src = section number |
| `weapon_facts` | Wikipedia raw wikitext "Dane axe", "Viking Age arms and armour" (section Shields, reached through the "Viking shield" redirect), "Longsword" (revision ids stored) | `LicenseRef-Facts` | `dane_axe.{haft_len, edge_len, mass_kg}` as stated, `viking_shield.diameter` (value 0.825 = midpoint of "most 75–90 cm", min 0.45, max 1.20), `longsword.{blade_len, grip_len}`. Board thickness and boss size are not stated, so they are not in the table |

**Met `dimensions` parser** (`tables.parse_met_dimensions`, with tests on real strings): splits on `;`,
reads the metric value in parentheses (cm, mm, m, g, kg) or converts the imperial one, and maps labels
through a table (`L.` → `overall_len`; `L. of blade` → `blade_len`; `W. of blade`, `Gr. width of blade`
→ `blade_w`; `Th.`, `Thickness of blade` → `blade_t`; `W.`, `Gr. W.` → `cross_w` for swords, else
`width`; `Diam.` → `diameter`; `H.` → `height`; `D.` → `depth`; `Wt.` → `mass_kg`); an unknown label is
kept under `other` and reported. A raw-JSON fixture holds the junk the plain searches return (the parade
sword, halberd, hauberk and rifle for Cleveland `q=shield`; the curb bit and katar for `q=boss`; the
Met "Bit boss" objects) and the test asserts every one is excluded.

`LICENSES.md` gets one entry per table in the existing format (source, licence, derived, credit; CC0
and facts need no credit, US Gov tables keep their wording).

### 14.2 Profile library v0 (`data/profiles/<family>.json`, schema `opus.profile.1`)

| Family (kind) | Variants traced (CC0 images; the record gives the scale) | `ref` |
|---|---|---|
| `blade.taper` (width_curve) | `cma:1921.1252` (c. 1400, blade 71.7 cm), `cma:1923.1121` (c. 1350), `cma:1921.1253` (hand-and-a-half, c. 1500), `met:23367` (c. 1400, blade 81.3 cm) | blade length |
| `cross.straight` (outline; anchors `seat_top`, `seat_bottom`) | `cma:1923.1121` (default), `cma:1921.1253` | cross length |
| `cross.arched` (outline; seats) | `cma:1921.1252` (default), `met:23367` (tips ≈2.2 cm toward the blade) | cross length |
| `axe.head` (outline; anchor `eye_c`; param `beard_drop`) | `cma:1922.28` (lower horn sweeping down; default when its `beard_drop` ≥ 0.25), `cma:1916.1601` (a fan head, not bearded) | edge chord between the two edge tips |
| `shield.boss` (radius_curve) | `met:22635` (near-side view DT257906; Ø 19.99 cm, H 16 cm for the cross-check) | diameter |
| `chair.turned_leg` (radius_curve, half-profile) | `met:15292` front leg (joined to rails in every photo: bridged) | leg length |
| `chair.arm` (outline) | `met:15292` arm, if a side view exists, else dropped | arm length |

That is up to 13 variants in 7 families, 11 of them weapons; the exit needs ≥6 weapon variants that pass
acceptance. **Fallbacks** written into the templates: the axe uses `prim:axe_bearded` (§5.4) when no
traced head has `beard_drop` ≥ 0.25; the chair uses `prim:baluster` when the leg trace fails acceptance;
the shield's boss stays `prim:dome_shell` (A.3) and `shield.boss` is an optional variant for S2's explore.

**Schema** (`data/schema/opus.profile.1.schema.json`, WP0):

```json
{"profile": "blade.taper", "version": 1, "kind": "width_curve",
 "ref": {"name": "blade_len", "def": "u spans the blade from the cross (0) to the point (1)"},
 "frame": {"u": "0 at the cross, 1 at the point", "v": "half-width / half-width at u = 0"},
 "default": "cma:1921.1252",
 "variants": {"met:23367": {
     "curve": [{"type": "line", "p0": [0, 1], "p1": [0.6, 0.85]},
               {"type": "arc", "p0": [0.6, 0.85], "p1": [1, 0], "c": [0.0, 0.04853], "ccw": false}],
     "anchors": {},
     "params": {"aspect": 0.109, "shoulder_u": 0.6},
     "fit_rms": 0.004,
     "cross_check": {"measure": "blade_w", "predicted_m": 0.0872, "recorded_m": 0.0889, "error": -0.019},
     "specimen": {"id": "met:23367", "image": "<exact URL>", "image_sha256": "…", "known_dim": {"blade_len": 0.8128},
                  "licence_id": "CC0-1.0", "traced": "2026-10-2x", "method": "opus.trace 1"}}},
 "params": {"aspect": {"value": 0.10, "min": 0.07, "max": 0.11, "unit": "ratio", "src": "4 specimens, observed range", "tag": "derived"},
            "shoulder_u": {"value": 0.6, "min": 0.55, "max": 0.75, "unit": "ratio", "src": "4 specimens", "tag": "derived"}},
 "licence_id": "CC0-1.0", "tag": "measured"}
```

(The numbers are placeholders for the format; the arc is a real arc: |c − p0| = |c − p1| = 1.00118.)
- **Kinds** (one enum, used by §5.4 too): `outline` (`loops`: closed loops in (u, v), the outer one
  counter-clockwise first, holes clockwise), `width_curve` (`curve`: an open chain from u = 0 to u = 1,
  v ≥ 0, v(0) = 1), `radius_curve` (`curve`: an open chain from u = 0 at the bottom to u = 1 at the top,
  v = r / r_max with max 1), `radius_loop` (`loops` in (r, z), r > 0).
- **Segments:** `line` (p0, p1), `arc` (p0, p1, centre c, `ccw`; | |c − p0| − |c − p1| | ≤ 1e-6),
  `cubic` (p0, c0, c1, p1); consecutive segments share end points exactly.
- **Units:** coordinates are in units where the `ref` measure is 1. Builders scale: extrude uniformly by
  `len` (then `h` rescales v); lathe z = u·len, r = v·r_max; loft a(s) = ½·w·v(s).
- **Anchors:** `{"name": {"p": [u, v], "n": [nu, nv]}}`; on an extrude, p goes to (u, v, 0), n to (nu,
  nv, 0) and t = local +z.
- **Files and keys:** a family lives in `data/profiles/<family>.json`, where family = the key without
  `lib:` and `#variant` (`lib:chair.turned_leg#met:15292` → `chair.turned_leg.json`).
  `resolved.profiles` is keyed by the literal key string the spec uses and holds that one variant:
  `{"family", "variant", "kind", "ref", "frame", "loops" | "curve", "anchors", "params", "licence_id",
  "tag", "sha256"}`.

**Tracing (`opus.trace`, maintainer only, needs `opus[ref]`, K20).** `opus data build --profiles` reads
`data/profiles/trace.yaml`, one entry per specimen:

```yaml
- {family: cross.straight, variant: "cma:1923.1121", mode: outline,
   image: {pack: cma_profile_images, url: "<exact URL>", sha256: "…"},
   crop: [x0, y0, x1, y1], seed: [x, y],              # the kept component is the one holding `seed`
   cuts: [[[x0, y0], [x1, y1]], [[x2, y2], [x3, y3]]], # pixel segments that cut the part free (grip, blade, haft)
   ref: {name: cross_len, px: [[x0, y0], [x1, y1]], value_m: 0.153, from: "cma:1923.1121 quillons width"},
   check: {name: blade_len, px: [[...], [...]], from: "cma:1923.1121 blade length"}}   # a second measure of the same object, if any
- {family: chair.turned_leg, variant: "met:15292", mode: half_profile, axis: [[x0, y0], [x1, y1]], side: left,
   bridges: [[0.62, 0.71], [0.12, 0.18]], ...}         # axis intervals where rails and stretchers join
- {family: axe.head, variant: "cma:1922.28", mode: outline, haft: [[[...], [...]], [[...], [...]]], edge_tips: [[x, y], [x, y]], ...}
```

Steps: background = a quadratic surface fitted to the crop border (CMA photos have grey gradients); mask
|I − bg| > 4σ; cut along `cuts`; keep the component holding `seed` (`cv2.connectedComponents`); fill
holes; align the principal axis; boundary (`cv2.findContours`); Douglas-Peucker at 0.5% of the
reference length; least-squares lines and arcs (merge while rms < 0.3%); normalize by `ref`. Anchors:
cross seats = the midpoints of the cut segments on the blade and grip sides (n pointing away from the
cross); axe `eye_c` = the centroid of the mask between the haft's two edge lines, n = the haft direction
(up); `half_profile` reads r(u) as the distance from `axis` to the boundary on `side`, interpolates
linearly across `bridges` and records them (`"bridged": [[u0, u1], ...]`). Writes the variant and a
review overlay PNG to `.opus/out/trace/`.

**Acceptance** (all before a variant is committed): `fit_rms` ≤ 0.005 (0.5% of ref); a cross-check
within ±5% against a second recorded measure of the same object visible in the same image (met:23367:
blade width 8.89 cm against cross 23.5 cm; met:15292: overall depth against overall height) — a variant
without one is tagged `derived` and cannot be a family default; the maintainer's overlay review (PNG
attached to the PR, not committed); `cross.straight` variants have a bar centre line within 2% of ref of
straight (else they go to `cross.arched`); `axe.head` records `beard_drop` = (eye bottom − lowest point)
/ ref. A perspective warning (OVERHAUL §3.3) is not computable without the camera distance; the
cross-check stands in for it.

### 14.3 When a source is unreachable

1. Table builds read only the local cache filled by `data_fetch`; CI never fetches (`OPUS_OFFLINE=1`).
2. A failed fetch keeps the committed table untouched (its `source.retrieved` date shows its age) and
   `opus data build` exits non-zero naming the source.
3. A maintainer with a manual copy uses `data_fetch --from-file … --pack …`; the sha256 and date are
   recorded.
4. Nothing is filled from memory. A value that cannot be fetched is left out; a template then uses a
   `design` range and says so in `doc`. Only an explicit `recalled` fact (with "recalled, unverified" in
   `src`) may stand in, and it only warns.
5. `record` dims resolve from `museum_records` (committed), then the library cache, then — only when
   `OPUS_OFFLINE` is unset — `data_fetch(record=…)`; a record from the cache gets soft
   `record_uncommitted`; none of these → `record_unavailable` (hard) unless the dim also has a `user`
   fallback.

---

## 15. MCP tools and CLI

All return JSON strings (plus an Image for previews), raise `ValueError` for bad input (shown to Claude),
resolve relative paths against the project, and log through `runs.log_if_open` (§4.9).

| Tool (module, owner) | Arguments | Returns |
|---|---|---|
| `spec_new` (spec, A) | `kind="assembly"`, `archetype` (sword, axe, round_shield, chest, barrel, chair, generic), `id`, `out=""`, `camera=""`, `style=""` | `{"path", "todo": ["/dims/blade_len: user or record", ...], "derived": camera numbers, "candidates": {dim: [table refs]}}` |
| `spec_validate` (spec, A) | `path`, `log=true` | `{"ok", "findings", "resolved": {dim: RDim}, "derived": {"px_per_m": {...}}, "tables_version"}` |
| `dims_resolve` (spec, A) | `spec_or_category`, `wielder=""`, `style=""`, `seed=-1` | `{"sheet": {dim: RDim}, "conflicts", "tables_version", "findings"}` |
| `spec_preview` (preview, C) | `path`, `views="front,right,back,top,three_quarter"`, `size=1024`, `seed=-1` | [Image, `{"sheet", "masks": {view: png}, "hash", "tris", "parts": [{"name","size_m","px_close","px_far","tier","tris"}], "lint": findings}`] |
| `spec_build` (build, E) | `path`, `out=""`, `exports="blend,glb"` (+ `fbx_ue`), `finish=true`, `seed=-1` | `{"blend", "exports", "hash", "emit_hash", "match", "readback", "post_eval", "consistency", "ledger", "seconds"}` |
| `spec_check` (check, D) | `path`, `built=""`, `tiers="T0-T2"` (`T2b` needs `built`), `profile=""`, `parts=""`, `all=false` | `run_gates` result + `{"round", "evidence"}` |
| `spec_edit` (edit, G) | `path`, `patch=""` (JSON), `edit=""`, `why`, `keep=""`, `mode="single"`, `dials=""`, `tag=""`, `dry_run=false`, `by_user=false` | §10.2 |
| `defect_inject` (check, D) | `gate="all"`, `fixtures="ab6"`, `seeds=8`, `n_per=200`, `check_armed=false`, `write_armed=false` | §9.7 |
| `gate_calibrate` (check, D) | `check`, `corpus` (folder or fixture set), `planted=true`, `noise=false` | §9.7 |
| `data_fetch` (data, F) | `pack=""`, `from_file=""`, `record=""`, `licence_page=""`, `list=false` | §13.2 |
| `export_asset` (build, E) | `path` (spec or .blend), `engine` (ue, godot or unity), `out_dir=""`, `collision=true`, `round_trip=true` | `{"files", "sidecar", "round_trip": {"ok","findings"}, "licence": {"ok","blocked"}, "engine_script", "checklist"}` |

CLI (same functions): `opus spec new|validate|resolve|preview|build|check|edit`, `opus dims`,
`opus data fetch|build|list`, `opus gates inject|calibrate|fixtures`, `opus export`; `opus eval compare
--tasks --metric` (WP0). `spec build --hash-check` also runs `spec_eval_hash` and `raster_tie` in
Blender and prints the three hashes and the tie rule seen. `tests/test_tools_s0b.py` (WP0) asserts the
11 tool names and argument lists and every CLI verb above, including those the A/B harness lists (§19.3).

---

## 16. CI, extras, doctor (WP-H; stub WP0)

`.github/workflows/ci.yml` (on push and pull_request):

| Job | Runner | Steps |
|---|---|---|
| `host` | matrix ubuntu-24.04, windows-2022 | `astral-sh/setup-uv` (pinned), `uv sync --frozen`, `ruff check` (pinned, configured), `pytest -m "not blender and not network and not perf"` with `OPUS_OFFLINE=1` and an empty `OPUS_LIBRARY_DIR` (import rules, licences, schema regenerates byte-identically, golden resolved JSON, tools and CLI verbs). The Windows job also computes `eval_hash` for the ab6 goldens and reports differences from the Linux values as warnings only (K3) |
| `blender` | ubuntu-24.04 | cache `blender-5.2.2-linux-x64.tar.xz` (key = version; verify sha256 `84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168` from `blender-5.2.2.sha256`); `apt-get install libegl1 libegl-mesa0 libgl1 libgl1-mesa-dri libxi6 libxkbcommon0 libsm6`; `OPUS_BLENDER=…`, `OPUS_PERF_ASSERT=1`, `OPUS_OFFLINE=1`; `pytest -m "blender or perf or integration"`; the numpy-only module tests again under Blender's numpy (`uv run --with numpy==2.3.4 pytest tests/test_contracts.py tests/test_builders.py tests/test_gates_t2.py`); `opus gates fixtures --build ab6`; `opus gates inject all --fixtures ab6 --check-armed`; upload `ci-artifacts/ab6/<id>/{<id>.glb, <id>.opus.json, blueprint.png}` (generated, never fetched assets) |
| `godot` | ubuntu-24.04, needs `blender` | download `Godot_v4.7-stable_linux.x86_64.zip` (sha256 pinned: `0b1a6c54c2c619c12e169fe9241edda4b81080b519451cec2984bf0d2c6cb73c`), copy the artifacts into `tests/godot/proj/assets/`, `--headless --import`, then `-s check_import.gd`: node names, classes and AABBs against the sidecars' `bbox_engine` |
| `licences` | ubuntu-24.04 | every file in `data/tables/` and `data/profiles/` has a LICENSES entry; `museum_records` entries are CC0; every `ported-from` header has a THIRD_PARTY_NOTICES entry |

Workbench only, CPU only (llvmpipe); EEVEE and Cycles checks stay on the PC.

**Reaching CI from the agents.** `gh api …/actions/*` is refused by the proxy here, but the GitHub MCP
tools work (`actions_list` returned the workflow list), so agents read runs and logs with
`actions_list` / `get_job_logs`. WP0 pushes the one-job stub first to prove both the push and the read;
if the push is refused for lack of the `workflow` permission, the user commits `ci.yml` (and every later
change to it) through the GitHub web UI (U4).

`opus doctor` adds: Blender ≥5.2 and its numpy version, Godot path and version, each extra (installed,
imports, version, a one-call smoke test), library_dir and per-pack status and size, and the fill rule
from a 16×16 `raster_tie` render (cached per GPU).

`docs/PC_CHECKS_S0B.md` (≤10 minutes): 1. update to 0.5.0 and run the doctor; 2. `opus spec build
--hash-check` on the six Appendix A specs (three hashes equal; note the tie rule the NVIDIA GPU shows);
3. Godot, headless as the exit asks: `Godot_v4.7-stable_win64_console.exe --headless --path <proj>
--import`, then `… -s check_import.gd` for the axe, shield and barrel (node names, sizes, `SOCKET_`
nodes); 4. Unreal: 4.1 run `import_<id>.py` for sword, chest and chair (PASS lines; any API-name error
is reported), 4.2 the sword's length in uu and its `grip_main` socket, 4.3 the chest lid turns about its
back edge; 5. paste the report block.

---

## 17. Work packages

**Merge order: WP0 → F → A → B → E → C → D → G → H → integration phase.** Every package develops in
parallel from WP0 (using WP0's fixtures and stand-ins) and rebases on the merges before it; each
package's exit needs only packages merged before it. Every package keeps `pytest -m "not blender"`
green on its own and adds Blender tests behind the `blender` marker.

### WP0 — Contracts (integrator, before fan-out)
- **Owns:** `compile/{__init__,resolved,evalmesh,conventions,fmath,expr,measure,kinds}.py`,
  `spec/__init__.py`, `gates/{__init__,finding,registry}.py`, `extras.py`, `tools/__init__.py`, the six
  `tools/*.py` stubs (then owned by their packages), hooks in `entry.py`, `blender/runner.py` and
  `runs.py`, `paths.safe_name`, `cli.py`, `mcp_server.py`, `pyproject.toml`, `uv.lock`,
  `opus/__init__.py`, `.claude-plugin/plugin.json`, `.gitattributes`, the `ci.yml` stub,
  `data/schema/{finding,opus.resolved.1,opus.profile.1}.schema.json`, `data/gates/profiles.json`,
  `tests/{conftest,test_contracts,test_import_rules,test_tools_s0b}.py`, `tests/test_mcp.py` (`EXPECTED`),
  `tests/fixtures/s0b/`.
- **Exit (package):** `eval_hash(fixture_boxes())` stable across two processes and equal inside Blender
  (a script under `tests/blender_scripts/`, since `spec_eval_hash` is WP-B's);
  `save_npz`/`load_npz` round trips with `frames`, `fields` and `extra`; `quads_to_tris` output passes
  `validate()` and a reordered layout fails it; `Finding` JSON (with numpy scalars) validates against its
  schema; `expr` accepts §4.4 and rejects attribute access outside the whitelist, lambdas, subscripts and
  comparisons; `project` reproduces the §2 probe masks; registry rejects duplicates, `armed()` follows K8,
  `load_checks` tolerates a missing module; the 11 stubs register and every CLI verb of §15 parses;
  `log_if_open` is a no-op without a run; `ruff check` clean; the CI stub's run is green (read through MCP).

### WP-F — Data: fetch, tables, profiles (first after WP0)
- **Owns:** `data_fetch.py`, `trace.py`, `tables.py`, `data/packs.yaml`, `data/tables/*.json` (including
  `museum_records.json`), `data/profiles/*` (including `trace.yaml`), `data/LICENSES.md`, `DOWNLOADS.md`,
  `tools/data.py`, tests `test_data_fetch.py` (local HTTP server: resume, sha mismatch, zip-slip,
  from-file, licence snapshot, offline mode, safe names), `test_tables_s0b.py` (Met string parser on real
  strings, class whitelists against the junk fixture, minimum n, duplicate merging, Wikidata aggregation,
  Wikipedia redirects), `test_profiles.py` (schema, arc validity, acceptance fields), `test_licences.py`
  additions.
- **Consumes:** only the §13–14 formats.
- **Exit (package):** the seven tables built and committed with LICENSES entries; ≥6 accepted weapon
  profile variants committed (overlays attached to the PR); WP0's stand-in fixtures match the real shapes
  (test).

### WP-A — Spec language, dims, templates, bible
- **Owns:** `spec/{model,schema,validate,templates}.py`, `dims.py`, `bible.py`,
  `data/templates/*.spec.json`, `data/schema/opus.asset.1.schema.json`, `tools/spec.py`, tests
  `test_spec_model.py`, `test_spec_validate.py`, `test_dims.py`, `test_templates.py`,
  `test_bible_s0b.py`, `test_ab_specs_real_data.py`, `test_golden_resolved.py` (skips until the integration
  phase commits the goldens).
- **Consumes:** contracts; F's tables and profiles.
- **Tests:** one failing fixture per §5.6 rule (≥28), including `free_anchor` and `reflect_sides` per
  plane; per-dim seeding (adding a dim leaves others bit-identical); `tables_version` equal for LF and CRLF
  copies; lock round trip; templates leave every `user` and `record` dim as a todo; the K14 brief-number
  grep with a reviewed allowlist; `opus.asset.1.schema.json` regenerates identically.
- **Exit (package):** `test_ab_specs_real_data.py`: the six Appendix A specs and six templates resolve
  against the committed tables and profiles with 0 hard T0 findings and n ≥ 3 behind every table measure
  they cite; resolved outputs validate against `opus.resolved.1.schema.json`.

### WP-B — Compiler core
- **Owns:** `compile/{evaluate,solver,profiles,triangulate,uv}.py`, `compile/builders/*`,
  `opus_bl/compile_eval.py`, tests `test_builders.py`, `test_solver.py`, `test_evaluate.py`,
  `test_determinism.py`, `test_locality_deps.py`.
- **Consumes:** contracts, WP0 fixtures, F's profiles, A's `dims_resolve`.
- **Tests:** each builder over 200 random parameter sets in range: closed, outward, no degenerate
  triangles, canonical quads, |built − spec| ≤ `tess_bound`; anchors match analytic positions; every
  placement mode of `resolved_mixed.json` (face with spin and offset, point, translate, squeeze, orient,
  reflect in yz, xz and xy, radial and linear arrays); joint re-origin; mates re-check to 0 within
  `anchor_m`; a grip–cross–blade stack closes with contact 0 for every committed cross variant (seat
  anchors); `deps` closures (§10.6 companion test); `@radius` and `@profile` contact exactly; fit vs
  build differ only in tessellation; host/Blender `eval_hash` equality on the WP0 fixtures.
- **Exit (package):** the six ab6 specs at seeds 0, 1, 7 evaluate with `validate() == []`, every mate
  closed within `anchor_m` (checked through `measure` and the mates, not D's code), and host `eval_hash`
  = Blender `eval_hash`.

### WP-E — Blender emit, finish, read-back, consistency task, export
- **Owns:** `opus_bl/{emit,finish,readback,consistency,export}.py`, `opus_bl/grip.py` (the
  `handle_props` extraction only), `opus/{build,export}.py`, `gates/built.py`, `blender/runner.py`
  (after WP0's hook), `data/engine/*`, `data/errors.json`, `tools/build.py`, tests `test_emit.py`,
  `test_finish.py`, `test_readback.py`, `test_export.py`, `test_build.py`, `test_ab_grip.py`.
- **Consumes:** contracts, `evalmesh_box3.npz`, `resolved_joint.json`, B's `evaluate`.
- **Tests:** read-back `geom_hash` = evaluator `geom_hash` on the WP0 fixtures; joint subtree parenting;
  the grip socket in v0.4 format (`grip_define(object=<id>)` replaces it, `grip_hold` finds a radius);
  finish settings and the <1 px skip; MANIFOLD no-op and EXACT non-manifold results both refused; FBX and
  glTF round trips (FBX string stamps); the per-part bake keeps bevel widths and custom normals;
  consistency task output (sRGB8 colours, background, grid); errors.json hints; `post_eval` merge.
- **Exit (package):** the six A/B specs build to .blend + .glb (+ FBX for the ue specs) with round trips
  passing; `test_ab_grip.py`: sword, axe and shield held by the v0.4 body blockout (`grip_hold`,
  `grip_check`) give "good grip" with 0 clipping verts; UE script and checklist rendered for sword, chest
  and chair.

### WP-C — Raster, preview, consistency metrics
- **Owns:** `compile/{raster,views}.py`, `preview.py`, `gates/consistency.py`, `opus_bl/raster_tie.py`,
  `tools/preview.py`, tests `test_raster.py`, `test_preview.py`, `test_perf.py`, `test_consistency.py`.
- **Consumes:** contracts, `fixture_boxes()`, WP0's raster cases, E's `spec_consistency` task.
- **Tests:** single-triangle and tie cases against Blender (`raster_tie`); spans = edge-function
  reference on 1,000 random meshes; crop maths; synthetic masks with known shifts give the expected
  boundary p95; the hidden-part rule; colour decoding; throughput logged (asserted under
  `OPUS_PERF_ASSERT=1`).
- **Exit (package):** consistency metrics on the six ab6 specs × 4 views pass (stage `emitted`).

### WP-D — Gates, defects, calibration
- **Owns:** `gates/{runner,t0,t1,t2,geom,defects,inject,calibrate}.py`, `data/gates/{armed.json,
  noise.json,calibration/}`, `tools/check.py`, tests `test_gates_t0.py`, `test_gates_t1.py`,
  `test_gates_t2.py`, `test_defects.py`, `test_calibrate.py`, `test_gates_perf.py`.
- **Consumes:** contracts, WP0 fixtures, A's `validate` (lazily, through `t0.py`), B, E and C merged.
- **Tests:** each check on hand-built pass and fail cases; each defect kind planted at its resulting size
  and detected on fixtures; 0 failures on clean fixtures; NaN never passes; `armed()` gating, and
  `needs_suite=False` checks block without `armed.json`; T2 perf.
- **Exit (package):** a `defect_inject all --fixtures ab6` report meeting §9.7 for contact, floating,
  manifold, sheet and naming (relation and overlap reported, armed if they pass).

### WP-G — spec_edit, acceptance, archive, joint solve, ledger
- **Owns:** `spec_edit.py`, `accept.py`, `optim.py`, `runs.py` (after WP0's hooks), `tools/edit.py`,
  tests `test_spec_edit.py`, `test_accept.py`, `test_optim.py`, `test_runs.py` additions.
- **Consumes:** contracts; A, B and D merged.
- **Tests:** patch and seed-edit grammar; design picks need a finding-cited `why` and log `design_pick`;
  each acceptance step decides a crafted case; archive keeps ≤4 non-dominated; locality rejects a planted
  non-local change and accepts changes inside the closure; Nelder-Mead solves a 2-dial coupled toy;
  `spec_round` logging and the new summary fields.
- **Exit (package):** `test_random_dial_edits` (§10.6) green on chest and chair, with the negative
  control failing as required.

### WP-H — CI, doctor, docs, A/B kit, `mesh_lint` / `model_report` additions
- **Owns:** `.github/workflows/ci.yml` (after WP0's stub), `doctor.py`, `opus_bl/lint.py`,
  `opus_bl/inspect3d.py` (additive), `skills/3d-modeling/SKILL.md`, `README.md`, `docs/PC_CHECKS_S0B.md`,
  `evals/README.md`, `tests/godot/` (`check_import.gd`, project), `tests/blender_scripts/ab_probes.py`
  (the chest hinge and chair seat-height probes as the task specs describe them), tests
  `test_ab_dryrun.py`, `test_lint_s0b.py`, and the A/B harness (outside the repo, §19).
- **Exit (package):** a green CI run on the integration branch; doctor output on Linux; `mesh_lint` and
  `model_report` keep every existing key and value on a fixture (test) and add MANIFOLD readiness, the
  custom-normal check and `findings`; the skill's compiler section reviewed; PC checklist ≤10 minutes as
  written.

### Integration phase (integrator, after WP-H)
1. Generate `tests/fixtures/s0b/ab6/<id>.seed{0,1,7}.resolved.json` from the real data and commit them as
   goldens (`opus spec resolve --seeds 0,1,7 --out …`).
2. Run every §1.3 test on the merged tree (CI host, blender and godot jobs).
3. `opus gates fixtures --build ab6`, then `opus gates inject all --fixtures ab6 --write-armed`; commit
   `data/gates/armed.json`.
4. The A/B entry gate (§19.0).
5. Tag `v0.5.0-s0b`.

---

## 18. Risks specific to S0b

| Risk | Design answer |
|---|---|
| Evaluator and Blender drift | Pinned conventions (§4.2) with a probe-derived test; emission by `foreach_set` of the same arrays with canonical quads; `emit_hash`; T2b at high resolution and at the game camera; finishing >1 px marks `post_eval` |
| Determinism across numpy versions, CPU paths and platforms | K3: per-machine promise, numpy op whitelist enforced by the AST test, transcendentals through `math.*`; numpy-only tests also run under Blender's numpy 2.3.4; cross-OS goldens only for resolved JSON; hash differences across machines reported, never asserted |
| GPU tie rule differs from llvmpipe | Jitter in T2b; tie test records the rule per machine; metrics tolerate 1 px |
| MANIFOLD silent no-op; EXACT leaves non-manifold edges | Verified boolean helper that refuses both; no booleans in S0b specs |
| Bevel growth breaks triangle budgets | `budget_tris` on the finished read-back (what the grader's `mesh_lint` counts); sub-pixel bevels skipped; tangent joins not flagged; constant sections get end stations only; `test_ab_dryrun` |
| S0b gates disagree with the grader's v0.4 checks | The A/B entry gate (§19.0): `test_ab_dryrun`, `test_ab_grip`, `test_ab_specs_real_data`; grip sockets in v0.4 format (K18); S0b contact tolerance (2 mm) is stricter than `model_report`'s (0.4% of size) |
| Weighted Normal weight meaning, Bevel enum names, Triangulate custom normals | Probed names in §11.2; errors.json hints |
| `BLENDER_EEVEE`, `media_type`, channelbags, relative render paths | errors.json; S0b uses Workbench only |
| VertexGroup has no ID properties | Object-level `opus_vgroups` map (S1+) |
| Windows traps | `paths.safe_name` for every id-derived path; `as_posix()` relpaths in `tables_version`; `with np.load`; `.gitattributes` LF; `encoding=` everywhere (ruff PLW1514); list-form subprocess; CI host tests on windows-2022 |
| pydantic missing in Blender | K1/K2: TypedDicts in `opus.compile`, an empty `opus/spec/__init__.py`, the AST import test |
| Spec authoring friction | Templates ~90% complete with `todo` pointers and candidate refs; validator messages carry a `fix.suggest`; rejections, design picks and tokens measured in the A/B |
| Data gaps (pommel width, board thickness, boss size, chest proportions) | `design` or `range` dims with `doc`; `museum_records` and whitelisted classes with n ≥ 3; `recalled` only warns; gaps visible in `spec_validate` |
| Junk records in museum searches | Class whitelists by objectName, date window and department; a junk fixture test; minimum n |
| Tracing errors (joined parts, gradient backgrounds, perspective) | Cut lines, seed components, half-profile mode with bridges, background surface model, `fit_rms` ≤0.5%, ±5% cross-check, overlay review, prim fallbacks |
| Templates overfit to the A/B briefs | K14 test; one `generic` session per prop |
| A/B floor effects and noise | U1 measure off the floor; 3 runs per prop per arm; token and wall-clock guards (U2); grader-confirmed counts; clay pairs (K11) |
| A/B sessions interrupted by usage limits (the v0.4 baseline was) | Harness resumable per run id; arms interleaved so an interruption hits both; concurrency 2 |
| CI unreachable from agents | GitHub MCP tools for runs and logs; the user commits `ci.yml` if the push lacks `workflow` permission (U4) |
| Perf asserts flaky under contention (load 8–9 on 4 CPUs during the reviews) | Asserted only with `OPUS_PERF_ASSERT=1` (CI); logged otherwise |
| T2 cost on large meshes | Grid hash, bbox-restricted samples, early exit, plant-scoped re-runs (§9.4, §9.7) |
| UE Interchange drops `SOCKET_`/`UCX_` | Import script re-creates them from the sidecar; checklist |
| UE join loses per-part finishing | Per-part bake with `new_from_object`, then join (probed) |
| Merge conflicts between packages | File ownership (§17), WP0 stubs for every tool and CLI group, contract freeze |
| Godot import noise | Ignore exit-leak lines; compare node names and AABBs |
| Extras cap numpy below 2.6 for everyone | Accepted while 2.5.3 is current; the doctor reports it; revisit when a core need for numpy 2.6 appears |

**If the A/B fails** (the pre-registered criterion is missed, or the user prefers v0.4 in ≥2 pairs): the
compiler stays as a **validator and blueprint tool over v0.4's socketed shape kit**. Kept: spec language,
dims, tables, profiles, `spec_validate`, `spec_preview`, `spec_check` on any .blend through read-back
(parts bound to objects by name; sheet checks against the spec), gates and `defect_inject`,
`data_fetch`, `export_asset`. `spec_build` stays available but is no longer the default path; S4 is
re-planned around kit parts with sockets plus the validator.

---

## 19. A/B protocol (exit)

0. **Entry gate** (integration phase; all must pass before any A/B session): `test_ab_specs_real_data.py`
   (A); `test_ab_grip.py` (E); `test_ab_dryrun.py` (H): each Appendix A spec at seeds 0–2 goes through
   `spec_build`, then that task's hard checks run with the v0.4 tools exactly as the grader runs them
   (`mesh_lint` with the task's budget, the `model_report` metrics, the chest hinge and chair seat-height
   probes, `grip_hold` + `grip_check` on the v0.4 body blockout for the held props). Without this gate a
   tooling bug would count as a compiler loss and trigger the §18 fallback.
1. **Freeze.** Tag `v0.5.0-s0b` and copy the tree to
   `/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad/s0b` (as `v04` was).
   The v0.4 baseline copy and its eval folder stay untouched.
2. **Arms.** v0.4 = the baseline runs (label `v0.4`) plus 2 runs per prop from the frozen v0.4 copy, so
   sword, axe, round_shield, chest, barrel and chair have 3 each. S0b = label `s0b`, 3 runs per prop,
   eval project `<scratch>/evals/s0b` with the same `opus.project.yaml`. Report-only: 1 `s0b-generic`
   run per prop whose session is told to start from `spec_new(archetype="generic")` (K14).
3. **Harness.** The baseline workflow script (`evalkit/baseline.js`) with V = the S0b copy, LABEL `s0b`,
   and ENV extended with the CLI names `spec new|validate|resolve|preview|build|check|edit`, `dims`,
   `export`, `data fetch`, `gates inject|calibrate` and the S0b skill file (`test_tools_s0b.py` checks
   these names exist). Same model (`claude-opus-5-5`), same prompt (`opus eval prompt <id>`, unchanged
   task specs), same caps (10 check rounds, 2 judge rounds without a pass, 90 minutes), same rule that
   sessions treat the plugin as installed software, same `evals/judge.py`, and the same independent
   grader re-running every hard check with the **v0.4 tools from the frozen v0.4 copy** for both arms.
   S0b sessions may still use v0.4 tools. The harness is resumable per run id (a run with a closing event
   is skipped on restart; an unclosed run is abandoned and redone under a new id), interleaves the arms
   (v0.4, s0b, v0.4, … per prop) so an interruption or a busy machine hits both, runs at most 2 builder
   sessions at a time, and logs tokens for every run with `opus eval tokens` (the earlier baseline runs
   get theirs from their transcripts).
4. **Measures** (pre-registered; the user signs off U1 and U2 before WP0).
   - *Iteration* (both arms): an `iteration` event after every round of the task's hard checks on a
     built asset. In the S0b arm every `spec_build` that writes the task's asset is followed by such a
     round before the next build; evaluator-only `spec_check` rounds are `spec_round`s, reported.
   - *Primary (U1, proposed):* per prop, the median grader-confirmed `iterations_to_accept` (a run the
     grader does not accept counts as never accepting = worst). A **win** is a strictly lower median than
     v0.4's **and** (U2) S0b's median tokens and median wall-clock are each ≤1.2× v0.4's for that prop.
     Criterion: ≥5 wins of 6. The v0.4 baseline's values are 2, 2, 2, 3, 3, 2 (sword, axe, shield, chest,
     barrel, chair), so every prop can be won.
   - *Reported:* `iterations_to_hard_pass` (OVERHAUL's measure; v0.4 sits at its floor of 1 on sword,
     chest and chair), `spec_rounds`, validator rejections, `design_picks`, tokens, wall-clock, failure
     histograms, and the `s0b-generic` numbers (template dependence).
   - `opus eval compare v0.4 s0b --tasks sword,axe,round_shield,chest,barrel,chair --metric
     iterations_to_accept`, plus the guard table the harness writes.
   - *If U1 is declined:* OVERHAUL's wording applies (strictly lower median `iterations_to_hard_pass` on
     ≥5/6). Three props are at the floor, so the A/B cannot pass and the §18 fallback follows; the user
     should decide with that known.
5. **Blind pairs for the user.** Per prop, each arm's representative asset = its accepted run with the
   median iteration count (earliest on ties; if none accepted, the abandoned run with the fewest hard
   failures). Two sheets per prop with `ab_sheet(a, b, render_pass="clay", view="three_quarter")`: one
   large (`height_px=0`) and one at game size (`height_px` from `critique.game_height_px` at d_typical),
   sides randomized by seed; keys go to a sealed JSON the user never sees. The user answers A, B or
   "same" for the 6 props in one sitting (≤20 minutes). Criterion: v0.4 preferred in ≤1 of 6 ("same" is
   not a preference).
6. **Claude judge (report only).** `judge.py letter` on both orders of each pair; agreement with the user
   is recorded for S3's calibration.
7. **Decision.** Pass → S1 starts and S4 keeps the compiler plan. Fail → §18 fallback, recorded in
   OVERHAUL's review log with the numbers.

---

## Appendix A. The six A/B specs as S0b would write them

`tables_version` and `seed` are filled by `spec_new`. Every literal outside `dims` is one of the §5.3
places (rev, seed, spin, ranks, min_px, budgets, relation `tol_deg`, anchor sixteenths 0/8/16). Values
come from the brief (`user`), the committed Met/Cleveland records (`record`), tables, profiles, wielder
formulas, or `design`/`range` dims. `test_ab_specs_real_data.py` resolves all six against the real data
(0 hard T0 findings, n ≥ 3 behind every table measure) and `test_ab_dryrun.py` builds them and runs the
grader's hard checks (§19.0). These files are also WP0's `tests/fixtures/s0b/ab6/<id>.spec.json`.

### A.1 Sword (hd, Unreal)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "sword_c1400", "rev": 1, "parent_rev": null,
 "category": "weapon/sword", "style": "hd", "camera": "ue_tp_1080", "units": "m", "up": "+Z", "front": "-Y",
 "template": "sword", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "long_tapered_blade", "parts": ["blade_C"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "straight_cross", "parts": ["cross_C"], "views": ["front", "game"], "min_px": 8},
  {"rank": 3, "id": "wheel_pommel", "parts": ["pommel_C"], "views": ["front"], "min_px": 4}],
 "dims": {
  "oal": {"record": "met:23367", "measure": "overall_len"},
  "blade_len": {"record": "met:23367", "measure": "blade_len"},
  "blade_w_base": {"record": "met:23367", "measure": "blade_w"},
  "blade_t_base": {"record": "met:23367", "measure": "blade_t"},
  "blade_t_tip": {"range": [0.0020, 0.0022], "src": "replica distal taper, Albion spec sheets"},
  "blade_n": {"design": [1.3, 1.8], "unit": "ratio", "doc": "section exponent: 1 diamond, 2 oval"},
  "cross_len": {"record": "met:23367", "measure": "cross_w"},
  "cross_seat": {"profile": "lib:cross.straight#cma:1923.1121", "param": "seat_h", "doc": "bar thickness at the centre / cross length"},
  "cross_t": {"design": [0.010, 0.016], "doc": "not stated by any source"},
  "pommel_d": {"range": [0.052, 0.067], "src": "Met 29117 (5.2 cm) and 32799 (6.7 cm), loose wheel pommels, CC0 dimension strings"},
  "pommel_t": {"design": [0.45, 0.7], "unit": "ratio", "doc": "thickness / pommel_d"},
  "grip_len": {"expr": "oal - blade_len - cross_len*cross_seat - pommel_d", "sanity": "oakeshott.types.XIV.grip_len"},
  "grip_d_eq": {"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005 (NIOSH): optimal handle diameter 19.7% of hand length",
                "tol": 0.10, "measure": "grip_C:circ_d:0.5"},
  "grip_aspect": {"design": [1.15, 1.35], "unit": "ratio"}},
 "parts": [
  {"name": "grip_C", "build": {"station_loft": {"len": "grip_len", "a": "grip_d_eq*grip_aspect/(1+grip_aspect)",
                                                 "b": "grip_d_eq/(1+grip_aspect)", "n": "round"}}},
  {"name": "cross_C", "build": {"extrude": {"profile": "lib:cross.straight#cma:1923.1121", "plane": "XZ",
                                            "len": "cross_len", "depth": "cross_t"}},
   "attach": {"to": "grip_C", "at": "top_c", "self": "seat_bottom"}},
  {"name": "blade_C", "build": {"station_loft": {"len": "blade_len", "width_profile": "lib:blade.taper#met:23367",
                                                 "w": "blade_w_base", "t": "lerp(blade_t_base, blade_t_tip, s)", "n": "blade_n"}},
   "attach": {"to": "cross_C", "at": "seat_top", "self": "bottom_c"}, "edges": {"cutting": "sharp"}},
  {"name": "pommel_C", "build": {"lathe": {"profile": "prim:disc", "r": "0.5*pommel_d", "t": "pommel_t*pommel_d"}},
   "attach": {"to": "grip_C", "at": "bottom_c", "self": "rim_+x", "spin": 1}}],
 "relations": [{"type": "coaxial", "a": "grip_C", "b": "blade_C", "tol_deg": 0.5},
               {"type": "perpendicular", "a": "cross_C.x", "b": "blade_C", "tol_deg": 1}],
 "sockets": {"grip_main": {"grip": "grip_C"}, "tip": "blade_C:top_c"},
 "materials": {"blade_C": "phys:steel", "cross_C": "phys:steel", "pommel_C": "phys:steel", "grip_C": "phys:leather"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [1500, 4000]}},
 "surface": {"uv": "analytic"}, "history": []}
```

The brief asks for a straight cross, but the Met sword's own cross is arched (its tips sit about 2.2 cm
toward the blade), so the shape comes from the straight `cma:1923.1121` at the Met's 23.5 cm length. The
blade sits on the cross's `seat_top` anchor (the bar's centre), not its bbox top, so an arched variant
would leave no gap either. `grip_len` makes the overall length the record's 1.022 m by construction (the
wheel stands on its rim below the grip); the Oakeshott XIV grip length is a sanity band. `spin: 1` turns
the wheel's axis from +X to ±Y so its face shows in the front view. `grip_main` is written in v0.4's grip
format (K18) along the grip's axis at its middle. The pommel size is a `range` from two loose Met
pommels because no sword record states one.

### A.2 Bearded axe (lowpoly, Godot)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "axe_bearded", "rev": 1, "parent_rev": null,
 "category": "weapon/axe", "style": "lowpoly", "camera": "godot_tp", "units": "m", "up": "+Z", "front": "-Y",
 "template": "axe", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "bearded_head", "parts": ["head_C"], "views": ["right", "game"], "min_px": 8},
  {"rank": 2, "id": "long_haft", "parts": ["haft_C"], "views": ["front", "game"], "min_px": 4}],
 "dims": {
  "haft_len": {"user": 0.9}, "edge_len": {"user": 0.20, "sanity": "weapon_facts.dane_axe.edge_len"},
  "head_t": {"design": [0.018, 0.03], "doc": "head thickness at the eye; no source"},
  "head_s": {"design": [0.88, 0.94], "unit": "ratio", "doc": "eye centre along the haft"},
  "grip_s": {"design": [0.12, 0.3], "unit": "ratio", "doc": "hand centre along the haft"},
  "haft_d_eq": {"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005 (NIOSH)", "tol": 0.10, "measure": "haft_C:circ_d:0.2"},
  "haft_aspect": {"design": [1.15, 1.4], "unit": "ratio"}, "segs": {"design": [8, 12], "unit": "count", "int": true}},
 "parts": [
  {"name": "haft_C", "build": {"station_loft": {"len": "haft_len", "a": "haft_d_eq*haft_aspect/(1+haft_aspect)",
                                                "b": "haft_d_eq/(1+haft_aspect)", "n": "round", "segments": "segs"}}},
  {"name": "head_C", "build": {"extrude": {"profile": "lib:axe.head#cma:1922.28", "plane": "YZ",
                                           "len": "edge_len", "depth": "head_t"}},
   "attach": {"to": "haft_C", "at": "ring@head_s", "self": "eye_c", "mode": "point"}}],
 "relations": [{"type": "embedded", "a": "haft_C", "b": "head_C"}],
 "sockets": {"grip_main": {"grip": "haft_C", "center": "grip_s"}},
 "materials": {"haft_C": "phys:wood", "head_C": "phys:iron"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [100, 600]}}, "surface": {"uv": "analytic"}, "history": []}
```

The beard comes from the traced head outline. `cma:1922.28` is the default because its lower horn sweeps
down; `cma:1916.1601` is a fan head, not bearded. If no traced head reaches `beard_drop` ≥ 0.25, the
template uses `prim:axe_bearded` with `design` dims for `beard_drop`, `neck_w` and `eye_h` (§5.4). The
haft is a constant section, so it gets end stations only, which keeps the lowpoly budget.

### A.3 Round shield (lowpoly, Godot)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "shield_round", "rev": 1, "parent_rev": null,
 "category": "weapon/shield", "style": "lowpoly", "camera": "godot_tp", "units": "m", "up": "+Z", "front": "-Y",
 "template": "round_shield", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "round_board", "parts": ["board_C"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "boss", "parts": ["boss_C"], "views": ["front", "right"], "min_px": 4},
  {"rank": 3, "id": "rim", "parts": ["rim_C"], "views": ["front"], "min_px": 1}],
 "dims": {
  "diameter": {"user": 0.8, "sanity": "weapon_facts.viking_shield.diameter"},
  "board_t": {"design": [0.006, 0.012], "doc": "no committed source states board thickness"},
  "boss_d": {"table": "museum_arms.classes.shield_boss_early.diameter"},
  "boss_h_frac": {"design": [0.35, 0.5], "unit": "ratio"}, "boss_wall": {"design": [0.002, 0.004]},
  "hand_clear": {"design": [0.01, 0.02], "doc": "clearance on each side of the hand in the boss opening"},
  "hole_d": {"expr": "wielder.hand_breadth + 2*hand_clear"},
  "boss_flange_w": {"expr": "0.5*(boss_d - hole_d)"},
  "rim_t": {"design": [0.003, 0.006]}, "grip_overlap": {"design": [0.03, 0.06]},
  "grip_len": {"expr": "hole_d + 2*grip_overlap"},
  "grip_d_eq": {"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005 (NIOSH)", "tol": 0.10, "measure": "grip_C:circ_d:0.5"},
  "segs": {"design": [12, 16], "unit": "count", "int": true}},
 "parts": [
  {"name": "board_C", "build": {"lathe": {"profile": "prim:annulus_slab", "r_out": "0.5*diameter", "r_in": "0.5*hole_d",
                                          "t": "board_t", "segments": "segs"}}, "orient": "front"},
  {"name": "boss_C", "build": {"lathe": {"profile": "prim:dome_shell", "d": "boss_d", "h": "boss_h_frac*boss_d",
                                         "wall": "boss_wall", "flange": "boss_flange_w", "segments": "segs"}},
   "attach": {"to": "board_C", "at": "top_c", "self": "bottom_c"}},
  {"name": "rim_C", "build": {"lathe": {"profile": "prim:band", "r_in": "@radius", "w": "board_t + 2*rim_t", "t": "rim_t",
                                        "segments": "segs"}},
   "attach": {"to": "board_C", "at": "ring@8/16", "self": "ring@8/16", "mode": "point"}},
  {"name": "grip_C", "build": {"station_loft": {"len": "grip_len", "a": "0.5*grip_d_eq", "b": "0.5*grip_d_eq", "n": "round",
                                                "segments": "segs"}},
   "attach": {"to": "board_C", "at": "bottom_c", "self": "side_+y@8/16"}}],
 "relations": [{"type": "coaxial", "a": "board_C", "b": "boss_C"}, {"type": "coaxial", "a": "board_C", "b": "rim_C"}],
 "sockets": {"grip_main": {"grip": "grip_C", "palm": "+z", "hand": "l"}},
 "materials": {"board_C": "phys:wood", "boss_C": "phys:iron", "rim_C": "phys:iron", "grip_C": "phys:wood"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [150, 800]}}, "surface": {"uv": "analytic"}, "history": []}
```

The board is an annulus, so the hand passes through the opening into the boss's hollow and grips the bar
spanning it: "grip behind the boss, inside its hollow" holds by construction, with no boolean. The
opening is sized from the wielder's hand (ANSUR II male p50 hand breadth 88 mm, so 108–128 mm), the boss
diameter from the three public-domain early medieval bosses (17.8–20.0 cm), and the flange is what is
left, 2.5–4.6 cm. Board thickness has no committed source, so it is a `design` range. The palm side
`+z` is the template's slot; `test_ab_grip.py` decides it (§17, WP-E).

### A.4 Iron-banded chest (hd, Unreal; 12 parts, one hinge)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "chest_banded", "rev": 1, "parent_rev": null,
 "category": "prop/container/chest", "style": "hd", "camera": "ue_tp_1080", "units": "m", "up": "+Z", "front": "-Y",
 "template": "chest", "tables_version": "t-000000000000", "seed": 0, "wielder": null, "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "box_and_lid", "parts": ["body_C", "lid_C"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "iron_bands", "parts": ["band_body_L", "band_lid_L"], "views": ["front", "three_quarter"], "min_px": 3},
  {"rank": 3, "id": "lock", "parts": ["hasp_C", "lock_C"], "views": ["front"], "min_px": 3}],
 "dims": {
  "width": {"user": 0.8}, "depth": {"user": 0.5}, "height": {"user": 0.55},
  "lid_frac": {"design": [0.2, 0.3], "unit": "ratio"},
  "band_w": {"design": [0.03, 0.05]}, "band_t": {"design": [0.003, 0.006]},
  "band_pos": {"design": [0.2, 0.3], "unit": "ratio", "doc": "band centre from the -X end"},
  "band_pos_l": {"expr": "1 - band_pos"},
  "hinge_pos": {"design": [0.08, 0.12], "unit": "ratio", "doc": "hinge centre from the -X end; clear of the bands"},
  "hinge_pos_l": {"expr": "1 - hinge_pos"},
  "bracket_leg": {"design": [0.04, 0.07]}, "bracket_frac": {"design": [0.5, 0.8], "unit": "ratio"},
  "hasp_w": {"design": [0.04, 0.06]}, "hasp_h": {"design": [0.08, 0.12]},
  "lock_w": {"design": [0.05, 0.08]}, "lock_h": {"design": [0.06, 0.09]}, "lock_d": {"design": [0.015, 0.025]},
  "hinge_d": {"design": [0.015, 0.025]}, "hinge_len": {"design": [0.06, 0.1]},
  "lid_open_max": {"design": [95, 110], "unit": "deg"}},
 "parts": [
  {"name": "body_C", "build": {"box": {"sx": "width", "sy": "depth", "sz": "height*(1 - lid_frac)"}}},
  {"name": "lid_C", "build": {"box": {"sx": "width", "sy": "depth", "sz": "height*lid_frac"}},
   "attach": {"to": "body_C", "at": "top_c", "self": "bottom_c"}},
  {"name": "band_body_L", "build": {"extrude": {"profile": "prim:rect_u", "plane": "YZ", "w_in": "@w", "h_in": "@h",
                                                "wall": "band_t", "open": "top", "depth": "band_w"}},
   "attach": {"to": "body_C", "at": "section_x@band_pos_l", "self": "inner_c", "mode": "point"}},
  {"name": "band_body_R", "reflect": {"of": "band_body_L", "plane": "yz"}},
  {"name": "band_lid_L", "build": {"extrude": {"profile": "prim:rect_u", "plane": "YZ", "w_in": "@w", "h_in": "@h",
                                               "wall": "band_t", "open": "bottom", "depth": "band_w"}},
   "attach": {"to": "lid_C", "at": "section_x@band_pos_l", "self": "inner_c", "mode": "point"}},
  {"name": "band_lid_R", "reflect": {"of": "band_lid_L", "plane": "yz"}},
  {"name": "bracket_front_L", "build": {"extrude": {"profile": "prim:angle_l", "plane": "XY", "leg": "bracket_leg",
                                                    "wall": "band_t", "depth": "height*(1 - lid_frac)*bracket_frac"}},
   "attach": {"to": "body_C", "at": "uvw:16,0,8", "self": "inner_corner", "mode": "point", "spin": 1}},
  {"name": "bracket_front_R", "reflect": {"of": "bracket_front_L", "plane": "yz"}},
  {"name": "hasp_C", "build": {"box": {"sx": "hasp_w", "sy": "band_t", "sz": "hasp_h"}},
   "attach": {"to": "lid_C", "at": "uvw:8,0,0", "self": "uvw:8,16,16", "mode": "point"}},
  {"name": "lock_C", "build": {"box": {"sx": "lock_w", "sy": "lock_d", "sz": "lock_h"}},
   "attach": {"to": "hasp_C", "at": "front_c", "self": "back_c"}},
  {"name": "hinge_L", "build": {"lathe": {"profile": "prim:cylinder", "d": "hinge_d", "len": "hinge_len", "axis": "x"}},
   "attach": {"to": "body_C", "at": "uvw:hinge_pos_l,16,16", "self": "ring@8/16", "mode": "point"}},
  {"name": "hinge_R", "reflect": {"of": "hinge_L", "plane": "yz"}}],
 "relations": [{"type": "embedded", "a": "hinge_L", "b": "body_C"}, {"type": "embedded", "a": "hinge_L", "b": "lid_C"}],
 "joints": {"lid": {"part": "lid_C", "type": "revolute", "anchor": "body_C:top_back", "axis": "t", "limits": [0, "lid_open_max"]}},
 "sockets": {"lock": "lock_C:front_c"},
 "materials": {"body_C": "phys:wood_oak", "lid_C": "phys:wood_oak", "band_body_L": "phys:iron", "band_lid_L": "phys:iron",
               "bracket_front_L": "phys:iron", "hasp_C": "phys:iron", "lock_C": "phys:iron", "hinge_L": "phys:iron"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [500, 6000]}}, "surface": {"uv": "analytic"}, "history": []}
```

`body_C` is not attached to `ground`: the body bands' bottom wall (`band_t`) runs under the body, and
`bottom_center` puts the band bottoms at z = 0 (v0.4 `on_floor` reads 0; the first draft's ground attach
left them `band_t` below the floor). Reflected parts inherit materials. The lid is the joint root, so its
origin sits on the back top edge (K19; the hinge probe reads 0 mm); its bands, the hasp and the lock are
its joint subtree, parented to it in the .blend and exported as `SM_chest_banded_lid`. The hinges sit
8–12% in from the ends, clear of the bands at 20–30%. The bands' arms meet at the body/lid seam
(contact 0) and the lid bands wrap over the lid's top.

### A.5 Barrel (lowpoly, Godot)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "barrel_staved", "rev": 1, "parent_rev": null,
 "category": "prop/container/barrel", "style": "lowpoly", "camera": "godot_tp", "units": "m", "up": "+Z", "front": "-Y",
 "template": "barrel", "tables_version": "t-000000000000", "seed": 0, "wielder": null, "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "bulged_body", "parts": ["body_C"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "hoops", "parts": ["hoop_bot_C", "hoop_mid_C", "hoop_top_C"], "views": ["front"], "min_px": 2}],
 "dims": {
  "height": {"user": 0.9}, "head_d": {"user": 0.55}, "bulge_d": {"user": 0.65},
  "stave_n": {"design": [10, 14], "unit": "count", "int": true},
  "hoop_w": {"design": [0.03, 0.05]}, "hoop_t": {"design": [0.004, 0.008]}, "hoop_gap": {"design": [0.0, 0.0005]},
  "hoop_end_s": {"design": [0.08, 0.15], "unit": "ratio"}},
 "parts": [
  {"name": "body_C", "build": {"lathe": {"profile": "prim:barrel_arc", "h": "height", "r_end": "0.5*head_d",
                                         "r_mid": "0.5*bulge_d", "segments": "stave_n"}},
   "attach": {"to": "ground", "at": "top_c", "self": "bottom_c"}},
  {"name": "hoop_bot_C", "build": {"lathe": {"profile": "prim:band", "r_in": "@profile", "w": "hoop_w", "t": "hoop_t",
                                             "clearance": "hoop_gap", "segments": "stave_n"}},
   "attach": {"to": "body_C", "at": "ring@hoop_end_s", "self": "ring@8/16", "mode": "point"}},
  {"name": "hoop_mid_C", "build": {"lathe": {"profile": "prim:band", "r_in": "@profile", "w": "hoop_w", "t": "hoop_t",
                                             "clearance": "hoop_gap", "segments": "stave_n"}},
   "attach": {"to": "body_C", "at": "ring@8/16", "self": "ring@8/16", "mode": "point"}},
  {"name": "hoop_top_C", "reflect": {"of": "hoop_bot_C", "plane": "xy", "through": "body_C:ring@8/16"}}],
 "relations": [{"type": "coaxial", "a": "body_C", "b": "hoop_mid_C"}],
 "materials": {"body_C": "phys:wood_oak", "hoop_bot_C": "phys:iron", "hoop_mid_C": "phys:iron"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [150, 800]}}, "surface": {"uv": "analytic"}, "history": []}
```

`segments: stave_n` with flat shading makes every facet a stave; hoops share the count and phase, so
their inner faces follow the facets exactly (contact by construction). The `xy` reflection keeps the side
(`C`) and differs by role (`hoop_top` vs `hoop_bot`), as `reflect_sides` requires. The hoops' bevels are
sub-pixel at d_close and are skipped (§11.2); the body, three hoops and rim chamfers are estimated at
about 600 triangles, which `test_ab_dryrun` checks against the 800 budget.

### A.6 Joined armchair (hd, Unreal; 11 parts)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "chair_joined", "rev": 1, "parent_rev": null,
 "category": "prop/furniture/chair", "style": "hd", "camera": "ue_tp_1080", "units": "m", "up": "+Z", "front": "-Y",
 "template": "chair", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "panelled_back", "parts": ["back_panel_C", "post_back_L"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "turned_front_legs", "parts": ["leg_front_L"], "views": ["front", "right"], "min_px": 4},
  {"rank": 3, "id": "arms", "parts": ["arm_L"], "views": ["right", "three_quarter"], "min_px": 4}],
 "dims": {
  "height": {"record": "met:15292", "measure": "height"},
  "width": {"record": "met:15292", "measure": "width"},
  "depth": {"record": "met:15292", "measure": "depth"},
  "seat_h": {"expr": "wielder.popliteal_height + 0.025", "src": "OVERHAUL 4.7: popliteal p50 + 25 mm shoe allowance",
             "sanity": "0.42..0.48"},
  "arm_h": {"expr": "seat_h + wielder.elbow_rest_height", "src": "ANSUR II elbow rest height (sitting)"},
  "seat_t": {"design": [0.025, 0.035]}, "leg_d": {"design": [0.04, 0.055]}, "post_w": {"design": [0.04, 0.055]},
  "leg_segs": {"design": [10, 14], "unit": "count", "int": true},
  "seat_overhang": {"design": [0.0, 0.03], "doc": "seat edge beyond the front legs"},
  "arm_w": {"design": [0.04, 0.06]}, "arm_t": {"design": [0.025, 0.035]}, "panel_t": {"design": [0.012, 0.02]},
  "str_h": {"design": [0.08, 0.15], "doc": "stretcher height above the floor"}, "str_w": {"design": [0.025, 0.035]},
  "leg_u": {"expr": "1 - (0.5*leg_d + seat_overhang)/width"}, "leg_v": {"expr": "(0.5*leg_d + seat_overhang)/depth"},
  "post_u": {"expr": "1 - 0.5*post_w/width"}, "post_v": {"expr": "1 - 0.5*post_w/depth"},
  "leg_seat_s": {"expr": "(seat_h - seat_t)/arm_h"}, "leg_str_s": {"expr": "str_h/arm_h"},
  "post_seat_f": {"expr": "(seat_h - seat_t)/height"}, "post_arm_f": {"expr": "arm_h/height"},
  "post_str_f": {"expr": "str_h/height"}, "post_panel_f": {"expr": "(seat_h + 0.5*(height - seat_h))/height"}},
 "parts": [
  {"name": "seat_C", "build": {"box": {"sx": "width", "sy": "depth", "sz": "seat_t"}},
   "attach": {"to": "ground", "at": "top_c", "self": "bottom_c", "offset": "seat_h - seat_t"}},
  {"name": "leg_front_L", "build": {"lathe": {"profile": "lib:chair.turned_leg#met:15292", "len": "arm_h", "r_max": "0.5*leg_d",
                                              "segments": "leg_segs"}},
   "attach": {"to": "seat_C", "at": "uvw:leg_u,leg_v,0", "self": "ring@leg_seat_s", "mode": "point"}},
  {"name": "leg_front_R", "reflect": {"of": "leg_front_L", "plane": "yz"}},
  {"name": "post_back_L", "build": {"box": {"sx": "post_w", "sy": "post_w", "sz": "height"}},
   "attach": {"to": "seat_C", "at": "uvw:post_u,post_v,0", "self": "uvw:8,8,post_seat_f", "mode": "point"}},
  {"name": "post_back_R", "reflect": {"of": "post_back_L", "plane": "yz"}},
  {"name": "arm_L", "build": {"box": {"sx": "arm_w", "sy": "auto", "sz": "arm_t"}},
   "squeeze": {"from": "leg_front_L:top_c", "to": "post_back_L:uvw:8,0,post_arm_f", "self": ["front_c", "back_c"]}},
  {"name": "arm_R", "reflect": {"of": "arm_L", "plane": "yz"}},
  {"name": "back_panel_C", "build": {"box": {"sx": "auto", "sy": "panel_t", "sz": "height - seat_h"}},
   "squeeze": {"from": "post_back_R:uvw:16,8,post_panel_f", "to": "post_back_L:uvw:0,8,post_panel_f", "self": ["right_c", "left_c"]}},
  {"name": "stretcher_side_L", "build": {"box": {"sx": "str_w", "sy": "auto", "sz": "str_w"}},
   "squeeze": {"from": "leg_front_L:ring@leg_str_s", "to": "post_back_L:uvw:8,0,post_str_f", "self": ["front_c", "back_c"]}},
  {"name": "stretcher_side_R", "reflect": {"of": "stretcher_side_L", "plane": "yz"}},
  {"name": "stretcher_front_C", "build": {"box": {"sx": "auto", "sy": "str_w", "sz": "str_w"}},
   "squeeze": {"from": "leg_front_R:ring@leg_str_s", "to": "leg_front_L:ring@leg_str_s", "self": ["right_c", "left_c"]}}],
 "relations": [{"type": "embedded", "a": "leg_front_L", "b": "seat_C"}, {"type": "embedded", "a": "post_back_L", "b": "seat_C"},
               {"type": "embedded", "a": "leg_front_L", "b": "arm_L"}, {"type": "embedded", "a": "stretcher_side_L", "b": "leg_front_L"},
               {"type": "embedded", "a": "stretcher_front_C", "b": "leg_front_L"}, {"type": "embedded", "a": "stretcher_front_C", "b": "leg_front_R"}],
 "sockets": {"seat": "seat_C:top_c"},
 "materials": {"seat_C": "phys:wood_oak", "leg_front_L": "phys:wood_oak", "post_back_L": "phys:wood_oak", "arm_L": "phys:wood_oak",
               "back_panel_C": "phys:wood_oak", "stretcher_side_L": "phys:wood_oak", "stretcher_front_C": "phys:wood_oak"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [1000, 5000]}, "soft": {"com_over_footprint": true}},
 "surface": {"uv": "analytic"}, "history": []}
```

The seat top lands at popliteal p50 + 25 mm (0.455 m for the ANSUR II male p50 of 430 mm, inside the
task's 0.42–0.48 m); the legs reach the floor because their seat station is `(seat_h − seat_t)/arm_h`;
the arms run from the front-leg tops to the back posts at the same height by squeeze. Leg and post
positions are derived ratio dims (`leg_u`, `leg_v`, `post_u`, `post_v`), not typed sixteenths.
`sanity: "0.42..0.48"` is the literal band from the task, allowed only in `sanity`. The turned leg is a
lathe of straight lines and arcs, so it gets stations only where the profile curves; with `leg_segs`
10–14 and sub-pixel bevels skipped, `test_ab_dryrun` must show the finished chair under 5,000 triangles.
If the leg trace fails acceptance, the template's fallback is `prim:baluster`.

---

## Review log (revision 2)

Three reviews of the first draft (commit e03ff8e): completeness and testability (C), interfaces and
parallel buildability (I), feasibility and risk (F). Each point, and what this revision did. Disputed or
new claims were re-probed (`rev/t2_grid_bench.py`, the Albion URLs, the baseline ledger, the ANSUR CSVs,
the Met boss records); everything else was checked against the code or the reviewers' probes.

### Completeness and testability

| # | Point | Resolution |
|---|---|---|
| C1 | Compiled `SOCKET_grip_main` clashes with v0.4 `grip_define`/`grip_hold` | Fixed: K18, §11.1 (v0.4 format on the root, `handle_props` helper), `test_ab_grip.py` (WP-E exit) |
| C2a | Chest bands below the floor | Fixed: A.4 no longer attaches `body_C` to ground |
| C2b | The "straight" cross is arched; blade attached at the bbox top | Fixed: `cross.straight` / `cross.arched` families, `seat_top`/`seat_bottom` anchors, A.1 uses `cma:1923.1121` and the seat anchors; WP-B tests contact 0 for every committed cross variant |
| C2c | `tol_deg` literals fire `unsourced_number` | Fixed: `tol_deg` is an allowed literal (deviation 6, as OVERHAUL's own example), default from the profile's `angle_tol_deg` |
| C2d | `pommel_w`, `viking_shield.board_t` have no data | Fixed: A.1 `pommel_d` is a `range` citing Met 29117/32799; A.3 `board_t` is `design`; `test_ab_specs_real_data.py` (WP-A exit) |
| C3 | The dial-edit test cannot fail | Fixed: §10.6 (dry-run candidates, ≥95% acceptance, negative control) |
| C4 | S0b gates and the grader's v0.4 checks disagree (triangle budget) | Fixed: `budget_tris` on the finished read-back, sub-pixel bevel skip, tessellation by segment type, `test_ab_dryrun.py` entry gate (§19.0) |
| C5 | Planted contact/floating defects undetectable on embedded parts | Fixed: resulting-size definitions, eligibility, `ineligible` count, recall per spec and placement mode (§9.5) |
| C6 | CI cannot resolve `record` dims | Fixed: K17 (`museum_records` committed, in `tables_version`), `OPUS_OFFLINE`, empty library in CI |
| C7 | Merge order vs exit evidence | Fixed: WP0 → F → A → B → E → C → D → G → H, plus an integration phase (§17) |
| C8 | Tracer underspecified (joined parts, `eye_c`, acceptance, axe default, chair fallback) | Fixed: cut lines, seed component, half-profile mode with bridges, `eye_c` rule, `fit_rms` ≤0.5% and ±5% cross-check, `cma:1922.28` default, `prim:axe_bearded` and `prim:baluster` fallbacks, optional `shield.boss` from Met 22635 (§14.2) |
| C9 | `museum_arms` string parsing and class rules | Fixed: Met string parser, whitelist + date window classes, minimum n, duplicate merging, junk fixture (§14.1). The suggested `sanity` on `hole_d` was replaced by sizing the opening from the hand (A.3), which cannot fail the grip |
| C10 | Arming rules contradict K8; no suites for several checks | Fixed: `needs_suite` (K8, §9.3); suites added for `relation_angle` (`tilt_part`), `grounded` (`lift_asset`), `dim_measure` (radial `scale_part`), `anchor_error` (rides on `offset_part`); consistency checks unarmed in S0b; read-backs in the clean set |
| C11 | `emit_hash` contract gaps (quads, joint origin) | Fixed: canonical quads in `validate()` and `quads_to_tris`; joint origin in the evaluator (K19); `resolved_joint.json` fixture |
| C12 | Locality deps must be transitive | Fixed: §7.2 step 3, §10.2, companion test in §10.6 |
| C13 | "Evaluator contract for all kinds" was only a dispatch table | Fixed: `kinds.py` levels per kind, `Proxy2D`, `frames`, `fields`, round-trip tests (§7.1) |
| C14 | A/B validity (iteration counting, guards, tie-break sign-off, template dependence) | Fixed: §19.4 iteration definition, U2 guards, the token tie-break dropped in favour of U1, `s0b-generic` sessions |
| C15 | Literal k/16 fractions and `spin` undeclared | Fixed: T0 `free_anchor` (0, 8, 16 only), deviations 3 and 4, A.4 `hinge_pos`, A.6 ratio dims |
| C16 | S0b items silently missing | Fixed, each placed: `mesh_lint`/`model_report` (WP-H, additive), `translate` (WP-B), relation solving and `along_tangent` (S4, deviation 3), `organic` (profile entry now, check S2), `sa` stamp and CREDITS.md (§12.3), `palette` (stored, S2), CI corpus (S2, §1.2), `post_eval` re-rasterization (§11.6), ε measurement (`gate_calibrate noise`, §9.7) |
| C17 | Albion URL 404 | Confirmed: every variant returns 404 (the first draft's "200" was a "Page not found" page); `oakeshott` is Wikipedia-only, Albion via `--from-file`; XIV crosses' "generally curved" kept as a note |
| C18 | `reflect_sides` must depend on the plane | Fixed: §5.3, §5.6 |
| C19 | Boundary metric for hidden parts | Fixed: §9.6 hidden-part rule; NaN never passes |
| C20 | Commit golden resolved JSON and hashes; assert on Windows | Partly: resolved-JSON goldens asserted on every OS; hash goldens are reported, not asserted, because CPU dispatch changes transcendental bits across machines (F-H3) |
| C21 | PC Godot check opens the editor | Fixed: headless command on Windows (§16 item 3) |
| C22 | No test of tool names and CLI verbs | Fixed: `test_tools_s0b.py` (WP0) |
| C23 | Skipping bevel for lowpoly contradicts OVERHAUL | Fixed by following OVERHAUL (segments 1), skipping only sub-pixel bevels (OVERHAUL's own detail tiers) |
| C24 | Claude setting `design` values breaks decision 16 | Declared: deviation 5, finding-cited `why`, `design_pick` logged and counted |
| C-r | Realism of the six specs | Sword (C2b–d), chest (C2a, C15), chair (C4, C8, C15), axe (C8), shield (C2d, C9) revised; barrel unchanged |

### Interfaces and parallel buildability

| # | Point | Resolution |
|---|---|---|
| I-B1 | `opus.spec` package import pulls pydantic into Blender | Fixed: TypedDicts in `compile/resolved.py`, empty `spec/__init__.py`, AST rule (K1, §3) |
| I-B2 | One `spec` CLI group needed by five packages; exit codes lost | Fixed: WP0 creates `spec`/`gates`/`data` groups, `add_cli(sub, groups)`, `run_cli → int \| None` (§4.9) |
| I-B3 | Quad layout not pinned | Fixed: canonical adjacent mates, `validate()`, `quads_to_tris` (§4.5) |
| I-B4 | `emit_hash` cannot match anchors; joint origin conflict | Fixed: `geom_hash` for `emit_hash`, `eval_hash` adds anchors and sockets (K4); read-back copies metadata; joint origin in the evaluator (K19) rather than export-only, because the grader's hinge probe reads the .blend |
| I-B5 | A/B specs an unowned fixture; records in CI; anthro v2 stand-in | Fixed: WP0 owns `ab6/*.spec.json` and stand-ins with real ids (including `anthro_ansur2` v2 and `museum_records`); K17; F merges first. Not adopted: WP0-committed resolved JSON built from stand-ins (WP0 has no resolver); packages use WP0's `resolved_*` fixtures and the goldens come from real data in the integration phase |
| I-B6 | `test_mcp.py` exact tool set | Fixed: WP0 registers all 11 stubs and updates `EXPECTED` once |
| I-B7 | `GateContext` and registration in a package file; unowned checks | Fixed: `GateContext` in `registry.py` with read-back paths and an injectable `run_task`; `CHECK_MODULES`; owners in §9.3 |
| I-B8 | `EvalMesh` lacks extra, mates, mirror links, relations | Fixed: `extra`, `relations`, `Mate`, `mirror_of`, `array_of`, `joint_root`, parent rules (§4.5) |
| I-H1 | Measures semantics undefined | Fixed: `measure.py`, canonical frames, `{spec, built}` measures, part-bound `measure`, `RDim` fields (§4.6, §4.8) |
| I-H2 | F → B profile contract was prose; the example arc was not an arc | Fixed: `opus.profile.1` schema, one kind enum, `ccw` arcs with a radius check, anchors, units, file naming, `resolved.profiles` keys; a real arc in the example (§14.2) |
| I-H3 | `ResolvedSpec` gaps | Fixed: features, wielder, optional builder/params, `post_eval`, category, `limits_deg` (§4.8) |
| I-H4 | Anchor grammar missing | Fixed: `ANCHOR_RE`, `BUILDER_ANCHORS`, `builder_anchor_names`, literal keys (§4.1) |
| I-H5 | Two owners for thresholds | Fixed: `data/gates/profiles.json` (WP0), merged into `resolved["gates"]` = `GateContext.profile` (§9.2) |
| I-H6 | A ↔ B cycle through tiers and `feature_px` | Fixed: both moved to `spec_preview` / T1 (§5.6, §8) |
| I-H7 | Run-ledger hooks fail without G or an open run | Fixed: WP0 adds the events, `log_if_open`, `findings_counts`; who logs what (§4.9) |
| I-H8 | Arming contradiction; finding keys depend on the caller | Fixed: `needs_suite`, runner stamps `armed`, `key()` without `gate` (§4.7) |
| I-M1 | Grep-based import rule flags decorators | Fixed: AST rule (§3) |
| I-M2 | Depth grid half a pixel off; non-square frames | Fixed: `i·kx + kx//2 + 0.5`, (W, H) multiples of 128 (§9.6) |
| I-M3 | `RasterCamera` cannot crop | Fixed: `crop` and the Blender border mapping (§4.2) |
| I-M4 | ID colour format unspecified | Fixed: 8-bit sRGB plus background (§9.6) |
| I-M5 | No task for the fill-rule render | Fixed: `raster_tie` task (WP0 name, WP-C module) |
| I-M6 | `KindNotAvailable` ownership and type | Fixed: `kinds.py`, subclass of `ValueError` |
| I-M7 | `part_hash(root_frame)` and anchors | Fixed: anchors offset too (§4.5) |
| I-M8 | Sidecar lacks per-group engine bboxes; artifact paths | Fixed: `groups[].bbox_engine`, `axis_matrix`, `ci-artifacts/ab6/<id>/` (§12.1, §16) |
| I-M9 | `provenance` has no schema | Fixed: §5.1 |
| I-M10 | numpy scalars in `Finding.to_json` | Fixed: conversion rule (§4.7) |
| I-M11 | `--tasks`/`--tiebreak` before G; `--check-armed` undefined | Fixed: WP0 adds `--tasks` and `--metric`; the tie-break is gone; `check_armed` defined (§9.7) |
| I-L | `plugin.json` version; conftest owner; naming drift (`typical`, `right`, three_quarter 38.66/26.6, `game`, view-model flag); probe-mask fixtures; `mesh_lint`/`model_report` owner; integration exits | All fixed (K16, §4.10, §4.2, §4.8, §17) |

### Feasibility and risk

| # | Point | Resolution |
|---|---|---|
| F-B1 | The A/B is at its floor on 3 of 6 props | Confirmed on the ledger (hard pass 1, 2, 2, 1, 2, 1; accept 2, 2, 2, 3, 3, 2); K15 rewritten; U1 asks the user to pre-register `iterations_to_accept` before WP0 |
| F-B2 | `record` dims cannot resolve in CI | Fixed: K17 |
| F-B3 | CI may not be pushable or readable | Adopted: GitHub MCP tools for reading, a WP0 stub push, U4 if the push lacks `workflow` permission (§16) |
| F-B4 | T2 budget impossible with winding numbers | Fixed: grid hash + early exit + parity inside test, probed at 0.01–0.04 s per pair (§2, §9.4); plant-scoped re-runs keep `defect_inject` in minutes. Not adopted: deferring `overlap` (it is cheap with the grid; it stays out of the exit families) |
| F-H1 | UE join drops per-part modifiers | Fixed: per-part bake, then join (§12.1) |
| F-H2 | Met search API retired / paginated | Fixed: separate endpoints, `limit=500&offset`, snapshot of the id list (§13.1) |
| F-H3 | Determinism is per machine and CPU path | Fixed: K3 reworded, numpy op whitelist, no cross-machine hash assertions |
| F-H4 | Windows traps | Fixed: `safe_name`, `as_posix`, `with np.load`, `.gitattributes`, `encoding=` (§4.10, §13.2) |
| F-H5 | A/B session budget and interruptions | Fixed: resumable, interleaved, concurrency 2 (§19.3); U3 |
| F-M1 | numpy version skew | Fixed: numpy-only tests also under numpy 2.3.4 in the blender job |
| F-M2 | ruff fails on the current tree | Fixed: WP0 pins and configures ruff and fixes the errors |
| F-M3 | Perf asserts flaky under contention | Fixed: `OPUS_PERF_ASSERT=1` only in CI |
| F-M4 | Joint emission vs `emit_hash` | Fixed another way: the joint origin lives in the evaluator (K19), so emit and hash agree and the .blend keeps the hinge origin |
| F-M5 | Resolved-spec import in Blender | Fixed with I-B1 |
| F-M6 | Data gaps (redirects, pommels, Wikidata duplicates) | Fixed: redirects followed, `design`/`range` dims, per-item aggregation |
| F-M7 | `opus.trace` without scipy/scikit-image | Fixed: `opus[ref]` (K20); scikit-image not added to the core now |
| F-L | Godot command; boolean fallback; FBX string stamps; extras pin numpy | Fixed: §16; §11.2 refuses EXACT non-manifold results and errors.json matches MANIFOLD's message; §12.2 parses string stamps; §4.10 and §18 note the numpy cap |
