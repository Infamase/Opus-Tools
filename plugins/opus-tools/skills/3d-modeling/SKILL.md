---
name: 3d-modeling
description: Build, check and fix 3D models for games (Unreal, Godot, Unity) in Blender 5.x, low-poly and HD, with the Opus 3D tools. Characters and creatures start from canon-proportioned rigged blockouts (body_blockout) and are verified with proportion_check, reference_match and a blind read; look_at and model_report show any angle and the part structure; grip_define, grip_hold and grip_check put weapons, tools and props in hands correctly (first-person views included); lookdev_sheet and mesh_lint check the result. Use whenever creating, editing, importing or reviewing 3D models, props, environments, characters, creatures, or anything a character holds.
---

# 3D modeling with Opus Tools

You can't see a mesh by reading its vertices, and you can't eyeball proportions from
memory. Start bodies from data, measure them, and look at them. Every time.

## Before modeling: the feature brief

Write it down (to the user or in your notes) before touching Blender:

1. **Subject and use:** what it is, game camera (first person, third person, top-down,
   side-scroller), how big it appears on screen, target engine.
2. **5–7 defining features**, the ones a stranger needs to recognize it. A western
   dragon: long S-curved neck, horned wedge head, bat wings with finger spars, membranes,
   four legs, long tapering tail, back spines. A knight: helmet with visor slit, pauldrons,
   tabard, sword and shield. If a feature isn't on this list, it's detail for later.
3. **Proportion intent:** which canon (realistic 7.5 heads, heroic 8, stylized 6, chibi 3)
   and which deliberate exaggerations ("head 20% bigger, hands oversized").
4. **Shape language:** round = friendly, square = sturdy, triangles = danger. Pick one to
   dominate and one to accent.

Get reference when you can: images from the user, or a concept sheet. Agree on real-world
size (see Conventions).

## Characters and creatures: canon first

1. **`body_blockout`** with the closest archetype and preset at the target height:
   humanoid realistic / heroic / stylized / chibi, quadruped dog / horse / cat, dragon
   western. Other creatures start from the nearest one (wolf, bear → dog; deer, unicorn →
   horse; wyvern, griffin → dragon) and you move joints from there. It returns a rigged,
   watertight body plus `landmarks_m` (chin, shoulder, waist, crotch, knee heights, limb
   lengths, widths). Model to those numbers.
2. **Build on it.**
   - HD: sculpt or shrinkwrap over the blockout, or replace parts with refined meshes,
     keeping joint positions. Keep the rig; bind your mesh to it (`ARMATURE_AUTO`).
   - Low-poly / blocky: build your chunky forms per bone region (`model_report` lists them
     with lengths and girths), keeping the landmark heights. Taper and chamfer boxes; a
     torso is a wedge, not a cube; limbs narrow toward the hands and feet.
3. **`proportion_check`** after every major change. Fix every finding you didn't choose
   in the brief. Red in the overlay is where the model sticks out, blue where it's missing
   volume. Name the preset when the style is decided; `auto` tells you which canon the
   model actually resembles.
4. **`reference_match`** against the concept or reference image (front, then side), with
   `humanoid: true` for people.
5. **`look_at`** for close inspection: hands, face, joints, a wing from below
   (`target: "hand_l"`, `zoom: 2`, `views: "20,-30"`). Use `render_pass: "focus"` to see one
   region highlighted, `"parts"` for a labeled map.
6. **`model_report`**: parts that should touch must be in contact, nothing floating by
   accident, symmetric where intended, center of mass over the feet.
7. **Blind read.** `blind_read_sheet`, then give its prompt to a fresh subagent (the
   `art-director` agent) **without saying what the model is**. If its top guess isn't the
   subject, the defining features aren't reading: exaggerate them (bigger, clearer in
   silhouette, more contrast), then test again. Without subagents, skip this step and say so.
8. **`lookdev_sheet`** and **`mesh_lint`** (category `character` or `hero_character`) last.

## Hands that hold things (first person especially)

Never place a held object by eye: it ends up inside the palm or floating beside it. Use the
grip tools, which seat the handle on the palm's skin and close each finger until it touches.

1. **Hands with fingers.** `body_blockout` humans have 15 finger bones per hand (Unreal
   names). Your own rigs work if their finger bones use Unreal, Mixamo, Rigify or
   Unity/Godot humanoid names.
2. **`grip_define` on the object.** `part` = the handle mesh. `up` = toward the end the
   thumb points to (blade, hammer head, slide). Round, symmetric handles: default palm side
   is fine. Pistol-style grips are handed: give `point_axis` (the barrel or nozzle axis,
   e.g. `-Y`) and `hand` instead of `palm_side`. `center` slides the hand along the handle
   (pistols sit high, about 0.6). Triggers: `index: "trigger"` plus the trigger's front
   point. Check the render: blue axis, red arrow toward the palm, green toward the thumb.
3. **`grip_hold`.** `pose`: `rest`, `front`, `fp_hip` (first-person hip spot; long guns sit
   closer: `offset` "0.05,0.12,0.25"), or `fp_ads` (needs a `SOCKET_sight` empty). For two
   hands, hold with the main hand first, then run `grip_hold` on the saved file with
   `move: "hand"`, `side: "l"` and the second grip (a handguard, a two-handed hilt).
4. **Read the report**, not just the picture:
   - verdict `good grip`: the palm and at least three fingers touch, nothing sinks in;
   - `aim_vs_hand_deg` above ~15 on a pistol means the grip is defined for the wrong hand;
   - `wrist_bend_deg` above ~50 looks broken: move the `offset`;
   - "can't reach" or "passes through the body": move the object or change the pose.
5. **`grip_check`** any scene after manual edits, imported animations or the user's own rigs.

**In the engine:** the object is parented to a `weapon_r` / `weapon_l` bone at its origin.
Attach the weapon to that bone with zero offset (Unreal: attach to the socket or bone
`weapon_r`; Godot: `BoneAttachment3D`; Unity: parent to the bone's transform). The finger
pose is the `Grip_<object>_<side>` action: layer it over locomotion on the hand and finger
bones (Unreal: Layered blend per bone from `hand_r`; Godot: an AnimationTree blend with a
bone filter; Unity: an Avatar Mask). Check one attach in the engine before doing a batch.

## Props and environments

1. Real-world size first (Conventions), then the feature brief's 2–3 defining features.
2. Model it, save the .blend, then `lookdev_sheet` and `mesh_lint` with the right category
   (prop_small, prop_large, environment_piece).
3. `model_report` for assemblies: every part attached, nothing floating, bases resting on
   the floor.
4. Fix, save, repeat. Show the user the final sheet. To pick between two versions, ask the
   `art-director` agent.

Use `engine: "eevee"` in `lookdev_sheet` for HD/PBR assets, where material response matters.
Workbench is the fast default for low-poly and form checks.

## Making it look intentional, not generic

- **Silhouette first, then secondary forms, then detail.** Check silhouettes at the size
  the asset appears in the game camera (the blind-read sheet has a small view).
- **Big, medium, small.** Vary the size of shapes. Uniform sizes and spacing read as
  procedural.
- **Exaggerate the defining features** 10–30% in stylized work, never the incidental ones.
- **Straights against curves.** A straight back leg against a curved calf, a flat blade
  against a curved guard.
- **Overlap and taper:** parts tuck into each other (pauldron over upper arm, scales
  overlapping) and limbs taper. Primitives butting edge to edge look like toys.
- **Bevel hard edges.** Small chamfers or weighted normals catch highlights.
- **Low-poly:** chunky readable proportions, flat-shaded faces, a limited palette (vertex
  colors or a palette atlas), polygons spent on the silhouette.
- **HD:** real proportions, PBR materials, even texel density (bible value), hidden UV
  seams, no overlapping UVs for unique bakes.

## Conventions

- **Scale:** 1 Blender unit = 1 m. Door 2.0–2.2 m, adult 1.6–1.9 m, table 0.75 m, chair
  seat 0.45 m, crate 0.5–1.0 m, horse 1.6 m at the withers, large dog 0.6 m.
- **Facing:** the front faces Blender −Y (Front view), Z up, left side is +X.
- **Origin:** bottom center for props and characters, unless the bible says otherwise.
  Apply scale and rotation before export.
- **Rig names:** blockouts use Unreal mannequin names (root, pelvis, spine_01..03,
  neck_01, head, clavicle_l, upperarm_l, lowerarm_l, hand_l, thigh_l, calf_l, foot_l,
  ball_l). Keep them.

## Export per engine

Verify every import in the engine with its MCP (bounds, facing, skeleton) rather than
assuming. Record library or AI-sourced assets with `ledger_record`.

- **Unreal (preferred):** FBX with scale applied, Add Leaf Bones off, smoothing set to
  Face. Keep the armature object named `Armature` (blockouts already are): Unreal's
  importer reads that name as Blender's armature node instead of adding an extra root
  bone. Check that a 1.8 m character imports about 180 units tall. The UE-style bone
  names retarget to the mannequin through an IK Retargeter; recent Unreal versions can
  auto-generate the retarget setup when names match.
- **Godot:** glTF 2.0 binary (.glb), +Y up (default), modifiers applied. Node name
  suffixes: `-col`, `-convcolonly`, `-navmesh`, `-loop`. Map the skeleton to Godot's
  humanoid profile with a BoneMap when retargeting.
- **Unity:** FBX, scale applied. Set the rig to Humanoid and check the Avatar mapping;
  fix any bone auto-mapping missed.

## Fixing lint findings

| Finding | Fix |
|---|---|
| flipped normals / inside out | recalculate outside (`bmesh.ops.recalc_face_normals`, or Shift+N) |
| unapplied / negative scale | apply transforms (`bpy.ops.object.transform_apply(scale=True)`) |
| floating part | snap it onto its support, or confirm it's intentional |
| loose / degenerate geometry | merge by distance, delete loose |
| n-gons on deforming meshes | triangulate or rebuild as quads |
| no UVs / collapsed / overlapping UVs | unwrap (Smart UV Project for props), pack islands |
| uneven texel density | average island scale, then pack |
| over budget | limited dissolve, decimate, or remove hidden faces |

## Blender 5.x scripting gotchas

- `material.use_nodes` is deprecated (always on). Use `mat.node_tree` directly.
- The EEVEE engine id is `BLENDER_EEVEE`.
- Actions are slotted: `action.fcurves` was removed in 5.0. Use channelbags
  (`bpy_extras.anim_utils.action_ensure_channelbag_for_slot`).
- Geometry Nodes modifier inputs moved to `mod.properties.inputs` in 5.2.
- Set `ImageFormatSettings.media_type` before `file_format`.
- In bmesh primitives, `create_cone(..., radius1=, radius2=)` and
  `create_uvsphere(..., radius=)` take radii.
- After deleting objects, call `view_layer.update()` before selecting others.
- When unsure about an API, use the official Blender MCP's documentation search.
