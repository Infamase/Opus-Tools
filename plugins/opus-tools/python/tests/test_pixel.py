import numpy as np
import pytest

from fakes import fake_pixel_art
from opus.imaging import load_rgba, save_rgba, upscale
from opus.pixel import analysis as an
from opus.pixel.cleanup import cleanup, detect_grid, trim
from opus.pixel.inspect import inspect_sprite
from opus.pixel.palette import (
    Palette,
    apply_palette,
    describe_palette,
    load_palette,
    make_ramp,
    swap_palette,
)
from opus.pixel.color import rgb_to_oklch
from sprites import blob, pillow_blob, ramp_tile, tileable, with_defects


def palette_of(img) -> Palette:
    cols = np.unique(img[img[..., 3] > 0][:, :3], axis=0)
    return Palette([tuple(int(v) for v in c) for c in cols])


# ---------------------------------------------------------------- analysis

@pytest.mark.parametrize("k", [1, 2, 3, 4, 8])
def test_detect_upscale(k):
    assert an.detect_upscale(upscale(blob(24), k)) == k


def test_single_pixels_and_alpha():
    img = with_defects(blob(32))
    strays, orphans = an.single_pixels(img)
    assert strays.sum() == 1 and strays[1, 1]
    assert orphans[16, 16]
    assert ((img[..., 3] > 0) & (img[..., 3] < 255)).sum() == 1


def test_clean_blob_has_no_defects():
    img = blob(32)
    strays, orphans = an.single_pixels(img)
    assert strays.sum() == 0 and orphans.sum() == 0


def test_shading_direction_vs_pillow():
    lit = an.shading_report(blob(40), "top-left")
    pillow = an.shading_report(pillow_blob(40), "top-left")
    assert lit["pillow_shading_likely"] is False
    assert lit["lightness_vs_light_direction"] > 0.6
    assert pillow["pillow_shading_likely"] is True


def test_tile_seams():
    assert an.tile_seams(tileable(16))["seams_visible"] is False
    assert an.tile_seams(ramp_tile(16))["seams_visible"] is True


def test_elbows_flag_doubled_diagonal_not_box_corner():
    line = np.zeros((12, 12), bool)
    for i in range(5):  # doubled staircase: (i,i) and (i,i+1)
        line[i, i] = line[i, i + 1] = True
    elbows, _ = an.jaggy_elbows(line)
    assert elbows.sum() >= 3
    box = np.zeros((12, 12), bool)
    box[2, 2:9] = box[8, 2:9] = box[2:9, 2] = box[2:9, 8] = True
    elbows, _ = an.jaggy_elbows(box)
    assert elbows.sum() == 0


def test_frame_report_loop():
    frames = [blob(16)] * 4
    rep = an.frame_report(frames)
    assert rep["frames"] == 4 and rep["loop_seam_changed_fraction"] == 0.0


# ---------------------------------------------------------------- palette

def test_ramp_is_monotonic_and_hue_shifted():
    r = make_ramp("#3a7d44", steps=6, hue_shift=25)
    lch = rgb_to_oklch(r.array.astype(float))
    assert np.all(np.diff(lch[:, 0]) > 0)  # lightness rises
    assert "#3a7d44" in r.hex()  # base color kept exactly
    assert abs(((lch[-1, 2] - lch[0, 2] + 180) % 360) - 180) > 10  # hue moves


def test_load_palette_formats(tmp_path):
    (tmp_path / "p.hex").write_text("ff0000\n00ff00\n0000ff\n")
    (tmp_path / "p.gpl").write_text("GIMP Palette\nName: test\n#\n255 0 0 red\n0 255 0 green\n")
    (tmp_path / "p.pal").write_text("JASC-PAL\n0100\n2\n255 0 0\n0 0 255\n")
    assert len(load_palette(str(tmp_path / "p.hex"))) == 3
    assert load_palette(str(tmp_path / "p.gpl")).name == "test"
    assert len(load_palette(str(tmp_path / "p.pal"))) == 2
    assert load_palette("#000 #fff") .hex() == ["#000000", "#ffffff"]
    assert load_palette("") is None


def test_apply_palette_is_exact_for_in_palette_colors():
    img = blob(24)
    out = apply_palette(img, palette_of(img))
    assert np.array_equal(out, an.normalize_transparent(img))


def test_swap_palette_by_index():
    src = Palette([(0, 0, 0), (255, 255, 255)])
    dst = Palette([(255, 0, 0), (0, 0, 255)])
    img = np.zeros((2, 2, 4), np.uint8)
    img[..., 3] = 255
    img[0, 0, :3] = 255
    out = swap_palette(img, src, dst)
    assert tuple(out[0, 0, :3]) == (0, 0, 255) and tuple(out[1, 1, :3]) == (255, 0, 0)


def test_describe_palette_groups_ramps():
    d = describe_palette(blob(32))
    assert d["color_count"] == 5
    # the three blues and the near-white highlight belong to one ramp
    assert max(r["steps"] for r in d["ramps"]) >= 4


# ---------------------------------------------------------------- cleanup

@pytest.mark.parametrize("scale", [5.5, 7.3, 10.5, 16.0])
@pytest.mark.parametrize("blur", [0.0, 1.0])
def test_cleanup_recovers_fake_pixel_art(scale, blur):
    clean = blob(32)
    fake = fake_pixel_art(clean, scale=scale, blur=blur, seed=1)
    g = detect_grid(fake)
    assert g.found and abs(g.px - scale) < 0.1
    from opus.pixel.cleanup import remove_background, sample_cells

    nat, _ = remove_background(sample_cells(fake, g))
    nat = trim(apply_palette(nat, palette_of(clean)))
    ref = trim(clean)
    assert nat.shape == ref.shape
    assert np.all(nat == ref, axis=-1).mean() > 0.97


@pytest.mark.parametrize("size", [16, 32, 64])
def test_native_art_is_left_alone(size):
    assert not detect_grid(blob(size)).found


def test_cleanup_end_to_end(tmp_path):
    src = save_rgba(fake_pixel_art(blob(32), scale=9.7, blur=0.9), tmp_path / "ai.png")
    clean_path, preview, rep = cleanup(src, max_colors=8, out=tmp_path / "clean.png")
    out = load_rgba(clean_path)
    assert rep["grid"]["found"] and rep["background_removed"]
    assert out.shape[0] in (25, 26, 27) and preview.exists()
    assert set(np.unique(out[..., 3])) <= {0, 255}


# ---------------------------------------------------------------- inspector

def test_inspector_report_and_sheet(tmp_path):
    src = save_rgba(upscale(with_defects(blob(32)), 4), tmp_path / "s.png")
    sheet, rep = inspect_sprite(src, out=tmp_path / "sheet.png")
    assert sheet.exists()
    assert rep["upscale_factor"] == 4 and rep["native_size"] == [32, 32]
    assert rep["single_pixels"]["strays"] == 1
    assert rep["alpha"]["semi_transparent_pixels"] == 1
    assert any("stray" in w for w in rep["warnings"])


def test_inspector_palette_and_tile_modes(tmp_path):
    tile = save_rgba(ramp_tile(16), tmp_path / "t.png")
    _, rep = inspect_sprite(tile, mode="tile", palette="#000000 #ffffff", out=tmp_path / "t_sheet.png")
    assert rep["tile"]["seams_visible"] is True
    assert rep["palette_check"]["off_palette_pixels"] == 16 * 16


def test_inspector_sheet_mode(tmp_path):
    frames = [blob(16), np.roll(blob(16), 1, axis=0), blob(16), np.roll(blob(16), -1, axis=0)]
    sheet_img = np.concatenate(frames, axis=1)
    src = save_rgba(sheet_img, tmp_path / "walk.png")
    _, rep = inspect_sprite(src, mode="sheet", frame_width=16, frame_height=16, out=tmp_path / "w.png")
    assert rep["animation"]["frames"] == 4
    assert rep["animation"]["baseline_jitter_px"] == 2
