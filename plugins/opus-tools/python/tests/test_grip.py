"""Hands holding things: grips on objects, the grip solver, and the grip check."""

import json
import subprocess
from pathlib import Path

import pytest

from opus.blender.runner import (
    BLENDER_MODULES,
    BlenderNotFound,
    BlenderTaskError,
    find_blender,
    run_task,
)

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

pytestmark = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"

# skin the held club to weapon_r with an Armature modifier, where the bone-parented club sits
# at the rig's rest pose, so the posed club lands where it was
SKIN_TO_WEAPON = """
import sys, bpy
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
club = bpy.data.objects["Club"]
assert club.parent_type == "BONE" and club.parent_bone == "weapon_r"
arm.data.bones["weapon_r"].use_deform = True
arm.data.pose_position = "REST"
bpy.context.view_layer.update()
rest = club.matrix_world.copy()
club.parent_type = "OBJECT"
bpy.context.view_layer.update()
club.matrix_world = rest
for o in (club, *club.children_recursive):
    if o.type == "MESH":
        o.vertex_groups.new(name="weapon_r").add(range(len(o.data.vertices)), 1.0, "REPLACE")
        o.modifiers.new("Armature", "ARMATURE").object = arm
arm.data.pose_position = "POSE"
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
"""

# a 6 mm cube on the club, inside the forearm near the wrist: nothing crosses, and the skin
# triangles nearest it are forearm, not hand
PIN_IN_FOREARM = """
import sys, bmesh, bpy
from mathutils import Matrix
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
pb = arm.pose.bones["lowerarm_r"]
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=0.006, matrix=Matrix.Translation(arm.matrix_world @ pb.head.lerp(pb.tail, 0.8)))
me = bpy.data.meshes.new("Pin")
bm.to_mesh(me)
pin = bpy.data.objects.new("Pin", me)
bpy.context.scene.collection.objects.link(pin)
club = bpy.data.objects["Club"]
pin.parent = club
pin.matrix_parent_inverse = club.matrix_world.inverted()
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
"""

ADD_SIGHT = """
import sys, bpy
from mathutils import Matrix
s = bpy.data.objects.new("SOCKET_sight", None)
bpy.context.scene.collection.objects.link(s)
s.parent = bpy.data.objects["Rifle"]
s.matrix_world = Matrix.Translation((0, -0.04, 0.16))  # on top of the receiver
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
"""

EYE_AND_SIGHT = """
import json, sys, bpy
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
from opus_bl import grip
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
eye, s = grip._eye(arm, grip.find_hand(arm, "r"), None)
print("RESULT", json.dumps({"eye": list(eye), "scale": s, "sight": list(bpy.data.objects["SOCKET_sight"].matrix_world.translation)}))
"""

# the same material (with an image) on the club and on the rig's body
SHARE_MATERIAL = """
import os, sys, bpy
club, human, club_out, human_out = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=club)
img = bpy.data.images.new("paint.png", 4, 4)
img.filepath_raw = os.path.join(os.path.dirname(club_out), "paint.png")
img.file_format = "PNG"
img.save()
mat = bpy.data.materials.new("club_paint")
mat.use_nodes = True
tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = img
mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
for o in bpy.data.objects:
    if o.type == "MESH":
        o.data.materials.append(mat)
bpy.ops.wm.save_as_mainfile(filepath=club_out)
bpy.ops.wm.open_mainfile(filepath=human)
with bpy.data.libraries.load(club_out) as (src, dst):
    dst.materials = ["club_paint"]
next(o for o in bpy.data.objects if o.type == "MESH").data.materials.append(bpy.data.materials["club_paint"])
bpy.ops.wm.save_as_mainfile(filepath=human_out)
"""

MATERIALS = """
import json, bpy
print("RESULT", json.dumps({"materials": sorted(m.name for m in bpy.data.materials if m.users),
                            "images": sorted(i.name for i in bpy.data.images if i.users),
                            "club": [s.material.name for s in bpy.data.objects["Club"].material_slots]}))
"""


def blender_expr(code: str, blend: Path | None, *args) -> dict | None:
    """Run ``code`` in Blender (on ``blend``, or an empty scene); its RESULT line as a dict."""
    cmd = [BLENDER, "-b", *([str(blend)] if blend else ["--factory-startup"]), "--python-exit-code", "1",
           "--python-expr", code, "--", *map(str, args)]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300).stdout
    lines = [x for x in out.splitlines() if x.startswith("RESULT ")]
    return json.loads(lines[-1][7:]) if lines else None


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    d = tmp_path_factory.mktemp("grip")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_props.py"), "--", str(d)],
                   check=True, capture_output=True, timeout=300)
    run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 6000, "out_blend": str(d / "human.blend")})
    return d


@pytest.fixture(scope="module")
def club(work):
    from opus.threed.grip import grip_define

    sheet, rep = grip_define(work / "club.blend", "Club", part="Club")
    return sheet, rep


@pytest.fixture(scope="module")
def holding_club(work, club):
    from opus.threed.grip import grip_hold

    return grip_hold(work / "human.blend", work / "club.blend", side="r", out_blend=work / "holding_club.blend")


def test_hands_have_fingers_that_do_not_share_skin(work):
    out = work / "weights.json"
    subprocess.run([BLENDER, "-b", str(work / "human.blend"), "--python", str(SCRIPTS / "weight_probe.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    r = json.loads(out.read_text())
    assert r["finger_verts"] > 100
    assert r["shared"] == 0


def test_grip_define_fits_the_handle(club):
    sheet, rep = club
    assert sheet.exists()
    assert rep["grip"] == "SOCKET_grip_main"
    assert rep["radius"] == pytest.approx(0.016, abs=0.002)
    assert rep["axis"] == pytest.approx([0, 0, 1], abs=0.01)
    assert rep["palm_side"] == pytest.approx([0, 1, 0], abs=0.01)


def test_club_is_gripped_without_sinking_in(holding_club):
    sheet, rep = holding_club
    c = rep["contact"]
    assert sheet.exists() and Path(rep["file"]).exists()
    assert c["verdict"] == "good grip", rep["text"]
    assert not [r for r, v in c["regions"].items() if v["status"] == "inside"]
    assert {"index", "middle", "ring", "pinky"} <= set(c["fingers_touching"])
    assert rep["weapon_bone"] == "weapon_r" and rep["action"] == "Grip_Club_r"
    # the saved file passes the independent check too
    assert "good grip" in run_task("grip_check", {"path": rep["file"], "side": "r"})["text"]


def test_check_catches_handles_through_the_palm_and_floating(work, club):
    for mode, expect in (("inside", "sinks in"), ("floating", "floating")):
        out = work / f"naive_{mode}.blend"
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "place_naive.py"), "--",
                        str(BLENDER_MODULES), str(work / "human.blend"), str(work / "club.blend"), str(out), mode],
                       check=True, capture_output=True, timeout=300)
        rep = run_task("grip_check", {"path": str(out), "side": "r", "object": "Club"})
        c = rep["sides"]["r"]["contact"]
        assert c["verdict"] == expect, rep["text"]
        if mode == "inside":
            assert c["regions"]["palm"]["depth_mm"] > 5


def test_pistol_first_person_with_index_on_the_trigger(work):
    from opus.threed.grip import grip_define, grip_hold

    _, g = grip_define(work / "pistol.blend", "Pistol", part="Pistol", up=[0, 0, 1], point_axis="-Y", hand="r",
                       style="pistol", center=0.62, index="trigger", trigger=[0, -0.034, 0.09])
    assert g["palm_side"] == pytest.approx([-1, 0, 0], abs=0.02)  # a right palm presses the grip's right side
    sheet, rep = grip_hold(work / "human.blend", work / "pistol.blend", side="r", pose="fp_hip")
    assert rep["contact"]["verdict"] == "good grip", rep["text"]
    assert rep["fingers"]["index"]["status"].startswith("on trigger")
    assert float(rep["fingers"]["index"]["status"].split("(")[1].split(" ")[0]) < 3.0
    assert rep["aim_vs_hand_deg"] < 15
    assert rep["reach_error_m"] < 0.01
    assert sheet.exists()


def test_support_hand_reaches_a_rifle_handguard(work):
    from opus.threed.grip import grip_define, grip_hold

    rifle = work / "rifle.blend"
    grip_define(rifle, "Rifle", name="main", part="Rifle", up=[0, 0, 1], point_axis="-Y", hand="r", style="pistol",
                center=0.6, index="trigger", trigger=[0, 0.009, 0.065])
    grip_define(rifle, "Rifle", name="fore", part="Handguard", up=[0, -1, 0], palm_side=[0, 0, -1], hand="l")
    _, right = grip_hold(work / "human.blend", rifle, grip="main", side="r", pose="fp_hip", offset=[0.0, 0.1, 0.22],
                         out_blend=work / "rifle_r.blend")
    assert right["reach_error_m"] < 0.01
    _, left = grip_hold(work / "rifle_r.blend", grip="fore", side="l", move="hand", out_blend=work / "rifle_rl.blend")
    assert left["reach_error_m"] < 0.01
    assert not [r for r, v in left["contact"]["regions"].items() if v["status"] == "inside"]
    assert len(left["contact"]["fingers_touching"]) >= 3


def test_check_holds_a_prop_skinned_to_the_weapon_bone(work, holding_club):
    """A prop skinned whole to weapon_r (one vertex group, an Armature modifier) is what the
    hand holds, not body: grip_check found 'no object near the hand', or 'no mesh' when named."""
    _, rep = holding_club
    skinned = work / "club_skinned.blend"
    blender_expr(SKIN_TO_WEAPON, Path(rep["file"]), skinned)
    parented = run_task("grip_check", {"path": rep["file"], "side": "r"})["sides"]["r"]
    for args in ({}, {"object": "Club"}):
        got = run_task("grip_check", {"path": str(skinned), "side": "r", **args})["sides"]["r"]
        assert got["object"] == "Club"
        assert got["contact"]["verdict"] == parented["contact"]["verdict"] == "good grip"
        palm, palm0 = got["contact"]["regions"]["palm"], parented["contact"]["regions"]["palm"]
        assert palm["status"] == palm0["status"] and palm["verts_inside"] == palm0["verts_inside"]
        assert palm["closest_mm"] == pytest.approx(palm0["closest_mm"], abs=0.11)
        assert got["contact"]["body"] == parented["contact"]["body"]


def test_body_depth_comes_only_from_what_is_counted(work, holding_club):
    """An object vertex inside the forearm near the wrist, nearest a forearm triangle, read as
    'embedded': depth_mm 26 with no skin vertex inside and no surface crossing."""
    _, rep = holding_club
    pinned = work / "club_pin.blend"
    blender_expr(PIN_IN_FOREARM, Path(rep["file"]), pinned)
    for path in (rep["file"], pinned):
        c = run_task("grip_check", {"path": str(path), "side": "r", "object": "Club"})["sides"]["r"]["contact"]
        assert c["verdict"] == "good grip"
        assert c["body"]["verts_inside"] == c["body"]["crossing_triangles"] == 0
        assert c["body"]["depth_mm"] == 0  # a plate through the forearm still has one: test_geom


def test_ads_offset_is_the_eye_to_sight_distance(work):
    """fp_ads always put the sight 0.2 m in front of the eye, whatever the offset."""
    from opus.threed.grip import grip_define

    rifle = work / "rifle_sight.blend"
    blender_expr(ADD_SIGHT, work / "rifle.blend", rifle)
    grip_define(rifle, "Rifle", name="main", part="Rifle", up=[0, 0, 1], point_axis="-Y", hand="r", style="pistol",
                center=0.6, index="trigger", trigger=[0, 0.009, 0.065])
    args = {"rig_path": str(work / "human.blend"), "object_path": str(rifle), "grip": "main", "side": "r", "pose": "fp_ads"}
    rep = run_task("grip_hold", {**args, "offset": [0.45, 0, 0], "out_blend": str(work / "ads.blend")})
    assert rep["reach_error_m"] < 0.01
    r = blender_expr(EYE_AND_SIGHT, work / "ads.blend", BLENDER_MODULES)
    eye, sight = r["eye"], r["sight"]
    assert eye[1] - sight[1] == pytest.approx(0.45 * r["scale"], abs=0.01)  # in front: characters face -Y
    assert sight[2] == pytest.approx(eye[2], abs=0.01)
    with pytest.raises(BlenderTaskError, match="eye line"):
        run_task("grip_hold", {**args, "offset": [0.45, 0.1, 0], "out_blend": str(work / "ads_bad.blend")})


def test_a_material_the_rig_already_has_is_not_appended_twice(work, club):
    """Holding a prop that shares a material with the rig left club_paint and club_paint.001."""
    blender_expr(SHARE_MATERIAL, None, work / "club.blend", work / "human.blend", work / "club_mat.blend",
                 work / "human_mat.blend")
    rep = run_task("grip_hold", {"rig_path": str(work / "human_mat.blend"), "object_path": str(work / "club_mat.blend"),
                                 "side": "r", "out_blend": str(work / "held_mat.blend")})
    assert rep["contact"]["verdict"] == "good grip"
    r = blender_expr(MATERIALS, work / "held_mat.blend")
    assert [m for m in r["materials"] if m.startswith("club_paint")] == ["club_paint"]
    assert [i for i in r["images"] if i.startswith("paint")] == ["paint.png"]
    assert r["club"] == ["club_paint"]
