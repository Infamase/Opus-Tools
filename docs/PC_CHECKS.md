# PC checks for S0a

About 10 minutes on the Windows PC. It answers four questions: does the update (v0.4.0) install,
is the doctor green, does every tool (the v0.3 tools and the v0.4 additions) run on Windows, and
does a 1.8 m blockout come into Unreal 180 units tall. Paste each prompt as written and note
anything that fails.

## 1. Update the plugin (2 min)

In PowerShell:

```
claude plugin marketplace update opus-tools
claude plugin update opus-tools@opus-tools
```

Fully quit the desktop app and reopen it. `claude plugin list` shows the installed version,
which should be 0.4.0.

## 2. Doctor (1 min)

Make an empty folder `C:\opus-check` and open a Code session in it. Paste:

> Run opus_doctor and show me the report.

Green: the first line says **ready**, and python, blender and gpu start with `OK`. A missing
project bible is fine; the next step makes one.

## 3. Every tool once (6 min, mostly waiting)

Paste these one at a time in the same session.

**Project and pixel tools**

> Run project_bible with action init, project "Opus check" and styles "pixel, lowpoly". Make a
> 5-step palette_ramp from #3a7d44 saved as palettes/grass.hex and one from #7d3a6b saved as
> palettes/berry.hex. Copy the newest PNG in .opus/out/palette to sprites/swatch.png. Then run
> sprite_inspect on sprites/swatch.png, pixel_cleanup on it, palette_apply with
> palettes/grass.hex, and palette_swap from palettes/grass.hex to palettes/berry.hex. List
> each tool as ran or failed, with the error if it failed.

**Body and model tools**

> Make a realistic humanoid body_blockout 1.8 m tall saved as bodies/human.blend, with glb
> true. On bodies/human.blend run model_report, proportion_check with preset realistic, look_at
> with target hand_l and zoom 2, lookdev_sheet, mesh_lint with category character, and
> blind_read_sheet. Then run look_at with views front and render_pass silhouette, and
> reference_match of bodies/human.blend against that image. Run readability_check on
> bodies/human.blend with defining "head, hand_l, foot_l", and blind_read_sheet with game_size
> true. List each tool as ran or failed, give the height from the body_blockout report, and the
> subject height in px at each distance from readability_check.

**Judge sheets**

> Make heroic and stylized humanoid body_blockouts saved as bodies/heroic.blend and
> bodies/stylized.blend. Run lineup_sheet with images bodies/human.blend, exemplars
> bodies/heroic.blend and bodies/stylized.blend, and distance_m 3.5, then ab_sheet with a
> bodies/human.blend and b bodies/heroic.blend. List each tool as ran or failed, with the
> height_px the lineup used.

**Grip tools**

> Write and run a Blender script that saves props/club.blend with one object named Club: a
> cylinder 3.2 cm across and 60 cm long, standing upright at the origin. Run grip_define on
> props/club.blend for object Club with part Club. Run grip_hold with rig bodies/human.blend,
> object_path props/club.blend and side r, then grip_check on the file grip_hold saved. List
> each tool as ran or failed, and give the grip_check verdict.

**Ledgers**

> Run ledger_record for bodies/human.blend with source "Opus Tools body_blockout" and
> licence_id CC0-1.0, then licence_check, licence_check with text "CC BY-NC 4.0", and
> make_credits. Then run_log a run_start with task knight and asset bodies/human.blend, an
> iteration with n 1 and hard_fail_count 0, an accept, and run_stats. List each tool as ran or
> failed, with the licence ID the text classified to.

## 4. A 1.8 m blockout is 180 units in Unreal (2 min)

1. In any Unreal project, import `C:\opus-check\bodies\human.glb` from the Content Browser
   (Import, default options).
2. Drag the imported mesh into the level and set its location to 0, 0, 0.
3. Click **Perspective** at the top left of the viewport and pick **Front**.
4. Hold the middle mouse button and drag from the soles to the top of the head. The ruler shows
   the distance in units. Expect **178–182**.

With an Unreal MCP connected you can ask instead: "Import C:\opus-check\bodies\human.glb,
place it at the origin and tell me its bounding box height in Unreal units."

## 5. What to report back

Copy this, fill it in and paste it into the chat:

```
Plugin version (claude plugin list):
Doctor first line, and any line starting with --:
Tools that failed (name and error):
Grip check verdict:
human.glb height in Unreal: ___ units
Anything that took over a minute:
```

Delete `C:\opus-check` afterwards. Nothing from it goes into the repo.
