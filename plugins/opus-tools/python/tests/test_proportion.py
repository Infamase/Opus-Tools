"""Silhouette math for proportion checks and reference matching (no Blender needed)."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from opus.threed.proportion import (
    align, band_findings, bone_ratios, canon_bone_ratios, compare_landmarks, humanoid_landmarks, image_mask, iou,
    to_height,
)


def figure(h=600, head=1 / 7.5, crotch=0.48, shoulders=0.26, arms=True, size=(500, 700), offset=(0, 0), fill=255):
    """A front-view figure drawn from proportions: head, neck, torso, A-pose arms, legs."""
    img = Image.new("L", size, 0)
    d = ImageDraw.Draw(img)
    cx, top = size[0] // 2 + offset[0], (size[1] - h) // 2 + offset[1]
    floor = top + h
    hh = head * h
    d.ellipse([cx - hh * 0.36, top, cx + hh * 0.36, top + hh], fill=fill)  # head
    neck_bot = top + hh * 1.3
    d.rectangle([cx - hh * 0.2, top + hh * 0.8, cx + hh * 0.2, neck_bot], fill=fill)
    crotch_y = floor - crotch * h
    sw = shoulders * h / 2
    d.polygon([(cx - sw, neck_bot), (cx + sw, neck_bot), (cx + sw * 0.75, crotch_y), (cx - sw * 0.75, crotch_y)], fill=fill)
    for s in (-1, 1):
        d.polygon([(cx + s * hh * 0.1, crotch_y - 2), (cx + s * sw * 0.75, crotch_y - 2),
                   (cx + s * sw * 0.45, floor), (cx + s * hh * 0.1, floor)], fill=fill)
        if arms:
            d.line([(cx + s * sw, neck_bot + 8), (cx + s * (sw + 0.3 * h), neck_bot + 0.3 * h)], fill=fill, width=int(h * 0.04))
    return np.asarray(img) > 127


def test_landmarks_read_the_drawn_proportions():
    lm = humanoid_landmarks(figure(crotch=0.48))
    assert lm["crotch_height"] == pytest.approx(0.48, abs=0.02)
    assert lm["neck"] == pytest.approx(0.17, abs=0.04)
    short = humanoid_landmarks(figure(crotch=0.40))
    findings = compare_landmarks(short, lm)
    assert any(f["metric"] == "crotch_height" and f["relative_pct"] < -10 for f in findings)
    assert any("legs" in f["text"] and "shorter" in f["text"] for f in findings)


def test_bigger_head_shows_as_fewer_heads_tall():
    normal, big = humanoid_landmarks(figure(head=1 / 7.5)), humanoid_landmarks(figure(head=1 / 5.5))
    assert big["neck"] > normal["neck"] * 1.2
    assert any(f["metric"] == "head_width" and f["relative_pct"] > 20 for f in compare_landmarks(big, normal))


def test_alignment_ignores_position_and_scale():
    big = figure(h=600)
    small = Image.fromarray(big.astype(np.uint8) * 255).resize((250, 350), Image.BILINEAR)
    canvas = Image.new("L", (700, 500), 0)
    canvas.paste(small, (40, 120))  # half size, off-center, on a different canvas
    a, b = to_height(big), to_height(np.asarray(canvas) > 127)
    assert iou(*align(a, b)) > 0.95


def test_band_findings_name_the_wider_region():
    a, b = align(to_height(figure(shoulders=0.36)), to_height(figure(shoulders=0.26)))
    bands = band_findings(a, b, humanoid=True, label="front")
    assert bands and all(x["model_wider"] for x in bands)
    assert any(x["region"] in ("shoulders and chest", "waist") for x in bands)


def test_image_mask_separates_subject_from_textured_background_and_caption(tmp_path):
    rng = np.random.default_rng(1)
    fig = figure()
    bg = np.empty(fig.shape + (3,), np.uint8)
    bg[:] = (232, 226, 210)  # paper
    bg = np.clip(bg + rng.normal(0, 3, bg.shape), 0, 255).astype(np.uint8)
    bg[fig] = (120, 60, 50)
    shade = fig.copy()
    shade[:, : fig.shape[1] // 2] = False
    bg[shade] = (70, 35, 30)  # a shadowed half must stay part of the subject
    img = Image.fromarray(bg)
    ImageDraw.Draw(img).text((10, 10), "CONCEPT v2", fill=(40, 40, 40))
    p = tmp_path / "concept.png"
    img.save(p)
    m = image_mask(p)
    assert iou(m, fig) > 0.97


def test_canon_hand_bone_is_compared():
    # blockout joints (joints_m), and a model rig whose hand bone also runs wrist to knuckles
    joints = {"shoulder_l": [0.2, 0, 1.46], "elbow_l": [0.45, 0, 1.21], "wrist_l": [0.65, 0, 1.01],
              "knuckles_l": [0.72, 0, 0.94]}
    canon = canon_bone_ratios(joints, 1.8)
    assert set(canon) == {"upperarm", "lowerarm", "hand"}
    model = bone_ratios({"mixamorig:LeftHand": ([0.65, 0, 1.01], [0.72, 0, 0.94])}, 1.8)
    assert model["hand"] == pytest.approx(canon["hand"])


def test_image_mask_uses_alpha(tmp_path):
    fig = figure()
    rgba = np.zeros(fig.shape + (4,), np.uint8)
    rgba[fig] = (200, 200, 200, 255)
    p = tmp_path / "cutout.png"
    Image.fromarray(rgba).save(p)
    assert iou(image_mask(p), fig) > 0.99
