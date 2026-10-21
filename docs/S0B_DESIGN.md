# S0b design: compiler core (v0.5)

Status: technical design, 2026-10-21. Governing document: [OVERHAUL.md](OVERHAUL.md) (§9 row S0b). This
document is what 8 implementation agents build from in parallel worktrees. Where it and OVERHAUL
differ, OVERHAUL sets the goals and this document sets the interfaces; §0 lists every deliberate
deviation.

How to use it:
- **WP0 (the contract commit, §4) lands first**, made by the integrator verbatim from §4. Every work
  package branches from it. Nobody edits a contract file in a package branch; a needed change goes to
  the integrator, who amends WP0 and tells every package.
- Each package owns the files listed for it in §17 and nothing else. Two packages never edit one file.
- Numbers in this document that came from a probe are marked **(probed)**; §2 lists the probes.

---

## 0. Key decisions

| # | Decision | Why |
|---|---|---|
| K1 | **pydantic 2 becomes a direct host dependency, pinned `pydantic>=2.11,<3`** (2.13.5 is already in the venv through `mcp`). It is used only by `opus.spec`. `opus.compile`, `opus.gates.geom` and `opus.gates.t2` import only the standard library, numpy, `opus.paths` and `opus.camera`, because Blender's Python must import them. A test enforces the import rule. | Blender 5.2.2 ships Python 3.13.13 + numpy 2.3.4 and no pydantic **(probed)** |
| K2 | The compiler consumes a **resolved spec**: a plain-JSON dict (§4.7) produced by `dims_resolve`. Pydantic models never cross into compile. | Same as K1; also makes the compile a pure function of one JSON file |
| K3 | **No BLAS on geometry paths.** Transforms are explicit elementwise sums (`fmath.apply`), never `@`/`dot`/`einsum`. Sampling uses Python's `random` seeded per dimension. | `A @ R.T` differs bitwise between Blender's numpy 2.3.4 and the host's 2.5.3; elementwise ops, `np.sin/cos/power/arctan2/exp`, `math.*` and `np.sum` are identical **(probed)** |
| K4 | **One mesh object per part**, emitted with local vertices plus a world matrix. EvalMesh carries both. The determinism hash is taken over float32-cast local vertices and matrices quantized to 1e-6, so the host evaluator, the in-Blender evaluator and a read-back of the emitted mesh all hash the same. | Blender stores float32; hashing float64 would make the read-back differ at quantum boundaries |
| K5 | **Raster conventions pinned and verified against Workbench**: pixel centres at (i+0.5, j+0.5), y down, sensor fit VERTICAL, `ortho_scale` = visible height, `angle_y` = vfov, perspective-correct depth. Tie rule: left and bottom edges inclusive. The consistency gate shifts the camera by a fixed sub-pixel offset so exact ties are improbable on any GPU. | 0 mismatched pixels on 18 random triangles × 2 projections × 3 resolutions; the tie rule was measured on Mesa llvmpipe **(probed)**; the PC's NVIDIA backend may differ |
| K6 | Silhouettes use a **scanline-span rasterizer with back-face culling**; IDs and depth use spans expanded to pixels. An edge-function rasterizer stays as the reference in tests. | Spans: 4,333 silhouettes/min worst case (37k tris filling 256²) vs 142/min for bounding-box edge functions, identical masks **(probed)** |
| K7 | **All T1/T2 gate code is numpy and runs on the host** on the EvalMesh, and again on arrays read back from Blender after a build. Blender only emits, finishes, renders, ray-casts and exports. | One implementation; the S1 worker can import the same code later |
| K8 | A geometric hard check **blocks only when `data/gates/armed.json` lists it**, written from a passing `defect_inject` run. Format checks (schema, references, licences, names) block from day one. | OVERHAUL §2.5: hard blocks once its recall test passes |
| K9 | Two additions to the source vocabulary (§5.2): **`record`** (a measurement from a CC0 museum record, e.g. Met 23367 "Length of blade") and **`profile` + `param`**. An expression literal other than 0.5, 1 or 2 must carry `src`. | The A/B briefs cite Met records; `0.197*hand_length` needs a citation |
| K10 | **No booleans in S0b specs.** Holes come from lathe annulus profiles and extruded rings or U-profiles. `finish.boolean()` exists, with verification, for S2+. | MANIFOLD silently returns the base mesh unchanged when an operand is non-manifold **(probed)** |
| K11 | **Materials are named slots only in S0b** (surface arrives in S2). The user's blind A/B pairs are clay renders. | Otherwise the A/B measures colour, not the compiler |
| K12 | **Godot headless import runs in CI.** The UE import script re-creates sockets and collision from the sidecar if the importer drops them. | Godot 4.7-stable imported our probe .glb headlessly in 8 s from this cloud environment **(probed)**; UE Interchange handling of `SOCKET_`/`UCX_` is unverified |
| K13 | MCP tools and CLI commands are added through **`opus/tools/<module>.py`** files registered by WP0, so no two packages edit `mcp_server.py` or `cli.py`. | Parallel worktrees |
| K14 | Spec templates (`spec_new`) contain **no number from an eval brief**; a test greps for them. | The A/B must measure the compiler, not templates tuned to the briefs |
| K15 | The A/B runs **3 fresh builder sessions per prop per arm** and pre-registers a tie-break at the floor (both arms pass at round 1 → lower median tokens wins). | One run per task is noisy; a v0.4 task that passes at round 1 cannot be beaten on iterations |
| K16 | Version 0.5.0. Spec files are `*.spec.json`; revisions and the Pareto archive live in `<project>/.opus/specs/<id>/`. | — |

Deviations from OVERHAUL: K9 adds `record` and `profile.param` sources; K10 removes booleans from S0b
spec surface; S0b ships Nelder-Mead joint solves only (CMA-ES moves to S2 with `spec_fit`); the
constraint sketch solver stays in S4 (the `sketch` source validates but reports `not_available`).

---

## 1. Scope

### 1.1 What S0b builds (every bullet of the §9 row)

| §9 bullet | Delivered as | WP |
|---|---|---|
| Spec envelope + validator | `opus.spec` (pydantic models, JSON Schema, T0 rules), `spec_new` templates for 6 archetypes + generic | A |
| dims resolver + first fact tables (ANSUR, Oakeshott, Cleveland swords, Wikidata firearms, ADA) with LICENSES entries | `opus.dims`; tables `anthro_ansur2` v2, `oakeshott`, `museum_arms` (Cleveland + Met), `firearms_wikidata`, `ada_2010`, `weapon_facts` | A, F |
| Anchor/graph solver | `opus.compile.solver` | B |
| Evaluator contract for all kinds; numpy builders box, extrude, lathe, station_loft | `opus.compile.evaluate` dispatch (non-assembly kinds raise `KindNotAvailable` with their sprint), builders box, superquadric, extrude, lathe, station_loft | WP0, B |
| Evaluator raster + blueprint sheet | `opus.compile.raster`, `opus.compile.views`, `opus.preview` | C |
| Profile library v0: ≥6 sword, axe and shield profiles traced from Cleveland/Met CC0 photos | `data/profiles/` (up to 11 traced variants in 5 families, 9 of them weapons) + `opus.trace` maintainer tool | F |
| Blender emitter + finish v1 via the one-shot runner | `opus_bl/emit.py`, `finish.py`, `readback.py` | E |
| Consistency gate v1 | `opus.gates.consistency` (host metrics) + `opus_bl/consistency.py` (renders, BVH depth) | C, E |
| Finding contract + T0–T2 + `spec_edit` (lexicographic) + run ledger | `opus.gates.*`, `opus.spec_edit`, `opus.accept`, `opus.runs` (`spec_round` event) | WP0, D, G |
| Minimal `defect_inject` / `gate_calibrate` harness | `opus.gates.defects`, `inject`, `calibrate`, `data/gates/armed.json` | D |
| CI workflow (Workbench and CPU) | `.github/workflows/ci.yml` (host on Linux and Windows, Blender, licences, Godot import) | H |
| FBX/glTF export presets + Blender round trip + UE import script and checklist | `opus_bl/export.py`, `opus.export`, `data/engine/` templates | E |
| `data_fetch` (manifest, `--from-file`, snapshots, lineage) | `opus.data_fetch`, `data/packs.yaml` | F |
| Optional-extras packaging | `[project.optional-dependencies]`, `opus.extras`, doctor report | WP0, H |

Also in S0b, because the exits need them: bible additions (gate profiles, `weapon_scale`, `allow_nc`,
rating budget), `spec_new` templates, ledger lineage on `spec_build`, the 3d-modeling skill update, the
S0b PC checklist and the A/B kit.

### 1.2 What S0b defers

| Deferred | To | Note |
|---|---|---|
| Persistent worker | S1 | One-shot runner (~0.8 s Blender start-up, probed) |
| visual_hull, sweep | S4 | |
| inflate, sdf_body, facet_loft, creature_cage | S2 | |
| Constraint sketch solver (`sketch` source) | S4 | Validates; compile reports `not_available` |
| Fullers and lenticular-with-fuller sections, `lib:point.*` | S4 | Blades use a superellipse section with exponent `blade_n` |
| `spec_explore`, `spec_fit`, CMA-ES, `critique_pack` | S3, S2 | `design` values resolve by seed and `spec_edit` until then |
| Surface: palette atlas, PBR values, bakes | S2 | Named material slots and analytic UVs only |
| CoACD hulls | S4 | One convex hull per part (`bmesh.ops.convex_hull`) |
| `ref_extract(profile)` for users | S4 | `opus.trace` is maintainer-only in S0b |
| Rigs, `post_eval` re-rasterization of SDF/cloth parts | S1, S2, S7 | The contract and flag exist; assemblies set it only for parts whose finishing moves the game raster by >1 px |
| Unity adapter verification | S8 | Preset exists, unverified |

### 1.3 Exit criteria and how each is tested

| Exit criterion (§9) | Test | Runs in |
|---|---|---|
| Same spec + seed + `tables_version` → identical quantized hash, host and Blender | `test_determinism.py`: the 6 A/B specs × seeds {0,1,7} evaluated on the host and inside Blender (`spec_eval_hash` task); plus the read-back hash of the emitted (unfinished) mesh. All three equal. | CI (blender job); PC checklist item 2 (Windows, NVIDIA) |
| Single-triangle projection convention test | `test_raster.py::test_single_triangle_blender`: ortho and perspective, 97×64 and 64×97, plus the 8×8 tie case (§2) against a Workbench mask render | CI; PC item 2 records the tie rule seen on the GPU |
| 5 specs × 4 views: IoU ≥0.99, per-part boundary p95 ≤0.5 px, depth p95 ≤1 game px | `test_consistency.py` on the 6 A/B specs × views front, side_px, top (ortho) and three_quarter (perspective), stage `emitted` (§9.6) | CI |
| ≥200 numpy silhouette evals/min (one view, 256², ≤12 parts) | `test_perf.py::test_silhouette_throughput`: `evaluate(level="fit")` + `raster.silhouette` at 256² for each A/B spec, 50 iterations; min over specs ≥200/min (expected ≥1,000) | CI (marker `perf`) |
| 6-part anchored prop survives 3 random dial edits with 0 gaps and 0 floating parts | `test_spec_edit.py::test_random_dial_edits`: chest (12 parts) and chair (11 parts); 20 seeds × 3 edits each of `design`/`range` dims and `style_mult` within their bounds through `spec_edit`; contact and floating checks after every edit | CI |
| `defect_inject`: contact, floating, manifold, sheet, naming ≥95% recall (≥99% at 2×), 0 failures on clean fixtures | `test_defects.py` + `opus gates inject all --fixtures ab6` artifact (§9.7) | CI |
| CI green | `.github/workflows/ci.yml` | GitHub |
| A/B against v0.4 on 6 props | §19 | cloud runs + user (≤20 min) |
| PC: Godot headless import of the exported .glb | CI job `godot` (probed feasible) and PC checklist item 3 | CI + PC |
| PC: UE import checklist | `docs/PC_CHECKS_S0B.md` item 4 | PC only |

**PC-only:** the UE import checklist, the user's blind pairs, and the Windows/NVIDIA runs of the
determinism hash, the tie rule and the Godot import (they also run on Linux in CI).

---

## 2. Probe evidence

Probes are in `/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad/s0b_design/` (Blender 5.2.2 LTS, Linux, Mesa llvmpipe).

| Probe | Result | Used in |
|---|---|---|
| Versions (`ver.py`) | Blender Python 3.13.13, numpy 2.3.4; host uv venv Python 3.13.16, numpy 2.5.3, pydantic 2.13.5, jsonschema 4.26 | K1 |
| Bitwise determinism (`det_probe.py`) | Identical: `np.sin`, `cos`, `power`, `arctan2`, `exp`, `sqrt`, `math.sin/pow`, `np.sum`, `math.fsum`, explicit elementwise transforms. **Different: `A @ R.T`.** | K3, §4.3 |
| Projection (`proj_host.py`, `proj_bl.py`) | 0 mismatched pixels (IDs and silhouettes): 3 parts × 6 triangles, ortho and perspective, 97×64, 64×97, 128×128, Workbench mask mode | K5, §4.2 |
| Tie rule (`tie_host.py`, `fill_rule.py`) | A pixel centre on an edge is inside when the edge's inward normal has nx > 0, or nx = 0 and ny < 0 (image y down): left and bottom edges. Reproduced exactly in numpy. GPU: OpenGL 4.5, Mesa 25.2.8 llvmpipe | §4.2 |
| Raster speed (`raster_bench.py`, `span_bench.py`) | Edge function, bbox pairs: 142/min worst case; spans + culling: 4,333/min worst case, 21k/min on a 4.5k-triangle sword; masks identical | K6 |
| Mesh emission (`api_probe.py`) | `foreach_set` 0.021 s vs `from_pydata` 0.061 s for 12.8k verts / 25k tris; vertex order preserved; `validate()` returns False when nothing was fixed, True when it fixed something | §11.1 |
| Stamps | `VertexGroup` refuses ID properties (TypeError). Objects keep `opus_part` through glTF (`export_extras`) and FBX (`use_custom_props`) re-import | §11.1 |
| Modifiers (`api_probe.py`, `uv_probe.py`) | Bevel `face_strength_mode='FSTR_AFFECTED'`, `miter_outer='MITER_ARC'`, `harden_normals`; Weighted Normal `keep_sharp`, `use_face_influence`, `weight`, `mode`; Triangulate `keep_custom_normals`; attributes `bevel_weight_edge` (FLOAT, EDGE), `sharp_edge`, `sharp_face`; `Mesh.set_sharp_from_angle`; `uv_layer.uv.foreach_set("vector")` all work; Bevel `limit_method='WEIGHT'` reads `bevel_weight_edge` | §11.2 |
| Booleans (`bool_probe.py`) | Solver enum FLOAT/EXACT/MANIFOLD. **MANIFOLD with a non-manifold operand returns the base mesh unchanged and raises nothing** (volume 1.0); EXACT computes (volume 0.938, 6 non-manifold edges) | K10, §11.2 |
| Export (`api_probe.py`) | glTF export 0.99 s; re-import keeps object names, `opus_part`, and a `SOCKET_` empty with its parent; FBX likewise | §12 |
| Godot (`gdproj/`) | Godot 4.7-stable Linux, `--headless --import` 8 s; `blade_C` → MeshInstance3D, AABB (0.04, 1.0, 0.04) (Z-up → Y-up), `SOCKET_grip_main` → Node3D. Exit prints benign leak `ERROR:` lines | K12, §12.4 |
| Exchange (`npz_bl.py`) | `.npz` written by numpy 2.5.3 loads in Blender with `allow_pickle=False` (float64, int32, `<U7`); 128² BVH ray casts 0.025 s | §4.5, §11.4 |
| Start-up | one-shot Blender run 0.76–0.84 s | §11 |

**Network, 2026-10-21, through the proxy:** Cleveland Open Access API 200 (511 sword records; structured
`dimensions` in metres; CC0 per record), Met `v1.1/search` 200 (4,639 hits for "sword", department 4),
Met `v1/objects/<id>` 200 (23367: blade length 81.28 cm, overall 102.24 cm, thickness of blade 0.64 cm,
greatest blade width 8.89 cm, greatest width 23.5 cm, 1.673 kg; 15292: 92.7 × 58.4 × 42.5 cm), Wikidata
SPARQL 200 (592 firearm items with a psn-normalized length via `(wdt:P31|wdt:P279)/wdt:P279* wd:Q12796`; 97
swords via Q12791), Wikipedia raw wikitext 200, Albion typology article 200, access-board.gov/ada 200,
ANSUR II female CSV 200, Blender 5.2.2 tarball + `.sha256` 200, Godot 4.7-stable zip 200, CMA image CDN 200.
`api.github.com` returned 403 here (scripts must not need it).

---

## 3. Architecture and module layout

```
spec.json ──spec_validate(T0)──► dims_resolve ──► resolved.json ──evaluate(level)──► EvalMesh
   ▲  (pydantic, host)              (host)          (plain dict)     (numpy; host or Blender)
   │                                                                     │
spec_edit ◄── findings ◄── gates T1/T2 (numpy, host) ◄───────────────────┤
   │                                     ▲                              raster ──► spec_preview (blueprint, masks)
   │                                     │ readback .npz                 │
   └──► spec_build ──► .npz ──run_task──► Blender: emit → finish → save .blend → readback → export
                                         └─ spec_consistency: Workbench ID masks + BVH depth ──► T2b (host metrics)
```

**Import rules** (enforced by `tests/test_import_rules.py`, which imports the listed modules with
`pydantic`, `yaml`, `PIL`, `mcp` blocked in `sys.modules`, and greps them for `@`/`matmul`/`dot(`/`einsum`/`linalg`):
numpy-only modules are `opus.paths`, `opus.camera`, `opus.compile.*`, `opus.gates.finding`,
`opus.gates.registry`, `opus.gates.geom`, `opus.gates.t2`.

### Module tree (new files; owner in brackets)

```
python/src/opus/
  spec/__init__.py            [A]  load_spec, validate, schema
  spec/model.py               [A]  pydantic models (§5)
  spec/schema.py              [A]  JSON Schema export → data/schema/opus.asset.1.schema.json
  spec/validate.py            [A]  T0 rules → Findings
  spec/templates.py           [A]  spec_new
  spec/resolved.py            [WP0] ResolvedSpec TypedDicts (§4.7)
  dims.py                     [A]  dims_resolve, wielders, tables_version, lock
  compile/__init__.py         [WP0]
  compile/evalmesh.py         [WP0] EvalMesh, Anchor, PartInfo, hash, npz, fixtures (§4.5)
  compile/conventions.py      [WP0] frames, names, views, RasterCamera, project (§4.1-4.2)
  compile/fmath.py            [WP0] deterministic math (§4.3)
  compile/expr.py             [WP0] expression evaluator (§4.4)
  compile/evaluate.py         [B]  evaluate(resolved, level, ppm) and the kind table
  compile/solver.py           [B]  anchor/graph solver
  compile/profiles.py         [B]  profile JSON → polylines; prim families
  compile/triangulate.py      [B]  polygon-with-holes ear clipping
  compile/uv.py               [B]  analytic UVs + shelf pack
  compile/builders/{box,superquadric,extrude,lathe,station_loft}.py   [B]
  compile/raster.py           [C]  silhouette, id_depth (spans), reference edge-function raster
  compile/views.py            [C]  view cameras, framing, consistency resolution
  preview.py                  [C]  blueprint sheet (PIL; host only)
  gates/__init__.py           [WP0]
  gates/finding.py            [WP0] Finding, Target, Fix, magnitude (§4.6)
  gates/registry.py           [WP0] CheckSpec, REGISTRY, armed()
  gates/runner.py             [D]  tiered runner, GateContext
  gates/t0.py, t1.py          [D]
  gates/t2.py, geom.py        [D]  numpy geometry (Blender-importable)
  gates/profiles.py           [D]  gate profiles from the bible
  gates/defects.py, inject.py, calibrate.py   [D]
  gates/consistency.py        [C]  T2b metrics and orchestration
  spec_edit.py, accept.py, optim.py           [G]
  build.py                    [E]  spec_build orchestration (host)
  export.py                   [E]  export_asset (host)
  data_fetch.py, trace.py     [F]
  extras.py                   [WP0] require(extra, module) lazy import helper
  tools/__init__.py           [WP0] register_all, add_cli_all, run_cli
  tools/spec.py [A], preview.py [C], build.py [E], check.py [D], edit.py [G], data.py [F]
blender/opus_bl/
  emit.py, finish.py, readback.py, consistency.py, export.py   [E]
  compile_eval.py             [B]  runs opus.compile.evaluate inside Blender, returns the hash
  entry.py                    [WP0 adds task names; lazy imports]
data/
  schema/{finding.schema.json, opus.resolved.1.schema.json} [WP0], opus.asset.1.schema.json [A]
  templates/*.spec.json [A]; tables/*.json [F]; profiles/*.json [F]; packs.yaml [F]
  gates/armed.json, gates/calibration/*.json [D]; engine/* [E]; errors.json [E]
.github/workflows/ci.yml [H]; docs/PC_CHECKS_S0B.md [H]
```

Changes to the proposed layout, and why: the blueprint sheet is `opus/preview.py`, not in
`opus.compile`, because it needs PIL and `opus.compile` must import in Blender; the expression evaluator
and the frame/raster conventions are WP0 contracts because three packages call them; the T2b metrics
live with the raster (WP-C) and the Blender half with the emitter (WP-E); MCP/CLI wiring is split into
`opus/tools/*` so packages never share `mcp_server.py` or `cli.py`; `opus.trace` (tracing) sits with the
data package because only maintainers run it in S0b.

Existing files changed: `bible.py` [A], `tables.py` [F], `runs.py` [G], `blender/runner.py` [E],
`doctor.py` [H], `skills/3d-modeling/SKILL.md`, `README.md`, `evals/README.md` [H],
`data/LICENSES.md` [F], `DOWNLOADS.md` [F], `mcp_server.py`, `cli.py`, `pyproject.toml`, `opus/__init__.py`
version [WP0 only].

---

## 4. Shared contracts (WP0)

WP0 writes these files exactly as specified, with tests in `tests/test_contracts.py`, and commits them
before fan-out. Code shown is normative; prose around it fills in what the code elides.

### 4.1 Frames, sides and names (`compile/conventions.py`)

- World: metres, **+Z up, −Y front, +X = the object's left**. An object faces −Y; seen in the front
  view its left side appears on the viewer's right.
- Sides: `L` = +X, `R` = −X, `F` = −Y, `B` = +Y, `C` = on the centre plane.
- Part names: `NAME_RE = r"^(?P<role>[a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)*)_(?P<side>[LRCFB])(?P<index>\d{2})?$"`,
  e.g. `blade_C`, `leg_front_L`, `stave_C07`. Array copies get the template name plus a 2-digit index.
  `ground` is a reserved virtual part (the z = 0 plane; anchor `ground:top_c` at the origin, n = +Z, t = +X).
- Reserved prefixes, never valid part names: `UCX_ UBX_ USP_ UCP_ SOCKET_ SM_ ground`.
- Anchor references: `"<part>:<anchor>"`, split at the first `:` (anchor names may contain `:` and `@`).
- Anchor frame: point **p**, unit normal **n** (frame z), unit tangent **t** (frame x, t ⟂ n), frame
  y = n × t. **Face mating** (attach mode `face`): the child is placed so that its anchor frame equals the
  parent's anchor frame turned 180° about its x axis (child t = parent t, child n = −parent n), then
  turned `spin` quarter turns (0–3, counter-clockwise about the parent's n), then moved `offset` metres
  along the parent's n. **Point mode**: the child's anchor point goes to the parent's anchor point and the
  child keeps the parent part's orientation, turned `spin` quarter turns about the parent's local Z.
- Grid: `GRID = 16`. Fractions in anchor names are `k/16` literals or ratio dims.
- `ORIENT = {"up": identity, "front": Z→−Y (Rx +90°), "back": Z→+Y, "left": Z→+X, "right": Z→−X, "down": Z→−Z}`
  for root parts only.

### 4.2 Raster conventions (`compile/conventions.py`)

```python
VIEWS = {"front": (0.0, 0.0), "side_px": (90.0, 0.0), "back": (180.0, 0.0), "side_nx": (270.0, 0.0),
         "top": (0.0, 90.0), "three_quarter": (35.0, 22.5)}   # (azimuth, elevation) in degrees
# direction from the target to the camera, as opus_bl.inspect3d.aim:
#   d = (sin az cos el, -cos az cos el, sin el)
TIE_RULE = "left+bottom"    # probed on Mesa llvmpipe 25.2.8 (OpenGL 4.5)
JITTER_PX = (0.137, 0.291)  # anti-tie camera shift for consistency renders (x right, y down)

@dataclass(frozen=True)
class RasterCamera:
    projection: str          # "persp" | "ortho"
    width: int               # pixels
    height: int
    vfov_deg: float          # persp only; sensor fit VERTICAL (Blender: data.angle_y)
    ortho_h: float           # ortho only: visible world height in m (Blender: ortho_scale)
    view: tuple[float, ...]  # 16 floats, row-major world -> camera; camera looks down -Z, +Y up, +X right
    near: float = 1e-3
    far: float = 1e4
    def ppm(self, depth: float | None = None) -> float: ...   # ortho: H/ortho_h; persp: (H/2)/tan(vfov/2)/depth
    def to_dict(self) -> dict: ...
    @staticmethod
    def from_dict(d: dict) -> "RasterCamera": ...

def look_view(target, d, distance) -> tuple[float, ...]:
    """Camera at target + d*distance looking at target. x_cam = normalize(cross(-d, up)), y_cam =
    cross(x_cam, -d), z_cam = d, with up = +Z; for |d.z| > 0.999 up = +Y (top view: image up = +Y)."""

def project(cam: RasterCamera, P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """World points (N,3) -> pixel x (right), pixel y (down), depth (m, > 0 in front).
    c = apply(view, P); depth = -c_z
    ortho: k = H/ortho_h; x = W/2 + c_x*k; y = H/2 - c_y*k
    persp: f = (H/2)/tan(vfov/2); x = W/2 + f*c_x/depth; y = H/2 - f*c_y/depth"""
```

- Pixel (i, j) has its centre at (i + 0.5, j + 0.5); row 0 is the top row.
- A pixel is covered when its centre is strictly inside a triangle, or on an edge whose inward normal
  (in image coordinates) has nx > 0, or nx = 0 and ny < 0. In span form: a row's centre y is covered when
  y_min < y ≤ y_max, and a pixel centre x when x_left ≤ x < x_right.
- Depth is view-space distance along −Z_cam, interpolated perspective-correctly (1/z for persp).
- Blender side (`opus_bl`): `cam.matrix_world = inverse(view)`, `data.sensor_fit = 'VERTICAL'`,
  `data.angle_y = radians(vfov)` or `data.type = 'ORTHO'; data.ortho_scale = ortho_h`, no shift,
  `resolution_percentage = 100`, `render.filepath` absolute (a relative path fails, probed), mask mode
  from `opus_bl.lookdev.mask_mode(color_type="OBJECT")`.

### 4.3 Determinism (`compile/fmath.py`)

```python
def apply(M, P):           # M: 16-tuple row-major, P: (N,3) float64 -> (N,3); explicit:
    # x' = M0*x + M1*y + M2*z + M3, y' = M4*x + ..., z' = M8*x + ...  (no matmul)
def compose(A, B) -> tuple # 4x4 product in pure Python floats, fixed summation order
def invert_rigid(M) -> tuple
def rot_axis(axis, quarter_turns) -> tuple   # exact 0/±1 entries
def ring_table(K: int, n: float, phase: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Superellipse ring: cx_k = sgn(cos θk)|cos θk|^(2/n), sy_k = sgn(sin θk)|sin θk|^(2/n),
    θk = 2πk/K + phase, computed with math.cos/math.sin/math.pow on scalars, cached."""
def spow(x, y)             # elementwise x**y via math.pow (arrays: list comprehension; ≤ a few thousand values)
def seeded_uniform(seed: int, key: str, lo: float, hi: float) -> float:
    """random.Random(int.from_bytes(sha256(f"{seed}:{key}".encode()).digest()[:8], "little")).random()
    scaled to [lo, hi]. One stream per key, so adding a dimension never moves another."""
```

Rules for `opus.compile` and `opus.gates.t2`: no `@`, `np.dot`, `np.matmul`, `np.einsum`,
`np.tensordot`, `np.linalg` (BLAS and LAPACK differ across numpy builds, probed); trigonometry and
non-integer powers through `fmath`; reductions that feed geometry use `math.fsum`.

### 4.4 Expressions (`compile/expr.py`)

Grammar: a Python expression parsed with `ast.parse(mode="eval")`, allowing only

| Node | Allowed |
|---|---|
| Constant | int, float (validator: a literal requires the dim's `src`, §5.2) |
| Name | dim names; `s` (station 0..1, station-loft params only); `pi` |
| Attribute | `wielder.<measure>`, `camera.ppm_close`, `ppm_typ`, `ppm_far`, `bevel_close` (flattened to dotted keys) |
| BinOp | `+ - * / **` (`**` → `fmath.spow`) |
| UnaryOp | `+ -` |
| Call | `min max clamp(x,a,b) lerp(a,b,t) sqrt abs floor ceil` |

```python
class ExprError(ValueError): ...
def names(text: str) -> set[str]                       # dotted names used
def evaluate(text: str, env: Mapping[str, float | np.ndarray]) -> float | np.ndarray
```

### 4.5 EvalMesh, exchange file and hash (`compile/evalmesh.py`)

```python
FORMAT = "opus.evalmesh/1"
Q = 1e-6
EDGE_SHARP, EDGE_BEVEL, EDGE_CUTTING, EDGE_SEAM = 1, 2, 4, 8

@dataclass
class Anchor:
    p: tuple[float, float, float]                 # world point (m)
    n: tuple[float, float, float]                 # unit normal (frame z)
    t: tuple[float, float, float]                 # unit tangent (frame x)
    attrs: dict[str, float] = field(default_factory=dict)  # radius | a, b, n | w, h, d

@dataclass
class PartInfo:
    name: str
    src: str                       # JSON pointer into the spec, e.g. "/parts/2"
    builder: str                   # box | superquadric | extrude | lathe | station_loft | fixture
    v0: int; v1: int; t0: int; t1: int        # slices of verts / tris
    matrix: tuple[float, ...]      # 16 floats row-major, local -> world
    material: str = ""
    parent: str | None = None      # placement parent; "ground" allowed
    closed: bool = True            # closed 2-manifold by construction
    post_eval: bool = False
    joint: dict | None = None      # {"name","type":"revolute|prismatic","origin":[3],"axis":[3],"limits":[2]} world
    measures: dict[str, float] = field(default_factory=dict)  # sheet key -> expected value (§9.3)
    deps: tuple[str, ...] = ()     # dims and parts this part depends on (locality, §10)

@dataclass
class EvalMesh:
    verts_local: np.ndarray        # (V,3) float64
    verts: np.ndarray              # (V,3) float64 = fmath.apply(part.matrix, verts_local) per part
    tris: np.ndarray               # (T,3) int32, CCW seen from outside; parts never share vertices
    part_id: np.ndarray            # (T,) int16
    uv: np.ndarray                 # (T,3,2) float32 corner UVs
    edge_flags: np.ndarray         # (T,3) uint8; edge k joins tris[:,k] and tris[:,(k+1)%3]
    quad_mate: np.ndarray          # (T,) int32: the other triangle of a quad, -1 if none
    parts: list[PartInfo]
    anchors: dict[str, Anchor]     # "part:anchor" world frames used by placements, sockets, joints
    sockets: dict[str, str]        # name -> "part:anchor"
    source: dict                   # {"spec_id","rev","seed","tables_version","level","evaluator","kind",
                                   #  "origin_offset": [x, y, z] applied by the origin rule}

    def part(self, name) -> PartInfo
    def bounds(self) -> tuple[np.ndarray, np.ndarray]
    def validate(self) -> list[str]   # shapes, dtypes, slices contiguous and covering, ids in range,
                                      # quad mates symmetric and sharing an edge, unit n/t, t.n≈0

def eval_hash(m: EvalMesh) -> str:
    def q(a):
        return np.rint(np.asarray(a, np.float32).astype(np.float64) / Q).astype("<i8").tobytes()
    h = hashlib.sha256(FORMAT.encode() + b"\0")
    for p in sorted(m.parts, key=lambda p: p.name.encode()):
        h.update(p.name.encode() + b"\0")
        h.update(q(p.matrix))
        h.update(q(m.verts_local[p.v0:p.v1]))
        h.update((m.tris[p.t0:p.t1] - p.v0).astype("<i4").tobytes())
    for k in sorted(m.anchors):
        a = m.anchors[k]
        h.update(k.encode() + b"\0"); h.update(q((*a.p, *a.n, *a.t)))
    return h.hexdigest()

def part_hash(m: EvalMesh, name: str, root_frame: bool = True) -> str
    # same recipe for one part; root_frame subtracts source["origin_offset"] from the matrix translation,
    # so re-centring the asset after an edit does not count as a change (locality, §10.2)
def save_npz(m: EvalMesh, path) -> None
def load_npz(path) -> EvalMesh                  # np.load(path, allow_pickle=False)
def fixture_boxes() -> EvalMesh                 # base_C 0.4x0.4x0.1 on ground, post_C 0.1x0.1x0.5 on it,
                                                # top_C 0.3x0.3x0.05 on that; anchors top_c/bottom_c; sockets {"top": "top_C:top_c"}
```

**`.npz` exchange** (host ↔ Blender, both directions): arrays `verts_local` (float64), `verts`
(float64), `tris` (int32), `part_id` (int16), `uv` (float32), `edge_flags` (uint8), `quad_mate`
(int32), and `meta`: a uint8 array holding UTF-8 JSON `{"format": FORMAT, "source", "parts": [PartInfo
as dict], "anchors": {k: {"p","n","t","attrs"}}, "sockets", "extra"}`. No object arrays; always
`allow_pickle=False`. Files are written to `cache_dir("spec_build")` and closed before Blender starts.
Read-back files set `source.level = "built"` and put `{"objects": [...], "stamps": {...}, "socket_empties": {...}}` in `extra`.

### 4.6 Finding contract (`gates/finding.py`, `data/schema/finding.schema.json`)

```python
CLASSES = ("hard", "soft", "report")
TIERS = ("T0", "T1", "T2", "T2b", "T3", "T4", "T5", "T6")

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
    gate: str                      # "spec_check" | "spec_validate" | "export_asset" | ...
    check: str                     # registry id, e.g. "contact_gap"
    klass: str                     # JSON key "class"
    tier: str
    target: Target
    value: float | int | str | bool | None
    expected: str                  # "<=0.002" | ">=0.99" | "==0" | "in[0.9,1.1]" | "true"
    unit: str                      # "m" | "px" | "deg" | "count" | "ratio" | ""
    noise_tol: float               # ε for spec_edit (§10.3); 0 for exact checks
    passed: bool                   # JSON key "pass"
    family: str | None = None      # contact | floating | manifold | sheet | naming | overlap | None
    armed: bool = True             # False: a hard check not yet in armed.json reports but never blocks
    evidence: str | None = None    # path to an image or npz
    fix: Fix | None = None
    message: str = ""

    def key(self) -> tuple: return (self.gate, self.check, self.target.part, self.target.other, self.target.view)
    def blocking(self) -> bool: return self.klass == "hard" and self.armed and not self.passed
    def magnitude(self) -> float:
        """0 when passed. "<=x": (v-x)/max(|x|,1e-9); ">=x": (x-v)/max(|x|,1e-9); "in[a,b]": distance
        outside /(b-a); "==x" numeric: |v-x|/max(|x|,1); booleans and strings: 1."""
    def to_json(self) -> dict; @staticmethod def from_json(d) -> "Finding"
```

JSON form (the OVERHAUL §2.5 example plus `tier`, `family`, `armed`, `message`):
`{"gate","check","class","tier","target":{...},"value","expected","unit","noise_tol","pass","family","armed","evidence","fix":{"spec_path","suggest","dial_unit"},"message"}`.

**Registry** (`gates/registry.py`):

```python
@dataclass(frozen=True)
class CheckSpec:
    check: str; tier: str; klass: str; family: str | None
    scope: str                     # "asset" | "part" | "pair"
    profiles: tuple[str, ...]      # gate profiles where it applies
    fn: Callable[["GateContext"], list[Finding]]
REGISTRY: dict[str, CheckSpec] = {}
def register(spec: CheckSpec) -> None
def armed(check: str) -> bool      # data/gates/armed.json[check]["armed"]; format checks (family None) -> True
```

### 4.7 Resolved spec (`spec/resolved.py`, `data/schema/opus.resolved.1.schema.json`)

```python
class RDim(TypedDict):
    value: float; min: float; max: float
    unit: str        # "m" | "ratio" | "deg" | "count" | "kg"
    src: str         # human-readable provenance
    tag: str         # measured | derived | recalled | user | design
    kind: str        # table | record | range | expr | profile | user | design
    path: str        # "/dims/<name>"
    licence_id: str | None

class RCamera(TypedDict):
    name: str; projection: str; vfov_deg: float; ortho_h: float; res_w: int; res_h: int
    d_close: float; d_typ: float; d_far: float; near_m: float; scale: float

class RPart(TypedDict):
    name: str; src: str
    builder: str                   # box | superquadric | extrude | lathe | station_loft
    params: dict                   # values: dim name, expr string, "@<attr>", "auto", preset word, profile id
    place: dict | None             # one of {"attach":..}, {"squeeze":..}, {"reflect":..}, {"orient":..}; None = root at origin
    array: dict | None             # {"radial":..} | {"linear":..}
    material: str
    edges: dict                    # {"cutting": "sharp", ...}

class ResolvedSpec(TypedDict):
    resolved: str                  # "opus.resolved/1"
    id: str; rev: int; kind: str; style: str; seed: int; tables_version: str
    camera: RCamera; origin: str   # "bottom_center" | "socket:<name>" | "none"
    dims: dict[str, RDim]
    profiles: dict[str, dict]      # profile id -> normalized profile JSON (§14.2)
    parts: list[RPart]
    relations: list[dict]; sockets: dict[str, str]; joints: dict[str, dict]
    gates: dict                    # resolved profile thresholds (§9.2)
```

### 4.8 Tool registration (`tools/__init__.py`) and Blender tasks

```python
MODULES = ("spec", "preview", "build", "check", "edit", "data")
def register_all(tool) -> None      # import opus.tools.<m>; m.register(tool) (tool = mcp_server._tool)
def add_cli_all(sub) -> None        # m.add_cli(sub)
def run_cli(args) -> bool           # first m.run_cli(args) that returns True
```

Each module defines `register(tool)`, `add_cli(sub)` and `run_cli(args) -> bool`. WP0 creates the six as
stubs, moves the existing `opus data build` subcommand from `cli.py` into `tools/data.py` unchanged, and
adds three lines to `mcp_server.py` (after `run_stats`) and `cli.py`. `entry.py` gains lazily imported
tasks: `spec_emit` (emit.run), `spec_readback` (readback.run), `spec_consistency` (consistency.run),
`spec_export` (export.run), `spec_eval_hash` (compile_eval.run). WP0 also makes `runner.run_task` set
`OPUS_HOST_SRC` (= `python/src`) in Blender's environment and `entry.py` append it to `sys.path`, so
Blender imports `opus.compile`; and adds `--tasks` and `--tiebreak` to `opus eval compare`, forwarded as
keyword arguments that WP-G implements in `runs.compare`. WP0 may touch files a package owns later,
because it lands before fan-out.

### 4.9 Packaging and fixtures in WP0

- `pyproject.toml`: version 0.5.0; dependency `pydantic>=2.11,<3`; extras `feq = ["PyGEL3D"]`,
  `terrain = ["fastscapelib", "pydelatin", "numba"]`, `hulls = ["coacd"]`, `uv = ["xatlas"]`,
  `ref = ["opencv-python-headless"]`, `gpu = ["cupy-cuda12x"]`, `lod = ["pyfqmr"]`; pytest markers
  `blender`, `perf`, `network` (network never runs in CI). `uv lock` refreshed. psutil, scipy and
  scikit-image join the core when first used (S1, S1, S3).
- `extras.py`: `require(extra: str, module: str)` imports lazily or raises `ValueError("install opus[<extra>]: …")`.
- `tests/fixtures/s0b/`: `resolved_box3.json` (three boxes stacked by face attach), `resolved_mixed.json`
  (lathe + station_loft + extrude with an inline outline, one reflect, one radial array),
  `profiles/*.json` (one profile of each kind in the §14.2 format, synthetic), `tables/*.json`
  (fake `oakeshott`, `museum_arms`, `weapon_facts`, `ada_2010` with the §14.1 shapes), and
  `evalmesh_box3.npz` from `fixture_boxes()`.

---

## 5. Spec language in S0b

### 5.1 Envelope

Implemented and validated: `spec` ("opus.asset/1"), `kind`, `id` (`^[a-z][a-z0-9_]{1,63}$`), `rev` (≥1),
`parent_rev`, `category`, `style` (lowpoly | stylized | hd | pixel3d), `units` ("m"), `up` ("+Z"),
`front` ("-Y"), `camera` (bible profile id or inline profile), `template`, `tables_version`, `seed`
(int ≥0), `wielder`, `origin`, `features` (1–7; soft warning outside 5–7 for characters, 3–7 for props),
`shape_language`, `size_tiers`, `palette_roles`, `must_avoid`, `dims`, the kind body (`parts`,
`relations`, `sockets`, `joints`, `materials` for `assembly`), `explore` (stored, unused until S3),
`gates`, `surface`, `lock`, `provenance` (written by tools), `history`. Every other kind validates its
envelope and an open body; `spec_build` then reports `not_available` with the kind's sprint.

`wielder`: `"ansur2:<male|female>:p<5|50|95>"` or `{"preset": ..., "user": {"stature": 1.83}}`.
It provides `wielder.stature, hand_length, hand_breadth, popliteal_height, buttock_popliteal_length,
elbow_rest_height, thumbtip_reach` in metres (absolute bands from `anthro_ansur2` v2; `user` values
override and are logged).

### 5.2 Dimension sources

Every number lives in `dims`. Each entry is exactly one source form plus optional common keys `unit`
(default "m"), `doc`, `tol`, `measure`, `sanity`, `int`, `value` (a resolved pick, written only by
`spec_edit`, the user, or lock).

| Form | Example | Resolves to | Tag |
|---|---|---|---|
| table | `{"table": "oakeshott.types.XIV.grip_len", "pick": "value\|sample\|min\|max", "style_mult": 1.15}` | the fact's value (or seeded sample in [min, max]) × style_mult; z-score logged | the fact's tag |
| record | `{"record": "met:23367", "measure": "Length of blade"}` (Met: `elementDescription` or `elementName[.key]`); `{"record": "cma:1921.1252", "measure": "quillions.width"}` (CMA: path in `dimensions`; the API takes accession numbers) | the record's measurement in m or kg from the cached object JSON (§14.1) | measured |
| range | `{"range": [0.0020, 0.0022], "src": "replica distal taper, Albion spec sheets"}` | seeded uniform sample | recalled (warnings only) |
| expr | `{"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005, NIOSH"}` | evaluated; `src` required for a literal other than 0.5, 1, 2 | weakest input tag |
| profile | `{"profile": "lib:cross.straight#cma:1921.1252", "param": "aspect"}` | the profile parameter's value | the profile's tag |
| user | `{"user": 0.9}` | the value; logged | user |
| design | `{"design": [0.9, 1.3], "unit": "ratio"}` | `value` if set, else seeded sample; T0 soft `design_unresolved` | design |
| sketch | `{"sketch": [...]}` | — | T0 hard `not_available` (S4) |

`sanity`: a table ref or `"lo..hi"` expression; outside it → soft `sanity_range`. `measure`: a
measurement the T1 sheet check takes on the build (`"circumference/pi"`, `"extent_z"`).

### 5.3 Parts

```json
{"name": "<role_side[index]>",
 "build": {"<builder>": {"<param>": "<dim | expr | @attr | auto | preset | profile id>", ...}},
 "attach":  {"to": "<part|ground>", "at": "<anchor>", "self": "<anchor>", "mode": "face|point",
             "spin": 0, "offset": "<dim|expr>", "clearance": "<dim|expr>"},
 "squeeze": {"from": "<part:anchor>", "to": "<part:anchor>", "self": ["<anchor>", "<anchor>"]},
 "reflect": {"of": "<part>", "plane": "yz|xz|xy", "through": "<part:anchor>"},
 "orient":  "up|front|back|left|right|down",
 "array":   {"radial": {"n": "<count dim>", "phase": "<k/16>"}} | {"linear": {"n": "<count dim>", "axis": "x|y|z", "span": "<dim|expr>"}},
 "edges":   {"cutting": "sharp|bevel|smooth", "rims": "...", "all": "..."},
 "post_eval": false}
```

Exactly one of `attach`, `squeeze`, `reflect`, `orient`, or none (a root at the origin). `reflect`
copies the source part's solved geometry mirrored through the plane (default through the root origin);
the reflected part is declared with its own name and `_L`/`_R` sides must swap. Its matrix is
M·R·M (a proper rotation, M the mirror) and its local vertices are mirrored with the winding reversed.
Box-type anchors (faces, edges, sections, `uvw`) are recomputed on its own local bbox, so `uvw` u still
runs −X→+X; builder anchors with a side in the name swap (`rim_+x`↔`rim_-x`, `side_+x@f`↔`side_-x@f`
for plane yz, the y or z pair for xz or xy). Relations naming the source part are mirrored onto it. Arrays generate
`<template name><index>` copies (radial about the attach parent's axis, linear centred on the attach
point). Literal numbers are allowed only in `rev`, `seed`, `spin` (0–3), `features[]`, `shape_language`,
`size_tiers`, `gates` overrides, joint closed limit `0`, and inside `dims` source forms. In any
expression (dims or build params) the literals 0.5, 1 and 2 are free (half of a diameter, a complement,
both sides); any other literal needs the dim's `src` and is rejected in build params.

Preset words for `n` (section exponent): `diamond` 1, `lens` 1.5, `round` 2, `squircle` 4, `boxy` 8.

### 5.4 Builders, parameters and anchors

| Builder | Params | Local frame | Anchors (plus `uvw:a,b,c` on every builder: bbox point at sixteenths or ratio dims, parent orientation) | Sheet measures |
|---|---|---|---|---|
| `box` | `sx sy sz` (`auto` allowed for squeeze) | centred bbox | face centres `top_c bottom_c front_c back_c left_c right_c` (t = +X; left/right t = +Y; attrs w, h of the face, d along n); edge midpoints `top_back top_front bottom_back bottom_front` (n outward-diagonal, t along the edge); `section_x@f`, `section_y@f`, `section_z@f` (attrs w, h of the cross-section) | `extent_x/y/z` |
| `superquadric` | `sx sy sz e1 e2` | centred | as box | `extent_x/y/z` |
| `extrude` | `profile`, `plane` XZ\|YZ\|XY, `len` (uniform scale so the profile's `ref` measure equals len), `h` (optional: rescales v to this extent), `depth` (centred), prim params | plane mapping: XZ (u,v)→(x,z), extrude ±y; YZ (u,v)→(−y,z), extrude ±x; XY (u,v)→(x,y), extrude ±z | bbox faces; every profile anchor (point at mid-depth, n from the profile); `inner_c`, `inner_corner` for prims | `extent_u`, `extent_v`, `depth` |
| `lathe` | `profile`, prim params (`r`, `r_max`, `len`, `h`, `d`, ...), `axis` z\|x\|y (default z), `segments` (count dim; default camera rule), `phase` | axis through origin, profile z from 0 | `bottom_c`, `top_c` (n ∓axis, t = +X), `ring@f` (on axis at height fraction f; attrs `radius` = outer radius there), `rim_+x rim_-x rim_+y rim_-y` (outer surface at the max-radius height; n radial, t = +axis) | `extent_z`, `radius_max` |
| `station_loft` | `len`, `stations` ("auto" or count dim), `width_profile` + `w` (a = ½·w·v(s)) or `a`; `t` (b = ½·t) or `b`; `n` (preset or dim or expr of s); `axis`; `segments` | axis +Z from 0 to len | `bottom_c`, `top_c`, `ring@f` (attrs a, b, n), `side_+x@f side_-x@f side_+y@f side_-y@f` (surface point, n outward, t = +axis) | `extent_z`, `width_at:f`, `thick_at:f` for f in {0.1, 0.5, 0.9} and profile breakpoints, `circumference_eq_d:0.5` when the dim has `measure` |

`@<attr>` in a param reads the attach target anchor's attribute (`@radius`, `@w`, `@h`, `@a`, `@b`);
`@profile` (lathe `band` only) copies the parent lathe's radius function over the band's height, plus
`clearance`.

**Tessellation.** `level="build"`: ring segments K = `camera.circle_segments(r_max, camera.ppm(d_close))`;
style `lowpoly` caps K at 12 and floors at 6 unless `segments` is given. Stations: profile breakpoints
plus uniform spacing of ≤8 game px at d_close (hd) or ≤24 px (lowpoly), 4–64 stations.
`level="fit"`: the same rules with `ppm` = the raster's own pixels per metre. A width or radius that
reaches 0 at an end becomes a single apex vertex (no degenerate triangles); lathe profiles touching the
axis become poles; seams are welded, so every part is a closed 2-manifold.

**Profiles and prims.** Library ids: `lib:<family>.<name>#<variant>` (variant optional = the family
default). Primitive families (`prim:`) are geometric, have no provenance and take every parameter from
dims:

| Prim | Kind | Params |
|---|---|---|
| `rect` / `rect_ring` / `rect_u` | outline | `w h` / `w_in h_in wall` / `w_in h_in wall open: top\|bottom` |
| `angle_l` | outline | `leg wall`; inner corner at the origin (anchor `inner_corner`), legs along +u and +v, walls on the −v and −u sides |
| `circle` | outline | `d` |
| `cylinder` / `disc` | radius | `d len` / `r t` |
| `annulus_slab` | radius (closed loop) | `r_out r_in t` |
| `band` | radius (closed loop) | `r_in` (or `@profile`), `w`, `t`, `clearance` |
| `dome_shell` | radius (closed loop) | `d h wall flange` |
| `barrel_arc` | radius | `h r_end r_mid` (circular arc through the three points, flat ends to the axis) |

### 5.5 Relations, sockets, joints

- Relations: `coaxial`, `parallel`, `perpendicular` (`{"a": "part[.axis]", "b": "...", "tol_deg"}`, axis
  default z), `symmetric` (implied by `reflect`), `embedded` (`a` may interpenetrate `b`; mirrored
  automatically for reflect pairs), `contact` (`a` and `b` must touch though neither attaches to the other).
- Sockets: `{"grip_main": "grip_C:uvw:8,8,10"}` → `SOCKET_<name>` empties.
- Joints: `{"lid": {"part": "lid_C", "type": "revolute", "anchor": "body_C:top_back", "axis": "t",
  "limits": [0, "lid_open_max"]}}`. The joint moves the part and its attach descendants; that subtree
  exports as its own mesh with its origin on the joint axis.

### 5.6 T0 validator rules (`spec/validate.py`)

| Check | Class | Family | Rejects |
|---|---|---|---|
| `schema` | hard | — | JSON Schema violations, unknown keys |
| `units_frame` | hard | — | units ≠ m, up ≠ +Z, front ≠ −Y |
| `unsourced_number` | hard | — | a numeric literal outside the allowed places (§5.3); an expression literal other than 0.5, 1, 2 without `src` |
| `typed_colour` | hard | — | a hex or RGB value without a palette source |
| `name_format`, `name_duplicate`, `name_reserved`, `reflect_sides` | hard | naming | §4.1 rules; reflect pairs must swap L/R |
| `unknown_ref` | hard | — | parts, anchors, dims, profiles or tables that don't exist; anchor fractions outside [0, 1] |
| `parent_cycle` | hard | — | cycles in attach/squeeze/reflect |
| `too_many_parts` | hard | — | >12 declared parts (array copies count once) |
| `table_range` | hard (soft if the fact is `recalled`) | sheet | a resolved value outside [min, max] × style_mult |
| `missing_licence` | hard | — | a table or profile without a `data/LICENSES.md` entry, or an unknown licence ID |
| `record_unavailable` | hard | — | a `record` not in the cache and not fetchable; a record that is not CC0 / public domain |
| `todo_unfilled` | hard | — | template placeholders left (`{"user": null}`) |
| `not_available` | hard | — | a kind, builder or source form from a later sprint |
| `design_unresolved` | soft | — | `design` dims without `value` |
| `sanity_range` | soft | — | outside `sanity` |
| `feature_px` | soft | — | a feature's projected size at d_far below its `min_px` |
| `tables_version_drift` | soft | — | the spec's `tables_version` ≠ current, unlocked |

Every hard T0 finding is logged as a `validator_rejection` when a run is open (`log=True` default).

---

## 6. dims_resolve, tables_version, lock (`opus/dims.py`)

```python
def dims_resolve(spec: dict | str, wielder: str | dict | None = None, style: str | None = None,
                 seed: int | None = None, near=None) -> tuple[ResolvedSpec, list[Finding]]
def resolve_sheet(category: str, wielder=None, style="hd", seed=0) -> dict   # template dims only (the tool's category mode)
def lookup(ref: str) -> dict          # "oakeshott.types.XIV.blade_len" -> fact; dotted path from the table's top level
def wielder_sheet(w) -> dict[str, RDim]
def tables_version() -> str           # "t-" + sha256 over sorted (relpath, bytes with CRLF->LF) of data/tables/*.json and data/profiles/*.json, first 12 hex
def lock(spec: dict) -> dict          # writes spec["lock"] = {"tables_version", "dims": {name: value}, "profiles": {id: sha256}, "records": {ref: value}, "rev"}
```

Order: wielder → tables/records/profile params/users/ranges/design (each with `seeded_uniform(seed,
"dims/<name>")`) → expressions in dependency order (cycle → `parent_cycle`) → style_mult → T0 range
checks → camera (bible profile with distances; `RCamera`) → profiles inlined → parts copied with params
untouched. Units: mm, cm, in convert to m; `stature` units multiply by `wielder.stature`. A locked spec
uses the lock's values and reports `tables_version_drift` as soft. Conflicting sources for one dim
(a table and a record) are not allowed in one entry; tables store conflicts as [min, max].

---

## 7. Compiler (`opus.compile`)

```python
class KindNotAvailable(Exception): kind: str; sprint: str
KINDS = {"assembly": "S0b", "body.human": "S1", "body.creature": "S2", "garment": "S7", "harness": "S7",
         "terrain": "S9", "tree": "S9", "building": "S10", "kit": "S10", "layout": "S10",
         "motion": "S5", "face": "S10", "hair": "S10"}
POST_EVAL_KINDS = {"garment", "harness", "tree", "face", "hair"}
def evaluate(resolved: ResolvedSpec, level: str = "build", ppm: float | None = None) -> EvalMesh
def build_part(rpart: RPart, env: dict, anchors_in: dict, level: str, ppm: float) -> LocalPart
@dataclass
class LocalPart:                      # builder output, local frame
    verts: np.ndarray; tris: np.ndarray; uv: np.ndarray; edge_flags: np.ndarray; quad_mate: np.ndarray
    anchors: dict[str, Anchor]        # local frames
    measures: dict[str, float]
```

**Solver** (`solver.py`):
1. Expand the declared parts into a DAG: edges from attach/squeeze/reflect targets, `@` attributes and
   expression dependencies on other parts. Topological order; ties by declaration order.
2. For each part in order: evaluate params (env = dims + wielder + camera; `s` arrays inside the loft),
   build locally, then place: `attach` (face or point mating, §4.1), `squeeze` (length param set to
   |P₂ − P₁| along the self-anchor axis, frame from the two points and the parent's t), `orient` (root),
   none (identity at origin). Array copies are placed after their template. Reflect parts are generated
   after their source is placed (symmetry restored before attachment of their descendants).
3. Collect world anchors used by placements, sockets and joints; record per-part `deps`.
4. Origin: `bottom_center` translates everything so the bbox bottom centre is at the origin (skipped
   when a part attaches to `ground`); `socket:<name>` puts that socket at the origin. The translation
   is stored in `source["origin_offset"]`.
5. Assemble the EvalMesh: parts concatenated in solve order, `verts = fmath.apply(matrix, verts_local)`.

**UVs** (`uv.py`): analytic islands per builder in metres (box faces planar; lathe and loft (θ/2π ×
circumference, arc length); extrude caps planar, sides (perimeter, depth)), seam edges flagged, then one
deterministic shelf pack per asset into [0, 1] with uniform texel density and 2 px padding at 1024 px.
S2 replaces this with the surface plan.

**Edges:** builders flag profile corners, box edges and cap rims `EDGE_SHARP|EDGE_BEVEL`; station-loft
θ = 0 and π lines are the `cutting` set; `edges` in the spec rewrites flags per set.

---

## 8. Raster, views, preview (`opus.compile.raster`, `views`, `opus.preview`)

```python
def silhouette(m: EvalMesh, cam: RasterCamera, parts: list[str] | None = None) -> np.ndarray     # (H,W) bool
def id_depth(m: EvalMesh, cam: RasterCamera) -> tuple[np.ndarray, np.ndarray]                    # (H,W) int16 (-1 bg), float32 depth (inf bg)
def raster_reference(m, cam) -> tuple[np.ndarray, np.ndarray]                                    # edge-function, tests only
def view_camera(view: str | tuple[float, float], lo, hi, res: int | tuple[int, int], projection="ortho",
                camera: RCamera | None = None, margin: float = 1.1, jitter: bool = False) -> RasterCamera
def game_camera(m, rcam: RCamera, level: str = "typ", view="three_quarter") -> RasterCamera     # true game pixel size, cropped
def consistency_resolution(m: EvalMesh, view, min_part_px=10, cap=2048, multiple=128) -> int
```

- **Silhouette**: project, drop back faces of closed parts (keep a triangle when its outward normal faces
  the camera; with y down that is a negative x₁y₂ − x₂y₁ signed area) and edge-on ones, expand
  (triangle, row) pairs, intersect each row centre with the three edges, apply the tie rule, accumulate
  `+1/−1` at span ends with `np.bincount`, cumulative sum per row.
- **IDs and depth**: the same spans expanded to pixels, depth by perspective-correct barycentrics, nearest
  per pixel by `np.lexsort((depth, pixel))`; processed in chunks of ≤4M pixel pairs.
- Ortho framing: centre on the bbox centre, `ortho_h` = max projected extent × margin, aspect from the
  projected bbox; perspective framing: distance so the bbox fits the vfov.
- **Consistency resolution**: the smallest part's larger projected extent ≥10 px, capped at 2048, rounded
  up to a multiple of 128 (so the 128² depth grid lands on pixel centres, §9.6).

**Blueprint sheet** (`preview.blueprint(m, resolved, out) -> Path`, PIL, host only): front, side_px,
back and top orthographic views at one scale, filled silhouette plus part outlines in ID colours;
horizontal landmark lines (each part's top and bottom) across all views; 0.1 m / 1 m grid; callouts with
each part's as-built size in metres; a 1.8 m figure drawn from ANSUR p50 male fractions; a
three_quarter view (az 35°, el 22.5°); game-size insets at d_typ and d_far (true pixels, ×4 nearest
neighbour, labelled with pixel heights); a footer with id, rev, seed, `tables_version` and hash. Masks
per view are saved as ID PNGs. 2D lint: per feature, the part's eroded width and extent in game pixels
at d_typ/d_far → soft `feature_px_game` findings.

---

## 9. Gates (`opus.gates`)

### 9.1 Runner

```python
@dataclass
class GateContext:
    resolved: ResolvedSpec; spec: dict; mesh: EvalMesh; built: EvalMesh | None
    profile: dict                  # thresholds (§9.2)
    parts: set[str] | None         # local re-run scope; None = all
    evidence_dir: Path; camera: RCamera
def run_gates(ctx, tiers=("T0","T1","T2"), stop_at_first_hard=True) -> dict
# -> {"ok": bool, "stopped_at": tier|None, "hard_fail_count": int, "hard_magnitude": float,
#     "soft_score": float, "findings": [Finding.to_json()], "by_tier": {tier: {"n","hard_fail"}}}
```

`ok` = no blocking finding. Local checks honour `parts` (the patched part, its attach descendants and
its mirror partner); asset checks (floating, budget, global symmetry, readability, T2b) always run.

### 9.2 Gate profiles (bible `gates`, defaults in `gates/profiles.py`)

| Key | cad_clean | kitbash |
|---|---|---|
| `contact_m` (third person) / `contact_fp_m` (view-model camera) | 0.002 / 0.0005 | 0.004 / 0.001 |
| `overlap_m` (undeclared interpenetration depth) | 0.0005 | declared or any (warn only) |
| `sheet_rel` / `sheet_abs_m` | 0.02 / 0.001 | 0.05 / 0.002 |
| `anchor_m` | 1e-6 | 1e-6 |
| manifold | per part, strict | per part, strict |

Bible additions (WP-A, `opus.project.yaml` and `bible.DEFAULTS`): `gates: {profile_by_style: {hd:
cad_clean, stylized: cad_clean, lowpoly: cad_clean, pixel3d: cad_clean}, profiles: {...overrides}}`,
`3d.weapon_scale: 1.0`, `3d.gravity_mult: 1.0`, `3d.style_mult: {}`, `allow_nc: true`,
`rating_budget_min: 20`, `twist_policy: ""` (S1). Overrides in a spec's `gates` are logged in `history`.

### 9.3 Check catalogue (S0b)

| Check | Tier | Class | Family | Measures |
|---|---|---|---|---|
| T0 rules | T0 | §5.6 | §5.6 | |
| `anchor_error` | T1 | hard | contact | distance between the child and parent anchor points ≤ `anchor_m` |
| `sheet_as_built` | T1 | hard | sheet | each `PartInfo.measures` key re-measured on `verts_local` (extent, slice width at f, polygon circumference/π) within max(sheet_rel × value, sheet_abs_m) |
| `dim_measure` | T1 | hard | sheet | dims with `measure` (e.g. grip `circumference/pi`) within their `tol` |
| `relation_angle` | T1 | hard | — | coaxial / parallel / perpendicular within `tol_deg` |
| `symmetry_pair` | T1 | hard | naming | reflect pairs mirror within `anchor_m`; `_L` centroid x > +ε, `_R` x < −ε |
| `budget_tris` | T1 | hard | — | triangles within `gates.hard.tris` or the bible budget |
| `feature_px_game` | T1 | soft | — | §8 2D lint |
| `manifold` | T2 | hard | manifold | per part: 0 boundary edges, 0 edges with ≠2 faces, consistent orientation, 0 triangles with area < 1e-12 m², signed volume > 0 |
| `shells` | T2 | hard | floating | 1 connected shell per part |
| `contact_gap` | T2 | hard | contact | for each attach/squeeze pair and `contact` relation: distance ≤ `contact_m` |
| `floating` | T2 | hard | floating | the contact graph (parts and `ground`, edges at distance ≤ `contact_m`) is one component |
| `overlap` | T2 | hard (armed only after its suite) | overlap | undeclared pairs: max inside depth ≤ `overlap_m` |
| `grounded` | T2 | hard | contact | assets attached to `ground`: min z ∈ [−0.0005, 0.0005] |
| `com_over_footprint` | T2 | soft | — | volume centroid over the support hull (≥5% margin) |
| `naming_built` | T2 (built only) | hard | naming | Blender names = spec names (no `.001`), stamps present and valid, `SOCKET_<name>` empties present |
| `emit_hash` | T2b | hard | — | read-back hash of the unfinished mesh = evaluator hash |
| `consistency_iou`, `consistency_boundary`, `consistency_depth` | T2b | hard | — | §9.6 |
| `finish_delta_px` | T2b | report | — | per part, finished vs evaluator boundary at the game camera; >1 px marks the part `post_eval` |

### 9.4 T2 algorithms (`gates/geom.py`, numpy only)

- **Distance between parts**: samples = vertices ∪ triangle centroids ∪ edge midpoints (stride-subsampled
  to ≤4,000, deterministic); candidate triangles of the other part from a uniform grid hash (cell = max
  of 4 × tolerance and bbox diagonal / 64) expanded by the tolerance; exact closest points (Ericson 5.1.5,
  ported from the vectorized `closest_on_triangles` in `opus_bl/geom.py`, which imports bpy and so cannot
  be imported here); both directions; min.
- **Inside depth**: generalized winding number of part B at A's samples (solid angles, Van
  Oosterom–Strackee), inside when w > 0.5; depth = distance to B's surface; max over inside samples.
- **Edges and shells**: undirected edge keys `min*V + max` with `np.unique(return_counts)`, orientation
  by directed-edge pairing; shells by label propagation (as `opus_bl.geom._labels`).
- Budget: T2 on 50k triangles ≤2 s on the CI runner (`test_gates_perf`).

### 9.5 Defects (`gates/defects.py`)

| Family | Defect | Stated size → 2× | Expected check |
|---|---|---|---|
| contact | `offset_part`: move a non-root part along its attach normal away from its parent | 3 mm → 6 mm | `contact_gap` |
| floating | `detach_leaf`: move a leaf part away from every neighbour | 5 mm → 10 mm | `floating` |
| floating | `split_shell`: duplicate one part's shell displaced by 2× its size inside the same part | 1 shell → 2 | `shells` |
| manifold | `delete_face`, `flip_face`, `unweld_seam` (duplicate one seam vertex), `degenerate` (collapse a triangle) | 1 element → 2 | `manifold` |
| sheet | `scale_part` along its main axis without changing the spec | ×0.95 → ×0.90 (also ×0.85) | `sheet_as_built` |
| naming | `rename_default` ("Cube.001"), `drop_side`, `duplicate_name`, `swap_side` (L name on the −X part), `strip_stamp` | 1 → 2 violations | `name_*`, `symmetry_pair`, `naming_built` |
| overlap | `embed_part`: push a part into its neighbour along the attach normal | 3 mm → 6 mm | `overlap` |

```python
@dataclass(frozen=True)
class DefectSpec: family: str; kind: str; size: float; target: str | None = None
def inject(m: EvalMesh, spec_or_meta: dict, d: DefectSpec, rng: random.Random) -> tuple[EvalMesh, dict, dict]
    # -> (mesh', spec' (naming defects edit names/stamps), expected {"check","family","part"})
```

### 9.6 Consistency gate v1 (T2b)

Stage `emitted` (exit test): finish modifiers disabled for rendering. For each view the host builds the
`RasterCamera` (orthographic front, side_px, top at `consistency_resolution`; perspective three_quarter at
d_close with the spec camera's vfov), applies `JITTER_PX`, rasterizes `id_depth`, and asks Blender for an
ID mask (mask mode, `id_colors` from `opus_bl.readability`) and a 128×128 BVH depth grid at pixel
centres (i·k + k/2, j·k + k/2), k = W/128. Metrics: whole-object IoU ≥0.99; per part, symmetric boundary
distance p95 ≤0.5 px (boundary pixels of each mask, chunked brute-force nearest distances); depth: p95 of
|z_blender − z_eval| over rays hitting in both ≤ 1/ppm(d_close) m. Stage `finished` (every build): the
game camera at d_close at true size; per part, boundary change between the evaluator and the finished
mesh; >1 px → `finish_delta_px` report and `post_eval: true` on that part in the read-back.

Blender task `spec_consistency(blend, cameras: [RasterCamera dict], stage, out_dir)` →
`{"views": [{"camera": i, "id_png": path, "colors": {part: [r,g,b]}, "depth_npz": path}]}`; the npz holds
`depth` (float32, 128×128, inf for misses) and `hit` (bool).

### 9.7 defect_inject and gate_calibrate

```python
def defect_inject(gate: str = "all", fixtures: str = "ab6", seeds=range(8), sizes=(1, 2), n_per=None) -> dict
# per family: {"planted", "detected", "recall", "recall_2x", "clean_failures", "misses": [first 10], "ok"}
def write_armed(report: dict, path=data_dir()/"gates"/"armed.json") -> None
def gate_calibrate(check: str, clean: list, planted: list, thresholds: list[float] | None = None) -> dict
# -> {"check","n_clean","n_planted","recall","false_alarm_rate","threshold","table":[...],"promote": bool,"written": path}
```

Fixtures `ab6` = the six A/B specs × seeds 0–7 at levels fit and build (96 clean meshes) plus the WP0
fixtures. Each family plants ≥200 defects (random target parts and kinds, seeded). Pass: recall ≥95%
at the stated size, ≥99% at 2×, 0 clean failures. `armed.json`:
`{"<check>": {"armed": true, "family", "recall", "recall_2x", "clean_failures": 0, "n", "date", "commit"}}`,
written by a maintainer from a passing run and re-verified by CI. `gate_calibrate` sweeps a threshold
over clean and planted sets, reports recall and false alarms per threshold and writes
`data/gates/calibration/<check>.json` (corpus sources and licence IDs, never assets).

---

## 10. spec_edit (`opus/spec_edit.py`, `accept.py`, `optim.py`)

### 10.1 Input

```python
def spec_edit(path: str, patch: list[dict] | None = None, edit: str = "", why: str = "",
              keep: list[str] | None = None, mode: str = "single", dials: list[str] | None = None,
              tag: str = "", dry_run: bool = False, near=None) -> dict
```

- `patch`: RFC 6902 operations `replace`, `add`, `remove`, `test` on the spec.
- `edit` (seed-edit grammar, `;`-separated): `<dim> (=|*=|+=|-=) <number>`, `<dim>.style_mult = <n>`,
  `seed = <int>`. On a `table` dim, `*=` becomes `style_mult`; on `design` and `range` dims it sets
  `value` (clamped to the range, a clamp is reported); `user` dims refuse edits unless `by_user=true`;
  `expr` dims refuse edits (change their inputs).
- `why` is required. `keep`: relation indices to hold (default all). `tag="locked"` runs `lock()`.

### 10.2 Steps

1. Apply to a copy (rev+1, parent_rev = rev); run T0. A new hard T0 failure rejects.
2. Resolve and evaluate the candidate.
3. **Locality**: allowed = parts whose `deps` include a touched dim or part, their attach descendants
   and reflect partners. Every other part's `part_hash(root_frame=True)` must equal the incumbent's;
   otherwise reject with `edit_locality` naming the parts.
4. Re-gate: local checks on the allowed parts, asset checks always.
5. Label each finding by `key()`: improved, unchanged, regressed, new, resolved.
6. Accept by §10.3. Accepted: write the spec (history entry `{"rev","op","path","from","to","why"}` per
   change), keep `.opus/specs/<id>/rev_<n>.json`, update the archive. Rejected: the spec file is
   untouched; the candidate is saved as `rev_<n>.rejected.json`.
7. Log `spec_round` (§10.5).

Returns `{"accepted", "rule": "<step that decided>", "rev", "diff": [...], "locality": {"touched",
"allowed", "changed", "violations"}, "findings": [... with "label"], "archive": [...], "coupled": [...]}`.

### 10.3 Acceptance rule (`accept.py`)

```python
@dataclass(frozen=True)
class Score: hard_count: int; hard_mag: float; soft_score: float; new_hard: tuple[str, ...]
def score(findings: list[Finding], incumbent: list[Finding] | None) -> Score
def accept(cand: Score, inc: Score, eps: dict[str, float]) -> tuple[bool, str]
```

In order: (1) any armed hard check that passed in the incumbent fails now → reject; (2) fewer hard
failures → accept; (3) equal count: summed magnitude lower by more than ε (ε = Σ per-check noise_tol
normalized, at least 2% of the summed band) → accept; (4) hard tie: soft score (Σ weights × magnitude)
lower, with each regressed soft check inside its band → accept; (5) otherwise reject ("judge tie-break"
is S3). Archive: up to 4 revisions non-dominated over (hard_count, hard_mag, soft_score), JSON
`.opus/specs/<id>/archive.json` `[{"rev","score","hash"}]`.

### 10.4 Coupled findings and joint solve (`optim.py`)

Coupled = two failing findings whose fix paths share a dependency, or that traded places over the last
2 rounds. `mode="joint"` with ≤3 `dials` (design/range dims or style_mults): Nelder-Mead in numpy
(`nelder_mead(f, x0, lo, hi, max_evals=60, seed)`), objective f = 1e6·hard_count + 1e3·hard_mag +
soft_score using host T1/T2 only; the best point then goes through §10.2 as one edit.

### 10.5 Run ledger (`runs.py`)

New event `spec_round`: `{"n": int, "tier": str, "hard_fail_count": int, "findings": dict, "outcome":
str ("accepted"|"rejected"|"checked"|"built"), "rev": int}`. `spec_check`, `spec_edit` and `spec_build`
log it when a run is open. `iteration` stays manual (one per round of the task's hard checks), so the
v0.4 and S0b arms count iterations the same way. `run_stats` and `summarize` add `spec_rounds` and
`spec_rounds_to_hard_pass`; `compare` gains `--tasks a,b,c` and `--tiebreak tokens`.

---

## 11. Blender side (`opus_bl`)

### 11.1 Emit (`emit.py`, task `spec_emit`)

`run(npz, out_blend, finish: dict, exports: list[str], stage_hash: bool = True) -> dict`:
`read_factory_settings(use_empty=True)`; collection `opus:<id>`; root empty `<id>` with
`opus_spec`, `opus_rev`, `opus_hash`. Per part: mesh via `vertices.add` + `foreach_set("co", float32)`,
`loops`, `polygons.foreach_set("loop_start")` (a quad for each `quad_mate` pair (a,b,c)+(a,c,d) emitted
as [a,b,c,d], else a triangle), `update(calc_edges=True)`, `validate()` must return False; UV map
`UVMap` via `uv.uv.foreach_set("vector")`; attributes `sharp_edge`, `bevel_weight_edge` from
`edge_flags`; lowpoly → `sharp_face` all True, else `set_sharp_from_angle(angle=radians(30))` plus flagged edges.
Object name = part name, parent = root (keep transform), `matrix_world` = part matrix (joint parts:
origin on the joint axis). Stamps: `obj["opus_part"]`, `obj["opus_src"]`, `obj["opus_builder"]`,
`obj["opus_joint"]`, `obj["opus_matrix"]`; vertex-group stamps (S1+) go in `obj["opus_vgroups"]` (JSON) because vertex groups
have no ID properties (probed). Sockets: empties `SOCKET_<name>` parented to their part at the anchor
frame, `["opus_socket"]`. Materials: one per material id, named as the id, neutral grey. Read-back of
the unfinished mesh → `emit_hash`. Then `finish.apply`, save `.blend` (`compress=False`), write the
finished read-back `.npz`, run exports. Returns `{"blend", "emit_hash", "readback_npz", "exports": {...},
"warnings"}`.

### 11.2 Finish v1 (`finish.py`)

Per part, as modifiers (non-destructive in the .blend, applied at export):

| Order | Modifier | Settings |
|---|---|---|
| 1 | Bevel (skip for lowpoly) | `limit_method='WEIGHT'` (weights from `EDGE_BEVEL`, 0 on `cutting`), `width = camera.bevel_width(ppm(d_close), thickness = part min extent)`, `segments` 2 (hd) / 3 (first-person profile), `profile=0.5`, `use_clamp_overlap=True`, `harden_normals=True`, `face_strength_mode='FSTR_AFFECTED'`, `miter_outer='MITER_ARC'` |
| 2 | Weighted Normal | `mode='FACE_AREA'`, `weight=50` (= plain area weighting), `keep_sharp=True`, `use_face_influence=True` |
| 3 | Triangulate | `quad_method='BEAUTY'`, `ngon_method='BEAUTY'`, `min_vertices=4`, `keep_custom_normals=True` |

`boolean(obj, cutter, op)`: requires both operands manifold (bmesh check), runs MANIFOLD, verifies the
volume changed when the bboxes overlap and the result is manifold; otherwise EXACT; FLOAT never.
Unused by S0b specs (K10).

### 11.3 Read-back (`readback.py`, task `spec_readback`)

Evaluated meshes per object. Unfinished stage (finish modifiers disabled): polygons read back, quads
split along (0, 2), so `emit_hash` compares like with like. Finished stage: `loop_triangles` of the
triangulated result. local verts
(float32 → float64); matrices from the `obj["opus_matrix"]` stamp (the 16 floats emitted, because Blender
re-derives `matrix_world` from location, rotation and scale), with `matrix_world` required to match it
within 1e-6 (else `emit_hash` fails with the object named); corner UVs, `sharp_edge` → `EDGE_SHARP`; `extra` = object names,
stamps, socket empties. Output: an EvalMesh `.npz`.

### 11.4 Consistency (`consistency.py`, task `spec_consistency`)

Camera from the `RasterCamera` dict (§4.2), mask mode with `color_type="OBJECT"` and `id_colors(n)`,
`render_aa='OFF'`; BVH per object (`BVHTree.FromObject(obj, depsgraph)`), rays through the grid pixel
centres (persp: origin = camera, direction (x−W/2, −(y−H/2), −f) rotated; ortho: origins on the image
plane, direction −Z_cam), depth = view-space z. 128² rays take ~0.03 s per object set (probed).

### 11.5 Traps (`data/errors.json`, matched against tracebacks by `runner.py`, hint appended)

| Pattern | Hint |
|---|---|
| `BLENDER_EEVEE_NEXT` | 5.x id is `BLENDER_EEVEE` |
| `solver.*FAST` | Boolean solvers are FLOAT, EXACT, MANIFOLD |
| `MANIFOLD` + unchanged volume | MANIFOLD silently skips non-manifold operands; use `finish.boolean` |
| `face_strength_mode.*AFFECTED` / `miter_outer.*ARC` | `FSTR_AFFECTED` / `MITER_ARC` |
| `id properties not supported for this type` | VertexGroup: store on the object (`opus_vgroups`) |
| `file_format` enum error | set `image_settings.media_type` first |
| `Couldn't create directory for file` | `render.filepath` must be absolute |
| `outdated internal index table` | call `ensure_lookup_table()` |
| `fcurves.ensure` / `channelbag` | S1+: slotted actions (`action_ensure_channelbag_for_slot`) |

---

## 12. Export (`opus_bl/export.py`, `opus/export.py`)

### 12.1 Presets

| Engine | Format | Groups | Settings | Naming |
|---|---|---|---|---|
| `ue` | FBX | all parts joined into `SM_<id>`; each joint subtree its own `SM_<id>_<joint>` with origin on the axis; sockets re-parented to the joined mesh | `use_selection`, `object_types={'MESH','EMPTY'}`, `use_mesh_modifiers=True`, `mesh_smooth_type='FACE'`, `use_tspace=True`, `add_leaf_bones=False`, `use_custom_props=True`, `apply_unit_scale=True`, default axes | `UCX_SM_<id>_NN` (one convex hull per part, `bmesh.ops.convex_hull`), `SOCKET_<name>` empties |
| `godot` | glTF binary (.glb) | one scene, one node per group | `export_format='GLB'`, `export_yup=True`, `export_apply=True`, `export_extras=True` | hull nodes `<group>-convcolonly`, `SOCKET_<name>` → Node3D |
| `unity` | FBX | as ue | as ue + `apply_scale_options='FBX_SCALE_UNITS'` | unverified until S8 |

Sidecar `<id>.opus.json`: id, rev, hash, engine, units, `bbox_m`, `bbox_uu` (ue), tris, materials,
sockets `[{"name","part","pos_m","quat_wxyz","pos_engine","rot_engine"}]`, joints, licence flags union,
files.

### 12.2 Round trip

Re-import each exported file into factory settings and compare: object and socket names (exact),
socket positions ≤0.1 mm, per-group bbox ≤0.1 mm, triangle counts equal, sorted quantized vertex sets
equal within 1e-5 m (after the format's axis conversion back). Failures → hard `export_round_trip`.

### 12.3 Licence policy

Before writing, `ledger.check` on the asset's lineage (§13.3) under the bible's policy; blocked flags
stop the export with findings `licence_blocked`.

### 12.4 Engine-side files (MIT)

- `data/engine/ue_import.py.tmpl` → `<project>/Opus/ue/import_<id>.py`: MIT header; imports the FBX with
  `unreal.AssetImportTask` (`automated`, `replace_existing`, `save`, destination `/Game/Opus/<id>`) via
  `AssetToolsHelpers.get_asset_tools().import_asset_tasks`; then for each static mesh compares
  `get_bounding_box()` with `bbox_uu` (±1 uu), adds missing sockets from the sidecar
  (`unreal.StaticMeshSocket`, `add_socket`), adds a box collision with
  `StaticMeshEditorSubsystem.add_simple_collisions` when none imported, and writes
  `Saved/Opus/<id>_import_report.json` plus PASS/FAIL lines in the Output Log. The API names are checked
  by checklist item 4.1 on the PC; a failing name is reported and fixed there.
- `data/engine/CHECKLIST_ue.md.tmpl` → `<project>/Opus/ue/CHECKLIST_<id>.md` (≤5 minutes per asset).
- Godot: no script; the CI job (§16) imports the .glb with `godot --headless --path <proj> --import`,
  then `-s tests/godot/check_import.gd` prints node names, classes and AABBs; `ERROR: … leaked at exit`
  lines are ignored.

---

## 13. data_fetch (`opus/data_fetch.py`, `data/packs.yaml`)

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
    endpoints: {met: "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}",
                cma: "https://openaccess-api.clevelandart.org/api/artworks/{id}"}
    licence_id: CC0-1.0
    requires: {met: "isPublicDomain == true", cma: "share_license_status == CC0"}
    target: records
```

Packs in S0b: `ansur2`, `museum_records`, `cma_arms` (API query snapshots), `met_arms`, `wikidata_firearms`
(SPARQL snapshot), `wikipedia_facts` (raw wikitext by revision id), `albion_typology`, `ada_2010`,
`cma_profile_images` and `met_profile_images` (the exact image URLs of §14.2), `kenney_ci` (a pinned CC0
Kenney kit for the CI corpus, optional). `kind: manual` packs (itch.io) accept only `--from-file`.

### 13.2 Behaviour

```python
def data_fetch(pack: str = "", from_file: str = "", record: str = "", licence_page: str = "",
               list_packs: bool = False, library_dir: str = "") -> dict
# -> {"pack","dir","files":[{"path","sha256","size"}],"licence_id","flags","licence_json","status"}
```

- `library_dir` = `$OPUS_LIBRARY_DIR` (plugin `userConfig.library_dir`), else
  `%LOCALAPPDATA%/OpusTools/library` / `~/.local/share/opus-tools/library`. Layout
  `<library>/<pack>/<YYYYMMDD>/...`, `<library>/<pack>/LICENSE.json`, `<library>/index.json`.
- Downloads stream to `<file>.part` with HTTP `Range` resume, then sha256; a mismatch deletes the file and
  fails. Packs with `sha256: null` (api snapshots) record the observed hash.
- Archives unpack into a fresh empty directory with path-traversal and symlink rejection; nothing is
  executed; `np.load` uses `allow_pickle=False`; pickle formats are rejected; parsers of downloads run in
  `python -I`.
- `LICENSE.json`: `{"pack","licence_id","flags","licence_url","snapshot_text" (page text, ≤200 KB),
  "snapshot_sha256","retrieved","source_urls","attribution"}`.
- `--from-file <zip> --pack <id> [--licence-page <url|html>]`: copies, hashes, checks against the
  manifest when it lists a hash, snapshots the page (or the saved HTML) with the date.
- User-Agent `OpusTools/<version> (+https://github.com/Infamase/Opus-Tools)`; no personal data in headers.

### 13.3 Lineage

`spec_build` records the built asset with `ledger.record(asset, source="opus spec_build <id> rev <n>",
licence_id="LicenseRef-Own-Work", inputs=[{"source": "table:<name>@<version>", "licence_id", "role":
"dims"}, {"source": "profile:<id>", "licence_id", "role": "profile"}, {"source": "record:met:23367",
"licence_id": "CC0-1.0", "role": "dims"}], tools=[{"name": "opus-tools", "licence_id":
"GPL-3.0-or-later"}])`. Flags come from `licences.yaml`; export applies the policy (§12.3).

---

## 14. Data acquisition

### 14.1 Tables (all committed under `data/tables/`, built by `opus data build --tables` from the cache)

Every value is `{value, min, max, unit, src, tag}` (existing `tables.fact`). `measured` = the number is
stated in the source (unit conversion allowed); `derived` = computed from measured values by a stated
rule (percentiles, ratios, merged ranges); `recalled` = not verified against a primary source (warnings
only; a test asserts recalled facts never produce a hard finding).

| Table | Source and access | Licence ID | Content (paths as dims use them) |
|---|---|---|---|
| `anthro_ansur2` v2 | ANSUR II CSVs (pack `ansur2`, sha256 above) | `LicenseRef-US-Gov-Public-Release` (existing entry) | adds `poplitealheight`, `buttockpopliteallength`, `elbowrestheight`, `thumbtipreach` ratios and a `measures_mm` block per sex (absolute p5/p50/p95 in mm) for stature, hand length and breadth, popliteal height, buttock–popliteal length, elbow rest height, thumb-tip reach. `sexes.<sex>.measures_mm.<name>` |
| `oakeshott` | Albion "The Oakeshott Typology" (`https://albion-swords.com/articles/oakeshott-typology.htm`) + Wikipedia "Oakeshott typology" raw wikitext (`https://en.wikipedia.org/w/index.php?title=Oakeshott_typology&action=raw`, revision id stored) | `LicenseRef-Facts` (numbers only; no prose copied) | `types.<X..XXII>.{blade_len, grip_len, cross_len, fuller_frac}`; two sources disagreeing → value = midpoint, [min, max] spans both, tag derived |
| `museum_arms` | Cleveland API `GET /api/artworks/?type=Arms%20and%20Armor&q=<term>&cc0=1&limit=1000` (terms sword, axe, shield, buckler) (structured `dimensions`, m); Met `v1.1/search?q=<term>&departmentId=4` then `v1/objects/<id>` (structured `measurements`, cm/kg; `isPublicDomain` only); throttled 10 req/s; raw JSON cached as packs `cma_arms`, `met_arms` | `CC0-1.0` | `classes.<class>.<measure>` with robust p5/p50/p95 after median ± 3 MAD outlier removal and per-class sanity bounds; classes `sword_1350_1450`, `sword_1300_1500`, `axe_1000_1600`, `shield_round`, `shield_boss`; measures `overall_len, blade_len, blade_w, blade_t, quillon_w, grip_len, pommel_w, mass_kg, head_h, edge_len, diameter`; each fact's `src` lists `n` and the record ids. Fewer than 5 records → `min`/`max` = observed range, `value` = median, `src` says n |
| `firearms_wikidata` | Wikidata SPARQL, items reached by `(wdt:P31 or wdt:P279)/wdt:P279*` from `wd:Q12796` with `p:P2043/psn:P2043/wikibase:quantityAmount` (length), optional P2067 mass, P2048 height, P2049 width, all psn-normalized (the query text is stored) (592 items with length on 2026-10-21); class QIDs for pistol, rifle, carbine, shotgun resolved by label at build and stored in the table | `CC0-1.0` | `items.<qid>.{label, len, mass, height, width}` and `classes.<class>.{len, mass, height, width}` percentiles; query text and response sha256 in `source` |
| `ada_2010` | 2010 ADA Standards, `https://www.access-board.gov/ada/` | `LicenseRef-US-Gov-PD` | `work_surface_h` 902.3 (28–34 in), `door_clear_w_min` 404.2.3 (32 in), `reach_forward_high/low` 308.2, `riser_h` 504.2 (4–7 in), `tread_d_min` 504.2 (11 in), `handrail_h` 505.4 (34–38 in), `seat_h_toilet` 604.4; tag measured, src = section number |
| `weapon_facts` | Wikipedia raw wikitext "Dane axe", "Viking shield", "Longsword" (revision ids stored) | `LicenseRef-Facts` | `dane_axe.{haft_len, edge_len, mass_kg}`, `viking_shield.{diameter, board_t, boss_d}`, `longsword.{blade_len, grip_len}`; a figure the page does not state stays out (no recalled fill-ins) |

`LICENSES.md` gets one entry per table in the existing format (source, licence, derived, credit; CC0
and facts need no credit, US Gov tables keep their wording).

### 14.2 Profile library v0 (`data/profiles/<family>.json`)

| Family (kind) | Variants traced (all CC0 images; record gives the scale) | Scale reference |
|---|---|---|
| `blade.taper` (width_curve) | `cma:1921.1252` (sword c. 1400, blade 71.7 cm), `cma:1923.1121` (c. 1350), `cma:1921.1253` (hand-and-a-half c. 1500), `met:23367` (c. 1400, blade 81.3 cm) | blade length |
| `cross.straight` (outline) | `cma:1921.1252` (quillons 16.7 cm), `cma:1923.1121` (15.3 cm), `met:23367` (gr. width 23.5 cm) | cross length |
| `axe.head` (outline, anchor `eye_c`) | `cma:1916.1601` (battle axe, 1400s, blade 18.7 cm), `cma:1922.28` (blade 20.4 × 21.6 cm) | edge chord |
| `chair.turned_leg` (radius_curve) | `met:15292` front leg | leg length |
| `chair.arm` (outline) | `met:15292` arm, side view if the record has one, else dropped | arm length |

That is 11 planned variants in 5 families, 9 of them weapons (4 blades, 3 crosses, 2 axe heads); the
exit needs ≥6 weapon variants that pass review. The probed shield records (Cleveland 1916.1504,
1916.1615, boss 1916.1968) are face-on photos, which give only a circle, so the shield template uses
prims. WP-F searches Met public-domain shields and bosses (department 4) for a side view among
`additionalImages`; if one exists it traces `shield.boss` (radius_curve) and the template switches to it.

```json
{"profile": "blade.taper", "version": 1, "kind": "width_curve",
 "frame": {"u": "0 at the cross, 1 at the point", "v": "half-width / half-width at u=0"},
 "ref": "blade_len", "default": "cma:1921.1252",
 "variants": {"cma:1921.1252": {"segments": [{"type": "line", "p0": [0, 1], "p1": [0.71, 0.62]},
                                              {"type": "arc", "p0": [0.71, 0.62], "p1": [1, 0], "c": [0.42, -0.31]}],
                                "anchors": {}, "fit_rms": 0.004,
                                "specimen": {"id": "cma:1921.1252", "image": "https://openaccess-cdn.clevelandart.org/1921.1252/1921.1252_print.jpg",
                                             "image_sha256": "…", "known_dim": {"blade_len": 0.717}, "licence_id": "CC0-1.0",
                                             "traced": "2026-10-2x", "method": "opus.trace 1: bg model, threshold, contour, DP 0.5%, lsq line/arc"}}},
 "params": {"aspect": {"value": 0.065, "min": 0.055, "max": 0.08, "unit": "ratio", "src": "4 specimens, range", "tag": "derived"},
            "shoulder_u": {"value": 0.71, "min": 0.6, "max": 0.8, "unit": "ratio", "src": "4 specimens", "tag": "derived"}},
 "licence_id": "CC0-1.0", "tag": "measured"}
```

(Numbers in this example are placeholders for the format.) Segment types: `line` (p0, p1), `arc` (p0,
p1, centre c), `cubic` (p0, c0, c1, p1). Outlines are closed (last p1 = first p0), counter-clockwise;
holes are extra loops, clockwise. `params` carry min/max across specimens with `n` in `src` (fewer than 5
specimens cannot give p5–p95; the range is the observed one).

**Tracing (`opus.trace`, maintainer only):** `opus data build --profiles` reads `data/profiles/trace.yaml`
(per specimen: image pack and URL, crop box in pixels, which region is the blade/cross/head, known
dimension and its pixel endpoints), estimates the background as a quadratic surface fitted to the border
(CMA photos have grey gradients), thresholds |I − bg| > 4σ, keeps the largest component, fills holes,
aligns the principal axis, extracts the boundary (marching squares), simplifies with Douglas-Peucker
(ε = 0.5% of the reference length), fits lines and arcs by least squares (merge while rms < 0.3%),
normalizes by the known dimension and writes the variant plus a review PNG (overlay) to
`.opus/out/trace/`. A variant is committed only after the maintainer reviews the overlay; fit_rms is
stored. Pixel crop boxes are inputs to the tracer, not geometry.

### 14.3 When a source is unreachable

1. Table builds read only the local cache filled by `data_fetch`; CI never fetches.
2. A failed fetch keeps the committed table untouched (its `source.retrieved` date shows its age) and
   `opus data build` exits non-zero naming the source.
3. A maintainer with a manual copy uses `data_fetch --from-file … --pack …`; the sha256 and date are
   recorded.
4. Nothing is filled from memory. A value that cannot be fetched is left out; a template then uses a
   `design` range and says so in `doc`. Only an explicit `recalled` fact (with "recalled, unverified" in
   `src`) may stand in, and it only warns.
5. `record` dims need the record in the cache: `spec_validate` calls `data_fetch(record=…)` when it is
   missing; offline it reports `record_unavailable` (hard) unless the dim also has a `user` fallback.

---

## 15. MCP tools and CLI

All return JSON strings (plus an Image for previews), raise `ValueError` for bad input (shown to Claude),
resolve relative paths against the project, and log `spec_round` / `validator_rejection` when a run is
open.

| Tool (module) | Arguments | Returns |
|---|---|---|
| `spec_new` (spec) | `kind="assembly"`, `archetype` (sword, axe, round_shield, chest, barrel, chair, generic), `id`, `out=""`, `camera=""`, `style=""` | `{"path", "todo": ["/dims/blade_len: user or record", ...], "derived": camera numbers, "candidates": {dim: [table refs]}}` |
| `spec_validate` (spec) | `path`, `log=true` | `{"ok", "findings", "resolved": {dim: RDim}, "derived": {"px_per_m": {...}, "tiers": [{"part","size_m","px_close","px_far","tier"}]}, "tables_version"}` |
| `dims_resolve` (spec) | `spec_or_category`, `wielder=""`, `style=""`, `seed=-1` | `{"sheet": {dim: RDim}, "conflicts", "tables_version", "findings"}` |
| `spec_preview` (preview) | `path`, `views="front,side_px,back,top,three_quarter"`, `size=1024`, `seed=-1` | [Image, `{"sheet", "masks": {view: png}, "hash", "tris", "parts": [{"name","size_m","tris"}], "lint": findings}`] |
| `spec_build` (build) | `path`, `out=""`, `exports="blend,glb"` (+ `fbx_ue`), `finish=true`, `seed=-1` | `{"blend", "exports", "hash", "emit_hash", "match", "readback", "post_eval", "ledger", "seconds"}` |
| `spec_check` (check) | `path`, `built=""`, `tiers="T0-T2"` (`T2b` needs `built`), `profile=""`, `parts=""`, `all=false` | `run_gates` result + `{"round", "evidence"}` |
| `spec_edit` (edit) | `path`, `patch=""` (JSON), `edit=""`, `why`, `keep=""`, `mode="single"`, `dials=""`, `tag=""`, `dry_run=false` | §10.2 |
| `defect_inject` (check) | `gate="all"`, `fixtures="ab6"`, `seeds=8`, `write_armed=false` | §9.7 |
| `gate_calibrate` (check) | `check`, `corpus` (folder or fixture set), `planted=true` | §9.7 |
| `data_fetch` (data) | `pack=""`, `from_file=""`, `record=""`, `licence_page=""`, `list=false` | §13.2 |
| `export_asset` (build) | `path` (spec or .blend), `engine` (ue, godot or unity), `out_dir=""`, `collision=true`, `round_trip=true` | `{"files", "sidecar", "round_trip": {"ok","findings"}, "licence": {"ok","blocked"}, "engine_script", "checklist"}` |

CLI (same functions): `opus spec new|validate|preview|build|check|edit`, `opus dims`,
`opus data fetch|build|list`, `opus gates inject|calibrate`, `opus export`. `spec build --hash-check`
also runs `spec_eval_hash` in Blender and prints the three hashes and the tie rule seen.

---

## 16. CI, extras, doctor (WP-H)

`.github/workflows/ci.yml` (on push and pull_request):

| Job | Runner | Steps |
|---|---|---|
| `host` | matrix ubuntu-24.04, windows-2022 | `astral-sh/setup-uv` (pinned), `uv sync --frozen`, `ruff check`, `pytest -m "not blender and not network"` (includes import rules, licences, schema-current check) |
| `blender` | ubuntu-24.04 | cache `blender-5.2.2-linux-x64.tar.xz` (key = version; verify sha256 `84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168` from `blender-5.2.2.sha256`); `apt-get install libegl1 libegl-mesa0 libgl1 libgl1-mesa-dri libxi6 libxkbcommon0 libsm6`; `OPUS_BLENDER=…`; `pytest -m "blender or perf"`; `opus gates inject all --check-armed`; upload the A/B fixture .glb files and blueprint PNGs (generated, never fetched assets) |
| `godot` | ubuntu-24.04, needs `blender` | download `Godot_v4.7-stable_linux.x86_64.zip` (sha256 pinned: `0b1a6c54c2c619c12e169fe9241edda4b81080b519451cec2984bf0d2c6cb73c`), import the artifact .glb files headless, run `check_import.gd`, compare node names and AABBs with the sidecars |
| `licences` | ubuntu-24.04 | every file in `data/tables/` and `data/profiles/` has a LICENSES entry; every `ported-from` header has a THIRD_PARTY_NOTICES entry |

Workbench only, CPU only (llvmpipe); EEVEE and Cycles checks stay on the PC. `opus doctor` adds:
Blender ≥5.2 and its numpy version, Godot path and version, each extra (installed, imports, version),
library_dir and per-pack status and size, and the fill rule from a 16×16 render (cached per GPU).

`docs/PC_CHECKS_S0B.md` (≤10 minutes): 1. update to 0.5.0 and run the doctor; 2. `opus spec build
--hash-check` on the six Appendix A specs (three hashes equal; note the tie rule the NVIDIA GPU shows);
3. open the Godot 4.7 project holding the axe, shield and barrel .glb files (nodes, sizes, `SOCKET_`
nodes); 4. Unreal: 4.1 run `import_<id>.py` for sword, chest and chair (PASS lines; any API-name error
is reported), 4.2 the sword's length in uu and its `grip_main` socket, 4.3 the chest lid turns about its
back edge; 5. paste the report block.

---

## 17. Work packages

Merge order after WP0: A, B, C, D, F, G, E, H (each rebases on the previous merges; contract files never
conflict). Every package keeps `pytest -m "not blender"` green on its own and adds Blender tests behind
the `blender` marker.

### WP0 — Contracts (integrator, before fan-out)
- **Owns:** §4 files, `pyproject.toml`, `uv.lock`, `opus/__init__.py` version, hooks in `mcp_server.py`,
  `cli.py`, `entry.py`, `tests/fixtures/s0b/`, `tests/test_contracts.py`, `data/schema/finding.schema.json`,
  `data/schema/opus.resolved.1.schema.json`.
- **Exit:** `eval_hash(fixture_boxes())` stable across two processes; `save_npz`/`load_npz` round trip
  equal; `Finding` JSON validates against its schema; `expr` accepts §4.4 and rejects attribute access
  outside the whitelist, lambdas, subscripts, comparisons; `project` reproduces the §2 probe masks;
  stub tools register; existing tests green.

### WP-A — Spec language, dims, templates, bible
- **Owns:** `spec/{__init__,model,schema,validate,templates}.py`, `dims.py`, `bible.py`,
  `data/templates/*.spec.json`, `data/schema/opus.asset.1.schema.json`, `tools/spec.py`, tests
  `test_spec_model.py`, `test_spec_validate.py`, `test_dims.py`, `test_templates.py`, `test_bible_s0b.py`.
- **Consumes:** contracts; fake tables in `tests/fixtures/s0b/tables/` (same shapes as §14.1); cached
  record JSON fixtures for met:23367, met:15292.
- **Tests:** one failing fixture per §5.6 rule (≥25) and the six Appendix A specs passing; per-dim seeding
  (adding a dim leaves others bit-identical); `tables_version` equal for LF and CRLF copies; lock round
  trip; templates leave every `user` and `record` dim as a todo, and a test fails if a number from an
  eval brief (a list in the test) appears in a template outside a reviewed allowlist; `opus.asset.1.schema.json` regenerates identically.
- **Exit evidence:** the six specs validate with only soft findings; resolved outputs validate against
  `opus.resolved.1.schema.json`.

### WP-B — Compiler core
- **Owns:** `compile/{evaluate,solver,profiles,triangulate,uv}.py`, `compile/builders/*`,
  `opus_bl/compile_eval.py`, tests `test_builders.py`, `test_solver.py`, `test_evaluate.py`,
  `test_determinism.py`.
- **Consumes:** contracts, `tests/fixtures/s0b/resolved_*.json`, fixture profiles.
- **Tests:** each builder over 200 random parameter sets in range: closed, outward, no degenerate
  triangles, `measures` exact within 1e-9 relative; anchors match analytic positions; face and point
  mating, spin, squeeze, reflect (mirror exact), radial and linear arrays; `@radius` and `@profile`
  contact exactly; level fit vs build differ only in tessellation; host/Blender hash equality on fixtures.
- **Exit evidence:** the 6 resolved A/B specs (after WP-A) evaluate with 0 `anchor_error`; hash equal
  host ↔ Blender for 6 specs × 3 seeds.

### WP-C — Raster, preview, consistency metrics
- **Owns:** `compile/{raster,views}.py`, `preview.py`, `gates/consistency.py`, `tools/preview.py`,
  `tests/blender_scripts/raster_probe.py`, tests `test_raster.py`, `test_preview.py`, `test_perf.py`,
  `test_consistency.py`.
- **Consumes:** contracts, `fixture_boxes()`, a fake `spec_consistency` result fixture until WP-E lands.
- **Tests:** single-triangle and tie cases against Blender (own probe script, like
  `proj_bl.py`); spans == edge-function reference on 1,000 random meshes; synthetic masks with known
  shifts give the expected boundary p95; throughput ≥200/min (assert) and logged.
- **Exit evidence:** consistency metrics on the 6 specs × 4 views pass once WP-E's task exists.

### WP-D — Gates, defects, calibration
- **Owns:** `gates/{runner,t0,t1,t2,geom,profiles,defects,inject,calibrate}.py`, `data/gates/`,
  `tools/check.py`, tests `test_gates_t0.py`, `test_gates_t1.py`, `test_gates_t2.py`, `test_defects.py`,
  `test_calibrate.py`, `test_gates_perf.py`.
- **Consumes:** contracts, EvalMesh fixtures, WP-A's `validate` behind an injectable callable;
  `raster.id_depth` (WP-C) for `feature_px_game`, which reports `not_available` until WP-C is merged.
- **Tests:** each check on hand-built pass/fail cases; each defect kind detected on fixtures; 0 failures on
  clean fixtures; T2 ≤2 s on a 50k-triangle mesh; `armed()` gating (`blocking()` false for unarmed).
- **Exit evidence:** `defect_inject all --fixtures ab6` report meeting §9.7 for contact, floating,
  manifold, sheet, naming (and overlap if it passes), committed `armed.json`.

### WP-E — Blender emit, finish, read-back, consistency task, export
- **Owns:** `opus_bl/{emit,finish,readback,consistency,export}.py`, `opus/{build,export}.py`,
  `opus/blender/runner.py`, `data/engine/*`, `data/errors.json`, `tools/build.py`, tests
  `test_emit.py`, `test_finish.py`, `test_export.py`, `test_build.py`.
- **Consumes:** contracts, `evalmesh_box3.npz`, `RasterCamera`, `evaluate` (after WP-B; before that the
  fixture npz).
- **Tests:** `emit_hash` = evaluator hash; finish modifiers present with §11.2 settings; MANIFOLD no-op
  detected and EXACT used; FBX and glTF round trips; joint subtree origin on the axis; sockets and stamps
  survive both formats; consistency task output format; errors.json hints attach to a raised traceback.
- **Exit evidence:** the 6 A/B specs build to .blend + .glb (+ FBX for the ue specs) with round trips
  passing; Godot CI job green; UE script and checklist rendered for sword, chest and chair.

### WP-F — Data: fetch, tables, profiles
- **Owns:** `data_fetch.py`, `trace.py`, `tables.py`, `data/packs.yaml`, `data/tables/*.json`,
  `data/profiles/*`, `data/LICENSES.md`, `DOWNLOADS.md`, `tools/data.py`, tests `test_data_fetch.py` (local
  HTTP server: resume, sha mismatch, zip-slip, from-file, licence snapshot), `test_tables_s0b.py`,
  `test_profiles.py`, `test_licences.py` additions.
- **Consumes:** nothing but the §14 formats.
- **Exit evidence:** six tables built and committed with LICENSES entries; ≥6 reviewed weapon profile
  variants committed (review PNGs attached to the PR, not committed); fake tables in WP0 fixtures match
  the real shapes (test).

### WP-G — spec_edit, acceptance, archive, joint solve, ledger
- **Owns:** `spec_edit.py`, `accept.py`, `optim.py`, `runs.py`, `tools/edit.py`, tests
  `test_spec_edit.py`, `test_accept.py`, `test_optim.py`, `test_runs.py` additions.
- **Consumes:** contracts; stubs for resolve, evaluate and gates (fixture functions in tests) until
  A/B/D land.
- **Tests:** patch and seed-edit grammar; each acceptance step decides a crafted case; archive keeps ≤4
  non-dominated; locality rejects a planted non-local change; Nelder-Mead solves a 2-dial coupled toy;
  `spec_round` logging and the new run_stats/compare fields; the random-dial-edit exit test (skipped until
  B and D are merged).
- **Exit evidence:** `test_random_dial_edits` green on chest and chair after integration.

### WP-H — CI, doctor, docs, A/B kit
- **Owns:** `.github/workflows/ci.yml`, `doctor.py`, `skills/3d-modeling/SKILL.md`, `README.md`,
  `docs/PC_CHECKS_S0B.md`, `evals/README.md`, `python/tests/godot/check_import.gd`, the A/B workflow
  script (outside the repo, §19).
- **Exit evidence:** a green CI run on the integration branch; doctor output on Linux; the skill's
  compiler section reviewed; PC checklist ≤10 minutes as written.

---

## 18. Risks specific to S0b

| Risk | Design answer |
|---|---|
| Evaluator and Blender drift | Pinned conventions (§4.2) with a probe-derived test; emission by `foreach_set` of the same arrays; `emit_hash`; T2b at high resolution and at the game camera; finishing >1 px marks `post_eval` |
| Determinism across numpy versions and platforms | No BLAS (matmul differed, probed); math via `fmath`; float32-cast quantized hash; per-dim seeded Python RNG; PC run of the hash test on Windows |
| GPU tie rule differs from llvmpipe | Jitter in T2b; tie test records the rule per machine; metrics tolerate 1 px |
| MANIFOLD silent no-op | Verified boolean helper; no booleans in S0b specs |
| Weighted Normal weight meaning, Bevel enum names, Triangulate custom normals | Probed names in §11.2; errors.json hints |
| `BLENDER_EEVEE`, `media_type`, channelbags, relative render paths | errors.json; S0b uses Workbench only |
| VertexGroup has no ID properties | Object-level `opus_vgroups` map (S1+) |
| Windows paths | `pathlib` only; list-form subprocess; temp files closed before Blender; CRLF normalized in hashes; short output names; CI host tests on windows-2022 |
| pydantic missing in Blender | K1/K2 import rules with a blocking test |
| Spec authoring friction | Templates ~90% complete with `todo` pointers and candidate refs; validator messages carry a `fix.suggest`; rejections and tokens measured in the A/B |
| Data gaps (pommel width, board thickness, chest proportions) | `design` ranges with `doc`; `recalled` only warns; gaps visible in `spec_validate` |
| Tracing errors from gradient backgrounds, scabbards, perspective | Background surface model, crop boxes, overlay review, fit_rms stored, ≥2 specimens per family |
| Templates overfit to the A/B briefs | K14 test |
| A/B noise, floor effects and colour confounds | K15 (3 runs, tie-break), grader-confirmed counts, clay pairs (K11) |
| UE Interchange drops `SOCKET_`/`UCX_` | Import script re-creates them from the sidecar; checklist |
| Merge conflicts between packages | File ownership (§17), WP0 hooks, contract freeze |
| T2 cost on large meshes | Grid-hash pruning, sample caps, perf test |
| Godot import noise | Ignore exit-leak lines; compare node names and AABBs |

**If the A/B fails** (fewer iterations on <5 of 6, or the user prefers v0.4 in ≥2 pairs): the compiler
stays as a **validator and blueprint tool over v0.4's socketed shape kit**. Kept: spec language, dims,
tables, profiles, `spec_validate`, `spec_preview`, `spec_check` on any .blend through read-back (parts
bound to objects by name; sheet checks against the spec), gates and `defect_inject`, `data_fetch`,
`export_asset`. `spec_build` stays available but is no longer the default path; S4 is re-planned around
kit parts with sockets plus the validator.

---

## 19. A/B protocol (exit)

1. **Freeze.** After integration and green CI, tag `v0.5.0-s0b` and copy the tree to
   `/tmp/claude-0/-home-user-Opus-Tools/091283a1-d296-519e-a85a-af7a607de9ae/scratchpad/s0b` (as `v04` was).
   The v0.4 baseline copy and its eval folder stay untouched.
2. **Arms.** v0.4 = the baseline runs (label `v0.4`); add 2 runs per prop from the frozen v0.4 copy so
   each of sword, axe, round_shield, chest, barrel, chair has 3. S0b = label `s0b`, 3 runs per prop,
   eval project `<scratch>/evals/s0b` with the same `opus.project.yaml`.
3. **Harness.** The baseline workflow script (`evalkit/baseline.js`) with V = the S0b copy, LABEL `s0b`,
   and ENV extended with the CLI names `spec new|validate|preview|build|check|edit`, `dims`, `export`,
   `data fetch`, `gates inject|calibrate`, and the S0b skill file. Same model (`claude-opus-5-5`), same
   prompt (`opus eval prompt <id>`, unchanged task specs), same caps (10 check rounds, 2 judge rounds
   without a pass, 90 minutes), same rule that sessions treat the plugin as installed software, same
   `evals/judge.py` for blind reads and checklists, same independent grader re-running every hard check
   with the v0.4 tool semantics. S0b sessions may still use v0.4 tools.
4. **Measures.** Primary: per task, the median grader-confirmed `iterations_to_hard_pass` (a run the
   grader does not accept counts as never passing = worst). Win = strictly lower median. Tie with both
   medians at 1 → lower median tokens wins (pre-registered). Criterion: ≥5 wins of 6. Reported:
   `spec_rounds`, validator rejections, tokens, wall-clock, failure histograms
   (`opus eval compare v0.4 s0b --tasks sword,axe,round_shield,chest,barrel,chair --tiebreak tokens`).
5. **Blind pairs for the user.** Per prop, each arm's representative asset = its accepted run with the
   median iteration count (earliest on ties; if none accepted, the abandoned run with the fewest hard
   failures). Two sheets per prop with `ab_sheet(a, b, render_pass="clay", view="three_quarter")`: one
   large (`height_px=0`) and one at game size (`height_px` from `critique.game_height_px` at d_typ),
   sides randomized by seed; keys go to a sealed JSON the user never sees. The user answers A, B or
   "same" for the 6 props in one sitting (≤20 minutes). Criterion: v0.4 preferred in ≤1 of 6 ("same" is
   not a preference).
6. **Claude judge (report only).** `judge.py letter` on both orders of each pair; agreement with the user
   is recorded for S3's calibration.
7. **Decision.** Pass → S1 starts and S4 keeps the compiler plan. Fail → §18 fallback, recorded in
   OVERHAUL's review log with the numbers.

---

## Appendix A. The six A/B specs as S0b would write them

`tables_version` and `seed` are filled by `spec_new`. Every literal outside `dims` is structural
(rev, seed, spin, ranks, budgets). Values come from the brief (`user`), the Met/Cleveland records
(`record`), tables, profiles, wielder formulas, or `design` ranges.

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
  "oal": {"record": "met:23367", "measure": "Length overall"},
  "blade_len": {"record": "met:23367", "measure": "Length of blade"},
  "blade_w_base": {"record": "met:23367", "measure": "Gr. width of blade", "sanity": "museum_arms.classes.sword_1350_1450.blade_w"},
  "blade_t_base": {"record": "met:23367", "measure": "Thickness of blade"},
  "blade_t_tip": {"range": [0.0020, 0.0022], "src": "replica distal taper, Albion spec sheets"},
  "blade_n": {"design": [1.3, 1.8], "unit": "ratio", "doc": "section exponent: 1 diamond, 2 oval"},
  "cross_len": {"record": "met:23367", "measure": "Gr. width"},
  "cross_aspect": {"profile": "lib:cross.straight#met:23367", "param": "aspect"},
  "cross_h": {"expr": "cross_len*cross_aspect"},
  "cross_t": {"design": [0.010, 0.016], "doc": "not stated by any source"},
  "pommel_d": {"table": "museum_arms.classes.sword_1350_1450.pommel_w"},
  "pommel_t": {"design": [0.45, 0.7], "unit": "ratio", "doc": "thickness / pommel_d"},
  "grip_len": {"expr": "oal - blade_len - cross_h - pommel_d", "sanity": "oakeshott.types.XIV.grip_len"},
  "grip_d_eq": {"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005 (NIOSH): optimal handle diameter 19.7% of hand length",
                   "tol": 0.10, "measure": "circumference/pi"},
  "grip_aspect": {"design": [1.15, 1.35], "unit": "ratio"}},
 "parts": [
  {"name": "grip_C", "build": {"station_loft": {"len": "grip_len", "a": "grip_d_eq*grip_aspect/(1+grip_aspect)",
                                                 "b": "grip_d_eq/(1+grip_aspect)", "n": "round"}}},
  {"name": "cross_C", "build": {"extrude": {"profile": "lib:cross.straight#met:23367", "plane": "XZ",
                                            "len": "cross_len", "h": "cross_h", "depth": "cross_t"}},
   "attach": {"to": "grip_C", "at": "top_c", "self": "bottom_c"}},
  {"name": "blade_C", "build": {"station_loft": {"len": "blade_len", "width_profile": "lib:blade.taper#met:23367",
                                                 "w": "blade_w_base", "t": "lerp(blade_t_base, blade_t_tip, s)", "n": "blade_n"}},
   "attach": {"to": "cross_C", "at": "top_c", "self": "bottom_c"}, "edges": {"cutting": "sharp"}},
  {"name": "pommel_C", "build": {"lathe": {"profile": "prim:disc", "r": "0.5*pommel_d", "t": "pommel_t*pommel_d"}},
   "attach": {"to": "grip_C", "at": "bottom_c", "self": "rim_+x", "spin": 1}}],
 "relations": [{"type": "coaxial", "a": "grip_C", "b": "blade_C", "tol_deg": 0.5},
               {"type": "perpendicular", "a": "cross_C.x", "b": "blade_C", "tol_deg": 1}],
 "sockets": {"grip_main": "grip_C:uvw:8,8,10", "tip": "blade_C:top_c"},
 "materials": {"blade_C": "phys:steel", "cross_C": "phys:steel", "pommel_C": "phys:steel", "grip_C": "phys:leather"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [1500, 4000]}},
 "surface": {"uv": "analytic"}, "history": []}
```

`grip_len` makes the overall length the record's 1.022 m by construction; the Oakeshott XIV grip is a
sanity band. `spin: 1` turns the wheel's axis from +X to +Y so its face shows in the front view.

### A.2 Bearded axe (lowpoly, Godot)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "axe_bearded", "rev": 1, "parent_rev": null,
 "category": "weapon/axe", "style": "lowpoly", "camera": "godot_tp", "units": "m", "up": "+Z", "front": "-Y",
 "template": "axe", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "bearded_head", "parts": ["head_C"], "views": ["side_px", "game"], "min_px": 8},
  {"rank": 2, "id": "long_haft", "parts": ["haft_C"], "views": ["front", "game"], "min_px": 4}],
 "dims": {
  "haft_len": {"user": 0.9}, "edge_len": {"user": 0.20, "sanity": "weapon_facts.dane_axe.edge_len"},
  "head_t": {"design": [0.018, 0.03], "doc": "head thickness at the eye; no source"},
  "head_s": {"design": [0.88, 0.94], "unit": "ratio", "doc": "eye centre along the haft"},
  "haft_d_eq": {"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005 (NIOSH)", "tol": 0.10, "measure": "circumference/pi"},
  "haft_aspect": {"design": [1.15, 1.4], "unit": "ratio"}, "segs": {"design": [6, 8], "unit": "count", "int": true}},
 "parts": [
  {"name": "haft_C", "build": {"station_loft": {"len": "haft_len", "a": "haft_d_eq*haft_aspect/(1+haft_aspect)",
                                                "b": "haft_d_eq/(1+haft_aspect)", "n": "round", "segments": "segs"}}},
  {"name": "head_C", "build": {"extrude": {"profile": "lib:axe.head#cma:1916.1601", "plane": "YZ",
                                           "len": "edge_len", "depth": "head_t"}},
   "attach": {"to": "haft_C", "at": "ring@head_s", "self": "eye_c", "mode": "point"}}],
 "relations": [{"type": "embedded", "a": "haft_C", "b": "head_C"}],
 "sockets": {"grip_main": "haft_C:uvw:8,8,3"},
 "materials": {"haft_C": "phys:wood", "head_C": "phys:iron"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [100, 600]}}, "surface": {"uv": "analytic"}, "history": []}
```

The beard comes from the traced head outline; if the review finds `cma:1916.1601` not bearded enough,
`spec_edit` switches the variant (`/parts/1/build/extrude/profile`) rather than drawing one.

### A.3 Round shield (lowpoly, Godot)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "shield_round", "rev": 1, "parent_rev": null,
 "category": "weapon/shield", "style": "lowpoly", "camera": "godot_tp", "units": "m", "up": "+Z", "front": "-Y",
 "template": "round_shield", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "round_board", "parts": ["board_C"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "boss", "parts": ["boss_C"], "views": ["front", "side_px"], "min_px": 4},
  {"rank": 3, "id": "rim", "parts": ["rim_C"], "views": ["front"], "min_px": 1}],
 "dims": {
  "diameter": {"user": 0.8, "sanity": "weapon_facts.viking_shield.diameter"},
  "board_t": {"table": "weapon_facts.viking_shield.board_t"},
  "boss_d": {"table": "museum_arms.classes.shield_boss.diameter"},
  "boss_h_frac": {"design": [0.35, 0.5], "unit": "ratio"}, "boss_wall": {"design": [0.002, 0.004]},
  "boss_flange_w": {"design": [0.015, 0.03]}, "hole_d": {"expr": "boss_d - 2*boss_flange_w"},
  "rim_t": {"design": [0.003, 0.006]}, "grip_overlap": {"design": [0.03, 0.06]},
  "grip_len": {"expr": "hole_d + 2*grip_overlap"},
  "grip_d_eq": {"expr": "0.197*wielder.hand_length", "src": "Kong & Lowe 2005 (NIOSH)", "tol": 0.10, "measure": "circumference/pi"},
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
 "sockets": {"grip_main": "grip_C:uvw:8,8,8"},
 "materials": {"board_C": "phys:wood", "boss_C": "phys:iron", "rim_C": "phys:iron", "grip_C": "phys:wood"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [150, 800]}}, "surface": {"uv": "analytic"}, "history": []}
```

The board is an annulus, so the hand passes through the hole into the boss's hollow and grips the bar
spanning it: the checklist's "grip behind the boss, inside its hollow" holds by construction, with no
boolean. If `board_t` or `boss_d` has no stated source, the template carries them as
`design` ranges instead.

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
  "band_pos": {"design": [0.15, 0.3], "unit": "ratio", "doc": "band centre from the -X end"},
  "band_pos_l": {"expr": "1 - band_pos"},
  "bracket_leg": {"design": [0.04, 0.07]}, "bracket_frac": {"design": [0.5, 0.8], "unit": "ratio"},
  "hasp_w": {"design": [0.04, 0.06]}, "hasp_h": {"design": [0.08, 0.12]},
  "lock_w": {"design": [0.05, 0.08]}, "lock_h": {"design": [0.06, 0.09]}, "lock_d": {"design": [0.015, 0.025]},
  "hinge_d": {"design": [0.015, 0.025]}, "hinge_len": {"design": [0.06, 0.1]},
  "lid_open_max": {"design": [95, 110], "unit": "deg"}},
 "parts": [
  {"name": "body_C", "build": {"box": {"sx": "width", "sy": "depth", "sz": "height*(1 - lid_frac)"}},
   "attach": {"to": "ground", "at": "top_c", "self": "bottom_c"}},
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
   "attach": {"to": "body_C", "at": "uvw:9,16,16", "self": "ring@8/16", "mode": "point"}},
  {"name": "hinge_R", "reflect": {"of": "hinge_L", "plane": "yz"}}],
 "relations": [{"type": "embedded", "a": "hinge_L", "b": "body_C"}, {"type": "embedded", "a": "hinge_L", "b": "lid_C"}],
 "joints": {"lid": {"part": "lid_C", "type": "revolute", "anchor": "body_C:top_back", "axis": "t", "limits": [0, "lid_open_max"]}},
 "sockets": {"lock": "lock_C:front_c"},
 "materials": {"body_C": "phys:wood_oak", "lid_C": "phys:wood_oak", "band_body_L": "phys:iron", "band_lid_L": "phys:iron",
               "bracket_front_L": "phys:iron", "hasp_C": "phys:iron", "lock_C": "phys:iron", "hinge_L": "phys:iron"},
 "gates": {"profile": "cad_clean", "hard": {"tris": [500, 6000]}}, "surface": {"uv": "analytic"}, "history": []}
```

Reflected parts inherit materials. The lid's joint moves `lid_C`, its bands, the hasp and the lock; they
export as `SM_chest_banded_lid` with its origin on the back top edge (the eval's hinge probe reads 0 mm).
The bands' arms meet at the body/lid seam (contact 0) and the lid bands wrap over the lid's top.

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
their inner faces follow the facets exactly (contact by construction).

### A.6 Joined armchair (hd, Unreal; 11 parts)

```json
{"spec": "opus.asset/1", "kind": "assembly", "id": "chair_joined", "rev": 1, "parent_rev": null,
 "category": "prop/furniture/chair", "style": "hd", "camera": "ue_tp_1080", "units": "m", "up": "+Z", "front": "-Y",
 "template": "chair", "tables_version": "t-000000000000", "seed": 0, "wielder": "ansur2:male:p50", "origin": "bottom_center",
 "features": [
  {"rank": 1, "id": "panelled_back", "parts": ["back_panel_C", "post_back_L"], "views": ["front", "game"], "min_px": 13},
  {"rank": 2, "id": "turned_front_legs", "parts": ["leg_front_L"], "views": ["front", "side_px"], "min_px": 4},
  {"rank": 3, "id": "arms", "parts": ["arm_L"], "views": ["side_px", "three_quarter"], "min_px": 4}],
 "dims": {
  "height": {"record": "met:15292", "measure": "Overall.Height"},
  "width": {"record": "met:15292", "measure": "Overall.Width"},
  "depth": {"record": "met:15292", "measure": "Overall.Depth"},
  "seat_h": {"expr": "wielder.popliteal_height + 0.025", "src": "OVERHAUL 4.7: popliteal p50 + 25 mm shoe allowance",
             "sanity": "0.42..0.48"},
  "arm_h": {"expr": "seat_h + wielder.elbow_rest_height", "src": "ANSUR II elbow rest height (sitting)"},
  "seat_t": {"design": [0.025, 0.035]}, "leg_d": {"design": [0.04, 0.055]}, "post_w": {"design": [0.04, 0.055]},
  "arm_w": {"design": [0.04, 0.06]}, "arm_t": {"design": [0.025, 0.035]}, "panel_t": {"design": [0.012, 0.02]},
  "str_h": {"design": [0.08, 0.15], "doc": "stretcher height above the floor"}, "str_w": {"design": [0.025, 0.035]},
  "leg_seat_s": {"expr": "(seat_h - seat_t)/arm_h"}, "leg_str_s": {"expr": "str_h/arm_h"},
  "post_seat_f": {"expr": "(seat_h - seat_t)/height"}, "post_arm_f": {"expr": "arm_h/height"},
  "post_str_f": {"expr": "str_h/height"}, "post_panel_f": {"expr": "(seat_h + 0.5*(height - seat_h))/height"}},
 "parts": [
  {"name": "seat_C", "build": {"box": {"sx": "width", "sy": "depth", "sz": "seat_t"}},
   "attach": {"to": "ground", "at": "top_c", "self": "bottom_c", "offset": "seat_h - seat_t"}},
  {"name": "leg_front_L", "build": {"lathe": {"profile": "lib:chair.turned_leg#met:15292", "len": "arm_h", "r_max": "0.5*leg_d"}},
   "attach": {"to": "seat_C", "at": "uvw:15,1,0", "self": "ring@leg_seat_s", "mode": "point"}},
  {"name": "leg_front_R", "reflect": {"of": "leg_front_L", "plane": "yz"}},
  {"name": "post_back_L", "build": {"box": {"sx": "post_w", "sy": "post_w", "sz": "height"}},
   "attach": {"to": "seat_C", "at": "uvw:15,15,0", "self": "uvw:8,8,post_seat_f", "mode": "point"}},
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

The seat top lands at popliteal p50 + 25 mm (≈0.455 m for the ANSUR II male p50, inside the eval's
0.42–0.48 m); the legs reach the floor because their seat station is `(seat_h − seat_t)/arm_h`; the arms
run from the front-leg tops to the back posts at the same height by squeeze. `sanity: "0.42..0.48"` is a
literal band taken from the task, allowed only in `sanity`.
