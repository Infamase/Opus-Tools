"""Lineup and A/B judge sheets: seeded order, equal heights, both orders, no key leakage."""

import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import numpy as np
import pytest
from PIL import Image

from opus.critique import LETTERS, ab_sheet, cutout, flood_from_border, lineup_sheet, reverse_order

RED, BLUE, GREEN, GOLD = (220, 40, 40), (40, 60, 220), (40, 200, 60), (230, 180, 30)


def figure(path: Path, color, h: int, w: int, canvas=(400, 300), bg=None, top: int = 40) -> Path:
    """A blocky figure (body plus a narrower head) on a transparent or flat background."""
    arr = np.zeros(canvas + (4,), np.uint8)
    if bg is not None:
        arr[:] = (*bg, 255)
    x0 = (canvas[1] - w) // 2
    arr[top + h // 4 : top + h, x0 : x0 + w] = (*color, 255)
    arr[top : top + h // 4, x0 + w // 4 : x0 + w - w // 4] = (*color, 255)
    img = Image.fromarray(arr, "RGBA")
    (img if bg is None else img.convert("RGB")).save(path, quality=95)
    return path


@pytest.fixture
def subjects(tmp_path):
    (tmp_path / "project.godot").write_text("")
    return {
        "asset": figure(tmp_path / "hero_mine.png", RED, 300, 120),
        "ex1": figure(tmp_path / "kenney_knight.png", BLUE, 200, 150, bg=(255, 255, 255)),
        "ex2": figure(tmp_path / "kaykit_rogue.png", GREEN, 350, 90, canvas=(500, 300), bg=(30, 30, 30)),
        "ex3": figure(tmp_path / "met_armor.png", GOLD, 120, 70, canvas=(200, 160), bg=(200, 205, 210)),
    }


COLORS = {"asset": RED, "ex1": BLUE, "ex2": GREEN, "ex3": GOLD}


def _blobs(sheet: str, colors: dict, zoom: int) -> dict:
    """Per named color: (x center, height in game pixels, bottom row) on the sheet."""
    a = np.asarray(Image.open(sheet).convert("RGB")).astype(int)
    out = {}
    for name, c in colors.items():
        ys, xs = np.nonzero(np.abs(a - c).sum(-1) <= 30)
        assert len(ys), f"{name} not on the sheet"
        out[name] = (xs.mean(), (ys.max() - ys.min() + 1) / zoom, ys.max())
    return out


def _check_key(rep: dict, paths: dict) -> None:
    """The letters, read left to right on each sheet, map through that sheet's key to the
    source actually drawn there."""
    colors = {n: COLORS[n] for n in paths}
    for sheet, key in zip(rep["sheets"], rep["key"]):
        blobs = _blobs(sheet, colors, rep["zoom"])
        left_to_right = sorted(blobs, key=lambda n: blobs[n][0])
        assert {LETTERS[i]: str(paths[n].resolve()) for i, n in enumerate(left_to_right)} == key


def test_lineup_order_is_deterministic_by_seed(subjects):
    imgs, ex = [subjects["asset"]], [subjects["ex1"], subjects["ex2"], subjects["ex3"]]
    one = lineup_sheet(imgs, ex, height_px=48, seed=11)
    two = lineup_sheet(imgs, ex, height_px=48, seed=11)
    assert one["key"] == two["key"] and one["seed"] == 11
    for p, q in zip(one["sheets"], two["sheets"]):
        assert np.array_equal(np.asarray(Image.open(p)), np.asarray(Image.open(q)))
    orders = {tuple(lineup_sheet(imgs, ex, height_px=48, seed=s)["key"][0].values()) for s in range(8)}
    assert len(orders) >= 3
    assert lineup_sheet(imgs, ex, height_px=48)["seed"] >= 0  # random seed, reported for replay


def test_lineup_height_comes_from_the_game_camera(subjects):
    """height_px = real size x the camera profile's px/m at a distance (opus.camera, via the bible)."""
    from opus import camera

    imgs, ex = [subjects["asset"]], [subjects["ex1"], subjects["ex2"]]
    rep = lineup_sheet(imgs, ex, seed=1, camera="", distance_m=20.0, size_m=1.8)  # project.godot: godot_tp
    want = round(1.8 * camera.px_per_m(20.0, 75.0, 1080))
    assert rep["height_px"] == want and rep["height_from_camera"]["camera"] == "godot_tp"
    for sheet in rep["sheets"]:
        assert {round(h) for _, h, _ in _blobs(sheet, {"asset": RED}, rep["zoom"]).values()} == {want}
    ue = lineup_sheet(imgs, ex, seed=1, camera="ue_tp_1080", size_m=0.25)  # its typical distance, 3.5 m
    assert ue["height_px"] == round(0.25 * camera.preset("ue_tp_1080").px_per_m(3.5)) == 69
    with pytest.raises(ValueError, match="size_m"):
        lineup_sheet(imgs, ex, camera="ue_tp_1080")  # an image has no real size to read


def test_lineup_subjects_share_one_height_on_one_ground_line(subjects):
    rep = lineup_sheet([subjects["asset"]], [subjects["ex1"], subjects["ex2"], subjects["ex3"]], height_px=64, seed=3)
    assert rep["zoom"] > 1
    for sheet in rep["sheets"]:
        blobs = _blobs(sheet, COLORS, rep["zoom"])
        assert {round(h) for _, h, _ in blobs.values()} == {64}
        assert len({bottom for _, _, bottom in blobs.values()}) == 1
    by = {Path(s["source"]).name: s for s in rep["subjects"]}
    assert by["hero_mine.png"]["background"] == "alpha"
    assert by["kenney_knight.png"]["background"] == "keyed #ffffff"
    assert by["met_armor.png"]["scale"] > 0.5 and by["kaykit_rogue.png"]["scale"] < 0.2
    assert rep["warnings"] == []


def test_lineup_key_maps_correctly_in_both_orders(subjects):
    for exemplars in (["ex1", "ex2"], ["ex1", "ex2", "ex3"]):  # odd and even counts
        paths = {"asset": subjects["asset"], **{n: subjects[n] for n in exemplars}}
        rep = lineup_sheet([paths["asset"]], [paths[n] for n in exemplars], height_px=40, seed=5)
        _check_key(rep, paths)
        for s in rep["subjects"]:
            first, second = s["letters"]
            assert first != second  # every subject changes place, the middle one too
            assert rep["key"][0][first] == rep["key"][1][second] == s["source"]
        assert [s["role"] for s in rep["subjects"]] == ["asset"] + ["exemplar"] * len(exemplars)
        assert len(rep["prompts"]) == 2 and rep["sheets"][1] in rep["prompts"][1]


def test_reverse_order_moves_every_subject():
    for n in range(2, len(LETTERS) + 1):
        order = list(np.random.default_rng(n).permutation(n))
        rev = reverse_order(order)
        assert sorted(rev) == sorted(order)
        assert all(a != b for a, b in zip(order, rev))
        if n % 2 == 0:
            assert rev == order[::-1]


def test_no_key_leakage_in_names_metadata_or_pixels(subjects, tmp_path):
    rep = lineup_sheet([subjects["asset"]], [subjects["ex1"], subjects["ex2"]], height_px=48, seed=2)
    words = ("hero", "mine", "kenney", "knight", "kaykit", "rogue", "asset", "exemplar", "rev", "order")
    names = [Path(p).name for p in rep["sheets"]]
    assert names[0] != names[1]
    for p in rep["sheets"]:
        assert not any(w in Path(p).name.lower() for w in words)
        with Image.open(p) as img:
            assert not getattr(img, "text", {}) and not (set(img.info) - {"dpi"})
        raw = Path(p).read_bytes().lower()
        assert not any(w.encode() in raw for w in words[:6])
    # pixels don't depend on file names or on which subjects are ours
    copies = tmp_path / "copies"
    copies.mkdir()
    renamed = [Path(copies / f"x{i}.png") for i in range(3)]
    for src, dst in zip((subjects["asset"], subjects["ex1"], subjects["ex2"]), renamed):
        dst.write_bytes(src.read_bytes())
    other = lineup_sheet(renamed[:2], renamed[2:], height_px=48, seed=2)  # two "assets", one exemplar
    for p, q in zip(rep["sheets"], other["sheets"]):
        assert np.array_equal(np.asarray(Image.open(p)), np.asarray(Image.open(q)))


def test_ab_sheet_shows_both_orders(subjects):
    a, b = subjects["asset"], subjects["ex1"]
    firsts = set()
    for seed in range(6):
        rep = ab_sheet(a, b, height_px=56, seed=seed)
        _check_key(rep, {"asset": a, "ex1": b})
        k1, k2 = rep["key"]
        assert k1["A"] == k2["B"] and k1["B"] == k2["A"]
        firsts.add(k1["A"])
        for sheet in rep["sheets"]:
            assert {round(h) for _, h, _ in _blobs(sheet, {"r": RED, "b": BLUE}, rep["zoom"]).values()} == {56}
    assert firsts == {str(a.resolve()), str(b.resolve())}  # the seed decides who starts on the left
    big = ab_sheet(a, b, seed=1, question="Which one has the clearer head shape?")
    assert big["zoom"] == 1 and "clearer head shape" in big["prompts"][0]
    assert all(Path(p).name.startswith("ab_") for p in big["sheets"])


def test_cutout_keys_only_background_reachable_from_the_border():
    rgba = np.full((60, 80, 4), 255, np.uint8)  # white backdrop
    rgba[10:50, 20:60, :3] = BLUE
    rgba[20:40, 30:50, :3] = 255  # a white window inside the subject stays
    cut, how = cutout(rgba)
    assert how == "keyed #ffffff" and cut.shape[:2] == (40, 40)
    assert (cut[10:30, 10:30, 3] == 255).all() and (cut[10:30, 10:30, :3] == 255).all()
    noisy = np.random.default_rng(0).integers(0, 255, (40, 40, 4)).astype(np.uint8)
    noisy[..., 3] = 255
    assert cutout(noisy)[1] == "kept"
    with pytest.raises(ValueError):
        cutout(np.zeros((10, 10, 4), np.uint8))


def test_flood_from_border_matches_a_plain_fill():
    rng = np.random.default_rng(4)
    for _ in range(20):
        ok = rng.random((23, 31)) < 0.6
        ref = np.zeros_like(ok)
        stack = [(y, x) for y in range(23) for x in range(31) if ok[y, x] and (y in (0, 22) or x in (0, 30))]
        while stack:
            y, x = stack.pop()
            if ref[y, x]:
                continue
            ref[y, x] = True
            stack += [(y + dy, x + dx) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))
                      if 0 <= y + dy < 23 and 0 <= x + dx < 31 and ok[y + dy, x + dx] and not ref[y + dy, x + dx]]
        assert np.array_equal(flood_from_border(ok), ref)


def test_jpeg_halo_is_trimmed(tmp_path):
    src = figure(tmp_path / "photo.jpg", GREEN, 360, 90, canvas=(480, 260), bg=(20, 20, 20))
    ex = figure(tmp_path / "ref.png", BLUE, 300, 120)
    rep = lineup_sheet([src], [ex, ex], height_px=48, seed=1)
    strip = np.asarray(Image.open(rep["sheets"][0]).convert("RGB")).astype(int)[26:-44]
    known = np.zeros(strip.shape[:2], bool)
    for c in ((128, 128, 128), GREEN, BLUE):
        known |= np.abs(strip - c).sum(-1) <= 45
    assert known.all()  # no rim of the photo's dark backdrop around the cut-out


def test_cli_lineup_prints_the_key(subjects, capsys):
    from opus.cli import main

    assert main(["lineup", str(subjects["asset"]), "--exemplars", str(subjects["ex1"]), str(subjects["ex2"]),
                 "--height", "32", "--seed", "4"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert len(rep["sheets"]) == 2 and rep["seed"] == 4 and set(rep["key"][0]) == {"A", "B", "C"}
    assert main(["ab", str(subjects["asset"]), str(subjects["ex1"]), "--seed", "1"]) == 0
    assert set(json.loads(capsys.readouterr().out)["key"][1]) == {"A", "B"}


async def _call(tmp_path, calls):
    from mcp import ClientSession, StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "opus.mcp_server"],
                                   env={**os.environ, "OPUS_PROJECT_DIR": str(tmp_path)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            return names, [await session.call_tool(n, a) for n, a in calls]


def test_mcp_tools_return_the_sheet_and_the_key(subjects, tmp_path):
    names, results = anyio.run(_call, tmp_path, [
        ("lineup_sheet", {"images": "hero_mine.png", "exemplars": "kenney_knight.png, kaykit_rogue.png", "height_px": 40,
                          "seed": 9}),
        ("ab_sheet", {"a": "hero_mine.png", "b": "kenney_knight.png", "height_px": 40}),
    ])
    assert {"lineup_sheet", "ab_sheet"} <= names
    for r in results:
        assert not r.is_error, r.content[0].text
        assert r.content[0].type == "image"
        rep = json.loads(r.content[1].text)
        assert len(rep["sheets"]) == 2 and len(rep["key"]) == 2
    assert json.loads(results[0].content[1].text)["seed"] == 9


def _has_blender() -> bool:
    from opus.blender.runner import BlenderNotFound, find_blender

    try:
        find_blender()
        return True
    except BlenderNotFound:
        return False


@pytest.mark.skipif(not _has_blender(), reason="Blender not found (set OPUS_BLENDER)")
def test_lineup_renders_3d_files_alike(subjects, tmp_path):
    from opus.blender.runner import find_blender

    barrel = tmp_path / "barrel.blend"
    script = Path(__file__).parent / "blender_scripts" / "make_barrel.py"
    subprocess.run([find_blender(), "-b", "--factory-startup", "--python", str(script), "--", str(barrel)],
                   check=True, capture_output=True, timeout=300)
    rep = lineup_sheet([barrel], [subjects["ex1"], subjects["ex2"]], height_px=48, seed=6, render_pass="clay")
    mine = rep["subjects"][0]
    assert mine["background"].startswith("keyed") and mine["scale"] < 1
    rows = np.asarray(Image.open(rep["sheets"][0]).convert("RGB")).astype(int)[26:-44]
    bg = np.abs(rows - (128, 128, 128)).sum(-1) > 12
    other = np.zeros(bg.shape, bool)
    for c in (BLUE, GREEN):
        other |= np.abs(rows - c).sum(-1) <= 30
    ys = np.nonzero((bg & ~other).any(axis=1))[0]  # rows that hold the rendered barrel
    assert abs((ys.max() - ys.min() + 1) / rep["zoom"] - 48) <= 1

    # sized from the game camera instead: the barrel's measured height x px/m at 3.5 m
    from opus import camera
    from opus.critique import subject_size_m

    h = subject_size_m(barrel)
    cam = lineup_sheet([barrel], [subjects["ex1"], subjects["ex2"]], seed=6, render_pass="clay", camera="ue_tp_1080",
                       distance_m=3.5)
    assert 0.3 < h < 2 and cam["height_from_camera"]["size_m"] == pytest.approx(h, abs=1e-3)
    assert cam["height_px"] == round(h * camera.preset("ue_tp_1080").px_per_m(3.5))
