# Opus Tools: overhaul of 3D models and animation, design v1.1

Status: design, 2026-10-21. **This document replaces all 3D-model and animation content in PLAN.md and DOWNLOADS.md**, not just PLAN §4.1, §4.1b and §4.3. §2.7 lists the lines it removes.

Basis: 9 verified research digests, 4 competing proposals, 3 judge reviews and 3 design reviews of v1.0 (see the Review log). The judges' totals were:

| Proposal | Score |
|---|---|
| P3 Vertical slices by user pain | 148.5 |
| P1 Spec compiler first | 144 |
| P2 Data and templates first | 137.5 |
| P4 Verification first | 132 |

The plan in order:

1. **A quick-win release (S0a, v0.4, 1–2 weeks)** built on the existing tools.
2. **P1's compiler core (S0b).** It must beat v0.4 in a measured A/B test before the remaining builders are built.
3. **P3's pain-ordered sprints**, each verified in the engine.

It also takes:
- from P4, the gate machinery: the finding format, gate classes, tiered gates and a lexicographic keep-best controller;
- from P2, the data plumbing: `data_fetch`, the library index and the CC0 test wardrobe;
- new in v1.1, licence lineage for everything derived from downloads.

---

## 1. The problem and the answer in one page

### Why Claude's 3D has needed trial and error

| Cause | Evidence | What the user sees |
|---|---|---|
| Claude makes up continuous numbers: lengths, 2D outlines, anchor positions, colours | The current "realistic" canon has foot = 0.133 of stature (ANSUR II p5 is 0.146) and hand = 0.100 (p5 is 0.103). The dog, cat and horse canons have hind MT/F of 0.64, 0.53 and 1.32, against 0.437 (wolf), about 0.35 (felids) and 0.806 (horse). ShapeLib and ParSEL both find LLMs weak at magnitudes. | Wrong proportions, generic outlines and colours, then re-guessing |
| Claude judges 3D by eye | VLM–human agreement is 0.66 vs 0.79 human–human (BlenderGym), and κ 0.51 (L3GO). Critics miss small gaps and parts that aren't attached (LL3M, qualitative). | Floating parts and slips nobody notices |
| Claude regenerates instead of editing | LL3M: regenerated code gives a "substantially different" asset | Each fix breaks something else |
| Claude designs for the wrong camera | Johnson's criteria at 50% probability: about 8 px across a target to recognise its class, about 13 px to identify which one it is | Detail where nobody looks; the subject can't be identified at game distance |
| Claude starts from uncalibrated geometry | Fused primitives plus voxel remesh leave no edge loops at joints and poles in random places | Bad deformation, "programmer art" |
| Claude hand-keys motion | — | Foot skating, timing wrong for the creature's size, robotic easing |
| Nothing compares the result with human-made work | Blind read tests only recognition, so a correct but dull asset passes | "Generic, not very artistic" (v0.1 feedback) |

### Principles that remove it

1. **Claude supplies the structure; data supplies the numbers, shapes and colours.** Claude writes a typed spec: parts, anchors, relations, ranked features and the game camera. Every value in it comes from one of these:
   - a sourced table;
   - a profile traced from human-made work;
   - a formula or an optimizer;
   - the user.

   That covers lengths, 2D profiles, free anchor positions, palette colours and timing. *Evidence: ShapeCraft's structured graph compiles 100% vs 60–80% without it; CADSmith passes 88/100 parts first time with planner JSON.*
2. **No coordinates.** Parts attach to anchors and are constrained by relations; a solver carries edits through to dependent parts. *ParSEL: 91.6% vs 61.7% of relations preserved.*
3. **One geometry per kind.** Each kind has one evaluator (numpy, or a host-native library behind the same interface). It produces the triangles behind the blueprint, the thumbnails, the masks and the build.
   - For assemblies, bodies, creatures, terrain and motion, the design you approve is what gets built.
   - For garments, armor, trees and hair you approve an *envelope* preview. Their final triangles come from Blender and are re-rasterized after the build (`post_eval`). The locked sheet is then updated with a logged diff, so it is never silently wrong.
4. **Start from calibrated templates.**
   - Humans: the hm08 CC0 body with CC0 skin weights.
   - Creatures and stylized bodies: a quad cage (FEQ) projected onto an SDF, or a faceted loft for low-poly.
   - Profiles: traced from museum photos and CC0 kits.
   - Motion: licensed mocap.
   - Terrain: statistics from real elevation data.
   - Materials: measured PBR values.
5. **Numbers before opinions, then narrow questions.** Tiered numeric checks run first. Then a fresh judge answers 2–5 yes/no questions. *A checklist judge reaches κ 0.79 (humans 0.88), against 0.51–0.66 for open judgements. MoVer went from 58.8% to 93.6% correct with verifier feedback, using up to 50 iterations.*
6. **Edit the spec, accept by rule, stop early.**
   - A fix changes spec values.
   - A change is accepted lexicographically: no new hard failure, then fewer or smaller hard failures, then soft metrics inside their noise bands.
   - A few non-dominated revisions are kept.
   - Numeric rounds are cheap, so up to 10 are allowed per finding. Judge rounds stay at 2 (CADCodeVerify saw no gain after 2).
   - *BlenderAlchemy keeping the best version: 28.2 vs 25.8.*
7. **The camera decides how much detail.** One formula, `px_per_m = H / (2·d·tan(vfov/2))`, sets:
   - feature-size floors and bevel widths;
   - circle segment counts and texel density;
   - LOD switch distances and the smallest fracture fragment.
8. **A check has to earn the right to block.**
   - Physical and contractual checks block from day one, once `defect_inject` shows they catch planted defects.
   - Rule-of-thumb checks only warn until they are calibrated: at least 95% recall on planted defects and at most 5% false alarms on a human-made corpus that actually has the property.
   - Taste metrics only report.
9. **Keep what works.** Generators that pass their checks go into a library. *SceneCraft's constraint score fell from 88.9 to 64.5 without its library (cumulative ablation).*
10. **Compare with human-made work.** Recognition is not appeal. Two things stand in for "does this look professionally made":
    - a lineup at true game size beside 2–3 human-made exemplars in the same style;
    - style statistics measured on the same corpus.

    The user's audition is final.

Caveat: most of this evidence comes from GPT-4o and Claude 3.5-era models. Proc3D shows o3 already compiles raw Blender code 65% of the time, against 94% with the structured graph. So nothing is assumed; everything is measured.
- **The compiler core must beat v0.4 in S0b.**
- **Primary measures come from the run ledger:** iterations to a hard pass, validator rejections, tokens and wall-clock per asset.
- **The user's blind A/B is the taste measure**, capped at 20 minutes per sprint.
- **The Claude judge only answers checklist questions** and breaks ties.
- **Ablations cover only the three most expensive layers** (§9).

---

## 2. Architecture

```
 brief / human-made references / the user's game screenshots (private style refs)
        │
 ┌──────▼──────────────── uv venv (host; MCP server; Python 3.13) ──────────────────┐
 │ SPEC     opus.asset/1 envelope + kind body ─ spec_validate (sources, camera,     │
 │          licences)                                                                │
 │ DATA     committed fact tables + profile library (data/LICENSES.md) · local       │
 │          caches (atlases, pose libraries, canons) · camera module · licence flags │
 │ COMPILE  evaluator contract per kind → EvalMesh(tris, part_id, anchors, source,   │
 │          post_eval) · numpy builders also import inside Blender                   │
 │          raster: silhouette · part-ID · depth (AA off) → blueprint · thumbnails · │
 │          masks · 2D lint · fit objective                                          │
 │ SOLVERS  anchor solver · sketch solver · CMA-ES / Nelder-Mead · lsq · sparse      │
 │          extras: PyGEL3D · fastscapelib · CoACD · xatlas · pydelatin · CuPy       │
 │ GATES    finding contract · classes (hard / soft / report) · tiers T0–T6 ·        │
 │          defect_inject · gate_calibrate · per-style gate profiles                 │
 │ LOOP     spec_explore · tournament · lineup · checklist judge · spec_edit         │
 │          (lexicographic acceptance, Pareto archive) · run ledger                  │
 └──────┬──── requests/results as JSON + .npz files in the session dir; stdout ack ─┘
        │
 ┌──────▼──── persistent Blender 5.2 worker (from S1; one-shot runner before, and as fallback) ─┐
 │ emit arrays → finish (MANIFOLD/EXACT, bevel, Weighted Normal) → rig/skin                      │
 │ pose batteries (BVH) → renders (Workbench masks, EEVEE lookdev, Cycles bakes)                 │
 │ anim_api (slotted actions/channelbags, twist bake) → export presets → arrays back as .npz     │
 └──────┬────────────────────────────────────────────────────────────────────────────────────────┘
        │ FBX / glTF + sidecar JSON + engine import scripts (emitted under MIT)
  Unreal (preferred) · Godot 4.7 (headless import on the PC) · Unity
```

### 2.0 Decisions: conflicts resolved

| # | Question | Options in the proposals and reviews | Decision |
|---|---|---|---|
| 1 | Delivery order | P1 foundation first, P2 data first, P3 pain slices, P4 gates first | **S0a quick wins (v0.4), then S0b compiler core (must beat v0.4 in an A/B), then pain-ordered slices** |
| 2 | When the shared evaluator arrives | S0 (P1), S2 (P3), S5 (P4), S11 (P2) | **S0b, with a per-kind evaluator contract (§2.3) fixed before any builder.** Kinds whose final triangles come from Blender or host natives are declared `post_eval`. Everything returns one `EvalMesh` type. |
| 3 | Worker transport | localhost socket (P2–P4), stdin/stdout (P1) | **Request and result files in the session dir, written with an atomic rename; a one-line stdout ack only wakes the host.** This avoids a clash with the Blender Lab MCP's port 9876, firewall and antivirus prompts, and corruption from Blender's C-level prints. The worker arrives in S1; the one-shot runner serves S0b and remains the fallback. |
| 4 | MCP surface | about 60 tools (P4) or about 30 (P1) | **32 new tools.** Categories are spec *kinds*, and category builders are internal, which keeps Claude's tool choice reliable. |
| 5 | One spec language or one per category | — | **One envelope** (header, dims, features, camera, gates, provenance, history, lock) with a **separate body, compiler and evaluator per kind**. Motion and terrain share only the envelope. |
| 6 | Feature-pixel floors as a hard gate | all four proposals | **Soft.** Measured as each part's minimum width (how many pixels survive erosion) and its extent. Hard only after calibration on CC0 characters at game size. Johnson's criteria were derived for whole targets, not sub-features. |
| 7 | What may block | — | **Hard = physical or contractual: blocks from day one, once its `defect_inject` recall test passes.** Heuristics stay soft until calibrated on a corpus that has the property. Taste metrics only report (§2.5). |
| 8 | Limb ratios for creatures | stance band (P3) or nearest species | **Declare the stance; take MT/F from the nearest species or family** (Garland & Janis). The bands overlap: lion 0.348, wolf 0.437, mountain goat 0.448. |
| 9 | Trot duty factor | all-gaits fit (P3) | **Trot fit: DF = 0.635 − 0.203·ln u** (Maes 2008) |
| 10 | Lip-sync default | Rhubarb (P3) | **Without audio: text path (CMUdict + JALI). With audio: classical energy and onset segmentation, plus word times the user marks.** Rhubarb (a classic HMM recognizer) only after the user confirms. |
| 11 | LAFAN1 for "private metric study" | P3 | **Excluded.** Its data and code are both under an ND licence. |
| 12 | Heavy solvers inside Blender (pip-installing scipy there) | armor digest | **Never modify Blender's Python.** scipy and the rest run in the uv venv and exchange `.npz` files with Blender. |
| 13 | Sprint exits that need an Unreal capture | P3 | **Automated proxies** (Blender FBX/glTF re-import round trip; Godot headless import on the PC, or in CI only if the runner can download Godot, which v0.1's cloud environment could not) **plus one PC checklist item per sprint**. Nothing is called "accepted by the engine" without a capture. |
| 14 | MakeHuman macro logic | reimplement (v1.0) or port | **Port it from MPFB2, which is GPL-3 like this plugin, with a THIRD_PARTY_NOTICES entry.** Never copy MakeHuman's AGPL code. Run a golden test against MPFB2 output. |
| 15 | Thumbnail diversity | "MAP-Elites" 5×5 over 24–64 samples | **Design Galleries dispersion in output space**, with descriptors computed on the evaluator's analytic outlines or on masks of 512 px or larger (128 px masks make shape-language descriptors unstable). A real MAP-Elites run (thousands of numpy evaluations) is optional. |
| 16 | Values with no source (fantasy parts) | — | A `design: [min, max]` range, resolved only by `spec_explore`, `spec_fit` or the user, never by Claude picking a value. Profiles, free anchor positions and palette colours follow the same rule. `user` and `style_mult` sources are logged. |
| 17 | Consistency gate | silhouette IoU ≥0.99 (P1) | **Whole-object IoU ≥0.99, plus per-part symmetric boundary distance p95 ≤0.5 px at a resolution where the smallest part spans ≥10 px, plus BVH-ray depth.** It runs after the build and after Blender-only operations, not on every `spec_check`. |
| 18 | Armor follower bones | Armature constraint on a parented helper | **Exactly one method:** Copy Rotation (LOCAL, ADD, influence i/n) on a helper parented to the parent bone. Nonlinear followers are rebuilt in the engine. |
| 19 | Low-poly and chibi bodies | hm08 at baby or child age | **Route A, FEQ cage, or route B, facet loft, plus the style canon. Both are scored against measured facet statistics.** hm08 child macros are for realistic children only. |
| 20 | Stylized FEQ route not de-risked | all four | **Parallel PC spike during S0b–S1 on the research prototype.** It ends in a numeric go/no-go plus a lineup against a KayKit character, decided before S2 (§9). |
| 21 | Accepting a spec edit | revert on any regression (v1.0) | **Lexicographic acceptance with noise tolerances, a Pareto archive, and a joint solve for coupled findings** (§2.6) |
| 22 | NC data (Bandai, MANN, FABDEM, O'Donovan) | opt-in (reviewer B) or on by default (reviewer C) | **On by default in the local library**, because PLAN §0 records that the user accepts NC licences. The user confirms once at `opus data build`. It is never committed, it is flagged in the ledger, and export blocks it when `commercial: true`. |
| 23 | Profiles, anchors, palettes | typed by Claude | **Taken from the profile library, a constraint sketch, a slot-template anchor or a `design` range.** Palettes come from measured packs, references or explore. |
| 24 | Native packages | "required" (v1.0) | **Optional extras with numpy fallbacks**, promoted to required only after the Windows spike |
| 25 | Twist bones in the engines | not addressed | **Every exported clip bakes twist keys (swing-twist); engine-retargeted clips get runtime recipes.** `twist_policy` is set in S1. |
| 26 | Appeal | blind read only | **Lineup against human-made exemplars, plus measured style statistics (soft), plus the user's audition** |

### 2.1 Spec language: `opus.asset/1`

**Envelope** (shared by every kind; pydantic models plus JSON Schema, versioned per kind):

| Field | Content |
|---|---|
| `spec`, `kind`, `id`, `rev`, `parent_rev`, `category`, `style` | `style` is one of `lowpoly`, `stylized`, `hd`, `pixel3d` |
| `units`, `up`, `front` | Always `m`, `+Z`, `-Y`; left = +X |
| `camera` | A bible profile id, or {engine, fov_axis, fov_deg, aspect, res_h, d_closest, d_typ, d_max \| ortho_h \| sprite_px}. View-model profiles add vm_fov, near and scale. `derived` is filled in by the tools. |
| `features` | 5–7 ranked {id, parts, views, min_px, exaggerate_pct} |
| `shape_language`, `size_tiers`, `palette_roles`, `must_avoid` | Mix in %, tiers (default 60/30/10, soft), role → sourced colour (never typed hex), banned choices |
| `dims` | Every number, each with a source (see below) |
| kind body | `parts`/`relations`/`sockets`/`joints` (assembly), `body`, `garment`, `harness`, `motion`, `terrain`, … |
| `explore` | Dials with ranges or choices, plus the morph box |
| `gates` | Per-asset overrides of the bible's gate profile and its hard, soft and judge thresholds |
| `surface` | UV mode, TD rule, bake list, LOD/hull policy |
| `lock` | Written on lock: the resolved value of every dim, profile and palette entry, plus `tables_version` (a hash of the fact tables and profile library), so a table rebuild never silently changes a locked asset |
| `provenance`, `history` | Sources with licence IDs; a JSON-patch log in which every change carries a `why` |

**Where values may come from.** Only from `dims`, `profiles` and `palette_roles` entries, each tagged `measured`, `derived` or `recalled`:

| Source | Example | Notes |
|---|---|---|
| `table` | `{"table": "oakeshott.XIV.blade_len"}` | Committed fact table |
| `range` + `src` | `{"range": [0.0047, 0.0061], "src": "replica distal taper"}` | Sampled with the seed |
| `expr` | `{"expr": "0.197*wielder.hand_length"}` | Over dims, wielder, body landmarks and the camera |
| `profile` | `{"profile": "lib:cross.straight_flat_taper"}` | Library profile traced from human-made work; its parameters carry p5–p95 ranges |
| `sketch` | `{"sketch": [["tangent","a1","l2"], ["distance","l1","blade_w_base"]]}` | Constraint sketch solved by Gauss-Newton; lengths refer to dims |
| `palette` | `{"palette": "kenney:colormap#12"}`, `{"fit": "ref_01.kmeans[2]"}` | Pack palettes, reference k-means, Lospec palettes (local only) or explore |
| `user` | `{"user": 1.83}` | The user's own value, logged |
| `design` | `{"design": [0.9, 1.3]}` | Invented parts; must be resolved by explore, fit or the user |
| `style_mult` | `{"table": "...", "style_mult": 1.15}` | Logged; the deviation is reported as a z-score |

**Rules.**
- **Builder parameters** are dims names, expressions over dims, library profiles, or dimensionless template coefficients from a template or the style canon (stations, superellipse n). They are never typed lengths, world positions, angles, profile points or colours.
- **Placement** is only by `attach` (a slot template's named anchor, or a `design`-ranged `[u,v,w]` on a 1/16 grid of the parent's bounding box), `squeeze`, `reflect`, `translate`, `radial`, or skeleton anchors `(u,v,r)`.
- **Orientation** comes only from relations (`coaxial`, `perpendicular`, `along_tangent`, `symmetric`) or from sourced angle dims (for example `flank_deg`).
- **Symmetry** is restored before attachment (ParSEL order).
- **Names** follow `role_side_index`, where side is one of L, R, C, F, B.
  - Blender object, vertex-group and bone names equal the spec names.
  - Builders stamp `opus_part` and `opus_src` (a JSON pointer into the spec) on every object, vertex group and bone.
- **Size:** at most 12 leaf parts per assembly level.

**The validator rejects:**
- missing units, or a number with no source;
- literal world coordinates, hand-typed profile points, free anchor positions or hex colours without a source;
- siblings without a side or index;
- parent cycles, or relations that name unknown parts;
- values outside their table range × the declared style multiplier;
- a table or profile with no `data/LICENSES.md` entry.

It **warns** when a feature's projected size falls below its `min_px`. Every rejection is logged to the run ledger, so spec-authoring friction is measured.

**Example** (assembly kind; the knight's sword):

```json
{
 "spec": "opus.asset/1", "kind": "assembly", "id": "sword_xiv_knight", "rev": 3, "parent_rev": 2,
 "category": "weapon/sword/oakeshott_XIV", "style": "hd", "camera": "ue_tp_1080",
 "units": "m", "up": "+Z", "front": "-Y", "wielder": "knight_01.spec.json#/body/landmarks",
 "template": "slot:sword", "tables_version": "2026.10.1",
 "features": [
  {"rank": 1, "id": "long_tapered_blade", "parts": ["blade_C"], "views": ["side", "game"], "min_px": 13},
  {"rank": 2, "id": "straight_cross", "parts": ["cross_C"], "views": ["front", "game"], "min_px": 13},
  {"rank": 3, "id": "wheel_pommel", "parts": ["pommel_C"], "views": ["side"], "min_px": 4}],
 "shape_language": {"dominant": "triangle", "dominant_pct": 60, "accent": "square", "n_default": 4},
 "dims": {
  "blade_len":    {"table": "oakeshott.XIV.blade_len"},
  "blade_w_base": {"table": "oakeshott.XIV.width_base"},
  "blade_w_tip":  {"table": "cleveland.sword.blade_w_tip"},
  "taper_k":      {"design": [0.9, 1.3], "doc": "w(s) = lerp(w_base, w_tip, s^k)"},
  "thick_base":   {"range": [0.0047, 0.0061], "src": "replica distal taper"},
  "thick_tip":    {"range": [0.0020, 0.0022], "src": "replica distal taper"},
  "grip_len":     {"table": "oakeshott.XIV.grip_len", "sanity": "wielder.hand_breadth p50..p95+0.010"},
  "grip_d_eq":    {"expr": "0.197*wielder.hand_length", "tol": 0.10, "measure": "circumference/pi"},
  "grip_aspect":  {"design": [1.15, 1.35]},
  "cross_len":    {"table": "oakeshott.XIV.cross_len", "style_mult": 1.15},
  "pommel_d":     {"table": "met.sword.pommel_d"}},
 "parts": [
  {"name": "grip_C", "build": {"station_loft": {"len": "grip_len", "section": "oval", "d_eq": "grip_d_eq", "aspect": "grip_aspect", "n": "canon.n_grip"}}},
  {"name": "cross_C", "build": {"extrude": {"profile": "lib:cross.straight_flat_taper", "len": "cross_len"}},
   "attach": {"to": "grip_C", "at": "top_c", "self": "bottom_c"}},
  {"name": "blade_C", "build": {"station_loft": {"len": "blade_len", "stations": "lib:blade.xiv.stations",
     "section": "lib:section.lenticular_fullered", "w": "lerp(blade_w_base, blade_w_tip, s**taper_k)",
     "t": "lerp(thick_base, thick_tip, s)", "point": "lib:point.acute"}},
   "attach": {"to": "cross_C", "at": "top_c", "self": "bottom_c"}, "edges": {"cutting": "bevel_weight_0"}},
  {"name": "pommel_C", "build": {"lathe": {"profile": "lib:pommel.wheel_K", "d": "pommel_d"}},
   "attach": {"to": "grip_C", "at": "bottom_c", "self": "top_c"}}],
 "relations": [
  {"type": "coaxial", "a": "grip_C", "b": "blade_C", "tol_deg": 0.5},
  {"type": "perpendicular", "a": "cross_C", "b": "blade_C", "tol_deg": 1},
  {"type": "embedded", "a": "blade_C.tang", "b": "grip_C"}],
 "sockets": {"grip_main": "grip_C@slot:grip_main", "tip": "blade_C@top_c"},
 "materials": {"blade_C": "phys:iron", "cross_C": "phys:iron", "pommel_C": "phys:iron", "grip_C": "ambientcg:Leather011"},
 "gates": {"profile": "cad_clean", "hard": {"contact_m": 0.002, "tris": [3000, 8000]},
           "soft": {"mass_kg": [0.9, 1.5], "pob_from_cross_m": [0.07, 0.15], "pivot": "cross - wielder.hand_breadth"}},
 "surface": {"uv": "analytic+rule_seams", "td": "camera", "bake": ["basecolor", "orm", "normal"]},
 "history": [{"rev": 3, "op": "replace", "path": "/dims/cross_len/style_mult", "from": 1.0, "to": 1.15,
              "why": "readability: cross_C extent 12 px < 13 px at d_max 15 m"}]
}
```

(The `slot:sword` template defines `grip_main` at `[0.5, 0.5, 0.625]` of the grip box, on the 1/16 grid. `canon.n_grip` comes from the style canon.)

**Kind bodies** (each shares the envelope):

| Kind | Body (abridged) |
|---|---|
| `assembly` | parts, relations, sockets, `joints` {type revolute\|prismatic, axis, origin, limits}, slot template |
| `body.human` | `{"template":"hm08","macro":{"gender":1,"age_y":30,"muscle":0.75,"weight":0.5},"fit":{"stature":{"pct":80,"sex":"m"},"biacromial":{"pct":90}},"stylize":[{"op":"edfm","k":1.2,"on":["biacromial"]}],"rig":"game_engine+twist","rest":"A45","topology":"hm08\|proxy741"}` |
| `body.creature` | `{"donor":"canid","stance":"digitigrade","mass_kg":40,"withers_m":0.8,"grafts":[],"sdf":[...],"pose_dials":["hip","knee","shoulder","elbow","neck","tail"],"cage":{"loops_at":[0.5,0.88],"level":1},"route":"feq\|facet","exemplars":{"wolf":0.8,"dog":0.2}}` |
| `garment` | `{"archetype":"gambeson","layer":2,"coverage":{"hem":{"between":["crotch","knee"],"t":0.3}},"ease_pct":{"chest":14},"fabric":"quilted","thickness_mm":15,"mask_inner":true}` |
| `harness` | `{"preset":"milanese_1450","pieces":[{"piece":"couter_L","joint":"lowerarm_l","theta_max":"rom.elbow*0.9","lames":"auto","gap_mm":2,"outline":"lib:armor.couter.milanese"}]}` |
| `motion.*` | `retarget`, `locomotion`, `quad_gait`, `flight`, `undulate`, `keyed`, `secondary`, `face`, each with: contact table, N, fps, speed, timing table (sourced or `design`), **`predicates`** (§5.4) |
| `terrain` | player metrics, world size, cell size, engine size, Lynch elements, POIs, critical path, primitives, targets |
| `tree` | species or archetype, biome, Tallo percentile, style, wind convention |
| `building` / `kit` / `layout` | grammar rules; kit footprint and sockets; constraint program (StableAgainst, SupportedBy, min_distance, accessibility, freespace) |
| `face` / `hair` | ARKit-52 contract and recipes; hairline, parting, whorl and clump list |

### 2.2 Data layer

- **Fact tables** live under `plugins/opus-tools/data/` (about 2 MB in total, each file under 200 KB).
  - Every value is `{value, min, max, unit, src, tag: measured|derived|recalled}`; a `recalled` value only ever produces warnings.
  - Tables are committed only when they derive from CC0, public-domain, factual or CC BY sources.
  - Each table has an entry in `data/LICENSES.md` giving source, licence ID, licence URL, the exact attribution string, and "derived/modified" wording.
  - Maintainers build them with `opus data build --tables` and review them before committing.
  - Everything else is a local cache (§7).
- **Profile library** (`data/profiles/`): named, parameterized 2D profiles built from line, arc and circle (plus an optional cubic).
  - Each is traced classically from human-made sources: blades, crosses, pommels, axe heads, shield rims, guards, armor outlines and flute lines, kit silhouettes.
  - Each carries p5–p95 parameter ranges across specimens and its provenance.
  - Profiles traced from CC0, public-domain and CC BY sources are committed (with attribution). Profiles traced from QAL or unknown-licence packs stay in the local cache.
- **`dims_resolve(class, wielder, style, seed)`** returns a sheet of `{value, min, max, unit, src}`.
  - It samples inside ranges with the seed (Infinigen style).
  - It evaluates wielder formulas such as grip_d = 0.197 × hand length and seat height = popliteal p50 + 25 mm.
  - Conflicts between sources are stored as ranges.
- **Bible additions** (`opus.project.yaml`):
  - camera profiles, **including a view-model profile** (its own FOV, near plane and scale; read from the project, never assumed);
  - `weapon_scale`, `gravity_mult`, per-feature `style_mult` defaults;
  - TD target, budgets, style canon id;
  - **gate profile per style** (`cad_clean`, `kitbash`, `organic`; §2.5);
  - **licence policy**: `commercial: false` and `allow_nc: true` (both defaults from PLAN §0, confirmed once), `publish_assets: false`;
  - **`twist_policy`**: `baked`, `runtime` or both (§4.1);
  - **rating budget**: 20 minutes of user A/B per sprint by default;
  - taste notes.
- **Camera module** (`opus.camera`, used everywhere). Examples use Unreal third person at 1080p: horizontal FOV 90° → vertical 58.7°, so px_per_m = 960/d.

| Quantity | Formula | Example |
|---|---|---|
| vfov from hfov | 2·atan(tan(hfov/2)/aspect) | 58.7°. Godot 75° vertical (tan 0.7673); Unity 60° vertical. Read the project's own value. |
| px_per_m(d) | H/(2d·tan(vfov/2)); ortho: H/view_height | 640 at 1.5 m, 274 at 3.5 m, 64 at 15 m, 24 at 40 m |
| Minimum feature | px / px_per_m | 4 px at 3.5 m = 14.6 mm; 13 px at 15 m = 0.20 m |
| Detail tier (at d_closest) | ≥3 px → geometry; 1–3 px → normal or trim; <1 px → omit | 6 mm rivet: 3.8 px at 1.5 m → geometry |
| Circle segments | n = ceil(π / acos(1 − ε/r)), ε = 0.5 px / px_per_m | 19 mm-radius grip: 11 sides at 1.5 m, 8 at 3 m, 20 at 0.45 m (first person) |
| Bevel width | clamp(1.5 px / px_per_m, 0.02t, 0.25t) | 2.3 mm cap at 1.5 m |
| Texel density | px_per_m(d_closest) → nearest power of two in log scale | 640 → 512 px/m |
| Texture size | R = TD·√(A/η), η 0.6–0.75 | — |
| Bake padding | 2^k texels for k mip levels that stay visible | 16 |
| LOD switch distance | dᵢ = eᵢ·H / (2·tan(vfov/2)·τ), τ = 1 px | — |
| Smallest fracture fragment | l_min = (6–10 px) / px_per_m | — |

- **`library_dir`** (set in `userConfig`) holds every download and local cache, fetched per a manifest (§2.7). It is never committed.

### 2.3 Builders and generators

**Evaluator contract** (fixed in S0b, before any builder). Every kind implements `evaluate(spec, level) → EvalMesh(tris, part_id, anchors, source, post_eval)`. Arrays computed in Blender come back as `.npz`, so every gate and raster reads the same type.

| Kind | Authoritative geometry (preview, fit, gates) | Computed by | Preview without Blender | `post_eval` |
|---|---|---|---|---|
| `assembly` | Evaluator triangles of box, extrude, lathe, sweep, station_loft, inflate. Visual hulls by per-pixel ray–prism interval intersection. | numpy (host and worker) | yes | Only parts whose booleans, SDF fusion or bevels change the game raster by >1 px |
| `body.human` | morphed hm08 vertices | numpy | yes | no |
| `body.creature` | Three stages:<br>• fit: a 2D projected proxy (capsules → stadiums, ellipsoids → ellipses, 2D smooth-min);<br>• confirm: SDF raster;<br>• build: the FEQ cage or facet loft at the chosen level, returned as arrays | numpy, plus host PyGEL3D for the cage | yes (host) | no |
| `garment`, `harness` | Envelope: station-slice convex hulls, Steiner offsets, plate outlines in pattern space | numpy | envelope only | yes (SDF closing, Shrinkwrap, Solidify, rolled edges, drape) |
| `terrain` | heightfield | host (numpy, fastscapelib extra) | yes (hillshade, layout) | no |
| `tree` | skeleton, radii, leaf cards | numpy | yes | yes (Curve to Mesh) |
| `building` / `kit` / `layout` | kit pieces as assemblies; grammar, WFC and annealing output as transforms | numpy | yes | per piece, as for assemblies |
| `motion.*` | FK poses per frame | numpy | yes (evaluator filmstrip) | no |
| `face`, `hair` | numeric contract checks; geometry from Blender | worker | no | yes |

**Numpy builders** (`opus.compile`; each returns verts, faces, part_id, named anchors and analytic UVs):

| Builder | Used for | Notes |
|---|---|---|
| `box` / `superquadric` | blockouts, crates, plates | S0b |
| `extrude(profile)` | guards, axe heads, kit pieces | Profile from the library or a constraint sketch: line, arc, circle (95% of CAD sketch curves) plus an optional cubic. S0b. |
| `lathe` | pommels, barrels, bottles | Segment count from the sagitta rule; seam welded so the mesh is manifold. S0b. |
| `station_loft` | limbs, blades, grips, barrels, sleeves | Superelliptic rings: a(t) from the front profile, b(t) from the side; n(t) is the shape-language dial (2 round, 4 squircle, ≈8 boxy) from the canon or explore. S0b. |
| `facet_loft` | low-poly route B | station_loft with K = 6–8 rings, explicit hard edges at silhouette turns, flat shading. S2. |
| `sweep` | straps, rails, pipes | Rotation-minimizing frames. S4. |
| `visual_hull` | receivers, axe heads, slides | **Prismatic parts only.** Closed prisms from 2–3 profiles, evaluated in numpy by ray–prism intervals. The Blender MANIFOLD intersect (EXACT fallback) is post-checked. S4. |
| `inflate` | ears, leaves, capes, membranes | Solve −Δh = c, c > 0, then z = √h, with red-black SOR (ω = 2/(1+sin(π/N))). Grid is 64² while fitting (150 iterations, ≈25 ms measured) and 256² at build. **Never Jacobi** (it reached only 3–13% of the true height). S2. |
| `sdf_body` | organic bodies | Ellipsoids and round cones joined with smooth-min; k is a blend radius in metres (one documented convention). S2. |
| `ring_loft_on_slice` | garments, armor tubes | Slice hulls → Minkowski offset → K-gon rings. S7. |
| `morph` | hm08 | V = V0 + Σ wᵢDᵢ (sparse targets). S1. |

**Templates.**
- `human_build`: the hm08 morph engine (§4.1), with macro logic ported from MPFB2 (GPL-3, notice in THIRD_PARTY_NOTICES).
- `creature_cage`: skeleton graph → PyGEL3D `skeleton_to_feq` (host extra) → Catmull-Clark → SDF projection with vectorized relaxation (§4.3).
  - Hands use one of three methods: the CC0 hm08 hand topology scaled to the canon and welded at a wrist ring; fingers as FEQ skeleton branches; or mitten hands at levels 0–1.
  - `body_blockout`'s voxel-remeshed hands are never used.
- `body_blockout` stays as a quick blockout and SDF target only. Its canons are fixed in S0a:
  - foot 1.0 → 1.15 HU, hand 0.75 → 0.82 HU;
  - dog, cat and horse hind MT/F from Garland & Janis (wolf 0.437, felid about 0.35, horse 0.806);
  - the horse gets a fetlock and pastern so its phalanges are separate.

**Profiles.**
- `ref_extract(mode=profile)` traces a clean-background photo or kit silhouette, then normalizes it by a known dimension from the museum record. Steps: mask → contour → Douglas-Peucker → least-squares line/arc fit.
- New profiles that have no trace use a constraint sketch: tangent, equal, symmetric, distance and angle, solved by Gauss-Newton.
- `spec_explore` chooses among library profiles before it varies dials.

**Blender finishing** (`opus_bl/finish.py`):
- booleans: MANIFOLD, with EXACT as the fallback (never FLOAT);
- Bevel with `face_strength_mode='FSTR_AFFECTED'`, `miter_outer='MITER_ARC'` and harden normals;
- Weighted Normal with keep_sharp and face influence (weight 50 means plain area weighting);
- Triangulate with `keep_custom_normals`;
- selective SDF fusion (Mesh to SDF Grid → SDF Grid Boolean → SDF Fillet → Grid to Mesh), only for parts thicker than 4 voxels.

**Generator library.** Code lives in `generators/<category>/<name>.py` and exposes `PARAMS {default, min, max, unit, src}`, `ANCHORS`, `build(p, seed)` and a self-test.
- `library_promote` admits a generator when two conditions hold:
  - every hard gate passes on ≥8 seeds;
  - it reproduces each reference it declares, at that reference's stop threshold. A generator with no references (fantasy) needs one user audition approval instead.

  This is our own rule; ShapeLib requires "valid applications across multiple seed shapes", with no fixed count.
- Macros (wheel pommel, D-section limb, strap, rivet row) are mined from approved spec histories (the ShapeMOD idea).
- CI re-runs every generator on each Blender upgrade.

### 2.4 Solvers

| Solver | Runs in | Used by |
|---|---|---|
| Graph/anchor solver (topological order; attach, squeeze, reflect, translate, radial; relations) | numpy (both sides) | every assembly; `spec_edit` re-solves dependents |
| Constraint sketch solver (Gauss-Newton over line and arc constraints; about 200 lines of numpy) | numpy | new profiles |
| CMA-ES and Nelder-Mead (about 100 lines of numpy each) | host | `spec_fit`; joint solves of coupled findings. Discrete structure is enumerated outside the optimizer. |
| Bounded least squares (`scipy lsq_linear`) plus Gauss-Newton | host | `fit_measurements` |
| Sparse Cholesky / `spsolve` / CG on the unmatched set plus a 2-ring | host (scipy) | weight inpainting; gradient-domain terrain |
| Analytic 2-bone IK (reach clamped at 0.999), 3-bone pantograph | numpy | contact re-planting, gaits, grips |
| Swing-twist decomposition and twist distribution | numpy | retarget, keyed motion, clip export |
| Spring and Verlet integrators (Holden) | numpy | secondary motion, inertialization, first-person sway and recoil |
| Binary search / constrained `trim_to_clear` | worker | armor clearance (the last repair step, §4.5) |
| fastscapelib (stream power, MFD, priority-flood); multi-scale erosion stencils (numpy ≤512², CuPy above) | host (`opus[terrain]`, `opus[gpu]`) | terrain |
| Galin k = 5 anisotropic A* (on the ≤512² working grid, then corridor refinement at full resolution; numba if installed) | host | roads |
| Simple-tiled WFC (D4 symmetry, restart on contradiction) | host | kits, dungeons |
| Layout simulated annealing (Infinigen-Indoors style; staged from large to small; Metropolis acceptance) | host | scene dressing, interiors, clutter on terrain |
| CoACD, xatlas, pydelatin, PyGEL3D | host extras | hulls, lightmap UVs, low-poly terrain meshes, FEQ cages |

### 2.5 Gates

**Finding contract.** Every check returns:

```json
{"gate": "spec_check", "check": "contact_gap", "class": "hard", "target": {"part": "cross_C", "bone": null, "frames": null, "pose": null, "cell": null},
 "value": 0.0042, "expected": "<=0.002", "unit": "m", "noise_tol": 0.0001, "pass": false,
 "evidence": "renders/cross_C_gap.png",
 "fix": {"spec_path": "/parts/1/attach", "suggest": "anchor bottom_c -> top_c of grip_C", "dial_unit": "anchor"}}
```

The `opus_src` stamps let every finding point mechanically at the spec field that fixes it. Scene tools still work on meshes and clips that have no spec: `model_report`, `mesh_lint`, `proportion_check`, `grip_check` and `motion_report`. Their findings then point at objects and bones.

**Tiers.** Gates run cheapest first and stop at the first tier with a hard failure:

| Tier | Where | Budget | Examples |
|---|---|---|---|
| T0 spec | host | <50 ms | sources, units, names, cycles, licences, camera feasibility, tier assignment |
| T1 evaluator | host numpy | <0.5 s | dims vs build, anchors, symmetry, silhouette and depth vs blueprint or reference, design_lint, pixel survival (inflate parts at 64²) |
| T2 geometry | worker | <2 s | contacts (sampled BVH both ways), overlaps, components, manifold, mesh_lint, mass properties |
| T2b consistency | worker | <10 s | evaluator vs Blender (§3.4); runs only after a build or a Blender-only operation |
| T3 batteries | worker | iterating: 2–30 s (10–20 extreme poses); sign-off: ≤10 min (full battery) | `deform_test`, `rom_check`, articulation sweeps, `motion_report`, terrain report |
| T4 renders | worker | 2–10 s | readability at the game camera, lookdev, filmstrips, lineup sheets |
| T5 judge | subagent | per call | checklist, blind read, lineup, tournament |
| T6 engine | PC | manual or MCP | import plus capture |

**Re-runs.** Local gates re-run only for the patched part, its attach descendants and its mirror partner. **Global gates always re-run after a patch:** mass and balance, centre of mass, silhouette, readability and budgets.

**Gate classes.**

| Class | Blocks | What it must show first | Examples |
|---|---|---|---|
| Hard: physical or contractual | from day one | `defect_inject` recall ≥95% at the stated defect size (≥99% at 2×), and 0 failures on clean fixtures (generator outputs built to pass) | penetration; contacts vs declared relations; floating parts vs the part list; skate; formats; drainage; influences; dimension-sheet violations; engine names and sockets; round trips; ARKit names; hm08 vertex order |
| Soft until calibrated | warns; promoted to hard after calibration | ≥95% recall on planted defects, ≤5% false alarms on a corpus that actually has the property (table below), and agreement with the user's ratings | deform thresholds, standoff and exposure, readability floors, clearance bands, walkable %, TD CV, style-match statistics, topology (quads, poles) |
| Report only | never | — | appeal lint, 60/30/10, shape-language mix, palette-harmony scores (Matsuda, O'Donovan), Muybridge IoU |

**False-positive corpora for soft gates:**

| Gate family | Corpus that has the property | Not usable, and why |
|---|---|---|
| Twist / candy-wrap | Paired: hm08 with twist bones (good) vs the same bodies without them (bad), at 3 macro settings | CC0 rigs without twist bones: they really do candy-wrap |
| Other deform joints | MPFB `game_engine`; KayKit and Quaternius rigs (local only) at elbow, knee, hip and spine | — |
| Garment clearance | MHCLO CC0 clothes on MPFB bodies within ±60% of CDC ranges, plus planted defects and user ratings | MHCLO at extreme poses: it penetrates |
| Armor ROM | planted-defect suite plus user ratings | no human-made rigged armor corpus exists |
| Readability, style statistics | Kenney and KayKit characters and props at game size, under the `kitbash` profile | Poly Haven scans for low-poly |
| Contact and overlap | our generators under `cad_clean`; Kenney and KayKit under `kitbash` | Kenney under `cad_clean`: embedded parts are intentional |
| Surface (TD CV, UV distortion) | Poly Haven models (API, credited) and Kenney | — |
| Motion | 100STYLE and UAL cycles, Fukuchi trials | LAFAN1 (ND) |
| Terrain realism | Copernicus crops; the Galin DEM repository (local only, no licence) | — |
| Trees | Tallo bands (table only); planted defects for meshes | — |

**Per-style gate profiles.**
- `cad_clean`: manifold per part; contacts and overlaps checked against the declared relations.
- `kitbash`: interpenetrating and embedded parts may be declared; manifold is checked per part.
- `organic`: single skin; self-overlap gates apply.

An asset may override its style's profile, and the override is logged.

**Trust machinery timing.** A minimal `defect_inject` / `gate_calibrate` harness ships in S0b. Every sprint ships the defect suites for its own hard gates and calibrates its soft gates where a corpus exists; otherwise they stay warnings. Planted-defect examples:
- part offset 3 mm, leg ×0.85, detached handle, flipped faces;
- 3 cm foot skate, 25° pop, 5° seam break, knee flip, swapped footfalls, missing twist keys;
- closed lame overlap, garment 2 mm inside the body at elbow 90°, inner layer through outer;
- terrain pit, uphill river, unreachable POI;
- 700 mm door, 12 mm riser variance;
- UV overlap, an island at 2× TD, wrong normal-map green channel.

**CI corpus.** A pinned, CC0-only subset fetched by `data_fetch` into a cache that is never committed: Kenney, KayKit packs with a CC0 snapshot, MPFB and ambientCG. Calibration that needs CC BY, NC or QAL corpora runs locally only. Only the resulting thresholds and their source list are committed. CI artifacts never contain fetched assets.

**Fixes in existing code (S0a).**
- Mask render mode: `render_aa='OFF'`, FLAT light, Standard view transform, dither 0. `lookdev.py:140` currently uses `'8'` with STUDIO light, which blends part colours at edges.
- Signed distance by angle-weighted pseudonormals or winding number. `grip.signed_distance` currently flips sign at edges.
- Thin-shell penetration measured by BVH triangle overlap plus a one-sided test against the plate's inner sheet. Closest-point sign misses a body that has passed right through a plate.

### 2.6 Critique loop and iteration controller

1. **Numeric gates T0–T4.** Hard failures go to `spec_edit`.
2. **`critique_pack(mode=checklist)`** renders fixed views in clay and normal passes:
   - CADSmith iso (el 35°, az 45°), rear (el 65°, az 220°), front (el 10°, az 0°), plus top;
   - one zoom crop for detail questions;
   - at most one view at the game camera.

   It writes 2–5 yes/no questions derived from the spec, one criterion per question. A fresh `art-director` subagent answers them, reasoning first. The subagent never sees code, file names or authorship. "Unclear" counts as No. After a fix, only the failed questions are asked again.
3. **`blind_read_sheet`** at true game pixel size. Its top-1 answer must name the subject.
4. **`critique_pack(mode=lineup)`** places the asset beside 2–3 human-made exemplars of the same style and camera, at true game size and in random positions. Exemplars come from Kenney, KayKit, Quaternius (local), Met photos or the user's references.
   - The judge answers "which one doesn't belong / looks least professionally made", in both orders.
   - The same sheet goes to the Audition Board for the user.
   - The soft style-match statistics are measured on the same corpus: size-tier ratios, detail features per 100 px at the game camera, silhouette complexity, facet-size distribution, and palette count, L* range and saturation.
5. **Tournament** (only when choosing between candidates): single elimination over ≤8 candidates, always including the incumbent. Every match runs in both orders and only consistent wins count, so 8 candidates cost ≤14 calls.
6. **User audition** on the Audition Board. Ratings go to `.opus/ratings` and become taste notes. User time is capped by the bible's rating budget.

**Acceptance rule (`spec_edit`).** A candidate revision is compared with the incumbent in this order. Each metric carries a noise tolerance ε, measured by re-running it on 3 seeds or render jitters (default 2% of its band).
1. A hard check that passed may not fail. A new hard failure rejects the candidate.
2. Accept if the number of hard failures drops.
3. If the count is equal, accept if the summed hard magnitude (each value normalized by its threshold) drops by more than ε.
4. If the hard results tie, soft metrics may regress within their tolerance bands; accept on the weighted soft score.
5. Use the judge only when steps 1–4 tie.

Up to 4 non-dominated revisions are kept: a Pareto archive over hard count, hard magnitude and soft score.

Two findings are **coupled** when their fix paths share a dependency, or when they trade off over 2 rounds. Coupled findings are solved jointly: CMA-ES or Nelder-Mead over both dials, with the ordering above as the objective. Example: `trim_to_clear` with an exposure ceiling.

**Caps.**
- 3 execution retries. The traceback is matched against `errors.json` first: BLENDER_EEVEE, FLOAT/EXACT/MANIFOLD, channelbags, `fcurves.ensure(group_name=)`, `media_type` before `file_format`, `mod.properties.inputs`, removed `BMLoopUV.select`.
- Judge rounds: 2 by default, 5 at most.
- Numeric and predicate iterations: up to 10 per finding. They cost no judge calls.
- Best-of-3 candidates only for a part that fails twice.
- Escalation to an A/B sheet for the user only after 10 numeric rounds without progress, or a deadlock the joint solve cannot break.
- "Tweak" rounds (dials) alternate with "leap" rounds (structure). Changing taste after the design is locked needs an explicit leap round.

**`spec_edit`** takes a JSON patch or a seed edit (`"blade_len*=1.1"`) plus the relations to keep. It then:
1. re-solves dependents;
2. checks edit locality (only the targeted parts and their dependents may change);
3. re-gates;
4. labels each finding improved, unchanged or regressed;
5. applies the acceptance rule.

**Run ledger.** `.opus/runs/*.jsonl` feeds `run_stats`:
- iterations to a hard pass, judge rounds, user rejections, time per tier;
- **validator rejections and tokens per asset** (spec-authoring cost);
- a failure histogram that decides which generator to improve next.

### 2.7 Infrastructure

**Persistent Blender worker** (`opus_bl/worker.py`, from S1):
- **Start:** lazily, by the MCP server, as `blender -b --factory-startup --python worker.py`. Never with `-y` or `--enable-autoexec`.
- **Protocol:**
  - Each request is a JSON file (plus `.npz` arrays) in the session dir. The worker writes its result as a file and renames it atomically into place.
  - The result file is the source of truth. A one-line stdout ack (`@@OPUS <id> ok|err`, matched by regex anywhere in the stream) only wakes the host.
  - Blender's other output, including C-level render progress, is logged and ignored.
  - stdin and stdout are reconfigured to UTF-8 explicitly (Windows defaults to cp1252).
- **Queue:** FIFO with per-command timeouts (render 120 s, bake 600 s by default), so parallel subagent calls queue rather than collide. An optional second worker handles bakes.
- **Commands:** `ping`, `build`, `render`, `check`, `pose_battery`, `bake`, `export`, `save`, `reset`. They share the task registry with `entry.py`.
- **Hygiene:**
  - `read_factory_settings(use_empty=True)` and an orphan purge between assets, then re-enable the Cycles GPU (OPTIX, falling back to CUDA). The existing code forces CPU, which a reset would also silently restore.
  - Checkpoints only before destructive commands (build, finish, bake, export). The last 3 are kept.
  - Restart on a crash or above 6 GB RSS (measured with psutil), reloading the last checkpoint.
  - Idle timeout of 10 minutes.
- **Security:** keep `--factory-startup`; prefer glTF or FBX import to appending `.blend` files; open `.blend` files with `load_ui=False` and Python auto-exec left off; every `np.load` uses `allow_pickle=False`; pickle formats from downloads are rejected.
- **Fallback:** `runner.py`'s one-shot `run_task` serves S0b, CI, and any time the worker is down.
- **Determinism test:** the same spec, seed and `tables_version` must give the same hash. Each side hashes float32 arrays quantized to 1e-6 m.

**Where code runs:**

| uv venv (host) | Blender worker |
|---|---|
| spec and validator, dims, camera, profile library and sketch solver, `opus.compile` evaluator and raster, optimizers, scipy solves, PyGEL3D, fastscapelib and terrain, mocap parsing and atlases, WFC and layout, CoACD, xatlas, pydelatin, critique packing, ledger | emit arrays, finishing, rig and skin, posing and BVH batteries, Workbench/EEVEE/Cycles renders, `anim_api` and twist bake, export, EXR writing. Imports `opus.compile` (numpy only). Never pip-modified. |

**uv dependencies.**
- **Core:** mcp, numpy, pillow, pyyaml, pydantic, scipy, scikit-image, psutil.
- **Optional extras**, imported lazily, each with the numpy fallback named in §10:

  | Extra | Packages |
  |---|---|
  | `opus[feq]` | PyGEL3D |
  | `opus[terrain]` | fastscapelib (GPL-3), pydelatin, numba |
  | `opus[hulls]` | coacd |
  | `opus[uv]` | xatlas-python |
  | `opus[ref]` | opencv-python-headless (GrabCut) |
  | `opus[gpu]` | cupy-cuda12x |
  | `opus[lod]` | pyfqmr |

- meshoptimizer is not used: it is sdist-only on PyPI and needs MSVC. Decimate plus a measured Hausdorff error is the default.
- Reported cp313 win_amd64 wheels exist for all the extras. The Windows spike tests runtime behaviour, and an extra becomes required only after the spike passes.
- `opus doctor` reports which extras are installed and working.

**Data fetching.**
- `data_fetch <pack>` reads `packs.yaml` (mirrored in DOWNLOADS.md): url, sha256, size, licence ID, flags, attribution and target folder.
- Downloads are resumable and unpack into a fresh directory. Code that reads downloads runs with `python -I`.
- Each pack gets a `LICENSE.json` holding the licence text or page snapshot and the download date.
- **`data_fetch --from-file <zip> --pack <id>`** imports packs that have no stable URL (itch.io: KayKit, Quaternius, UAL). It records sha256, the licence-page snapshot and the date.
- `opus data build` derives local caches: gait and quadruped atlases, pose libraries, style canons, raw museum JSON. Every cache element carries the licence IDs and flags of its inputs. Caches are never committed.

**Provenance and licences.**
- **Ledger schema.** Each entry lists `inputs: [{source, licence_id, flags, role}]` and `tools: [{name, licence_id, flags}]`, plus the union of flags. Licence IDs are SPDX or `LicenseRef-*`, mapped to flags in the committed `data/licences.yaml`. The flags are `attribution`, `nc`, `sa`, `nd`, `no-redistribute-as-asset` (QAL), `use-restricted` and `unknown`.
- **Free text is never matched.** This replaces `ledger.py`'s substring test, which flags "licence", "since" and "including" as NC and misses the NVIDIA Source Code License.
- **Lineage.** `spec_build`, retarget and keyed motion copy the union of their inputs' flags into the output's entry. Tools are tagged too; for example, the GarmentCode Warp fork is `nc`.
- **Export policy:**
  - `unknown` blocks until the licence is classified;
  - `commercial: true` blocks `nc` and `use-restricted`;
  - `publish_assets: true` blocks `no-redistribute-as-asset` and `nd`;
  - `sa` stamps the output's licence;
  - `attribution` goes into CREDITS.md.
- **Tests** use the misfiring strings as fixtures: "QAL v1.0 licence", "Copernicus free licence with credit", "research and commercial projects", "CC BY 4.0 … since 2026", "Royalty-free incl. games" and "NVIDIA Source Code License".
- **Repo files:**
  - `LICENSE` (GPL-3.0 text) at the root;
  - `THIRD_PARTY_NOTICES.md` with each ported project's copyright line and full MIT, BSD-3 or GPL-3 text;
  - a header in every ported module (`ported-from: <repo>@<commit> (<SPDX>)`);
  - `data/LICENSES.md`;
  - a CI check that every `ported-from` module has a notice entry and every committed table and profile has a LICENSES entry.
- **Porting rule.** Code may be ported only from MIT, BSD, Apache-2.0 or GPL-3-compatible sources (MPFB2, Infinigen, Holden, Epic's robust transfer, Schott), with notices. Never from AGPL-only, ND, NC or unlicensed sources. This rule follows from the repo's GPL-3 licence; switching to MIT later would mean removing the GPL ports.
- **Engine-side output.** Import scripts and engine recipes emitted into the user's projects are original code under MIT, so no GPL obligations reach the games.
- **Poly Haven.** Requests send a unique User-Agent, and "Powered by Poly Haven" appears in the README, `library_search` output and CREDITS.md.

**CI** (`.github/workflows/ci.yml`, an S0b deliverable):
- runs headless Blender 5.2 with Workbench and CPU only: bpy snippets, every generator and every `defect_inject` suite;
- adds Godot headless import only if the runner can download Godot; otherwise that check is PC-only;
- leaves EEVEE and Cycles GPU checks to the PC.

**Removed from PLAN.md and DOWNLOADS.md** (the user's no-generative-models rule for 3D and animation):

| Location | What goes |
|---|---|
| PLAN.md:49 | Principle 3, rewritten as: "human-made libraries, mocap, measured data and the user's references are inputs; generative models are excluded for 3D and animation (their published methods and data statistics may be used)" |
| PLAN.md:62 | Principle 8, rewritten as: "stable interfaces sized to the PC: native packages and GPU accelerators sit behind optional extras with numpy fallbacks" |
| PLAN.md:81, 134 | Generative backends; `opus-gen` |
| PLAN.md:168–169 | Gen3D + Cleanup, Gen Texture |
| PLAN.md:192–193 | Concept-first 3D, AI texturing |
| PLAN.md:225 | Unity Generators as an asset source; MetaHuman marked "licence unverified, not used" |
| PLAN.md:254 | Mocap from video or text |
| PLAN.md:324–327 | TRELLIS.2 / trellis.cpp, Pixal3D, MeshAnything V2, Hunyuan3D Paint, paid image-to-3D |
| PLAN.md:342 | Wan 2.2 sprite animation (it is animation); suspended pending the user's answer below |
| PLAN.md:352–354 | Auto-rig models, text-to-motion, video-to-motion |
| PLAN.md:381–382 | Those roadmap items |
| PLAN.md:480–484 | "image-to-3D + cleanup" and "AI generation" routes in Honest limits |
| DOWNLOADS.md | trellis.cpp, the ComfyUI hub for 3D and motion, the motion-model rows |
| `doctor.py` | The ComfyUI check is relabelled "optional, 2D only" until the user answers |

Their papers' *methods and data statistics* remain usable.

**Open question for the user:** is the 2D image-model pixel pipeline (Z-Image, FLUX, PixelLab; `pixel_cleanup` itself is classical) also excluded? Until the user answers, it is untouched, because it is outside this document's scope.

**Documentation fixes:**
- **Quaternius:** QAL v1.0. The licence is recorded per pack from the page snapshot at download time, not as CC0 (PLAN.md:323, DOWNLOADS.md:38).
- **BONES-SEED:** eligibility for an individual is unclear, so skip it. PLAN's "free for anyone under $1M" overstates it.
- **Mixamo:** manual, optional input only, under revocable preview terms.
- **The Met:** `/v1/search` was retired; use `/v1.1/search`.
- **CDC ROM and NHANES:** "US Gov public-use data under 308(d)/NCHS data-use terms (statistical use only)", not public domain.
- **Muybridge:** fetched from a source with a stated public-domain or no-known-restrictions licence (Library of Congress or Wikimedia Commons).

---

## 3. How a design gets nailed down

### 3.1 Common opening (every asset)

1. `project_bible(show)`: camera profile, style, gate profile, budgets, `gravity_mult`, `weapon_scale`, licence policy.
2. `spec_new(kind, archetype)` returns a template that is about 90% complete, with defaults, slot anchors, library profiles and derived camera numbers.
3. Claude fills in the features (5–7, ranked, with views), shape-language mix, palette roles (sourced), must-avoid list and dials. Mood words go through the **adjective-to-dial table**:

| Word | Dials |
|---|---|
| menacing | triangle ≥60% of contour; shoulder:hip ≥1.4; one saturated accent ≤10% of area |
| friendly | curve ≥60%; superellipse n ≈2; larger head ratio (baby schema +0.5–1 SD) |
| sturdy | n ≥4; low centre of mass; square ≥60% |
| agile | slim limb radii (−0.5 SD); higher leg:torso ratio; triangle accent |
| ancient or worn | wear bevel tier +1; asymmetric rhythm, spacing CV 0.2–0.35 |

4. `spec_validate` reports derived numbers, a tier table (what is geometry, what is a map, what is omitted) and pixel warnings. **Nothing is built before this step.**

### 3.2 Without references

| Step | Tool | Detail |
|---|---|---|
| Morph box | `spec_new` / `spec_explore` | 4–6 discrete dials × 3–5 values. **Values are seeded from human-made variety:** typology lists (Oakeshott types, era presets), pack variants of the category, library profiles, and the user's style references. Claude may add at most one value per dial, tagged `design`. Zwicky cross-consistency pruning removes incompatible pairs. |
| Sample | `spec_explore` | Latin hypercube over `design` ranges × pruned configurations → 24–64 numpy evaluations (or thousands for real MAP-Elites, about 10–20 s) |
| Diversify | `spec_explore` | Descriptors on the evaluator's analytic outlines: elliptic Fourier contour, aspect, angularity share, area tiers. Design Galleries dispersion picks 6–9. |
| Show | `spec_explore` | Contact sheet at 128 px **and at true game pixel height**, with 2D lint (warnings) |
| Select | Audition Board, or `critique_pack(mode=tournament)` then `mode=lineup` | Tournament: both orders, incumbent included, ≤14 calls for 8. The winner is then lined up against exemplars at game size, and its dials are written into the spec. |
| Blueprint | `spec_preview` | Front, side, back, top and 3/4 views (az ≈35°, el 22.5°); shared landmark guide lines; head and metre grids; callouts in metres; a 1.8 m figure; game-pixel insets. Garments and harnesses show their numpy envelopes and plate outlines. |
| Lock | `spec_edit(tag=locked)` | Snapshots resolved values and `tables_version`. Every later gate measures against this revision. |

### 3.3 With references (references are converted to numbers)

**Valid references are human-made only:**
- user sketches and concept sheets;
- CC0 museum photos (Met with `isPublicDomain` true, Cleveland, AIC public-domain images);
- PhyloPic CC0 silhouettes;
- Muybridge plates;
- real DEMs;
- CC0/CC BY scans (for example the Swedish History Museum, CC BY 4.0);
- **the user's screenshots of games they like, as private style references.** These are used only for palette, proportion, size-tier and framing statistics. They are never fitted as geometry and never stored in the repo.

**Never** generated images.

`ref_extract(image, kind, known_dim)` works in these steps:
1. **Mask** by alpha, flat-background flood fill, threshold or GrabCut (`opus[ref]`), or a user polygon. No segmentation networks.
2. **Symmetry axis** by flip-IoU.
3. **Scale** from a known dimension (stature, blade length, withers).
4. **Perspective check.** The error is about dz/D; it warns above 5%, which needs D ≥ 20× the subject's front-to-back half-depth. An optional vanishing-point camera solve reimplements the maths (not fSpy's GPL code).
5. **Landmarks, automatic first.** Width-profile extrema and run topology on the mask find crotch, armpits, neck, shoulders and waist. This generalizes v0.2's `humanoid_landmarks` to creatures and side views (withers, hip, hock, elbow, chin).
6. **Internal boundaries** that a silhouette cannot show (hems, necklines, plate edges, sleeve ends):
   - Claude reads rows on a labelled 5% grid, then on 1% zoom crops, with the fitted body's landmark ruler overlaid.
   - Large images are downscaled to about 1568 px, so zoom crops are mandatory.
   - User clicks on the Audition Board are the fallback.
7. **Palette:** k-means in OKLab or CIELAB with k = 5–8, L* kept separate.
8. **Profile mode** (S4): contour → Douglas-Peucker → least-squares line/arc fit → a normalized library profile with provenance.

It outputs a spec patch (landmark ratios, coverage fractions, palette roles, profiles) plus target masks.

**Calibration (S1).** A 20-image test measures automatic and grid-read landmark error before the ±2% landmark tolerances are trusted. If the measured error is larger, the tolerances are widened to match.

**`spec_fit(spec, targets, dials)`**:

| Item | Setting |
|---|---|
| Objective | 1 − mean IoU + contour chamfer (distance transform) + λ·landmark ratio error + μ·depth error + ‖w − w0‖² regularized to the canon |
| Optimizer | CMA-ES or Nelder-Mead, 300–1,000 evaluations on the numpy raster |
| Creatures | Coarse to fine. CMA-ES runs on the 2D projected proxy at 96² (≈8 ms per view measured, so 400 evaluations × 2 views ≈ 7 s). Confirmation runs on the SDF raster at 128–256² (≈1 s per view brute force). IoU is then re-measured on the built cage. Inflate parts use 64². |
| Pose | Limb angles, neck and tail curve are dials, regularized like the radii, so CMA-ES does not distort radii to match a stride |
| Stop | IoU ≥0.92 for hard surface, ≥0.85 for creatures and organics |
| Perspective references, or posed references without pose dials | Landmark-only fit; IoU is not used |

**Reference sources by category:**

| Category | Sources |
|---|---|
| Humans | user turnarounds; ANSUR percentiles when there is no image |
| Creatures | PhyloPic CC0 sides (standing preferred); Muybridge per gait phase |
| Weapons and armor | Met/Cleveland/AIC CC0 photos and their measurements; traced profiles |
| Terrain | Terrarium or Copernicus crops, as a base or as statistics targets |
| Trees | Tallo species bands |
| Style (any) | the user's game screenshots (private) |

### 3.4 How the 3D build matches the design by construction

- **Same arrays.** `spec_preview` and `spec_build` call the same evaluator. The Blender emitter writes those triangles with `from_pydata` or `foreach_set` and adds only finishing.
- **Builders that reproduce profiles.** Station lofts take their half-width from the front profile and their half-depth from the side profile. Visual hulls are used only where the cross-section really is prismatic. Inflation is used for flat organic parts. SDF bodies take FEQ cages projected onto them. Cages at levels 0–1 sit inside the SDF by the chord sagitta, so radii are inflated by the measured mean inset before projection. **Cage-vs-SDF fidelity** is reported separately: symmetric distance p95 ≤1 game px, and per-view IoU ≥0.97.
- **Consistency gate (T2b).** It runs after the build and after any Blender-only operation, not on every `spec_check`. Projection conventions are pinned by a single-triangle unit test covering pixel centres, ortho scale, sensor fit and half-pixel offset. For each view:
  - whole-object IoU ≥0.99;
  - per-part symmetric boundary distance p95 ≤0.5 px, at a resolution where the smallest declared part spans ≥10 px (capped at 2048);
  - depth from BVH ray casts in the worker on a 128² grid, compared with the evaluator's z-buffer: p95 ≤ one game pixel's worth of metres at d_closest.

  A Blender-only operation (boolean, bevel, remesh, cloth) must change the game-camera raster by ≤1 px. Otherwise that part becomes `post_eval`.
- **`post_eval` kinds and parts** are re-rasterized from Blender's arrays after the build. The locked sheet is updated with a logged diff.
- **After the lock,** iteration converges rather than explores: `spec_build` → gates → one-dial `spec_edit` → re-gate what was affected plus the global gates → accept by rule.

---

## 4. Per-category pipelines

Every category goes through `spec_new → spec_validate → (explore | ref_extract + spec_fit) → spec_preview → spec_build → spec_check → critique_pack → export_asset`. The rows below cover only what is specific to each kind.

### 4.1 Characters: HD humans (`body.human`)

| | |
|---|---|
| **Build** | `human_build`: a numpy hm08 morph engine on MPFB2 CC0 data.<br>• base.obj is 1,749,303 bytes: 19,158 verts, of which the first 13,380 are body; 18,486 quads.<br>• Units are dm → ×0.1 m; Y-up → Z-up.<br>• **Full macro logic, ported from MPFB2 (GPL-3):** ethnic targets `{african\|asian\|caucasian}-{gender}-{baby\|child\|young\|old}` weighted ethnic × gender × age; universal targets carry muscle and weight; plus height, proportions, `measure-*` and local modifiers including the face modifiers. Porting `human.py` alone gives genderless, ageless bodies.<br>• Golden test against MPFB2. In S1 week 1, verify that MPFB2 runs on Blender 5.2. If it doesn't, generate the golden numbers once on the newest Blender it supports and commit only the numbers.<br>• Joints = mean of each 8-vertex helper cube.<br>• Rig: MPFB `game_engine` (53 UE4-named bones, stored rolls, **CC0 weights**, so no heat weighting) **plus 2 twist bones each in upperarm, lowerarm, thigh and calf**, with a linear weight split. Twist and helper bones live in the base skeleton.<br>• **`twist_policy`** (per project, set in S1): `baked` means every exported clip carries twist keys from swing-twist decomposition (linear in roll, so blend-safe); `runtime` means a UE post-process AnimBP or Control Rig, Godot `BoneTwistDisperser3D` or Unity Twist Correction. Clips retargeted in the engine always need `runtime`.<br>• Rest pose **A45** (armor fits there).<br>• Bone maps for Godot `SkeletonProfileHumanoid`, Unity Humanoid and UE Manny (IK Retargeter). |
| **Fit** | `fit_measurements`: bounded least squares on macro and `measure-*` weights against ANSUR percentile targets. Heights and breadths are exactly linear in the weights; girths take 3–5 Gauss-Newton steps on hull-perimeter slices; λ‖w − w0‖². |
| **Stylize** | EDFM s = μ + k(x − μ), k 1.2–1.6 per feature; baby schema (Borgi's 6 ratios) up to ±2 SD; head-count retarget. Before and after z-scores are reported. |
| **Low budget** | Proxies proxy741, male1591 or female1605 via MHCLO (verify they are in the system-assets zip), or the stylized routes (§4.2) |
| **Clothing fixture** | MPFB CC0 MHCLO clothes (3 base verts + barycentric weights + offset, `delete_verts` masking). Any morph is re-dressed in one call; they are also the test wardrobe for the garment gates. |
| **Face** | `faceunits01` ARKit-52 keys (CC0) come with the body (§4.11) |
| **Data** | ANSUR II (stature-normalized p5/p50/p95; head height derived as 7.43 HU for men, 7.33 for women); NHANES BMX for children and heavy bodies; de Leva segment parameters |
| **Expected fidelity** | MakeHuman-grade bodies and faces. Close-up hero faces stay limited (§10). |
| **Hard gates** | Weights: ≤4 influences, Σ = 1 ± 1e-4, no zero-weight vertices. Left/right leak judged by the sign of the bone head's x (+X = left). Topology contract: hm08 vertex count and order unchanged (targets and MHCLO depend on it). Mirror median <0.5 mm, max <2 mm. Budget +10%. Twist keys present in exported clips (policy `baked`). |
| **Soft until calibrated** | Topology: quads 100% and poles of valence 3/5 outside joint zones (no engine requires quads).<br>Landmark ratios inside p5–p95 or the declared stylization; fit residual ≤1% of stature (girths ≤2%).<br>`deform_test` in **pure LBS** (preserve-volume off, no Corrective Smooth), also run on the FBX/glTF re-import: elbow and knee 90/135°, shoulder abduction 120°, hip flexion 90°, forearm twist 60°, spine 30°, neck 45° → volume loss ≤15%, ring-radius ratio ≥0.6, stretch ≤2×, 0 self-intersections. Twist thresholds are calibrated on the paired with/without-twist hm08 bodies (§2.5).<br>de Leva centre of mass inside the support hull with ≥10% margin; blind read top-1. |
| **Repair path** | Twist-bone weight split first, then pose-driven corrective shape keys (UE Pose Driver plays them) |

### 4.2 Characters: stylized, low-poly, chibi (`body.creature` with a humanoid donor)

| | |
|---|---|
| **Canon** | `style_canon_extract` runs over CC0 Kenney and KayKit packs, and Quaternius (QAL; measured locally, never redistributed). It writes a canon:<br>• heads tall and landmark fractions;<br>• triangle, bone and influence budgets;<br>• bevel-to-size ratio, palette size, flat-shading share;<br>• **facet statistics:** planar-region size distribution, dihedral histogram, silhouette vertex count at game size. |
| **Build** | `sdf_body` (smooth-min k ≈2–3% of height), then one of two routes, or both compared:<br>• **Route A:** `creature_cage` FEQ at levels 0–1 (about 350–1,400 quads).<br>• **Route B:** `facet_loft` (K = 6–8 rings with explicit hard edges at silhouette turns), or planar clustering of route A.<br>Both are scored against the canon's facet statistics and checked in a lineup. Hands: hm08 hand topology scaled to the canon, FEQ finger branches, or mittens. Palette-atlas UVs with colours from the pack palette or a reference.<br>**Chibi is never a shrunken adult:** retarget the head count on the canon. |
| **Gates** | As §4.1 for weights. Inverted faces 0 against **both** the SDF gradient and the cage normals (>90°); BVH self-overlap 0. Soft: canon budget ±10%, facet statistics inside canon p5–p95, readability at game size, lineup. |

### 4.3 Creatures (`body.creature`)

| | |
|---|---|
| **Spec** | Donor composition: base plan (canid, felid, equid, bovid, bird, bat, pterosaur, varanid, crocodilian, insect, arachnid) + declared stance + mass_kg + length + grafts {part, donor, attach to a girdle}. Variants are **convex combinations of 3–5 exemplars**, never noise on handles. **A donor template ships only after `spec_fit` has fitted it to ≥2 PhyloPic or Muybridge references.** |
| **Donor tables (S2)** | **Data:** Garland & Janis (mammal hindlimbs), Fischer 2002 (scapula), AVONET and Wang 2011 (bird wings).<br>**To fetch from primary papers in S2; tagged `recalled` (warnings only) until fetched:**<br>• bat wing-bone ratios and Norberg & Rayner span, area and aspect-ratio scaling (AR 5–11 via review);<br>• pterosaur limb ratios;<br>• varanid limb, neck and tail ratios (candidate: Christian & Garland 1996);<br>• crocodilian limb and tail ratios. |
| **Limb chains** | Hindlimb = nearest Garland & Janis species × (M/M_ref)^0.35, split by **that species' MT/F** (wolf 0.437, horse 0.806, lion 0.348); femur ≈ tibia; phalanges added separately.<br>A scapula is the dominant forelimb segment, with the scapular pivot at hip height (Fischer 2002).<br>Hierarchies come from the bundled Rigify metarigs, **with their proportions overridden** (artist foot/thigh: wolf 0.79, cat 1.18, horse 1.08, vs the data).<br>Limb thickness: per-family robustness from data, never d ∝ l^1.5. |
| **Grafts** | Every graft attaches to a girdle; a third limb pair gets its own girdle and shoulder mass. The wing girdle sits over the forelimb girdle at a `design` fraction of trunk length. Neck, tail and head lengths are donor-table fractions (p5–p95) with a logged `style_mult`. |
| **Wings** | Plausibility comes from **wing loading and aspect ratio**, not from a span formula. Span from the band: S = M·g/(W/S), b = √(AR·S).<br>• Heavy flapping fliers sit at about 150–250 N/m² (`recalled` until Pennycuick is fetched in S2).<br>• Primaries 0.79–1.55 × arm-bone length (Wang 2011).<br>• Raptor proportions from AVONET.<br>• Membranes are inflate sheets. |
| **Surface** | `sdf_body` → `creature_cage`:<br>• PyGEL3D `skeleton_to_feq` (host), with joint-loop nodes at t = 0.5 and 0.88 of bending bones;<br>• Catmull-Clark ×2;<br>• 40 rounds of Newton projection plus tangential relaxation (**vectorized** with a sparse adjacency matrix; the list version took 8.5 s at 5.6k verts), then a final projection.<br>Ears, fins and membranes are separate inflated sheets. |
| **Rig** | Heat weights only on the closed cage body, limited to 4 influences. **Ears and fins are bound rigidly to one bone.** **Membranes are weighted analytically by distance to their spar bones**, normalized over the two bounding spars, top-4. No geodesic voxel bind: it is not a Blender feature. |
| **With reference** | PhyloPic CC0 sides (standing preferred) or Muybridge → `spec_fit` on radii, joint scalars and pose dials (§3.3) |
| **Hard gates** | 0 inverted faces (SDF and cage normals); BVH self-overlap 0; edge-length ratio ≤20; every limb chain has a girdle; flexion signs match the donor (knee apex forward, hock and elbow back); weights as §4.1 |
| **Soft** | MT/F within 10% of the nearest species; hindlimb vs mass within ±25% of the power fit; centre of mass in the support hull; flight band (style overrides logged); silhouette IoU ≥0.85 against the reference, measured on the cage; cage fidelity; quadruped `deform_test` (neck ±45°, tail curl, hock/knee/elbow flexion); blind read names the species. A hybrid must read as both donors. |

### 4.4 Clothing (`garment`)

| | |
|---|---|
| **Spec** | Archetype library: tunic, shirt, doublet, gambeson, trousers, skirt, circle skirt, robe, coat, cape, hood, tabard.<br>• Coverage as landmark or bone fractions.<br>• **Ease %** from FreeSewing (shirt 15/15/5/20, T-shirt 12/18, trousers 2/2/6, coat +10), cross-checked against Opian's cm table.<br>• **Layer clearance:** L0 1–2 mm, L1 3, L2 4–6, L3 6–10, L5 straps 1–3.<br>• **Fabric** sets thickness, ARCSim areal density (denim 0.324, interlock 0.187 kg/m²) and Blender cloth preset. |
| **Envelope preview (numpy)** | Station-slice convex hulls of the body or the layer below, Steiner ease offsets and coverage boundaries are rasterized at game size for explore and lock |
| **Target surface** | Per-part SDF closing (Mesh to SDF Grid → offset +r/−r or Fillet → Grid to Mesh) bridges armpits and crotch the way a tape measure does. One SDF per part, so arm and torso don't fuse. Each layer wraps **the outer cage of the layer below**, never the bare body. |
| **Build** | **`garment_shell`** (fitted): extract region → Steiner ease offset d = ease × P_hull / 2π, with **P_hull shrunk 2–3%** to match tape measurements (hull girths overestimate tape by +2.81 cm at the bust in GarmentCodeData) → Shrinkwrap OUTSIDE **last** → Solidify offset +1.<br>**`garment_loft`** (tubes and flares): ring radius r = max((hull_r + c)/cos(π/K), r_ease), where r_ease makes the polygon perimeter (1 + ease)·P. K is 6–8 low-poly, 12–16 mid, 24–32 HD. Joint-loop triplets; analytic UVs with the seam on the medial side.<br>Above 10% ease, a **support-zone rule** keeps shoulders and waistband at clearance only; otherwise the part goes to the drape pass. |
| **Weights** | `weight_transfer_robust` (Epic 2023, ported from the MIT reference): match within D = 0.05 × bbox diagonal and normals within 35°, plus a flipped-normal pass; bi-Laplacian inpainting on the unmatched set + 2-ring with scipy; forced inpainting between the legs and at collars; clamp, top-4, renormalize. **Final topology first.** |
| **Masking** | `body_mask`: bone-ray test with reach \|v − o\| + 0.15 m and a 20–30 mm opening buffer, stored per outfit.<br>**`layer_mask`**: the same test deletes inner-layer faces under opaque outer layers. Inner-layer vertices within 2× the outer layer's clearance then take the outer layer's weights (robust transfer outer → inner), so the layers bend together. |
| **Detail** | `fold_pass`: cause-tagged design folds only. Rohmer rule: trace only at ≥10% compression, spacing ≥2 Rmin (Rmin values are guesses). Tension folds from Cerda–Mahadevan λ ~ (B/K)^¼; catenaries for two-point supports. Joint compression folds go to normal maps or wrinkle maps.<br>`trim_kit`: buttons sized by ligne, belts 30–40 mm.<br>Optional bounded `drape_sim`: mass per vertex = density × area / vertex count; distance_min 2–5 mm; 5–10 zero-gravity frames; pins; ≤5–10k verts.<br>Secondary chains: skirt 6–8 × 3–4, cape 3–5 × 4–6.<br>GarmentCode's own Warp simulator (NVIDIA SCL, flag `nc`) runs out-of-process, only for hero sewing-pattern garments. |
| **Hard gates** | `rom_check(mode=garment)` over 14 range-of-motion poses (10–20 extremes while iterating, the full battery at sign-off): 0 unmasked body penetrations >1 mm (pseudonormal or winding-number sign); garment-to-garment ≤0.5% of vertices after `layer_mask`; weight hygiene with leak test; 0 see-through pixels |
| **Soft** | Rest clearance min ≥0.8 × layer clearance, p95 ≤ clearance + d + 10 mm outside drape zones; ease achieved ±2 pp at chest, waist, hip, biceps, knee; coverage ±1 cm or ±1 output px; layer steps and hem lips ≥1 px (outlines ≥2 px); modelled folds ≥3 px; drape settled when ≤1.5% of verts move >0.4 mm/frame, ≤35 body-intersecting edges and ≤300 self-intersections |

### 4.5 Armor (`harness`)

| | |
|---|---|
| **Spec** | Era presets: 1250 mail, 1350 transitional, 1450 Gothic/Milanese, 1520 Maximilian, 1600 cuirassier/munition, lamellar, brigandine, sci-fi light/medium/heavy.<br>Ranges come from Met v1.1 and AIC CC0 dimension strings: robust p5–p95, each tagged **projected vs surface/girth**, with outliers such as a 198 cm "breastplate" removed. Thickness from Lazar & Kraner (CC BY 4.0).<br>**Shapes come from the profile library:** outlines, cusps and flute lines traced from CC0 Met, AIC and Cleveland photos and CC BY Swedish History Museum scans, scaled by each record's dimension string. |
| **Envelope preview (numpy)** | Station-slice envelopes with the standoff table, plus plate outlines laid out in pattern space, rasterized at game size for explore and lock |
| **Poses** | `rom_poses`: CDC limits × 0.85–0.9 (US Gov public-use data; Enlyte, which is unsourced and `recalled`, only as a fallback). Limits are **split across clavicle/upperarm (about 2:1 scapulohumeral) and pelvis/thigh**, with a per-rig axis map verified once by render. Add compound gameplay poses and the user's clips. Iterate on 10–20 extreme poses; run the full battery at sign-off. |
| **Regions** | `armor_regions`: rigidity residual over the battery, τ 3 mm HD / 6 mm low-poly. A seed only, bounded by bone-length priors. Plate extents = p5–p95 stations; open zones listed (elbow pit, back of knee, armpit, groin). |
| **Shells** | `armor_shell`: station-slice convex envelope plus a standoff profile (breast 25–40 mm, back 15–25, upper arm 10–20, thigh 15–25, shin 10–15, skull 15–30) and a superellipse per station. **Caps** (skull, pauldron dome, cops, toes) use a radial (θ, φ) envelope or a convex hull plus offset. Library outline cut in pattern space; Solidify; rolled edge 8–13 mm.<br>`helmet_build`: W / head breadth 1.25–1.55; visor hinge at the temples swept 0–100°; gorget rings coaxial with neck yaw. |
| **Articulation** | `joint_articulation`: **concentric spheres about the child bone's head** (cylinders only on hinge-locked joints).<br>• n_int = ceil(θmax/25°);<br>• overlap ≥ θ/n + 5°;<br>• r_k = R + k(t + g), with g ≥1 mm HD and ≥2 mm third person;<br>• wing B = 0.45A; rivets on the axis; slot length ρΔθ + d;<br>• nesting rule e_max = √((R_in − c)² − r²). |
| **Rig** | Every plate on **one bone at weight 1.0**. Linear followers: helper parented to the parent bone with Copy Rotation (LOCAL, ADD, i/n), baked with `anim_utils.bake_action`. **Nonlinear** followers (push-only tassets, k·max(0, θ − θ_free); the pauldron swing ramp, which is a guess) are emitted as engine recipes: UE Control Rig or AnimDynamics; Godot `ConvertTransformModifier3D`, `BoneTwistDisperser3D`, `SpringBoneSimulator3D` + capsule; Unity Multi-Rotation or Damped Transform. Twist and helper bones live in the **base skeleton** (UE Leader Pose, Godot shared Skeleton3D). |
| **Soft layers** | `soft_layer_fit` through §4.4, including `layer_mask`: gambeson 10–25 mm; mail as ambientCG Chainmail001–004 textures with a modelled hem; surcoat. Sci-fi: shells on rigid zones, an undersuit at joints, `panel_split` (3 levels; tunable defaults, not gates). |
| **Hard gates** | `rom_check(mode=armor)`: body–plate triangle overlap 0; inner-sheet depth ≤2 mm third person / ≤0.5 mm first-person gauntlets; piece–piece overlap 0; lame overlap ≥5° and ≥3 mm through a 5° sweep including off-axis rotation; plate edge strain ≤0.2% with a single influence; FBX round trip changes penetration by ≤0.5 mm |
| **Soft** | Exposure ≤5% at rest, ≤15% at extremes outside open zones; standoff p5 >0, median ≤2× target; piece size and mass (7850 kg/m³ × area × t) within [0.8·min, 1.2·max] of Met ranges; harness area 0.9–1.1 × body surface; edges, rivets and slits ≥2 px or exaggerated |
| **Repair order** | 1. **Articulation first:** more interfaces, adjusted sphere radii and overlap.<br>2. **Then θ_free and follower fractions.**<br>3. **Trim last, as an optimization:** `trim_to_clear` minimizes trimmed area subject to zero penetration and exposure ≤ its ceiling, solved jointly (§2.6). It never trims alone. |

### 4.6 Weapons (`assembly`)

| | |
|---|---|
| **Sheet** | `dims_resolve(sword/XIV \| axe/dane \| spear \| bow/longbow \| shield/round \| firearm/pistol \| firearm/rifle_carbine \| scifi_gun \| staff, wielder)`. Sources:<br>• Oakeshott via Albion and Wikipedia (conflicts kept as ranges);<br>• Cleveland CC0 structured sword dimensions (511 records); Met v1.1 strings;<br>• Wikidata **psn-normalized** values (557 firearms with length);<br>• wielder formulas: handle d_eq = 0.197 × hand length, about 38 mm at p50 male, checked as circumference/π on oval grips; grip length from typology, with ANSUR as a sanity bound;<br>• bible `weapon_scale` (Kenney blasters are about 2× real). |
| **Graph** | Slot templates with named anchors. Sword = pommel/grip/cross/blade. Firearm: barrel on the bore axis; chamber where the bore and mag-well axes meet; sights on a line parallel to the bore; stock at length of pull (recalled → warning); ejection port right. Magazine, bolt and slide are separate parts with prismatic joints. Sockets: `grip_main`, `grip_off`, `muzzle`, `sight_*`, `mag_well`. |
| **Builders** | Blade station loft at the library's stations, w = lerp(w_b, w_t, s^k), distal taper 4.7–6.1 → 2.0–2.2 mm, fuller fraction per type. Lathe pommels and barrels with sagitta segment counts; extruded guards and axe heads; visual hulls for receivers. **Every outline is a library profile or a constraint sketch.** Low-poly can kitbash KayKit or Kenney parts (`library_import`, `kitbash` gate profile). |
| **Finish** | `hs_finish` from the camera (§2.2): cutting edges and points get bevel weight 0; segments 1 for low-poly, 2–3 HD, 3–4 first-person hero; panel lines ≥3 px as geometry, 1–3 px as maps, <1 px omitted |
| **Function** | `mass_props` (Eberly integrals, density per part) → PoB from the cross plane; **CoP = I_pivot/(M·r)** about a declared pivot (not 0.66 L). Mass and inertia feed animation timing. `function_check`: magazine and bolt sweeps; axis intersections. Then `grip_define` (auto from sockets), `grip_hold`, `grip_check`. |
| **First person** | **View-model camera profile** from the bible (its own FOV, near plane and scale: the project's UE first-person rendering settings where available, or a second camera in Godot or Unity). px_per_m for first person uses this profile.<br>**Hip framing is solved, not typed.** Screen-space targets: grip and muzzle at screen fractions, screen coverage %, muzzle convergence on the crosshair at N m. The targets are measured with `ref_extract` from the user's screenshots of first-person games they like, or picked on the Audition Board among 6 dispersed framings. v0.3's typed hip offset (0.5, 0.2, 0.18 m) is retired.<br>Procedural idle sway, walk bob, recoil and ADS blend are springs with per-frame `grip_check`: muzzle inside the frustum, no near-plane clipping, contacts held. |
| **Hard gates** | 0 sheet violations; as-built within 2% or 1 mm (station slices); contacts ≤0.5 mm FP / 2 mm TP; undeclared overlaps 0; firearm axes meet at the chamber, sights ∥ bore ≤0.1°, magazine path free; planar-face normal spread <1°; sockets and hulls present; one collidable or socketed mesh per FBX |
| **Soft** | Mass and PoB in the typology band (arming sword 0.9–1.5 kg, Albion PoB about 11 cm); grip d_eq 30–40 mm × wielder scale; set silhouette IoU <0.8 at the smallest game size (calibrate on the 18 Kenney blasters); low-poly about 300–900 tris (Kenney median 478); class feature ≥3 px; hip framing within 2% of its screen targets |

### 4.7 Props and objects (`assembly`, `layout`)

| | |
|---|---|
| **Sheet** | Infinigen ranges **re-checked against ANSUR**: seat top = popliteal p50 + 25 mm = 455 mm, not Infinigen's 0.47–0.54; depth ≤ female p5 buttock–popliteal 441 mm. ABO item dimensions (CC BY); ADA (tables 710–865 mm, doors ≥815 mm clear); Poly Haven API dimensions, polycount and TD as HD bounds. |
| **Build** | PartNet-style And/Or slot templates (chair = back/seat/base{legs \| pedestal \| star}/arms) with squeeze for legs and library profiles. Or `library_import` of Kenney, KayKit or Poly Haven parts, normalized by an anchor dimension on the **evaluated world bbox** (Kenney GLBs carry node scale; furniture is about 0.5×), with orientation fixed and anchors added. Joint graph JSON for doors, drawers, lids and chests feeds open/close clips. |
| **Kits** | Footprint F; snap F/2; every vertex on an F/16 grid; fixed pivot and floor thickness; door size fixed early; 1way…4way naming |
| **Breakables** | `fracture_prefab`: Voronoi seeds denser near the impact (∝ 1/(r + r₀)); l_min from the camera; support graph; interior material; CoACD hull and mass per fragment |
| **Vehicles and mechanisms** | Contract rigs: wheel bones FL/FR/BL/BR; UE wheel radius in cm with sphere bodies; Godot `VehicleWheel3D` import script (forward axis to confirm in 4.7); gears by Copy Rotation ratio −N₁/N₂ |
| **Dressing** | `layout` kind: Infinigen-Indoors-style constraints (StableAgainst, SupportedBy, min_distance, angle alignment, accessibility, freespace) solved by staged annealing; motif programs for racks, shelves and rubble |
| **Hard gates** | Contacts and components per `spec_check` under the asset's gate profile; articulation sweep (16 poses) with 0 overlaps; kit harness: 0 unmatched boundary edges (0.1 mm KD-tree), 0 coplanar overlaps; fracture: volume sum within 1%, all fragments manifold, none < l_min, every non-anchor connected; vehicle: wheel bone ≤1 mm from the centroid, \|r − mesh\| <2 mm, wheels on the ground ±1 cm; hulls: volume ratio 1.00–1.15, distance ≤2% of the diagonal |
| **Soft** | Centre of mass in the support hull with ≥5% margin, empty and loaded; drawer ≥70% extension, door ≥90°; layout score terms |

### 4.8 Landscapes (`terrain`)

| | |
|---|---|
| **Spec** | Player metrics (from the engine contract table); world_m = minutes × 60 × speed × 1.2–1.5; cell 1 m first/third person, 0.5–1 top-down, 2–4 low-poly; engine size (UE 1009/2017/4033; Unity 2ⁿ+1). Lynch elements: critical path, POIs every 150–300 m, 1 primary and 2–4 secondary landmarks, edges, districts, a vista ring of 10–20%. Primitives with numbers: ridge polylines (crest_m, flank_deg), mesas (cliff 50–70°), passes, lakes, rivers with monotone beds. Targets. **The layout diagram is reviewed before any heightfield exists.** |
| **Build** | `terrain_build` (uv venv), in this fixed order. **Hydrological conditioning is the last height edit.**<br>1. Primitives blended with smax/smin (k 5–30 m), base noise, domain warp of 5–10% of map size.<br>2. **Relief calibrated before erosion**, in closed form on macro + base noise: R = tan(target)/quantile(\|∇h\|), on unauthored components only (primitives are hard constraints).<br>3. fastscapelib uplift + stream power from the ridge polylines (K 2e-4, m 0.4, n 1, Kd 0.01, MFD) at 256–512², about 6 s per 50 steps at 512². Post-erosion slope is checked, never rescaled.<br>4. Schott 2024 multi-scale amplification presets (MIT; numpy ≤512², CuPy above; the full CPU preset takes 25–30 minutes).<br>5. Detail fBm (H 1, lacunarity 2.01/1.99, octaves = log₂(λ/(2–3 cells))) × an amplitude map: **0 in river, road and pad corridors**, 0.03–0.15 on paths.<br>6. Optional droplets at a **2–4 m working cell, heights normalized to about N/255**, with a hardness mask.<br>7. Thermal talus (tan 0.9–1.4 noise on rock).<br>8. Pads. Roads by Galin k = 5 A* **planned on the ≤512² working grid and refined in a corridor at full resolution** (grade caps, cut and fill). **Road–river crossings become bridge or ford segments, with no fill in the river corridor.**<br>9. Gradient-domain slope clamp on paths (Poisson rebuild), masked away from river corridors.<br>10. Re-add 10–20% detail with the same corridor mask.<br>11. **Rivers carved last:** width ∝ A^0.5, monotone beds, meanders 10–14 × width; lakes from the fill difference.<br>12. **Final conditioning:** priority-flood with epsilon (or breaching), masked to authored lakes. How much this step raises each cell is the measured pit signal (hard gates). |
| **Paint, scatter** | Splat thresholds fitted from ESA WorldCover × Copernicus slope, elevation and aspect (jittered smoothstep). Multi-layer Bridson scatter with habitat masks, Thomas clusters, optional Deussen thinning. Cliff bands >50–60° get CC0 rock-kit meshes plus a triplanar note (heightfields can't overhang). |
| **Real places** | `dem_fetch`: Terrarium (keyless; h = R·256 + G + B/256 − 32768) or Copernicus GLO-30 (decoded by Pillow; it's a DSM, so smooth it). Mode `stats` (the default) turns slope histogram, hypsometric integral and spectral slope into targets. Mode `base` crops and amplifies; with FABDEM it stamps the exported maps BY-NC-SA (flags `nc, sa`). |
| **Styles** | Low-poly TIN via pydelatin (bisect max_error to the triangle budget; 1024² → 90k tris in 0.22 s); top-down terraces in 3–6 levels; side-scroller 1D profiles bounded by jump metrics |
| **Export** | UE 16-bit PNG/r16, XY scale = cell × 100, **Z scale = range_m × 100/512**, actor Z at the midpoint; Unity via a generated C# `SetHeights` script (MIT); Terrain3D r16, or EXR (written by the worker) in real metres (scale 1, offset 0); weightmaps; PCG CSV; river splines and bridge segments; sidecar JSON |
| **Hard gates** | Valid size, uint16, round trip ≤1 LSB; 100% of cells drain; **final conditioning raised no cell by >0.5 m outside authored lakes** (a raised cell becomes a finding that names the stage that made the pit); river uphill steps = 0; every POI in the main walkable component; splats sum to 1 ± 1/255, ≤4 layers per component; scatter: 0 instances on roads, water or pads, sink ≤5 cm |
| **Soft** | Mean slope in band; walkable % (≤ engine floor angle − 5°) ≥ target; largest connected walkable component (eroded by the capsule) ≥0.75; POI travel 30–60 s (`MCP_Geometric`, 0.57 s at 1024²); critical-path grade cap; landmark visible from ≥70% of path samples at ≥2° (R² sweep with about 4N rays); crest fidelity 2–3 cells; D8 anisotropy <1.2; border band ≤2× the interior; spectral slope ±0.5 of the DEM target |

### 4.9 Trees and foliage (`tree`)

| | |
|---|---|
| **Build** | `tree_factory` (port of the numpy parts of Infinigen, BSD-3, with notice):<br>• height, crown radius and DBH from **Tallo** quantile fits (H ~ a·DBH^b, CR ~ c·DBH^d) per species or biome; Claude picks a species and percentile, never a size;<br>• momentum paths for the trunk;<br>• space colonization (N 375–12,000 attraction points; kill distance 2–20 D; influence ∞ or 8–17 D; step ≈1.5 D; pull +z for excurrent, −z for pendulous);<br>• pipe-model radii with n 2.0–2.5;<br>• Curve to Mesh with profile 16 (trunk) or 4 (twigs), `post_eval`;<br>• leaves at the 137.5° divergence angle → alpha cards. |
| **Game delivery** | Crysis wind vertex colours (R edge stiffness, G phase, B leaf stiffness, A AO) plus main bend, or Pivot-Painter-style pivots for UE; `lod_chain` plus hemi-octahedral impostors (8–12 grid); UE Nanite foliage for HD. Low-poly: smooth-min blob crowns fitted to k-means clusters of attraction points, flat shaded, or library trees scaled by Tallo. Grass and flowers come from Infinigen grassland ports, or shells for short grass. |
| **Hard gates** | Branch–branch BVH overlap 0; wind attributes present and in range; LOD error × px_per_m ≤1 px at each switch distance |
| **Soft** | Pipe residual \|r_pⁿ − Σr_cⁿ\|/r_pⁿ ≤5% per junction; H, CR and DBH in the Tallo p5–p95 for the species; crown porosity at the game camera in band; card count and triangles within budget; blind read: conifer vs broadleaf |

### 4.10 Buildings and interiors (`building`, `kit`, `layout`)

| | |
|---|---|
| **Build** | `building_grammar`: CGA-style `split(axis){size: op}` with absolute, relative and floating (~) sizes so facades fill exactly; repeat n = max(1, round(L/s)); component splits; leaves instance kit pieces or call generators.<br>`kit_wfc`: simple-tiled WFC over socketed kit tiles with D4 symmetry; minimum entropy plus propagation; restart on contradiction; navigability post-check.<br>Interiors are dressed with `layout`. |
| **Numbers** | ADA scaled by canon height / 1.75 m: door clear ≥815 mm, headroom ≥2030 mm, risers 100–180 mm uniform, treads ≥280 mm (pitch ≤32.5°), handrail 865–965 mm (Ø 32–51 mm), ramps ≤1:12. Bethesda kit rules (footprint multiples, fixed pivot, passages ≥2 character widths). Godot gets ramp colliders ≤45° under stairs (no step climbing); UE uses its walkable floor angle. |
| **Surface** | Trim sheets (strip scaling ≤±25%); LockBorder LODs for kit seams; xatlas UV2 for lightmaps; HLOD or impostor batches |
| **Hard gates** | All vertices on the F/16 grid; 0 unmatched boundary edges, 0 z-fighting pairs; WFC socket mismatches 0; every POI reachable (scipy label + A*); door clear width by ray cast at 1.0 m; riser max − min ≤5 mm; collision present and named per engine |
| **Soft** | Pitch, rail height, ramp slope and vertical clearance along paths; facade bay rhythm; TD within one power of two of the bible |

### 4.11 Hair and faces (`face`, `hair`)

| | |
|---|---|
| **Face shape** | HD: MakeHuman face modifiers; sanity bands from ANSUR (bizygomatic 143/134 mm, head length 200/190 mm) and neoclassical canons. Stylized: baby-schema operators in SD units. Basic face-shape operators ship in S3 for the regression subjects. |
| **Face contract** | `face_contract`: exactly the **ARKit-52** names, 0–1, with left/right from the face's point of view; a jaw bone; eye bones; lids that follow eye pitch; jawOpen = 1 at 40–50 mm; eyeball ≈24 mm. hm08 gets `faceunits01` directly. Stylized heads get the keys by surface-correspondence transfer, or a declared minimal subset (jawOpen + both blinks). |
| **Face motion** | `motion.face` kind (§5):<br>• FACS recipes (happy 6+12, sad 1+4+15, surprise 1+2+5B+26, anger 4+5+7+23, …) through a fixed AU→ARKit table (our own convention; validate once visually), with intensity A–E = 0.2–1.0 and onset/apex/offset envelopes;<br>• **lip sync, two paths.** *No audio:* CMUdict phonemes + a duration table. *With audio:* classical energy and onset segmentation, plus word boundaries the user marks on the Audition Board (or TTS timing when the user's TTS supplies it). Both feed JALI rules (m b p close; f v lip to teeth; lip-heavy visemes start early and override; tongue-only phonemes leave the lips; onset −120 ms, hold to 75%, decay 120 ms, protrusion 150 ms). Rhubarb only after the user confirms;<br>• eyes: Poisson blinks about 17/min at 100–400 ms; main-sequence saccades; a blink on gaze shifts >30°. |
| **Hair** | `hair_builder`, stylized and low-poly (v0 in S3 for the regression subjects): hairline, parting and whorl from head landmarks; Poisson-disk roots in scalp UV; a flow field combed from the parting; superellipse clumps (n 2–4) tapered to the tip; kept outside the head SDF plus clearance; long clumps on spring chains.<br>HD: Blender hair curves → k-means clumps → cards → atlas bake (alpha, depth, root-tip gradient, ID).<br>Fur: 16 shells + fins (Lengyel 2001) with an engine shader recipe. Many MakeHuman hair packs are CC BY, so the ledger keeps attribution. |
| **Hard gates** | ARKit names exact; lip gap ≤1 mm at every bilabial apex; labiodental ≤2 mm; scalp ray coverage ≥98%; hair-to-head signed distance ≥ clearance at rest and over ROM |
| **Soft** | Sibilant jawOpen ≤0.3; onsets 100–150 ms before the sound (audio path only); over 60 s of idle, 10–25 blinks/min; lid covers the iris top at all pitches; card overdraw at the game camera within budget; clump spacing CV 0.1–0.35 (not helmet-uniform); blind read names the hairstyle and expression |

### 4.12 Surface layer (`surface_build`, `surface_report`)

Runs on every asset after the shape gates pass.
- **v0 (S2)** is applied to every eval subject: palette atlas, baked AO and curvature masks driving edge wear and grime (PLAN's Material Lab wear, revived), and measured PBR.
- **S4** adds hero bakes.
- **S8** delivers the full plan.

| Stage | Rules |
|---|---|
| UVs | TD = px_per_m(d_closest) → power of two; R = TD·√(A/η).<br>Seams from part-graph and material boundaries, dihedral ≥60° on hard surfaces, placed on the declared hidden side. Lofts and sweeps keep analytic UVs.<br>Otherwise: `unwrap(ANGLE_BASED)` → `average_islands_scale` → `pack_islands(CONCAVE, margin = 2^k/R)`. xatlas for UV2 and junk geometry.<br>Low-poly: palette-atlas swatch UVs (one material, 512² colormap, Kenney convention). Modular: trim strips. |
| Bake | Cycles headless on the GPU (re-enabled after every worker reset); triangulate first; margin 2^k EXTEND (16 px default).<br>Base colour, ORM (R = AO, G = roughness, B = metallic), normal with **green NEG_Y for UE, POS_Y for Godot and Unity**.<br>AO and curvature masks drive wear and grime rules (edge wear on convex curvature, grime in AO). Procedural materials are **always baked** (they don't survive export), and the material is rebuilt on image textures. |
| Materials | physicallybased.info measured values (iron [0.530, 0.513, 0.494], metallic 1); DONTNOD ranges (dielectric sRGB 50–243, metal ≥186); ambientCG, Poly Haven or the MatSynth CC0 subset scaled by physical size.<br>**Palettes are never typed hex.** They come from measured CC0 pack palettes, Lospec palettes (local only; licence unstated), or reference k-means. The O'Donovan rating model (CC BY-NC-SA, local) is a report-only score. |
| LOD | Decimate + measured Hausdorff error (default), or pyfqmr (`opus[lod]`) if the spike passes; LockBorder for kits; dᵢ from τ = 1 px.<br>Engine policy: Godot auto-LOD on import (ship the base mesh plus impostors); UE Nanite for static opaque meshes (no morphs, no translucency), classic LODs for skeletal; Unity LODGroup. |
| Collision | CoACD threshold 0.05, max_ch_vertex 32–256 (`opus[hulls]`; convex hull per part as fallback); `UCX_` for UE, `-colonly`/`-convcolonly` for Godot; one collidable mesh per FBX |
| Pixel art | `pixel_preflight`: part-ID mask at sprite scale with no AA; every defining part ≥2 px; a flicker metric on a slow pan. Then `pixel_render` (S6): orthographic N-direction cameras, film filter 0, toon ramp (Shader-to-RGB → colour ramp), outline, palette lock, per-frame normal maps (the Dead Cells route). |
| Hard gates | 0 flipped UV triangles; 0 unintended overlap pixels at R; island gap ≥2^k; 0 NaN or black texels in coverage; green channel matches the engine; power-of-two sizes; LOD error ≤1 px with ≤0.5× the triangles of the previous level; hull volume ratio 1.00–1.15 and distance ≤2% of the diagonal |
| Soft | TD CV ≤0.10–0.15 per asset and set median within one power of two of the bible; conformal distortion p95 ≤1.5 organic / ≤1.2 hard surface; bake normal-angle error p95 ≤10°; ≤5% of metallic texels in 0.1–0.9; texture memory within budget (BC7 1 B/texel × 4/3) |

---

## 5. Animation

### 5.1 Source by task (Claude never hand-keys a curve it has to judge by eye)

| Task | Kind (`spec_build`) | Source of the pose content |
|---|---|---|
| Human action that exists in a library | `motion.retarget` | In licence order:<br>1. CMU<br>2. 100STYLE (CC BY)<br>3. ACCAD (CC BY 3.0; martial arts)<br>4. Quaternius UAL1/UAL2 (licence = the page snapshot at download; moves to first once a CC0 snapshot is recorded)<br>5. Bandai Namco (CC BY-NC; on by default under the project's NC policy; local only) |
| Cyclic biped locomotion | `motion.locomotion` | Fukuchi 2018 (walk) and 2017 (run) stride fits; gait-atlas medoids (100STYLE, CMU, UAL); Schreiber & Moissenet 2019 for arms, trunk and slow speeds |
| Quadruped and multi-leg gaits | `motion.quad_gait` | Maes 2008 regressions; Hildebrand phase tables; **MANN dog mocap (CC BY-NC, on by default locally)** as a phase atlas for spine, head and tail, rescaled to other quadrupeds by dynamic similarity (time × √(h/h_dog), length × h/h_dog); Muybridge phase targets |
| Flight and undulation | `motion.flight`, `motion.undulate` | Pennycuick frequency (`recalled` until fetched in S2) and a Strouhal check; travelling waves |
| Human one-shots: attacks, hits, deaths, jumps, props, reloads | `motion.keyed` | `pose_library` mined from mocap key frames (ACCAD, UAL2, Bandai) plus `grip_hold`, timing tables |
| Creature one-shots: pounce, bite, roar, hit, death | `motion.keyed` | MANN key frames (jump crouch, launch and land; sit, lie and stand transitions) plus procedural head, neck, jaw and tail channels under predicates, with a Muybridge or user reference. MANN has no bites or roars (§10). |
| Hair, tails, capes, straps | `motion.secondary` | Spring presets |
| Faces | `motion.face` | FACS, JALI and eye statistics (§4.11) |

Pose libraries and atlases are local caches built by `opus data build`. Every element carries its licence flags, and none is ever committed.

### 5.2 Generators

**Contact schedule first.** Every motion spec carries:
- a per-effector contact table (phase intervals; pivot heel, flat, ball or toe);
- integer N at 30 fps; speed; phase events;
- a timing table; the bible's gravity multiplier.

Stance feet are pinned by analytic IK in world space, so **skating is zero by construction**.

**Biped locomotion.**
- Fr = v²/(g·L); walk below Fr 0.5.
- Stride fitted from Fukuchi (Alexander's relation, ±15%, only for creatures without data).
- N = round(T·fps), then λ re-solved as v·N/fps.
- Nearest-speed **medoid** cycle from the atlas, retargeted by the L ratio and retimed; IK corrects only the residual. The atlas holds 64 phase samples in exp-map, mined from straight, steady segments (yaw rate <10°/s, speed CV <10%), with units detected from hip height.
- Heel–ball–toe roll. An 8-way set shares N, with left touchdown at frame 0. In-place and root-motion variants.

**Quadrupeds.**
- Maes dog regressions with speeds × √(h/0.61) and lengths × h/0.61:
  - DF_trot = 0.635 − 0.203·ln u;
  - F = 1.314 + 0.762·ln u (Hz);
  - S = 0.489 + 0.297·u (m).
- Phases (touchdown, LH = 0):
  - dog walk: LF 0.16, RH 0.5, RF 0.66;
  - horse walk: 0.25 spacing;
  - trot: RF 0, RH 0.5, LF 0.5;
  - gallops from the Maes lags.
- 3-bone pantograph hind legs. Swing apex, spine bob and head and tail motion are taken from the MANN atlas medoid at the nearest gait and speed. The fallback, tagged `design`, is apex 0.10–0.25 L with body bob twice per trot cycle.
- Non-mammals: spine undulation (travelling wave), tail (springs), wings (flight cycle) and legs (Hildebrand tables) are procedural channels. Each needs predicates plus a Muybridge or user reference.

**Flight.**
- f = m^(3/8)·g^(1/2)·b^(−23/24)·S^(−1/3)·ρ^(−3/8). Example: a 1,000 kg dragon with a 15 m span and 39 m² wing area gives ≈0.85 Hz, about 35 frames per beat.
- Strouhal 0.2–0.4; downstroke 50–60%; wing folds on the upstroke.

**`keyframe_director`.**
- Named poses: rig-independent effector targets normalized by L, spine split ratios, grips through `grip_hold`.
- **Timing tables are `design` values until resolved,** either by audition or by measurement of mined clips: anticipation, strike and recovery frame counts measured in UAL2 and Bandai combos give p25–p75 bands per action class. Defaults before resolution:
  - light attack: anticipation 3–6 / strike 2–4 / hold 1–3 / recovery 8–15;
  - heavy: 10–20 / 3–5 / 2–4 / 15–30;
  - impact = the peak tip-speed frame ±1; hit-stop 2–5.
- Principle passes (their ranges are also `design` defaults):
  - AUTO_CLAMPED easing (VECTOR at hard impacts);
  - overshoot 10–20% with each rebound ≤0.5× the previous;
  - per-link delay of 1–3 frames;
  - cartoon LoG filter on **exp-map deltas** (never on Euler or raw quaternions), then contacts re-applied;
  - volume-preserving squash: s_x = s_z = 1/√s_y.

**Physical timing everywhere.** T ∝ √(L/g); jump v = √(2gH); one project gravity multiplier, never set per clip.

### 5.3 Retargeting, secondary motion and clip tools

**Retarget.**
- World-delta transfer: R_t = R_s·R_s_rest⁻¹·R_t_rest; root scaled by the hip-height ratio.
- Contacts detected on the source (sole <3–5 cm and speed <0.15–0.2 m/s, 2-frame median) and re-planted with 2-bone IK.
- Spine redistribution (100STYLE has Chest..Chest4; UE has spine_01–03); clavicle synthesis (CMU has none).
- **Twist distribution:** per frame, swing-twist decompose the hand relative to the forearm, and the forearm relative to the upper arm (likewise foot, calf and thigh). Bake twist fractions 1/3 and 2/3 onto the two twist bones. `keyframe_director` does the same.
- CMU resampled from 120 fps with the frame-0 T-pose dropped.
- A **procedural relaxed-finger layer** (mocap has no fingers) plus `grip_hold` for held objects.

**Secondary motion.** Holden springs and Verlet chains, 4–8 substeps. Simulate 2–3 cycles and keep the last, then run the seam fix. Presets:

| Part | Frequency (Hz) | Damping ζ |
|---|---|---|
| hair | 2.5–4 | 0.3–0.5 |
| tail | 1–2 | 0.4–0.6 |
| cape | 1–1.5 | 0.5–0.7 |
| ears | 3–5 | 0.3 |

**`clip_tools`.**
- Holden softfade loop fix plus velocity inertialization (halflife 0.1 s), with root motion handled in character space.
- Loop and transition search using motion-matching features at +10/+20/+30 frames (at 30 fps).
- In-place ↔ root-motion conversion.
- `joint_limits_fit` from CMU, used both as QA and as an IK projection step.

### 5.4 Motion predicates (MoVer-style; missed by all four proposals)

Each `motion.*` spec carries a `predicates` program that the numpy FK evaluator runs per frame. Failing predicates name the frames and the spec field to change. MoVer went from 58.8% to 93.6% correct with this kind of verifier feedback.

```json
"predicates": [
 {"planted": "foot_l", "frames": [0, 12], "max_speed_cm_per_frame": 1.0},
 {"reach": "hand_r", "target": "weapon.grip_main", "by_frame": 18, "tol_m": 0.002},
 {"range": "pelvis.z", "min": "0.92*rest", "max": "1.04*rest"},
 {"loop": true, "pose_tol_deg": 1.0, "vel_tol_pct": 20},
 {"peak": "weapon.tip.speed", "at_frame": "events.impact", "tol": 1}]
```

### 5.5 Motion gates (`motion_report`)

Gates run in Blender and **again on the FBX/glTF re-import**.

| Hard | Soft (calibrated on 100STYLE and UAL cycles) |
|---|---|
| Skate ≤1 cm per plant (realistic) / 2 cm (stylized); GMD ratio 0 | Stride/speed 0.97–1.03; measured Fr inside the declared gait |
| Penetration and float during contact ≤1 cm | Knee-angle deviation from the prior ≤8° (IK not fighting the prior) |
| Loop seam ≤0.5–1° per joint, velocity Δ ≤20%, root ≤0.5 cm | Jerk spikes >5× median only at declared impacts |
| 0 quaternion hemisphere flips; 0 knee or elbow pole flips; hyperextension ≤5° | XcoM inside support at touchdown; idle COM margin ≥2 cm |
| Predicates all pass | Timing ±1 frame vs the resolved table; overlap lag 1–3 frames per link |
| Twist keys present (policy `baked`); twist ring-radius ratio ≥ threshold over the whole clip in pure LBS | Footfall phases ±0.05 cycle; DF ±0.05; biped half-cycle correlation ≥0.9 |
| Export round trip ≤0.5° per joint; clip length, loop flag and names correct | Flight parabola residual ≤1 cm; cycle time within ±20% of √(L/g) scaling |
| | Realistic creatures vs Muybridge: per-phase limb-segment angles ±10° and footfall timing ±0.05 cycle, read from plate keypoints (automatic, or clicked by the user) and normalized by body length. Per-phase IoU is report-only. |

`motion_filmstrip` (Workbench silhouettes, onion skins, effector trails, curve plots) and a blind motion read check **legibility only**: action, gait and emotion.

### 5.6 Export and engine

**Blender side.**
- `anim_api`: slotted actions, `slots.new`, `action_ensure_channelbag_for_slot`, `fcurves.ensure(group_name=)`, `foreach_set`. **One layer per Action** (a 5.2 limit); NLA strips for previews; one baked Action per clip, with twist keys baked.
- FBX preset: `add_leaf_bones=False`, `bake_anim_simplify_factor=0`, one of NLA strips or all actions, armature named `Armature`.
- glTF preset: `export_animation_mode`, `export_anim_slide_to_zero=True`, influences 4.

**Engine side.**
- Godot loop naming via the `-loop` suffix; headless import checked on the PC.
- Runtime layers stay in the engine:
  - Godot: `TwoBoneIK3D`, `SpringBoneSimulator3D`, `BoneTwistDisperser3D`, BoneMap retargeting;
  - UE: IK Retargeter, Control Rig foot IK and twist, Pose Search databases built in UE (they can't be exported from Blender);
  - Unity: Humanoid, Animation Rigging and Twist Correction.

  Wiring recipes are emitted as JSON plus notes, under MIT. Clips that the engine retargets at runtime get the `runtime` twist recipe.

**Pixel art.** Sprite frames come from the contact table and velocity extrema (contact, down, passing, up; anticipation, impact, settle), not uniform sampling, with CONSTANT interpolation at 8–12 fps. They are rendered by `pixel_render`.

---

## 6. Session flows (worked examples)

**All findings, call counts, round counts and intermediate numbers below are illustrative.** Measured targets live in the sprint exits (§9).

Shared opening: `project_bible(show)` → `spec_new` → Claude fills the spec → `spec_validate` → `spec_preview`. The worker stays alive for the whole session, and every fix is a `spec_edit`.

**When each example first runs end to end:**

| Example | Runs end to end from | What works earlier |
|---|---|---|
| (a) HD knight | S7 (S8 for the full surface) | S1 body; S4 sword and holding; S5 retargeted clips. Armor and tabard stay v0.4-style hand-built blockouts until S7. |
| (b) Low-poly wolf + trot | S6 (S2 for the model) | S0a blockout wolf with corrected MT/F |
| (c) First-person rifle + reload | S6 (S4 for the model, holding and sway) | S0a v0.3 grip tools with the signed-distance fix |
| (d) Forest valley | S9 | none |
| (e) Dragon + flight | S6 (S2 for the model) | S0a corrected dragon blockout |

### (a) HD knight with sword, third person, Unreal (about 25 calls)

1. **Camera** `ue_tp_1080` (hfov 90 → vfov 58.7°), so px_per_m = 960/d:

   | Distance | px/m | 1.83 m knight |
   |---|---|---|
   | d_closest 1.5 m | 640 | — |
   | d_typ 3.5 m | 274 | 501 px |
   | d_max 15 m | 64 | 117 px |
   | 40 m | 24 | 44 px |

   TD = 512 px/m.
2. **`spec_new(body.human, knight)`.**
   - Features: 1 armet helm mass; 2 layered pauldrons (Milanese asymmetric allowed); 3 longsword; 4 tabard with charge; 5 knee cops.
   - Body: male, stature p80 → `user: 1.83`, biacromial p90, heroic EDFM k = 1.2 on shoulders.
   - `spec_validate` soft findings:
     - "visor slit 15 mm = 4.1 px at 3.5 m, 1 px at 15 m → geometry at d_typ, dark band in texture at distance";
     - "rivets 6 mm = 3.8 px at d_closest → low-segment geometry";
     - "sword blade width 52 mm = 3.3 px at 15 m (below the 4 px read floor), extent 51 px → accept (reads by length) or style_mult 1.2". Accepted.
3. **Design lock without a reference.**
   - Morph box seeded from the era presets and library outlines: helm {armet, sallet + bevor, great bascinet} × pauldrons {symmetric, Milanese} × tabard {none, short, long} × mass {top-heavy wedge, column} × sword {XIV, XVIIIa}, pruned to 12 configurations.
   - `spec_explore` produces 48 numpy envelope previews (body, garment and harness envelopes with library plate outlines) rasterized at 117 px and 501 px. Dispersion keeps 8. The user picks on the Audition Board (or a ≤14-call tournament).
   - A lineup places the pick beside 2 Met photos of Milanese harnesses scaled to 501 px.
   - `spec_preview` blueprint; lock at rev 3 (resolved values and `tables_version` snapshotted).
   - *With a concept sheet:* `ref_extract` finds body landmarks automatically and reads the internal boundaries (helm top, pauldron top, hem, cop height) on the ruler grid; then `spec_fit` runs on envelope dials only.
4. **`spec_build(body.human)`:** human_build → fit_measurements (every landmark residual <1% of stature) → stylize (z-scores) → `game_engine` + twist bones, A45 rest. Then `deform_test`: forearm twist ring ratio 0.52 < 0.6. `spec_edit /body/rig/twist_split` brings it to 0.71, which passes, also on the FBX re-import.
5. **Gambeson** `spec_build(garment, gambeson L2, chest ease 14%, 15 mm quilted)`: shell → outer cage → robust weights → body_mask. `rom_check(garment)` finds 0 penetrations >1 mm over 14 poses.
6. **Armor** `spec_build(harness milanese_1450, pauldron_L style_mult 1.15)`:
   - `armor_regions` (τ 3 mm) → shells (breast standoff 25–40 mm) with library outlines;
   - elbows: θ = 0.9 × CDC ≈131° → **6 interfaces, overlap ≥27°, g = 2 mm**;
   - armet W = 1.25–1.55 × head breadth;
   - `armor_rig` with the tasset push-only recipe written for UE Control Rig;
   - `layer_mask` hides gambeson faces under the plates and tabard.

   `rom_check(armor)` returns ranked failures:
   - `tasset_L ∩ thigh_l, inner-sheet depth 6 mm @ kneel (hip flex 110°) → /pieces/tasset_L/theta_free`;
   - `pauldron_R ∩ helm @ arm raise 150° → /pieces/pauldron_R/articulation`.

   Repairs follow the §4.5 order: pauldron_R gets one more lame and adjusted sphere radii. tasset_L gets θ_free, then a constrained trim with exposure ≤15%. Only those two pieces and the global gates are re-gated. Mass is checked per piece against Met ranges.
7. **Tabard** (L5): `garment_loft` → bounded `drape_sim` (wool coat) → 4×4 secondary chains → `rom_check(garment)`.
8. **Sword** (the §2.1 spec, wielder = this body):
   - grip_d_eq = 0.197 × hand length;
   - `spec_check`: contacts ≤2 mm, coaxial ≤0.5°, mass 1.15 kg and PoB 11 cm in band;
   - `grip_define` (from socket) → `grip_hold(r, rest)` → `grip_check` "good grip".
9. **Review:**
   - `readability_check` at 3.5, 15 and 40 m.
   - `critique_pack` with 4 views and 4 questions: "visor a dark band in 3/4 rear?", "pauldrons overlap the upper arm rather than butt against it?", "tabard hem between crotch and knee?", "sword reads at 117 px?".
   - `blind_read_sheet` at game size: the fresh judge says "armored knight with sword".
   - Lineup at 117 px beside 2 human-made HD knights from the user's references.
10. **Surface:** `surface_build` (TD 512; unique bake for helm and breastplate, trim for lames; AO and curvature-driven wear; normal NEG_Y; iron albedo; classic skeletal LODs from τ = 1 px) → `surface_report`.
11. **Animation:** `spec_build(motion.retarget, UAL2 3-hit combo)` with contacts re-planted, twist baked and the grip layer added; or `motion.keyed` heavy attack (timing measured from mined combos, impact = peak tip speed). Then `motion_report`, including the re-import.
12. **Export:** `export_asset(ue)`: FBX (no leaf bones, simplify 0, `Armature`), armor pieces laid out for Leader Pose, Control Rig recipe, Blender round trip. **PC check:** the model imports at ≈183 uu and a capture is taken.

### (b) Low-poly wolf with a trot, Godot 4.7, third person (about 15 calls)

1. **Camera** `godot_tp` (vfov 75°): px_per_m = 703.8/d, so 117 at d_typ 6 m. The 1.15 m body is 135 px long. 13 px = 0.11 m, so the ears (about 0.10 m) are marginal → stylize ears ×1.2. Claws (2 cm = 2.3 px) are omitted and drawn in the texture.
2. **Style canon:** `style_canon_extract` over the animal packs the user downloaded (cached once per project) gives the triangle and bone budget, head/body ratio, limb girth, palette and facet statistics.
3. **`spec_new(body.creature, canid)`:** stance digitigrade, 40 kg, withers 0.8 m.
   - Garland & Janis wolf: 35.3 kg, hindlimb 59.0 cm, MT/F 0.437.
   - × (40/35.3)^0.35 → **61.6 cm** hindlimb: femur ≈ tibia ≈ 25.3 cm, metatarsal 11.0 cm, paw separate.
   - Scapula bone with its pivot at hip height. Plausibility gates (T0) pass.
4. **Design lock with a reference:**
   - `ref_extract(PhyloPic CC0 Canis lupus side, standing)`: mask from alpha, scale from the withers, automatic landmarks (withers, hip, hock, elbow, chin).
   - `spec_fit`: CMA-ES over 8 SDF radii, 3 joint scalars and 6 pose dials on the 2D proxy (96², ≈8 ms per view), about 400 evaluations in seconds, regularized to the canon. Confirmed on the SDF raster; side IoU ≥0.85 re-measured on the built cage.
   - `spec_explore` over ear size, ruff mass, tail volume and snout length → tournament → stylize EDFM k = 1.3 on ears, ruff and tail.
5. **`spec_build`:**
   - sdf_body (ribcage, waist and haunch ellipsoids; neck, head and muzzle round cones; tail tube; ears as inflate sheets 0.15–0.25 thick);
   - route A `creature_cage` (loops at t 0.5 and 0.88, level picked to hit the canon budget, 40 vectorized relax rounds) or route B `facet_loft`, whichever is closer to the canon's facet statistics;
   - flat shading + palette atlas from the pack palette;
   - rig with UE-style names, heat weights on the body, ears rigid.

   Then the checks:
   - `spec_check`: 0 inverted faces (both tests), 0 self-overlap, centre of mass in support; `deform_test` on the quadruped battery.
   - `blind_read_sheet`: "wolf" ("dog" accepted per the spec).
   - Lineup at 135 px beside 2 KayKit/Quaternius animals.
6. **`spec_build(motion.quad_gait, trot, 3.0 m/s)`:**

   | Quantity | Calculation | Result |
   |---|---|---|
   | Froude number | 9/(9.81·0.8) | 1.15 → trot |
   | Dog-equivalent speed u | 3/√(0.8/0.61) | 2.62 m/s |
   | Duty factor | 0.635 − 0.203·ln 2.62 | **0.44** |
   | Stride frequency | dog F = 2.048 Hz ÷ 1.145 | **1.79 Hz** |
   | Cycle | T = 0.56 s at 30 fps | **N = 17** |
   | Stride length | λ = 3·17/30 | 1.70 m (Maes fit × h/0.61 gives 1.66 m, consistent) |

   Phases LH 0, RF 0, RH 0.5, LF 0.5. Spine, head and tail come from the MANN trot medoid, rescaled. Predicates: every stance foot moves <1 cm/frame; loop seam.
7. **`motion_report`:**
   - The first run reports "RF skate 2.6 cm, frames 3–6 → /contacts/RF/pivot". `spec_edit` sets pivot = ball, and it passes.
   - `secondary` adds a tail spring (1.5 Hz, ζ 0.5) and ears (4 Hz, ζ 0.3), simulated for 3 cycles with the last kept; `clip_tools` fixes the seam.
   - `motion_filmstrip`, plus Muybridge dog-trot limb angles and footfalls per phase.
8. **Export:** `export_asset(godot)` writes a .glb with `Trot-loop`, `slide_to_zero` and 4 influences. Godot headless import passes on the PC. The ledger records PhyloPic (CC0) and MANN (`nc`, attribution). If the game is pixel art, `pixel_preflight` and `pixel_render` run, with key frames chosen from the contact table.

### (c) First-person rifle with two-handed hold and reload, Unreal (about 20 calls)

1. **Camera:** the view-model profile `ue_fp_vm` is read from the project. In this example it matches the world camera (hfov 90), so px_per_m = 960/d. The viewmodel sits at d 0.35–0.7 m → 2,743–1,371 px/m.
   - TD 2,048 px/m (log-nearest power of two).
   - Grip (19 mm radius): 20 sides at 0.45 m. Handguard (25 mm): 27 sides at 0.35 m.
   - Bevel cap 1.5/2,743 = 0.55 mm.
2. **`spec_new(assembly, firearm/rifle_carbine)`** → `dims_resolve` from the Wikidata psn table, with anchors such as AK-47 (OAL 880 mm, barrel 415 mm = 0.47·OAL, 3.47 kg) and M4 (838/756 mm, barrel 368 mm, 2.92 kg).
   - Length of pull and grip angle come from a `recalled` ergonomics table, so they only warn.
   - Layout by bore-axis anchors; outlines from the profile library or constraint sketches.
   - The magazine is a separate part with a prismatic joint on the `mag_well` axis; the charging handle is prismatic too.
3. **Design lock:** `spec_explore` over {handguard profile, stock type, magazine curvature, sight type}, shown in the true first-person inset → tournament. Or, with a reference: `ref_extract` of the user's orthographic side sketch → `spec_fit` within table ranges (IoU ≥0.92).
4. **`spec_build` → `hs_finish` → `spec_check`:**
   - hard: axes meet at the chamber within 0.5 mm; sights ∥ bore ≤0.1°; magazine sweep over 16 samples free of collision; contacts ≤0.5 mm;
   - soft: mass in band.
5. **Arms, framing and hold:**
   - `spec_build(body.human, arms_only)` from the player body, with a camera socket at the eye.
   - `grip_define` is generated from the sockets: `grip_main` (pistol grip with trigger point), `grip_off` (handguard), `SOCKET_sight`.
   - **Framing solve:** screen-space targets are measured with `ref_extract` from 3 screenshots the user supplied of first-person games they like. Example targets: grip at (0.62, 0.78) of the screen, muzzle at (0.55, 0.60), coverage 18%, muzzle converging on the crosshair at 25 m. The solver places the weapon to meet them. ADS: the stock butt is centred on the shoulder-pocket landmark and the sight line passes through the eye.
   - `grip_hold(main, r, index: trigger)` → `grip_hold(move: hand, side: l, grip_off)`.
   - Idle sway, walk bob, recoil and ADS blend are springs.
   - `grip_check` in fp_hip, fp_ads and at the sway, bob and recoil extremes: palm + ≥3 fingers in contact on each hand; depth ≤0.5 mm; ADS sights ≤1 mm from the eye line; 0 clipping into the body or across the near plane.
6. **Reload** `spec_build(motion.keyed, reload_mag)`. The total comes from the game bible (e.g., 2.0 s = 60 frames); the phase split is a `design` preset resolved by audition. Predicates:
   - `hand_r` on `grip_main` ≤2 mm for all frames;
   - `hand_l` reaches the magazine by f14, and the magazine follows `hand_l` from f14 to f30 (baked constraint on a `mag` bone);
   - the old magazine clears the well along its axis by f20 with no overlap;
   - the new magazine is seated within 1 mm by f40;
   - the charging handle makes its full stroke f44–f50;
   - the muzzle stays inside the view frustum;
   - `grip_check` every frame: no penetration >1 mm.

   Hand poses (pinch, open) come from the hand-pose library and are solved by the contact solver. Passes: overshoot on the seat, 1–2 frame lag on the off hand, a camera-kick spring (halflife 0.05–0.1 s).

   First run: "mag_seated 3.2 mm at f40 → /timing/insert +2 frames". `spec_edit` → pass.
7. **Surface:** `surface_build` with a unique bake at 2,048 px/m for receiver and handguard, trim for rails, wear from curvature; NEG_Y normals; `material_lint`. The third-person world model is LOD1 from `lod_chain`.
8. **Export:** `export_asset(ue)`:
   - arms skeletal mesh (`game_engine` names + camera socket);
   - weapon skeletal mesh (root, mag and bolt bones, `SOCKET_muzzle`, `SOCKET_sight`);
   - clips `FP_Rifle_Idle/ADS/Reload` for both meshes; grip pose as a pose asset; Blender round trip ≤0.5°.

   **PC check:** UE capture of hip, ADS and reload, signed off by the user.

### (d) Forest valley landscape, Unreal, third person (about 15 calls; heavy compute in the uv venv)

1. **`spec_new(terrain)`:**
   - 6 min traversal × 5 m/s × detour 1.3 ≈2.3 km of path → a 2 km map, UE 2017² at 1 m, 15% vista ring.
   - Two ridges (crests 260–310 m, flanks 25–30°); valley floor at 80 m; a river from the NE pass to a lake (monotone bed, 0.5–1%).
   - Primary landmark: a ruined tower on a west-ridge spur, ≥35 m above its surroundings so it subtends 2° at 1 km.
   - 7 POIs along the critical path; edges and districts (meadow floor, beech slopes, spruce ridges).
   - Targets: playable mean slope 12–18°, walkable ≥85%, road grade ≤15%, landmark visible from ≥70% of samples, POI-to-POI travel 30–60 s.

   `spec_preview` renders the layout diagram; POI spacing and the landmark line of sight are checked in 2D first.
2. **`dem_fetch(mode=stats, temperate forested valley)`:** slope histogram, hypsometric integral and spectral slope targets; WorldCover × Copernicus splat thresholds, cached per biome.
3. **Design lock:** 3–6 layout variants with 256² hillshades → tournament → the user.
4. **`spec_build(terrain, preset forested_valley)`:** the §4.8 order at a 512² working grid (relief calibrated before erosion; roads planned at 512²; rivers and final conditioning last), then up to 2017².
5. **`spec_check(terrain)`** at 512² (seconds):
   - "walkable 79% < 85%: west ridge flank mean 31° → /primitives/ridges/0/flank_deg";
   - "landmark visible 61% < 70%";
   - "POI3 travel 74 s > 60 s".

   `spec_edit`: flank 30 → 26°, spur crest +15 m, POI3 moved 120 m along the path. Only the affected stages rebuild. Everything passes at 2017²: final conditioning raised no cell >0.5 m outside the lake, rivers monotone, round trip ≤1 LSB.
6. **Trees:** `spec_build(tree)` × 3 species (Picea abies excurrent, Fagus sylvatica decurrent, Betula), Tallo p30–p80, 3–4 seeds each, with cards, wind colours and impostors. The tree report passes.
7. **Paint and scatter:** WorldCover-fitted thresholds; spruce r 4–6 m, beech 6–8 m on slopes <30–35° and ≥1 m above water; shrubs 1.5–3 m in a 5–15 m ecotone; rocks sunk 10–30%; rock kit on cliff bands.
8. **Review:** `critique_pack(kind=terrain)`: annotated hillshade, 4 obliques, player-eye views from spawn and each POI (≤12), and the questions "tower in frame from spawn?", "path readable?", "ridges read impassable?", "no floating trees?".
9. **Export:** `export_asset(ue)`:
   - 16-bit PNG, XY scale 100, Z scale = range_m × 100/512 (330 m → 64.45), actor Z at the midpoint;
   - weightmaps, PCG instance CSV, river splines with bridge segments, sidecar JSON and import script.

   The ledger records DEM, WorldCover and Tallo attribution. **PC check:** import and capture from spawn.

### (e) Western dragon with flight, Unreal, third person (about 15 calls)

1. **Camera** `ue_tp_1080`, boss at d_typ 25 m → 38.4 px/m. Horns 0.3 m = 11.5 px → style_mult 1.15 to reach 13 px.
2. **`spec_new(body.creature, dragon)`:**
   - base donor varanid (neck, trunk and tail fractions from the varanid table, p5–p95), stance declared erect (style override logged);
   - bat-wing graft on its own girdle over the forelimb girdle (girdle position is a `design` fraction);
   - mass 1,000 kg.
3. **Wings from the loading band:** W = 9,810 N, so 150–250 N/m² gives S = 39–65 m². Bat AR 5–11 (`recalled` until Norberg & Rayner is fetched). Explore picks S = 45 m² and AR 6 → b = √270 ≈16.4 m. Bones: bat wing-bone ratios; membranes are inflate sheets weighted by spar distance.
4. **Design lock:** the morph box is seeded from the donor tables and the user's dragon references (head type, horn set, spine row, wing-finger count). `spec_fit` on the user's side sketch if one exists; otherwise per-part fits of the varanid and bat templates, each already fitted to ≥2 references.
5. **Build and gates:** sdf_body → creature_cage; girdle and flexion-sign gates; flight band (warning while `recalled`); blind read "dragon"; lineup against the user's references.
6. **Flight (S6):** Pennycuick f ≈0.74 Hz → 40 frames per beat; Strouhal 0.2–0.4; downstroke 55%; fold on the upstroke; body bob from the wing beat; tail springs. `motion_report` with flight-parabola and predicates.

---

## 7. Data plan

**Rules.**
- **Committed:** small derived **fact tables** and the **profile library** (about 2–3 MB). Only from CC0, public-domain, factual or CC BY sources. Each table carries its citation, measured/derived/recalled tags, and an entry in `data/LICENSES.md`.
- **Local only:** everything else goes through `data_fetch` into `library_dir`, listed in DOWNLOADS.md with sha256, licence ID, flags and LICENSE.json. That includes every cache derived from NC, SA, ND, QAL or unlicensed sources: gait and quadruped atlases, pose libraries, style canons, raw museum JSON and calibration corpora.
- **Ported code:** only under the §2.7 porting rule, with THIRD_PARTY_NOTICES entries and module headers.
- **NC sources:** on by default locally (PLAN §0, confirmed once). `commercial: true` in the bible blocks them at export.

### 7.1 Committed fact tables

| Table | Source | Licence | Notes |
|---|---|---|---|
| ANSUR II stature-normalized p5/p50/p95, derived head height | ANSUR II public CSVs | US Gov, "cleared for unlimited public release" | Military sample: no children, heavy bodies truncated |
| NHANES BMX percentiles | CDC/NCHS | US Gov public-use data, NCHS data-use terms (statistical use only) | Summary statistics only; raw files never committed |
| de Leva segment parameters | BMClab | facts | — |
| Garland & Janis 49-species hindlimb table; Fischer 2002 rules | papers | facts | MT/F per species |
| AVONET raptor wing and tarsus ratios | figshare | CC-BY-4.0 | Attribution in LICENSES.md |
| Wang et al. 2011 bird wing ratios | paper | facts | — |
| Norberg & Rayner bat wings; pterosaur, varanid, crocodilian morphometrics; Pennycuick loading bands | papers (fetched in S2) | facts | `recalled` until fetched |
| Maes 2008 dog regressions and lags; Hildebrand phases | papers | facts | The lateral-walk DF intercept is suspect; fit walk DF from MANN locally |
| Fukuchi 2017/2018 stride fits | figshare | CC-BY-4.0 | Attribution |
| CDC ROM (Enlyte fallback); scapulohumeral split | CDC | US Gov public-use data, 308(d) terms | Summary limits only; Enlyte unsourced → recalled; neck and trunk recalled |
| Oakeshott / Albion sword table | Albion, Wikipedia | facts | Conflicts kept as ranges |
| Firearm dims (psn-normalized) | Wikidata SPARQL | CC0-1.0 | — |
| Met / AIC / Cleveland per-piece percentiles | museum APIs | CC0-1.0 data | Projected vs girth tags |
| ABO prop dimensions | ABO | CC-BY-4.0 | Attribution |
| Armor thickness | Lazar & Kraner 2019 | CC-BY-4.0 | Attribution |
| Ease % and cm | FreeSewing; Opian | MIT; facts | — |
| Fabric densities | ARCSim materials (Wang 2011) | UC non-profit terms; facts | — |
| ADA 2010 dimensions | access-board.gov | public domain (US Gov) | — |
| PBR ranges and values | DONTNOD; physicallybased.info | facts; CC0-1.0 | — |
| FACS recipes, ARKit-52 names, AU→ARKit; JALI rules; eye statistics | Wikipedia / Apple / JALI paper | facts | AU→ARKit is our convention |
| Crysis wind layout; Lengyel shell parameters | GPU Gems 3; paper | facts | — |
| Tallo quantile fits | Tallo | CC-BY-4.0 | Attribution |
| Splat thresholds | WorldCover × Copernicus | CC-BY-4.0 / Copernicus credit | Exact credit strings in LICENSES.md |
| Infinigen ranges; Schott presets | repos | BSD-3; MIT | Notices; Infinigen re-checked vs ANSUR |
| Profile library | Met PD images, Cleveland CC0, AIC PD images, Swedish History Museum (CC BY), Kenney (CC0) | CC0 / PD / CC-BY-4.0 | KayKit- and Quaternius-traced profiles stay local |
| Engine contracts, camera presets, `errors.json`, `licences.yaml` | docs; own | — | — |

### 7.2 Downloads (on demand, never committed)

| Pack | Use | Licence (flags) | Size | Fetch |
|---|---|---|---|---|
| MPFB2 data: base.obj, targets `.target.gz`, rig + weights JSON, MHCLO clothes | humans, fixtures | **CC0** assets (code GPL-3; logic ported with notice) | 1.75 MB + tens of MB (check page) + 3 MB/5 MB | raw GitHub per file |
| MakeHuman system assets (proxies), faceunits01, visemes, poses | low-poly proxies, faces, test poses | **CC0** | check page | asset pack zips |
| MakeHuman hair, clothes and other community packs | optional | mixed, often **CC-BY** (attribution) | per pack | ledger attribution |
| ANSUR II CSVs; NHANES BMX | fact-table rebuild | public release / NCHS data-use terms | ~10 MB | direct |
| AVONET | bird wing proportions | **CC-BY-4.0** | 21.5 MB | figshare |
| PhyloPic silhouettes | creature references | filtered to **CC0** | per image | API |
| Muybridge plates | gait-phase references | public domain (LoC / Wikimedia items with a stated status) | per plate | archive |
| Met v1.1 / AIC / Cleveland caches and photos | dimensions, references, profiles | **CC0** data; images only if public domain | JSON MBs | APIs |
| ABO metadata | prop dimensions | **CC-BY-4.0** | listings only | S3 |
| Kenney kits (incl. pixel-art packs) | style canon, kitbash, lineups, flicker reference | **CC0** | 50–300 MB selected | zip |
| KayKit packs | style canon, kitbash, lineups | CC0 per page snapshot | per pack | `--from-file` (itch) |
| Quaternius packs | style canon, kitbash, lineups | **QAL v1.0** per page snapshot and date (`no-redistribute-as-asset` unless the snapshot says CC0); local only | per pack | `--from-file` (itch) |
| Poly Haven | HD bounds, materials, calibration | **CC0**; API needs a unique User-Agent and a credit line | per asset | API |
| ambientCG (incl. Chainmail001–004) | materials | **CC0** | per material | API |
| MatSynth CC0 subset | materials, lint distributions | **CC0** subset only | 1–3 GB if selected | per material |
| Lospec palettes | palette priors | unstated → local only (`unknown` until classified) | small | site |
| O'Donovan colour model | report-only palette score | **CC BY-NC-SA** (nc, sa); local | small | site |
| Quaternius UAL1 / UAL2 | human clips | per page snapshot (CC0 on the itch page as of the research; re-check vs QAL) | per pack | `--from-file` (itch) |
| CMU BVH | clips, atlas, joint limits | free incl. commercial | several GB in full; fetch per file | index URLs |
| 100STYLE BVH | atlas, styles | **CC-BY-4.0** | 1.5 GB | Zenodo |
| ACCAD | combat poses | **CC-BY-3.0** | ~300 files | site |
| Fukuchi 2018 walk; 2017 run | stride fits | **CC-BY-4.0** | 0.69 GB; check | figshare |
| Schreiber & Moissenet 2019 | arms, trunk, slow speeds | **CC-BY-4.0** | 382 MB | figshare |
| Bandai Namco DS1/DS2 | combat poses, timing measurement | **CC BY-NC** (nc); on by default locally | check | GitHub |
| MANN dog | quadruped atlas, creature poses, walk DF fit | **CC BY-NC** (nc); on by default locally | check | starke-consult archive |
| CMUdict | lip sync | BSD | ~3.5 MB | GitHub |
| Rhubarb | audio lip sync (opt-in after the user's OK) | MIT (HMM recognizer) | small | release |
| GarmentCode (+ Warp fork) | hero sewing patterns, out-of-process | MIT (Warp: NVIDIA SCL, flag `nc`) | check | GitHub |
| Korosteleva 2021 subset | gap calibration (weak prior, one body) | **CC-BY-4.0** (its SMPL body is NC and unused) | 2–3 category zips | Zenodo |
| EA Dem Bones | sim → bones, optional | BSD-3 | small CLI | release |
| Terrarium tiles | DEM base or statistics | keyless; mixed attribution recorded wholesale | ~100 KB per tile | AWS HTTPS |
| Copernicus GLO-30 COG | DEM | free with credit | tens of MB per 1° tile | anonymous S3 |
| ESA WorldCover 10 m | splat calibration | **CC-BY-4.0** | per tile | anonymous S3 |
| USGS 3DEP | optional DEM | public domain | per tile | — |
| FABDEM | bare-earth DEM | **CC BY-NC-SA** (nc, sa); `stats` mode by default | per tile | — |
| Galin DEM repository | metric calibration only, never shipped | no licence (`unknown`; local only) | — | local |
| Tallo CSV | tree allometry | **CC-BY-4.0** | check | Zenodo |
| Python packages (uv venv) | — | core: scipy, scikit-image, pydantic, psutil (BSD/MIT). Extras: numba (BSD); fastscapelib (GPL-3); pydelatin, coacd, xatlas-python, PyGEL3D, CuPy, pyfqmr (MIT/BSD-type); opencv-python-headless (Apache-2.0) | — | pip |

**Excluded:**
- SMPL, SMPL-X, SMAL and AMASS;
- LAFAN1 (ND, data and code); SFU; BONES-SEED (eligibility unclear);
- Mixamo as an automated source;
- ShapeNet, PartNet, Fusion 360 Gallery data; MB-Lab (AGPL outputs); Z-Anatomy;
- GarmentCodeData until its licence is confirmed;
- MakeHuman's AGPL code;
- every generative model's weights; Anny as a torch runtime (only its sampling idea is reused).

**Disk:** core plus facts <50 MB; a typical library 5–10 GB; ≤15 GB with all of CMU and 100STYLE. Well inside the ~100 GB budget, and `opus doctor` reports usage per pack.

---

## 8. Tool list

Priorities: P0 = foundation, P1 = biggest quality win, P2 = strong upgrade.

### 8.1 New tools (32)

| Tool | Purpose | Pri | Sprint |
|---|---|---|---|
| `spec_new` | Template for a kind or archetype (about 90% complete), with defaults, slot anchors, library profiles and derived camera numbers | P0 | S0b |
| `spec_validate` | Schema, sources, units, names, licences, camera feasibility, detail tiers | P0 | S0b |
| `spec_preview` | Numpy blueprint sheet, game-size insets, ID masks, 2D lint (no Blender); envelopes for garments and harnesses | P0 | S0b (envelopes S7) |
| `spec_build` | Compile any kind: assembly, bodies, garment, harness, motion, terrain, tree, building, layout, face, hair | P0 | S0b+ |
| `spec_check` | Tiered gates T0–T4 by kind; findings with fix paths | P0 | S0b |
| `spec_edit` | JSON patch or seed edit; re-solve dependents; locality check; re-gate; lexicographic acceptance; Pareto archive; joint solve | P0 | S0b |
| `dims_resolve` | Sourced, ranged, wielder-aware dimension sheet | P0 | S0b |
| `data_fetch` | Download from the manifest with sha256, licence snapshot and LICENSE.json; resumable; `--from-file` for manual packs | P0 | S0b |
| `defect_inject` | Plant defects of known size per gate class; measure recall | P0 | S0b (harness), every sprint |
| `gate_calibrate` | False-positive rates on per-gate corpora; soft thresholds from p5/p95 and user ratings | P1 | S0b (harness), S3 |
| `ref_extract` | Reference → mask, symmetry, scale, perspective warning, automatic landmarks, grid-read internal boundaries, palette, profile tracing → spec patch | P1 | S1 (v1), S3 (v2), S4 (profiles) |
| `spec_fit` | Optimizer fit of dials to references (silhouette, landmarks, depth, pose, DEM statistics) | P1 | S2 |
| `deform_test` | Pure-LBS bend and twist battery, in Blender and on re-import; candy-wrap, volume, stretch, weight hygiene | P0 | S1 |
| `style_canon_extract` | Measure CC0 packs into a style canon (proportions, budgets, palette, facet statistics) | P1 | S2 |
| `library_search` | SQLite index of downloaded packs: thumbnails, licence flags, tris, normalized bbox, fingerprints; Poly Haven credit | P1 | S2 |
| `library_import` | Kitbash import normalized by an anchor dimension; anchors and ledger lineage added | P1 | S4 |
| `spec_explore` | Seeded morph box, sampling, output-space dispersion → contact sheet at game pixels | P1 | S3 |
| `critique_pack` | Fixed views plus spec-derived yes/no questions; tournament, lineup and terrain modes | P1 | S3 (protocol in the agent from S0a) |
| `readability_check` | Feature min-width and extent at the game camera, squint, cast lineup | P1 | S0a (v0), S3 |
| `run_stats` | Ledger KPIs: iterations to a hard pass, validator rejections, tokens, judge rounds, failure histogram | P1 | S3 (ledger from S0b) |
| `library_promote` | Admit a generator after ≥8 passing seeds and its declared references reproduced (or one user audition approval) | P1 | S4 |
| `export_asset` | Engine presets, `UCX_`/`SOCKET_`/suffixes, twist bake, round trip, MIT import script and checklist, licence-policy check | P0 | S0b, S4 |
| `rom_check` | Range-of-motion battery in garment or armor mode: overlap, inner-sheet depth, lames, exposure; iterate vs sign-off sets | P1 | S7 |
| `mocap_ingest` | BVH parse, units, contacts, fps, licence flags; builds the gait and quadruped atlases | P1 | S5 (MANN S6) |
| `motion_report` | All motion metrics plus predicate results, in Blender and on re-import | P0 | S5 |
| `motion_filmstrip` | Silhouette strips, onion skins, trails, curves; blind motion-read sheet | P1 | S5 |
| `clip_tools` | Softfade loop fix, inertialization, loop and transition search, root motion | P1 | S5 |
| `surface_build` | UV plan, bakes, wear masks, LOD chain, impostors, collision hulls | P1 | S2 (v0), S4 (hero bake), S8 |
| `surface_report` | TD, UV, bake QA, material_lint, LOD error, hulls, pixel_preflight | P1 | S8 |
| `pixel_render` | 3D → pixel sprites: orthographic N-direction cameras, film filter 0, toon ramp, outline, palette lock, per-frame normal maps, contact-table key frames | P1 | S6 |
| `dem_fetch` | Terrarium or Copernicus crop and WorldCover tiles; statistics (default) or base mode | P1 | S9 |
| `fracture_prefab` | Impact-aligned Voronoi pre-fracture with support graph and hulls | P2 | S10 |

### 8.2 Changed tools (15)

| Tool | Change | Sprint |
|---|---|---|
| `body_blockout` | Canon fixes: foot 1.15 HU, hand 0.82 HU; dog, cat and horse MT/F from Garland & Janis; horse fetlock. Marked as blockout and SDF target only. | S0a |
| `lookdev_sheet` / `look_at` | Mask mode (AA off, FLAT, Standard, dither 0); part-ID passes | S0a |
| `mesh_lint` | MANIFOLD readiness, custom-normal checks, influences, kit grid, gate profiles | S0b |
| `model_report` | Uses the finding contract; contacts sampled both ways; thin-shell penetration; works without a spec | S0a, S0b |
| `proportion_check` | ANSUR percentiles and z-scores | S1 |
| `reference_match` | Becomes the full silhouette score: chamfer, Hausdorff95, per-band widths, landmarks, depth error, part attribution | S3 |
| `blind_read_sheet` | Game-size mode (S0a); motion mode; cast lineup | S0a, S3 |
| `grip_define` / `grip_hold` / `grip_check` | Signed-distance fix (S0a). Auto-define from sockets; long guns to the shoulder; sights on the eye line; view-model framing solve; sway, bob, recoil and ADS springs; hand-pose library; per-frame checks; UE pose assets (S4). | S0a, S4 |
| `project_bible` | Camera and view-model profiles (S0a); `weapon_scale`, `gravity_mult`, style multipliers, TD, gate profiles, licence policy, `twist_policy`, rating budget (S0b) | S0a, S0b |
| `ledger_record` / `make_credits` | Licence IDs + flags, no free-text matching (S0a); `inputs` lineage, tool tags, export policy, Poly Haven credit (S0b) | S0a, S0b |
| `opus_doctor` | ComfyUI check relabelled (S0a); worker status, extras smoke tests on Windows, per-pack status and disk use (S0b) | S0a, S0b |

The `art-director` agent and the `3d-modeling` skill switch to the checklist protocol in S0a: 2–5 yes/no questions, one criterion each, both-order A/B with the incumbent, and a lineup against human-made exemplars using v0.3 renders.

**Internal stages** invoked by `spec_build` and `spec_check` (not MCP tools): human_build, fit_measurements, stylize, sdf_body, creature_cage, facet_loft, sketch_solve, profile_trace, garment_shell/loft, weight_transfer_robust, body_mask, layer_mask, armor_regions/shell, joint_articulation, helmet_build, armor_rig, trim_to_clear, hs_finish, mass_props, function_check, framing_solve, fp_springs, locomotion_cycle, quad_gait, flight_cycle, keyframe_director, twist_bake, secondary_bake, terrain_build/paint/scatter/export, tree_factory, building_grammar, kit_wfc, layout_solve, face_contract, face_anim, hair_builder.

---

## 9. Roadmap

Sizes: S = 1–2 weeks, M = 2 weeks, L = 3–4 weeks.

Every sprint ends with three things:
- something usable;
- an **automated exit** (CI, or a headless check on the PC);
- a **PC check** on the user's Windows machine, through the engine MCPs.

**User time is budgeted** at ≤20 minutes of blind A/B and ≤10 minutes of PC checklist per sprint. Every sprint ships `defect_inject` suites for its hard gates and calibrates its soft gates where §2.5 names a corpus. Without a corpus, a gate stays a warning.

**Parallel spike (PC, during S0b–S1), decided before S2 starts:**
- **Windows runtime test of the extras:** PyGEL3D, openvdb inside Blender, fastscapelib, CoACD, xatlas, pydelatin, CuPy, pyfqmr.
- **FEQ go/no-go** on the research prototype (moved to `tests/spikes/feq/`), with a welded hm08 hand, a membrane sheet and a non-T rest pose. Go requires all of:
  - 0 faces >90° from cage normals after relaxation;
  - 0 BVH self-overlaps;
  - quad share ≥98%;
  - finger-joint ring ratio ≥0.6 at a 90° bend in pure LBS;
  - ≤10 s per creature at level 1;
  - in 3 lineups (front, 3/4, game camera) against one KayKit character, the user prefers ours or calls it equal in ≥2.
- **Route B (`facet_loft`)** is built and scored against the same canon facet statistics.
- **No-go** makes route B the main low-poly route, with Skin + Subsurf + Shrinkwrap as the HD-organic fallback.

| Sprint | Builds | Exit criteria (measurable) | Size |
|---|---|---|---|
| **S0a · v0.4 quick wins on v0.3** | • PC smoke test of v0.3.<br>• Camera profiles + `opus.camera`; game-size `blind_read_sheet`; `readability_check` v0 on the existing part map.<br>• Canon data fixes: human foot and hand; dog, cat and horse MT/F with a fetlock.<br>• Hygiene: mask mode, pseudonormal signed distance, thin-shell penetration.<br>• Checklist, both-order A/B and lineup protocol in the art-director agent and the skill.<br>• Ledger licence IDs and flags with tests; `LICENSE`, `THIRD_PARTY_NOTICES.md`, `data/LICENSES.md` skeleton.<br>• Generative paths removed from PLAN, DOWNLOADS and doctor; documentation fixes.<br>• 24-task eval suite: the 8 regression subjects plus 16 category tasks. | • PC: v0.3 installs, doctor green, every v0.3 tool runs on Windows, a 1.8 m blockout = 180 uu in UE.<br>• Foot and hand inside ANSUR p5–p95; dog, cat and horse MT/F within 10% of wolf, felid and horse.<br>• Mask mode: 0 blended edge pixels on a planted two-part test.<br>• The 6 misfiring licence strings classify correctly.<br>• No generative 3D or animation path left in PLAN, DOWNLOADS or doctor.<br>• **v0.4 baseline recorded** on all 24 tasks: iterations to accept, tokens, wall-clock. | S |
| **S0b · Compiler core** | • Spec envelope + validator.<br>• dims resolver + first fact tables (ANSUR, Oakeshott, Cleveland swords, Wikidata firearms, ADA) with LICENSES entries.<br>• Anchor/graph solver.<br>• **Evaluator contract for all kinds**; numpy builders box, extrude, lathe, station_loft.<br>• Evaluator raster + blueprint sheet.<br>• Profile library v0: ≥6 sword, axe and shield profiles traced from Cleveland/Met CC0 photos.<br>• Blender emitter + finish v1 via the one-shot runner.<br>• Consistency gate v1.<br>• Finding contract + T0–T2 + `spec_edit` (lexicographic) + run ledger.<br>• Minimal `defect_inject` / `gate_calibrate` harness.<br>• CI workflow (Workbench and CPU).<br>• FBX/glTF export presets + Blender round trip + UE import script and checklist.<br>• `data_fetch` (manifest, `--from-file`, snapshots, lineage).<br>• Optional-extras packaging. | • Same spec + seed + `tables_version` → identical quantized hash, host and Blender.<br>• Single-triangle convention test passes. On 5 specs × 4 views: IoU ≥0.99, per-part boundary p95 ≤0.5 px, depth p95 ≤1 game px.<br>• ≥200 numpy silhouette evals/min (one view, 256², ≤12 parts).<br>• A 6-part anchored prop survives 3 random dial edits with 0 gaps and 0 floating parts.<br>• `defect_inject`: contact, floating, manifold, sheet and naming gates ≥95% recall, 0 failures on clean fixtures. CI green.<br>• **A/B against v0.4 on 6 props (sword, axe, round shield, chest, barrel, chair): fewer iterations to a hard pass on ≥5/6, and the user prefers v0.4 in ≤1 of 6 blind pairs.** If this fails, the compiler stays as validator and blueprint tool over v0.4's socketed shape kit, and S4 is re-planned.<br>• **PC:** Godot headless import of the exported .glb; UE import checklist. | L |
| **S1 · HD humans with right proportions** | • **Persistent worker** (file protocol, queue, psutil, GPU re-enable, rotated checkpoints, security).<br>• human_build (MPFB2 port + golden test), fit_measurements, ANSUR/NHANES tables, stylize.<br>• **Rest pose and rig contract:** A45, twist and helper bones in the base skeleton, `twist_policy`, bone maps.<br>• `deform_test` with paired twist calibration.<br>• Topology and weight hygiene, balance.<br>• MHCLO wardrobe refit + delete_verts masking, faceunits01, proxies.<br>• `ref_extract` v1 (automatic landmarks, grid internal boundaries, scale, perspective warning) + 20-image calibration.<br>• Percentile `proportion_check`. | • Worker: 100 consecutive calls without restart; a forced RSS restart reloads the checkpoint; Cycles GPU active after reset; `spec_check` (T0–T2) ≤1 s at 50k tris; 2 parallel requests queue correctly.<br>• Golden test: getHeightCm and 10 vertex positions within 1 mm of MPFB2 at 3 macro settings.<br>• "p75 male 1.85 m" fits with residual ≤1% of stature in one solve.<br>• Twist: on 3 bodies, hm08 + twist passes 60° forearm twist and the same bodies without twist fail (100% separation). Other joints ≤10% false fails on CC0 rigs. Baked twist survives FBX and glTF re-import, and `deform_test` passes on the re-import.<br>• Landmark error measured: automatic ≤1.5% H and grid ≤2% H on orthographic references, or tolerances widened to the measured values.<br>• The wardrobe re-dresses 3 morphs in one call each. Realistic, heroic and child variants each pass blind read.<br>• **PC:** UE import plus IK Retargeter to Manny plays a mannequin clip, with twist driven per policy. | L |
| **S2 · Creatures and stylized bodies** | • creature_spec + donor tables (Garland & Janis, Fischer, AVONET, Wang; fetch Norberg & Rayner, pterosaur, varanid, crocodilian and Pennycuick).<br>• Donor templates fitted to ≥2 references each; graft rules.<br>• sdf_body, inflate (SOR), creature_cage (vectorized), facet_loft.<br>• `spec_fit` (2D proxy, pose dials, cage re-measure, fidelity metric); flight check.<br>• `style_canon_extract` with facet statistics; `library_search`.<br>• Separate-part rigging rules.<br>• **`surface_build` v0** (palette atlas, AO and curvature wear, measured PBR) on all eval subjects. | • FEQ go/no-go recorded before the sprint.<br>• Wolf, horse, dragon, griffin and stylized goblin: 0 inverted faces (both tests), 0 self-overlap, biomechanics and deform gates pass.<br>• Standing-side wolf fit: IoU ≥0.85 on the cage, ≤60 s on the PC. Cage fidelity p95 ≤1 game px.<br>• Facet statistics inside the canon's p5–p95. Lineups vs KayKit/Quaternius: the user singles ours out in ≤3 of 6 (chance 2).<br>• Blind read top-1 ≥4/5. Budgets within ±10% of the canon.<br>• **PC:** wolf and goblin in UE and Godot. | L |
| **S3 · Design lock, recognizability and appeal** | • `spec_explore` (seeded morph box, dispersion, optional MAP-Elites).<br>• `critique_pack` (checklist, both-order tournament, **lineup**), `readability_check`, design_lint (warnings), style-match statistics, adjective-to-dial table.<br>• `ref_extract` v2 (symmetry, palette, landmark rulers, style screenshots).<br>• Full silhouette score with depth; game-size blind read.<br>• `gate_calibrate` on the §2.5 corpora; `run_stats`; minimal Audition Board.<br>• Face-shape operators and stylized hair v0 for the 8 regression subjects. | On the 8 regression subjects (knight, goblin, wolf, dragon, chest, barrel, house, sword):<br>• Blind-read top-1 ≥7/8 (fresh Claude judge at game size).<br>• User blind A/B new vs v0.4: ≥12 of 16 pairs (p ≈ 0.04).<br>• Lineups: the user singles ours out in ≤5 of 12 (chance 4).<br>• Tournament consistent across both orders ≥80%.<br>• Judge catches ≥90% of planted semantic defects with ≤10% false Nos.<br>• Median iterations to a hard pass ≤3, and lower than v0.4 on ≥17 of 24 tasks (p ≈ 0.03).<br>• Median validator rejections per asset ≤3; spec templates ~90% complete for all 8.<br>• User time ≤20 min. | L |
| **S4 · Weapons, props, first-person holding** | • Dimension tables (Cleveland/Met percentiles, Infinigen vs ANSUR, ABO), slot templates.<br>• **Profile library** (≥30 traced profiles) + constraint sketch solver; visual_hull and sweep builders.<br>• 10 weapon and 6 prop generators; hs_finish full, mass_props, function_check; `library_import`.<br>• Grip upgrades: sockets, long guns, sights, hand poses, two hands, pose assets.<br>• **View-model profile, framing solve, sway, bob, recoil and ADS springs.**<br>• Hero bake in `surface_build`; CoACD hulls + engine prep; `library_promote`. | • ≥80% of weapons and props pass every hard gate on the first build; median ≤2 rounds.<br>• 0 hand-typed profile points in the 16 generators.<br>• Arming sword mass and PoB in band.<br>• First-person pistol, rifle and sword: palm + ≥3 fingers, index on trigger, ADS sights ≤1 mm from the eye line, hip framing within 2% of its screen targets, 0 clipping at hip, ADS, sway, bob and recoil extremes.<br>• Generators promoted.<br>• **PC:** the user signs off a UE first-person capture. | L |
| **S5 · Motion eyes and human motion** | • `anim_api`, `motion_report` + predicates (also on re-import), `motion_filmstrip`.<br>• `mocap_ingest` + gait atlas.<br>• Retarget (world delta, re-plant, spine and clavicle, **swing-twist bake**, finger layer).<br>• locomotion_cycle (8-way), `clip_tools`, joint_limits_fit, engine wiring recipes (incl. runtime twist). | • 100% of planted 3 cm skates, 25° pops, 5° seams, knee flips, swapped footfalls and missing twist keys detected; ≥95% of clean mocap cycles pass.<br>• 10 retargeted UAL/CMU clips: skate ≤1 cm, seam ≤1°, twist keys present with ring ratio ≥ threshold on re-import.<br>• Walk, run and sneak at 3 speeds pass on first generation.<br>• FBX and glTF round trip ≤0.5°. Godot imports loops headlessly (PC).<br>• **PC:** a UE blend space walks a slope without visible skate. | L |
| **S6 · Creature gaits, one-shots and pixel rendering** | • quad_gait with the **MANN atlas**, flight_cycle, undulate.<br>• keyframe_director + pose libraries (human and MANN creature); timing tables resolved from mined clips; principle passes; secondary_bake.<br>• Prop articulation clips (chest, door, reload).<br>• **`pixel_render`** + contact-table key frames. | • Wolf trot, horse walk, dragon flap, light and heavy sword attacks, hit, death, chest open and rifle reload pass motion_report and predicates: footfall and DF ±0.05, timing ±1 frame vs the resolved tables, Muybridge per-phase limb angles ±10° and footfalls ±0.05 cycle (realistic creatures).<br>• Blind motion read names each action.<br>• **An 8-direction 64 px wolf trot sheet** passes pixel_preflight (every defining part ≥2 px, 0 partial-alpha pixels, palette locked exactly, flicker within the p95 of 3 CC0 Kenney pixel animations).<br>• **PC:** Godot plays the sheet with nearest filtering. | L |
| **S7 · Clothing and armor** | • Garment archetypes, numpy envelope previews, SDF closing, shell and loft (corrected radius), outer cages, robust weights (scipy), body_mask and **layer_mask**, `rom_check` garment mode, fold_pass, trim_kit, bounded drape, secondary chains.<br>• Harness presets (Met/AIC) with **traced outline and flute profiles**, armor envelopes, regions and shells with caps, joint_articulation, helmet_build, armor_rig + engine recipes, soft layers, `rom_check` armor mode, repair order with constrained trim, panel_split. | • A peasant outfit (shirt, trousers, coat, belt) on realistic, heroic and stylized bodies passes `rom_check(garment)` with no hand edits, including garment-to-garment ≤0.5% after layer_mask; ease within ±2 pp.<br>• Milanese harness + gambeson + tabard on the knight passes the full battery with ≤2 parameter edits and exposure inside its soft band; FBX round trip Δpenetration ≤0.5 mm.<br>• **PC:** UE Leader Pose plays S5 clips for 30 s without visible poke-through. | L |
| **S8 · Surface and delivery** | Full surface plan (rule seams, analytic UVs, xatlas UV2, trim), bakes, material_lint, lod_chain + impostors with engine policy, hulls, per-frame normal maps for `pixel_render`, Unity adapter | • Every S1–S7 asset: TD CV ≤0.15, 0 UV flips or overlaps, bake p95 ≤10°, LOD error ≤1 px at the computed distances, hulls pass.<br>• **PC:** Godot, Unity and UE imports show correct normals (green channel) and collision. | M |
| **S9 · Landscapes and trees** | • Terrain kind + layout diagram; `terrain_build` in the §4.8 order; terrain gates + sightlines; paint (WorldCover-fitted), scatter, terrain review pack.<br>• Exports (UE, Unity, Terrain3D); `dem_fetch`; low-poly, top-down and side-scroller adapters.<br>• Tree kind (Tallo, space colonization, pipe model, cards, wind, impostors). | • Forest valley, mesa desert and island pass the terrain report on the first build after lock or with ≤2 edits. Final conditioning raises no cell >0.5 m outside authored lakes. Round trip ≤1 LSB.<br>• Trees inside the Tallo band with pipe residual ≤5%.<br>• **PC:** UE landscape at the correct Z with a PCG forest; the user approves the spawn view. | L |
| **S10 · Buildings, dressing, faces, hair, breakables, vehicles** | • building_grammar, kit + kit_test, kit_wfc, arch_check.<br>• Layout kind (constraint DSL + annealing).<br>• Face kind (contract, FACS, text and audio lip-sync paths, eyes; Rhubarb opt-in).<br>• Hair kind (stylized clumps, fur shells, HD cards last).<br>• `fracture_prefab`; vehicle and mechanism contracts. | • House kit + WFC dungeon: 0 seam gaps, ADA and navigation pass.<br>• Dressed tavern: 0 floating props, accessibility constraints met.<br>• 10 s of dialog: 100% bilabial closure, blink statistics in range; on the audio path, onsets 100–150 ms ahead.<br>• Hair coverage ≥98% with 0 penetration over ROM.<br>• Breakable crate and 4-wheel cart contract gates pass (Godot headless on the PC).<br>• **PC:** UE Chaos check. | L |
| **S11 · Calibration and library growth** (continuous) | Recalibrate thresholds from Audition Board ratings; taste notes; failure-histogram re-ranking; macro mining; CI across Blender upgrades | • Median iterations to a hard pass shows a non-increasing trend over ≥3 cycles (Theil-Sen slope ≤0).<br>• Judge–user agreement tracked and not falling.<br>• Every remaining heuristic gate is either calibrated or still a warning.<br>• No library generator fails CI on the current Blender LTS. | S/cycle |

**Dependencies.**
- S0b's harness, ledger and acceptance rule are used by every later sprint.
- The FEQ and extras spike decides S2's routes.
- S1's rig contract and `twist_policy` must be fixed before S5 and S7.
- Profile library v0 arrives in S0b, the full library in S4, armor profiles in S7.
- Surface v0 arrives in S2, hero bakes in S4, full surfaces in S8.
- S3's `gate_calibrate` hardens the soft gates of S0b–S2 retroactively.

**Drop order if the schedule slips:** HD hair cards → vehicles → fracture → side-scroller and top-down terrain adapters → sci-fi panel_split → drape_sim → GarmentCode route → MAP-Elites.

**Cut rule.** Only the three most expensive layers are ablated, each on the tasks it touches:
- the compiler core (S0b A/B);
- explore + tournament (S3);
- gate tiers (S3).

A layer stays if it lowers iterations to a hard pass on ≥17 of 24 tasks (sign test, p < 0.05) or wins the user's blind A/B at p < 0.05. Otherwise it is cut or demoted. Other tools are judged by the run ledger: a tool that never changes an outcome over 2 sprints is demoted to optional.

---

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The compiler core does not beat v0.4 for current Claude | S0b A/B gate with a fallback (compiler as validator over v0.4's socketed shape kit); ablations of the expensive layers |
| Evaluator and Blender drift apart, so 2D review stops predicting 3D | Per-kind evaluator contract; consistency gate (IoU + per-part boundary distance + BVH depth); single-triangle convention test; ≤1 px finishing rule; `post_eval` re-rasterization with logged sheet diffs; determinism hash with `tables_version` |
| Creature fit too slow, or fit and build disagree | 2D proxy at 96² (≈8 ms per view measured); SDF confirmation; IoU re-measured on the cage; cage-vs-SDF fidelity metric with inset compensation; S2 exit set on the PC |
| The keep-best loop stalls on coupled findings | Lexicographic acceptance with noise tolerances, Pareto archive, joint solves, global gates always re-run, 10 numeric rounds before escalating |
| Goodhart on uncalibrated heuristics (60/30/10, IoU <0.8, deform 15%, standoff tables, walkable 85%, landmark 2°) | Three gate classes. Heuristics warn until calibrated on a corpus that has the property; taste metrics only report; per-style gate profiles |
| Correct but generic output | Profiles traced from human-made work; morph boxes seeded from human variety; lineups against exemplars; style-match statistics; the user's audition |
| Feature-pixel floors misapplied to thin sub-features | Measured as min-width and extent per part; soft until calibrated on CC0 characters at true game size |
| Worker fragility on Windows (memory, encoding, interleaved output, crashes, antivirus) | File-based exchange with ack; UTF-8; FIFO queue with timeouts; factory reset and orphan purge; psutil restart above 6 GB; rotated checkpoints; one-shot runner fallback |
| Untrusted downloads opened in Blender or numpy | Auto-exec never enabled; `--factory-startup`; glTF/FBX preferred; `load_ui=False`; `allow_pickle=False`; `python -I` on the host |
| Native packages misbehave on Windows | Optional extras with lazy imports. Numpy fallbacks: SOR, CG, Nelder-Mead, priority-flood, convex hull per part; Decimate + Hausdorff for LODs; route B or Skin/Subsurf+Shrinkwrap for FEQ. Spike before promotion; doctor reports extras. |
| FEQ route fails on hands, membranes, non-T rest, or looks like a decimated sculpt | Parallel spike with numeric go/no-go and a KayKit lineup; hm08 hands, FEQ fingers or mittens; membranes as separate sheets; route B facet loft scored on facet statistics |
| MakeHuman macro port subtle | Port from MPFB2 (GPL-3) with notices; golden test, with golden numbers generated on an older Blender if needed |
| LBS candy-wrap at forearm twist and shoulder raise, in Blender or in the engine | Twist bones in the base skeleton; swing-twist keys baked into every clip; runtime twist recipes; deform and motion checks on re-import; corrective shape keys |
| Garment layers collapse through each other at deep bends | `layer_mask` deletes hidden inner faces; outer-layer weights copied to the inner layer in the overlap band |
| Terrain hydrology gates fail by stage order | Relief calibrated before erosion; corridor masks on detail; bridges at crossings; rivers and priority-flood conditioning last; pit gate measures the final fill |
| Claude judges Claude; position and self-enhancement bias | Numbers stay authoritative; fresh-context judge without code or authorship; one criterion per question; both-order matches with the incumbent; lineups anchored by human-made exemplars; agreement with the user tracked |
| References in perspective, posed or stylized; landmark reading inaccurate; images downscaled to about 1568 px | Automatic landmarks first; grid reading only for internal boundaries; calibration in S1; zoom crops; user clicks; pose dials; landmark-only fits for perspective images |
| Silhouette metrics blind to depth and interior form | Per-view depth error; top views; clay and normal renders in the checklist; cross-sections |
| Noisy museum and Wikidata dimensions | Robust p5–p95; unit and convention tags; per-type sanity bounds; psn-normalized SPARQL |
| Data priors pull toward realism against stylized art direction | Bible style multipliers; z-score reporting instead of failure; style canon from CC0 packs |
| Creatures beyond data (dragons, hybrids) | Per-donor tables fetched in S2; `recalled` → warnings until fetched; donor templates fitted to ≥2 references; numeric graft rules; remaining proportions as `design` ranges resolved by explore or the user |
| Rig and rest-pose contract changes force re-skinning | Decided in S1 (A45, twist and helper bones in the base skeleton, `twist_policy`) before clothing, armor and animation |
| UE and Unity import can't be checked headlessly; CI can't download Godot | Blender round trips automated; Godot headless import on the PC unless CI can fetch it; one PC checklist per adapter; never claim acceptance without a capture |
| Compute cost (full multi-scale erosion 25–30 min on CPU; millions of ROM ray casts; cloth taking minutes; road A* at 2017²) | Coarse to fine; CuPy or numba on the 4070 Ti Super; 10–20 extreme poses while iterating and the full battery at sign-off; roads planned at ≤512²; drape ≤5–10k verts |
| Licence lineage lost through derived data (atlases, pose libraries, canons, kitbash parts, NC tools) | Licence IDs and flags, `inputs` lineage, per-element cache tags, tool tags, export policy by flags, no free-text matching, tests with known misfires |
| Licence obligations in the public repo (ports, CC BY tables) | `LICENSE`, `THIRD_PARTY_NOTICES.md`, module headers, `data/LICENSES.md`, CI checks; NC/QAL-derived data never committed; engine-side output under MIT |
| Recalled numbers (Pennycuick, Alexander, Heglund, neck ROM, Rmin, fabric thickness, LOP, UE walkable angle, bat AR) | The `recalled` tag means warnings only, until a primary source is fetched |
| Borderline cases under "no other models" (Rhubarb, FABDEM's ML correction, the 2D image pipeline) | Opt-in after explicit user confirmation; defaults use the text lip-sync path and the Copernicus DSM in statistics mode; the 2D question is put to the user |
| Spec authoring cost and token use | Templates about 90% complete; `spec_edit` deltas; macros; ≤12 leaves per level; validator rejections and tokens logged; spec-free scene tools |
| User rating time is the scarce resource | ≤20 min per sprint; numeric KPIs primary; only 3 layers ablated with statistical thresholds |
| Scope (13 sprints, mostly L) and Blender API churn | S0a ships value in 1–2 weeks; pain order; drop order; cut rule; CI re-runs snippets and generators on every Blender upgrade |

### What stays hard

- **Hero-close organic detail.** HD humans are MakeHuman-grade. Faces, musculature, wrinkles and hands seen up close are beyond what code can sculpt well. hm08 targets, normal bakes, wear masks and CC0 materials narrow the gap without closing it.
- **Taste beyond rules.** Lineups and style statistics catch "generic", but appeal, charm and acting can't be fully reduced to checks. The user's audition stays the final judge, and calibration needs the user's rating time.
- **Heavily stylized faces** (anime, cartoon) and perspective concept art. Fitting is limited to landmarks, and stylized faces depend on transferring the ARKit keys by correspondence.
- **Fantasy proportions beyond the data.** Dragons and hybrids rest on donor tables plus `design` ranges. Plausibility is checked, but beauty still comes from explore and the user.
- **Loose cloth and HD hair cards.** These stay bounded, slower and less predictable than rigid parts.
- **Motion outside library coverage.** Unusual human acting and creature bites, roars and pounces have no generative fallback by design. They rely on keyframe_director, mined poses and procedural channels under predicates.
- **Engine runtime behaviour** (Control Rig followers, runtime twist, blend spaces, Nanite and Lumen looks) can only be confirmed on the user's PC.

---

## Review log

Reviewers: **A** = feasibility and architecture, **B** = licences and provenance, **C** = user value and art.

### Blockers

| # | Issue | Resolution |
|---|---|---|
| A-B1 | "One geometry for every view" was true only for assemblies: visual hulls, garments, armor, terrain and FEQ cages had no numpy triangles, and creature fit geometry differed from the built cage | Principle 3 restated per kind. §2.3 adds an evaluator contract table with one `EvalMesh` interface and `post_eval` for Blender-made triangles. Visual hulls are evaluated by numpy ray–prism intervals. Garment and harness envelopes are previewed in numpy. Creatures fit on a 2D proxy, confirm on the SDF raster and re-measure on the cage, with a separate cage-fidelity metric and inset compensation (§3.3, §3.4). |
| C-B1 | S0 was plumbing-first and not pain-ordered: months of work before any visible change | S0 split. **S0a (1–2 weeks, v0.4)** is quick wins on v0.3: PC smoke test, camera readability, canon data fixes including MT/F, mask and signed-distance fixes, checklist critique, licence fixes, and the baseline. **S0b** builds the compiler core and must win an A/B against v0.4 on 6 props before more builders are built, with a fallback if it doesn't. The worker moved to S1; spikes run in parallel (§9). |

### Major issues

| # | Issue | Resolution |
|---|---|---|
| A-1 | Creature fit budget not credible (1.1 s per 128² view brute force) | 2D projected proxy measured at ≈8 ms per 96² view (400 evaluations × 2 views ≈ 7 s); SDF confirmation; 64² SOR for inflate parts (≈25 ms measured); S2 exit measured on the PC (§3.3, §2.3) |
| A-2 | S0 overloaded and dependent on S2 components; no go/no-go thresholds | S0a/S0b split; S0b builders reduced to four; FEQ spike runs in parallel on the research prototype, with numeric thresholds and a lineup, decided before S2 (§9) |
| A-3 | Consistency gate IoU ≥0.99 fails on thin parts; depth source unspecified; it broke the `spec_check` ≤1 s budget; "eval" undefined | Per-part boundary distance p95 ≤0.5 px at a resolution where the smallest part spans ≥10 px, plus whole-object IoU; single-triangle convention test; BVH-ray depth; runs only after builds and Blender-only operations (T2b); "eval" defined as one numpy view at 256² (§3.4, §2.5, S0b exit) |
| A-4 / C-1 | "Any regression reverts" stalls on coupled findings; noisy metrics; global gates not re-run; caps undercut MoVer | Lexicographic acceptance with noise tolerances, a Pareto archive, joint solves for coupled findings, global gates always re-run, up to 10 numeric rounds, judge rounds capped at 2 (§2.6, principle 6, decision 21) |
| A-5 | Gate-trust rule contradicted decision 7; corpora did not have the gated properties; per-sprint calibration impossible before S3 | Three gate classes: hard gates block from day one with `defect_inject` recall only; soft gates calibrated on named corpora that have the property; report-only class. Per-style profiles (`cad_clean`, `kitbash`, `organic`). Harness moved to S0b (§2.5) |
| A-6 | S1 exit self-contradictory (CC0 rigs have no twist bones) | Paired calibration: hm08 with vs without twist bones; twist excluded from the CC0 false-positive set (§2.5, S1 exit) |
| A-7 / C-6 | Twist bones not driven in the engines; candy-wrap returns | Swing-twist twist keys baked into every exported clip; runtime recipes (UE AnimBP or Control Rig, Godot BoneTwistDisperser3D, Unity Twist Correction) for engine-retargeted clips; `twist_policy` set in S1; hard motion check; deform and motion checks on re-import (§4.1, §5.3, §5.5, decision 25) |
| A-8 | Terrain stage order guaranteed hydrology failures; relief calibrated after erosion | Relief calibrated before erosion on macro + noise; zero-detail corridors; bridges at crossings; rivers carved after roads, clamp and detail; priority-flood conditioning as the last height edit; pit gate measures the final fill (§4.8) |
| A-9 | Inner garment layers collapse through outer layers | `layer_mask`: inner faces under opaque layers deleted, outer-layer weights copied to the inner layer in the overlap band; S7 exit checks garment-to-garment after masking (§4.4) |
| A-10 | 3D→Pixel renderer unscheduled despite the pixel exit | `pixel_render` tool scheduled in S6 with its own exit; S8 adds per-frame normal maps (§4.12, §8.1, §9) |
| A-11 / C-14 | Cut rule not executable; rater unnamed; S3 6/8 not significant; S11 "falls every cycle" | Numeric ledger KPIs are primary; the user is the named rater (≤20 min per sprint); only 3 layers ablated; thresholds ≥17/24 (p ≈ 0.03) and ≥12/16 (p ≈ 0.04); S11 uses a ≥3-cycle trend (§1 caveat, §9) |
| B-1 | Generative paths survived in PLAN §2/§3/§6/§7/§8, DOWNLOADS and doctor | Precedence widened to all 3D and animation content; removals listed by line; principles 3 and 8 rewritten; MetaHuman marked unverified; Unity Generators removed; ComfyUI check relabelled; 2D-pipeline question put to the user (§2.7) |
| B-2 | Provenance could not follow derived data; the NC substring test misfires | SPDX/LicenseRef IDs with a flag vocabulary; `inputs` lineage; per-element cache tags; tool tags; export policy by flags; free text never matched; misfire strings used as tests (§2.7, S0a/S0b) |
| B-3 | Ported code without notices; no LICENSE file | `LICENSE` (GPL-3); `THIRD_PARTY_NOTICES.md`; module headers; porting rule; CI check (§2.7, §7) |
| B-4 | CC BY tables without attribution; committed-vs-cache contradiction | `data/LICENSES.md` with exact attribution strings; committed vs local decided per table; AVONET, ABO, Wang 2011 and Fukuchi added to §7.1; validator and CI refuse unlisted tables; Poly Haven credit in the README, `library_search` and CREDITS (§2.2, §7.1) |
| B-5 | Bandai was "opt-in" in §7.2 but a default pose source in §5.1; pose libraries might be committed | Pose libraries and atlases declared local caches, never committed, with per-element flags; §5.1 and §7.2 made consistent. **Opt-in default not adopted:** PLAN §0 records that the user accepts NC licences, so NC data stays on locally (confirmed once), flagged, and blocked by `commercial: true` (decision 22). |
| B-6 | Native packages "required" before the spike; one missing wheel downs the server; OpenCV missing | Core kept minimal; native packages moved to optional extras with lazy imports and numpy fallbacks; opencv-python-headless added as `opus[ref]`; promotion only after the spike (§2.7) |
| C-2 | Profiles, anchors and stations were invented as dimensionless numbers | Profile library traced classically from CC0/CC BY human-made sources; Gauss-Newton constraint sketch solver; hand-typed profile points, anchors and hex colours rejected unless `design`; explore chooses profiles first (§2.1, §2.2, §2.3) |
| C-3 | Nothing measured appeal or genericness | Lineup mode against human-made exemplars; soft style-match statistics; morph boxes seeded from human-made variety; lineup exits in S2 and S3; principle 10 (§2.6, §3.2) |
| C-4 | Dragons and fantasy creatures weakly grounded | Per-donor morphometric tables (bats, pterosaurs, varanids, crocodilians; Pennycuick) fetched in S2, `recalled` until then; donor templates fitted to ≥2 references before shipping; numeric graft rules; worked example (e) (§4.3, §6e) |
| C-5 | No pose data for creatures; timing tables unsourced | MANN on by default (local): quadruped atlas and creature pose library rescaled by dynamic similarity; timing tables tagged `design`, resolved by audition or measured from mined clips; non-mammal channels declared procedural under predicates (§5.1, §5.2). MANN has no bites or roars; this is listed in §10. |
| C-7 | The approved design differed from the build for garments and armor; worked examples read as near-term | Numpy envelope previews for garments and harnesses at explore and lock; `post_eval` sheet diffs; a table of the sprint where each example first runs end to end, with interim paths (§4.4, §4.5, §6) |
| C-8 | Armor style by eye; `trim_to_clear` yields stingy armor | Outlines and flute lines traced from Met/AIC/Cleveland CC0 and Swedish History Museum CC BY scans; repair order: articulation → θ_free and followers → constrained trim with an exposure ceiling (§4.5) |
| C-9 | First-person framing still invented | View-model camera profile; hip pose solved from screen-space targets measured from the user's screenshots or chosen by audition; sway, bob, recoil and ADS springs with per-frame checks in S4 (§4.6, §6c) |
| C-10 | `ref_extract` regressed v0.2's automatic landmarks; calibration came too late; no style references | Automatic landmarks first; grid reading only for internal boundaries with rulers; calibration moved to S1; the user's game screenshots accepted as private style references (§3.3) |
| C-11 | The FEQ low-poly route gives a "decimated sculpt" look | Facet statistics in the style canon; route B `facet_loft` or planar clustering; KayKit lineup in the FEQ go/no-go (§4.2, §9) |
| C-12 | Surfaces arrived late; colours chosen by eye; grey mannequins | `surface_build` v0 in S2 for all eval subjects (palette atlas, AO and curvature wear, measured PBR); palettes from packs, references or Lospec, never typed hex; face-shape operators and stylized hair v0 in S3; HD fidelity stated as MakeHuman-grade (§4.12, §4.1, §9) |

### Minor issues (resolved where cheap)

| # | Issue | Resolution |
|---|---|---|
| A-m1 | PhyloPic references are posed | Pose dials, standing references preferred, otherwise landmark-only (§3.3) |
| A-m2 | Voxel-remeshed hands welded into the FEQ cage | hm08 hand topology, FEQ finger branches or mittens (§2.3, §4.2) |
| A-m3 | Heat weights fail on sheets; geodesic voxel bind is not a Blender feature | Rigid ears and fins; membranes weighted analytically by spar distance (§4.3) |
| A-m4 | Worker robustness | File exchange + ack, UTF-8, FIFO queue with timeouts, psutil, GPU re-enabled after reset, rotated checkpoints (§2.7) |
| A-m5 | Determinism across float32/float64; table rebuilds | Quantized float32 hash; lock snapshots resolved values and `tables_version` (§2.1, §2.7) |
| A-m6 | Dependencies (OpenCV, psutil, EXR, meshoptimizer) | Added or rerouted: EXR via the worker; meshoptimizer dropped; pyfqmr as an extra (§2.7) |
| A-m7 | Packs without stable URLs | `data_fetch --from-file` with sha256, snapshot and date |
| A-m8 | MPFB2 is GPL-3 and portable; "no vendored code" conflicted with planned ports | Decision 14 and the porting rule; golden numbers from an older Blender if needed |
| A-m9 | Quads and poles were hard gates | Moved to soft; hm08 vertex order is the hard contract |
| A-m10 | Text lip sync has no audio timing | Separate text and audio paths; onset gate only on the audio path |
| A-m11 | Road A* and ROM batteries too slow | Roads planned at ≤512²; T3 split into iterate and sign-off budgets |
| A-m12 | No CI; Godot can't be downloaded in the cloud | CI workflow is an S0b deliverable; Workbench/CPU only; Godot import on the PC |
| A-m13 | Wrong numbers and labels | 11 sides (handguard 27); Johnson recognition 8 px and identification 13 px; the socket now uses the slot anchor at 0.625; promote rule re-sourced; `defect_inject` added to §8; descriptors on analytic outlines |
| B-m1 | CDC, NHANES and Muybridge licence labels | Relabelled; Enlyte marked recalled; Muybridge source named |
| B-m2 | Quaternius licence contradiction | Per-download snapshot; `no-redistribute-as-asset` by default; UAL ranked after CMU until a CC0 snapshot is recorded |
| B-m3 | FABDEM share-alike | Flags `nc, sa`; `base` mode stamps outputs; `stats` mode by default |
| B-m4 | MakeHuman licence reasoning | Port from MPFB2 GPL-3; reimplement-only reserved for NC, ND, AGPL-only and unlicensed code |
| B-m5 | CI corpus could leak NC or QAL data | Pinned CC0-only CI corpus; other calibration local only; no fetched assets in CI artifacts |
| B-m6 | Worker opens untrusted files | Auto-exec off, factory startup, glTF/FBX preferred, `load_ui=False`, `allow_pickle=False` |
| C-m1 | Kenney and Poly Haven break CAD-clean gates | Per-style gate profiles (merged with A-5) |
| C-m2 | User rating time unbudgeted | ≤20 min per sprint (merged with A-11) |
| C-m3 | §6 numbers read as expectations | Labelled illustrative; targets moved into the exits |
| C-m4 | Spec authoring cost unmeasured | Validator rejections and tokens logged; templates about 90% complete; spec-free scene tools |
| C-m5 | Muybridge IoU produces false failures | Per-phase limb angles and footfall timing from keypoints; IoU report-only |

### Reviewer suggestions not adopted, or adopted only in part

- **B-5 (Bandai and MANN opt-in):** not adopted as a default. PLAN §0 records that NC licences are fine for this user. NC data stays local, flagged and export-blocked when `commercial: true`.
- **A-2 (persistent worker in the first sprint):** not adopted. S0b runs on the one-shot runner, and the worker arrives in S1 with its own exit, as reviewer C proposed.
- **C-5 (a creature one-shot library built from MANN):** adopted in part. MANN contains locomotion, jump, sit, lie and stand, but no bites, roars or pounces; those stay procedural under predicates.
- **C-12 (Lospec palettes and the O'Donovan model as priors):** adopted in part. Lospec has no stated licence and O'Donovan is CC BY-NC-SA, so both are used only as local priors and report-only scores, never committed.