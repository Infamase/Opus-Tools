"""Look, model report, proportion check and reference match against real Blender renders."""

import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from opus import imaging as im
from opus.blender.runner import BlenderNotFound, find_blender, run_task

try:
    BLENDER = find_blender()
except BlenderNotFound:
    BLENDER = None

needs_blender = pytest.mark.skipif(BLENDER is None, reason="Blender not found (set OPUS_BLENDER)")
SCRIPTS = Path(__file__).parent / "blender_scripts"


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    return tmp_path_factory.mktemp("understand")


@pytest.fixture(scope="module")
def human(work):
    out = work / "human.blend"
    rep = run_task("body", {"archetype": "humanoid", "preset": "realistic", "target_tris": 5000, "out_blend": str(out)})
    return out, rep


@pytest.fixture(scope="module")
def barrel(work):
    out = work / "barrel.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPTS / "make_barrel.py"), "--", str(out)],
                   check=True, capture_output=True, timeout=300)
    return out


@pytest.fixture(scope="module")
def barrel_report(barrel, work):
    from opus.threed.understand import model_report

    return model_report(barrel, out=work / "barrel_report.jpg", size=300)


@needs_blender
def test_model_report_of_a_prop(barrel_report):
    sheet, rep = barrel_report
    assert sheet.exists()
    assert rep["mode"] == "objects" and {p["name"] for p in rep["parts"]} == {"Barrel", "Band0", "Band1"}
    shapes = {p["name"]: p["shape"] for p in rep["parts"]}
    assert shapes["Band0"] == "plate / slab"
    assert any({c["a"], c["b"]} == {"Barrel", "Band0"} for c in rep["contacts"])
    assert rep["gaps"] == []
    assert rep["symmetry"]["symmetric"] and rep["on_floor"]
    assert "Parts (3, one per object)" in rep["text"]


@needs_blender
def test_model_report_has_the_eval_metrics(barrel_report):
    """evals/README.md names these metrics; every builder and grader read the same ones."""
    _, rep = barrel_report
    m = rep["metrics"]
    size = rep["bounds_m"]["size"]
    assert m["floating_parts"] == 0 and m["penetrations"] == len(rep["penetrations"])
    assert m["longest_m"] == max(size)
    assert [m["width_m"], m["length_m"], m["height_m"]] == size
    assert m["on_floor"] is True and m["symmetric"] is True and m["com_over_footprint"] is True
    assert m["rig_style"] is None
    assert "Floating parts: 0" in rep["text"]


@needs_blender
def test_model_report_splits_a_skinned_body_by_bone(human, work):
    from opus.threed.understand import model_report

    sheet, rep = model_report(human[0], out=work / "human_report.jpg", size=300)
    names = {p["name"] for p in rep["parts"]}
    assert rep["mode"] == "bones" and {"head", "upperarm_l", "thigh_r"} <= names
    thigh = next(p for p in rep["parts"] if p["name"] == "thigh_l")
    assert thigh["main_axis"] == "vertical (Z)" and thigh["bone_length_m"] > 0.3
    assert rep["rig"]["style"].startswith("unreal")
    assert rep["balance"]["com_over_footprint"] is True


@needs_blender
def test_look_at_frames_a_bone_region_from_any_angle(human, work):
    from opus.threed.understand import look_at

    sheet, rep = look_at(human[0], views=["front", "30,20", "three_quarter_back"], pass_="focus",
                         target="hand_l", zoom=1.5, size=240, out=work / "look.jpg")
    assert sheet.exists() and rep["target"] == "hand_l"
    with pytest.raises(Exception, match="no part named"):
        look_at(human[0], target="tentacle_l", size=120, out=work / "x.jpg")


@needs_blender
def test_proportion_check_flags_short_legs_and_big_head(human, work):
    from opus.threed.proportion import proportion_check

    out, rep = human
    _, good = proportion_check(out, preset="realistic", out=work / "good.png")
    assert good["iou"]["front"] > 0.95
    assert not [f for f in good["findings"] if not f["metric"].startswith("band")]
    bad = work / "bad.blend"
    lm = rep["landmarks_m"]
    subprocess.run([BLENDER, "-b", str(out), "--python", str(SCRIPTS / "distort_body.py"), "--", str(bad),
                    str(lm["crotch"]), str(lm["chin"])], check=True, capture_output=True, timeout=300)
    sheet, rep = proportion_check(bad, preset="realistic", out=work / "bad.png")
    assert sheet.exists()
    metrics = {f["metric"]: f["relative_pct"] for f in rep["findings"]}
    assert metrics["crotch_height"] < -10  # legs shorter
    assert metrics["head_width"] > 20
    assert rep["heads_tall_estimate"] < 6.5


@needs_blender
def test_proportion_check_picks_the_closest_canon(work):
    from opus.threed.proportion import proportion_check

    chibi = work / "chibi.blend"
    run_task("body", {"archetype": "humanoid", "preset": "chibi", "target_tris": 4000, "out_blend": str(chibi)})
    _, rep = proportion_check(chibi, out=work / "chibi.png")
    assert rep["canon"] == "chibi"
    assert rep["heads_tall_estimate"] == pytest.approx(3.0, abs=0.3)


@needs_blender
@pytest.mark.parametrize("archetype,preset", [
    ("humanoid", "realistic"), ("humanoid", "heroic"), ("humanoid", "stylized"),
    ("quadruped", "dog"), ("quadruped", "horse"), ("quadruped", "cat"), ("dragon", "western"),
])
def test_proportion_check_names_each_presets_own_canon(work, archetype, preset):
    from opus.threed.proportion import proportion_check

    model = work / f"own_{preset}.blend"
    run_task("body", {"archetype": archetype, "preset": preset, "target_tris": 4000, "out_blend": str(model)})
    _, rep = proportion_check(model, archetype=archetype, pose="A", out=work / f"own_{preset}.png")
    assert rep["canon"] == preset, rep["iou_by_canon"]


@needs_blender
def test_reference_match_finds_a_mirrored_side_view(work):
    from opus.threed.proportion import reference_match

    dog = work / "dog.blend"
    run_task("body", {"archetype": "quadruped", "preset": "dog", "target_tris": 4000, "out_blend": str(dog)})
    shot = run_task("views", {"path": str(dog), "out_dir": str(work / "ref"), "size": 400,
                              "shots": [{"view": "right", "pass": "clay", "ortho": True}]})
    concept = work / "dog_concept.png"
    Image.open(shot["tiles"][0]["path"]).transpose(Image.FLIP_LEFT_RIGHT).save(concept)
    sheet, rep = reference_match(dog, concept, view="right", out=work / "match.png")
    assert sheet.exists()
    assert rep["flipped"] is True and rep["iou"] > 0.9


# ---------------------------------------------------------------- sheets, with the Blender tasks faked or captured

class Captured(Exception):
    pass


@pytest.fixture
def sheets(monkeypatch):
    """Every contact sheet made during the test, with its title, subtitle and rows."""
    made = []

    class Sheet(im.Sheet):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

    monkeypatch.setattr(im, "Sheet", Sheet)
    return made


def silhouette(path, w, h=300, size=360) -> str:
    img = np.full((size, size), 255, np.uint8)
    y0, x0 = (size - h) // 2, (size - w) // 2
    img[y0 : y0 + h, x0 : x0 + w] = 0
    Image.fromarray(img, "L").save(path)
    return str(path)


def fake_views(tmp_path, widths=(16, 74, 50)) -> dict:
    """A views task result: front, right and 3/4 silhouettes this wide (an axe seen edge-on
    from the front), then the 3/4 clay."""
    tiles = [{"path": silhouette(tmp_path / f"{v}.png", w), "pass": "silhouette", "azimuth": az, "elevation": el, "labels": []}
             for (v, az, el), w in zip((("front", 0.0, 0.0), ("right", 90.0, 0.0), ("three_quarter", 38.66, 26.6)), widths)]
    tiles.append({"path": silhouette(tmp_path / "clay.png", 50), "pass": "clay", "azimuth": 38.66, "elevation": 26.6, "labels": []})
    return {"mode": "objects", "parts": ["Head", "Haft"], "target": "", "tiles": tiles}


def fake_game(tmp_path, args, size_m, clipped=()) -> dict:
    """A readability task result: each shot at each level, a small image per pass."""
    small = silhouette(tmp_path / "game.png", 4, h=20, size=24)
    return {"mode": "objects", "parts": [], "size_m": list(size_m),
            "renders": [{"shot": s["key"], "azimuth": s["azimuth"], "elevation": s["elevation"], "level": name, "distance_m": d,
                         "clipped": name in clipped, "files": {s["passes"][0]: small}}
                        for s in args["shots"] for name, d in args["levels"]]}


@pytest.fixture(scope="module")
def plate(work):
    """A 2 cm thin plate in the YZ plane: edge-on from the front, full face from the right."""
    out = work / "plate.blend"
    code = ("import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); "
            "bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.75)); o = bpy.context.object; o.name = 'Plate'; "
            "o.scale = (0.02, 1.0, 1.5); bpy.ops.object.transform_apply(scale=True); "
            f"bpy.ops.wm.save_as_mainfile(filepath={str(out)!r})")
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", code], check=True, capture_output=True, timeout=300)
    return out


@needs_blender
def test_game_size_silhouette_turns_to_the_side_that_shows_the_most(plate, monkeypatch):
    from opus.threed import understand

    seen = {}

    def task(name, args, **k):
        if name == "readability":
            seen.update(args)
            raise Captured
        return run_task(name, args, **k)

    monkeypatch.setattr(understand, "run_task", task)
    with pytest.raises(Captured):
        understand.blind_read_sheet(plate, game_size=True, camera="godot_tp")
    shots = {s["key"]: s for s in seen["shots"]}
    assert shots["sil"]["azimuth"] == pytest.approx(90.0) and shots["sil"]["elevation"] == 0.0
    assert shots["clay"]["azimuth"] == pytest.approx(35.0)  # the clay stays turned from the profile's view


def test_blind_sheet_leaves_out_game_sizes_seen_from_inside_or_clipped(tmp_path, monkeypatch, sheets):
    """A 16 x 8 x 8 m house: at 1.5 and 3.5 m the camera stands inside it, and 40 m is set
    clipped here; neither may reach the judge as a game-size tile."""
    from opus.threed import understand

    calls = {}

    def task(name, args, **k):
        calls[name] = args
        return fake_views(tmp_path) if name == "views" else fake_game(tmp_path, args, (16, 8, 8), clipped=("40 m",))

    monkeypatch.setattr(understand, "run_task", task)
    sheet, prompt = understand.blind_read_sheet(tmp_path / "house.blend", game_size=True, camera="ue_tp_1080",
                                                distances=[1.5, 3.5, 15, 40])
    assert sheet.exists()
    assert {s["key"]: s["azimuth"] for s in calls["readability"]["shots"]}["sil"] == 90.0  # the widest silhouette
    rows = dict(sheets[0].rows)
    sil, clay = rows["Silhouette at game size"], rows["Form at game size"]
    assert len(sil) == len(clay) == 1  # far 15 m only, of four distances
    assert sil[0].title.startswith("far view")
    note = prompt.split("For the caller")[1]
    assert "close 1.5 m" in note and "typical 3.5 m" in note and "camera inside the subject" in note
    assert "40 m" in note and "clipped" in note and "far" not in note
    assert "For the caller" not in understand.BLIND_PROMPT


def test_blind_sheet_with_no_framed_game_size_says_so(tmp_path, monkeypatch, sheets):
    from opus.threed import understand

    monkeypatch.setattr(understand, "run_task", lambda name, args, **k: (
        fake_views(tmp_path) if name == "views" else fake_game(tmp_path, args, (16, 8, 8))))
    _, prompt = understand.blind_read_sheet(tmp_path / "house.blend", game_size=True, camera="ue_tp_1080",
                                            distances=[1.5, 3.5])
    assert [label for label, _ in sheets[0].rows] == ["Silhouettes", "Form"]
    assert "no game-size rows" in prompt


def test_look_and_part_map_sheets_never_name_the_file(tmp_path, monkeypatch, sheets):
    """Judges get look_at sheets (and model_report's part map) and must never see file names."""
    from opus.threed import understand

    report = {"mode": "objects", "bounds_m": {"min": [0, 0, 0], "max": [1, 2, 3], "size": [1, 2, 3]}, "on_floor": True,
              "centered_x": True, "parts": [], "contacts": [], "penetrations": [], "gaps": [],
              "symmetry": {"symmetric": True, "plane_x_m": 0.0, "offset_pct_of_size": 0.1, "asymmetric_parts": []},
              "balance": {}, "rig": None, "stats": {}}
    monkeypatch.setattr(understand, "run_task", lambda name, args, **k: dict(report) if name == "report" else fake_views(tmp_path))
    path = tmp_path / "woman.blend"
    sheet, rep = understand.look_at(path, views=["front", "right"], target="Head", out=tmp_path / "look.jpg")
    _, mr = understand.model_report(path, out=tmp_path / "report.jpg")
    assert len(sheets) == 2 and sheet.exists()
    for s in sheets:
        assert "woman" not in s.title and "woman" not in s.subtitle
        assert s.title == "Look"
    assert "framed on Head" in sheets[0].subtitle
    assert rep["sheet"] == str(sheet) and mr["sheet"] == str(tmp_path / "report.jpg")
    assert mr["metrics"]["longest_m"] == 3 and mr["metrics"]["com_over_footprint"] is None
