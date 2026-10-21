"""Camera profiles and the §2.2 worked examples (Unreal third person, 1080p, hfov 90)."""

import math

import pytest

from opus import camera as c
from opus.bible import DEFAULTS, TEMPLATE, camera_profile, init_bible, load_bible

UE = c.preset("ue_tp_1080")


def test_vertical_fov_from_unreal_horizontal():
    assert c.vfov_from_hfov(90, 16 / 9) == pytest.approx(58.7155, abs=1e-3)
    assert UE.vfov_deg == pytest.approx(58.7155, abs=1e-3)
    assert c.hfov_from_vfov(UE.vfov_deg, 16 / 9) == pytest.approx(90)
    assert math.tan(math.radians(c.preset("godot_tp").vfov_deg) / 2) == pytest.approx(0.7673, abs=1e-4)
    assert c.preset("unity_tp").vfov_deg == 60


@pytest.mark.parametrize("d,ppm", [(1.5, 640), (3.5, 274), (15, 64), (40, 24)])
def test_px_per_m_is_960_over_d(d, ppm):
    assert UE.px_per_m(d) == pytest.approx(960 / d)
    assert round(UE.px_per_m(d)) == ppm


def test_orthographic_px_per_m():
    side = c.preset("sidescroller")
    assert side.px_per_m() == pytest.approx(1080 / 12) == c.ortho_px_per_m(12, 1080)
    assert side.levels() == [("screen", None)]


def test_minimum_feature():
    assert c.min_feature_m(4, UE.px_per_m(3.5)) * 1000 == pytest.approx(14.6, abs=0.05)
    assert c.min_feature_m(13, UE.px_per_m(15)) == pytest.approx(0.20, abs=0.005)


def test_detail_tier_of_a_rivet():
    ppm = UE.px_per_m(1.5)
    assert c.on_screen_px(0.006, ppm) == pytest.approx(3.84)
    assert c.detail_tier(0.006, ppm) == "geometry"
    assert c.detail_tier(0.003, ppm) == "map"  # 1.9 px
    assert c.detail_tier(0.001, ppm) == "omit"  # 0.64 px


def test_circle_segments_of_a_grip():
    r = 0.019
    assert c.circle_segments(r, UE.px_per_m(1.5)) == 11
    assert c.circle_segments(r, UE.px_per_m(3.0)) == 8
    assert c.circle_segments(r, UE.px_per_m(0.45)) == 20  # first person
    assert c.circle_segments(0.025, UE.px_per_m(0.35)) == 26  # handguard: π/acos = 25.999 (§6(c) says 27)
    assert c.circle_segments(0.001, UE.px_per_m(40)) == 3  # smaller than a pixel


def test_bevel_width_cap():
    assert c.bevel_width(UE.px_per_m(1.5)) * 1000 == pytest.approx(2.3, abs=0.05)
    assert c.bevel_width(960 / 0.35) * 1000 == pytest.approx(0.55, abs=0.01)
    assert c.bevel_width(UE.px_per_m(1.5), thickness_m=0.004) == pytest.approx(0.001)  # 25% of t
    assert c.bevel_width(UE.px_per_m(1.5), thickness_m=0.5) == pytest.approx(0.01)  # 2% of t


def test_texel_density_and_texture_size():
    assert c.texel_density(640) == 512
    assert c.texel_density(960 / 0.35) == 2048
    assert c.texture_size(512, 1.0, eta=0.7, pow2=False) == pytest.approx(612, abs=1)
    assert c.texture_size(512, 1.0) == 1024


def test_bake_padding_lod_and_fracture():
    assert c.bake_padding(mips=4) == 16
    assert c.bake_padding(td=512, ppm_far=64) == 8  # minified 8x at 15 m: 3 mips
    assert c.lod_switch_distance(0.01, UE.vfov_deg, 1440) == pytest.approx(12.8, abs=0.01)
    lo, hi = c.min_fracture_fragment(64, 6), c.min_fracture_fragment(64, 10)
    assert (lo, hi) == pytest.approx((0.094, 0.156), abs=0.001)


def test_johnson_levels():
    assert c.johnson(1) == "below detection"
    assert c.johnson(8) == "recognize"
    assert c.johnson(12) == "recognize"
    assert c.johnson(13) == "identify"


def test_profile_derived_numbers():
    rows = UE.derived()["levels"]
    assert [r["level"] for r in rows] == ["close", "typical", "far"]
    assert [round(r["px_per_m"]) for r in rows] == [640, 274, 64]
    assert UE.derived()["texel_density"] == 512


def test_bible_has_a_camera_section():
    assert set(DEFAULTS["camera"]) == {"profile", "distances", "overrides", "viewmodel"}
    assert DEFAULTS["camera"]["viewmodel"] == {}
    assert "viewmodel:" in TEMPLATE and "cameras:" in TEMPLATE


def test_active_profile_follows_engine_and_cameras(tmp_path):
    assert camera_profile(load_bible(tmp_path)).name == "ue_tp_1080"
    (tmp_path / "project.godot").write_text("")
    init_bible(tmp_path, cameras=["top-down"])
    assert camera_profile(load_bible(tmp_path)).name == "topdown"
    (tmp_path / "opus.project.yaml").unlink()
    init_bible(tmp_path, cameras=["third-person"])
    prof = camera_profile(load_bible(tmp_path))
    assert prof.name == "godot_tp" and "auto-picked" in prof.note


def test_bible_overrides_and_distances(tmp_path):
    (tmp_path / "opus.project.yaml").write_text(
        "camera:\n"
        "  profile: my_cam\n"
        "  distances: {ue_tp_1080: {far: 30}, my_cam: {typical: 5}}\n"
        "  overrides:\n"
        "    ue_tp_1080: {res_w: 2560, res_h: 1440}\n"
        "    my_cam: {base: godot_tp, fov_deg: 70}\n",
        encoding="utf-8",
    )
    bible = load_bible(tmp_path)
    mine = camera_profile(bible)
    assert (mine.name, mine.fov_deg, mine.distances["typical"], mine.distances["close"]) == ("my_cam", 70, 5, 2.0)
    ue = camera_profile(bible, "ue_tp_1080")
    assert ue.px_per_m(3.5) == pytest.approx(1440 / (2 * 3.5 * 0.5625))
    assert ue.distances == {"close": 1.5, "typical": 3.5, "far": 30}
    with pytest.raises(ValueError, match="unknown camera profile"):
        camera_profile(bible, "nope")


def test_viewmodel_is_never_silently_assumed(tmp_path):
    vm = camera_profile(load_bible(tmp_path), "viewmodel")
    assert vm.fallback and vm.viewmodel and "FALLBACK" in vm.label and "viewmodel missing" in vm.note
    assert vm.px_per_m(0.45) == pytest.approx(960 / 0.45)
    (tmp_path / "opus.project.yaml").write_text(
        "camera:\n  viewmodel: {fov_deg: 74, fov_axis: horizontal, near_m: 0.05, scale: 0.5}\n", encoding="utf-8")
    vm = camera_profile(load_bible(tmp_path), "viewmodel")
    assert not vm.fallback and vm.fov_deg == 74 and vm.near_m == 0.05
    rows = vm.summary()["levels"]
    assert rows[0]["depth_m"] == pytest.approx(0.175) and rows[0]["inside_near_plane"] is False
