---
name: 3d-modeling
description: Build, check and fix 3D models for Godot games in Blender 5.x (low-poly and HD) with the Opus 3D tools. lookdev_sheet renders a model from every side; mesh_lint checks game-readiness. Use whenever creating, editing, importing or reviewing 3D models, props, environments or characters for a game.
---

# 3D modeling with Opus Tools

You can't see a mesh by reading its vertices. Render it with `lookdev_sheet` and check it
with `mesh_lint`, every time.

## The loop

1. Read the project bible (`project_bible`): styles, triangle budgets per category, texel
   density, origin rule, look-dev engine. Get reference: ask the user for images or agree
   on real-world dimensions first.
2. Build or edit the model (through the Blender MCP or a script) and **save the .blend**.
3. Run `lookdev_sheet` on the file. Check proportions against the scale figure,
   silhouettes from the front and side, form in clay, and topology density in the
   wireframe. Faces should read blue (outward), and the UV checker should show even
   squares.
4. Run `mesh_lint` with the right `category` (prop_small, prop_large, environment_piece,
   character, hero_character).
5. Fix, save, and repeat until there are no errors and the sheet looks right. Show the user
   the final sheet. For two candidate versions, ask the `art-director` agent to pick.

Use `engine: "eevee"` for HD/PBR assets, where material response matters. Workbench is the
fast default for low-poly and form checks.

## Conventions

- **Scale:** 1 Blender unit = 1 m = 1 Godot unit. Typical sizes: door 2.0–2.2 m tall,
  adult 1.6–1.9 m, table 0.75 m, chair seat 0.45 m, crate 0.5–1.0 m.
- **Facing:** the model's front faces Blender −Y (Front view). glTF export turns that into
  +Z, which is Godot's model front. Blender +Z up becomes Godot +Y up.
- **Origin:** bottom center for props, unless the bible says otherwise. Apply scale and
  rotation before export.

## Pick the route by asset type

| Asset | Route |
|---|---|
| Hard-surface props, architecture, modular kits, low-poly stylized | Model in code: bmesh and modifiers, real proportions, bevels. |
| Organic HD characters and creatures | Don't hand-place anatomy. Start from a library base (CC0 Quaternius/Kenney), image-to-3D (Phase 2), or the user's blockout, then clean up and check. |
| Downloaded or generated meshes | `mesh_lint` first, then fix scale, origin, normals and budget, then `lookdev_sheet`. |

## Craft rules

1. **Silhouette first, then secondary forms, then detail.** Check the silhouette tiles at
   the size the asset will appear in the game camera.
2. **Bevel hard edges.** Small chamfers or weighted normals catch highlights. Razor-sharp CG
   edges read as fake in HD and as flat in low-poly.
3. **Low-poly stylized:** exaggerate proportions (chunky and readable), use flat-shaded
   faces with a limited palette (vertex colors or a palette texture atlas), and spend
   polygons on the silhouette.
4. **HD:** real proportions, PBR materials, an even texel density (bible value), UV seams in
   hidden places, and no overlapping UVs for unique bakes. Mirrored overlaps are fine for
   tiling or trim textures.
5. **Materials that reach Godot:** Principled BSDF with image textures exports to glTF.
   Procedural node trees do not; bake them to textures first.
6. **Budgets:** stay inside the bible's triangle budget. Flat areas need few polygons, the
   silhouette needs more.

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
- When unsure about an API, use the official Blender MCP's documentation search.

## Export to Godot

glTF 2.0 binary (.glb), +Y up (default), modifiers applied. Godot reads hints from node
name suffixes: `-col` (collision), `-convcolonly`, `-navmesh`, `-loop` (animation).
Record library or AI-sourced assets with `ledger_record`.
