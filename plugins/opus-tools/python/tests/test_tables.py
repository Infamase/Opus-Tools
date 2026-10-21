"""Committed fact tables: format, sources, and that the builders reproduce them."""

import json
import os
from pathlib import Path

import pytest

from opus import tables
from opus.cli import main as cli
from opus.tables import build_anthro_ansur2, build_quadruped_hindlimb, check_table, load_table

NAMES = ("anthro_ansur2", "quadruped_hindlimb")


@pytest.mark.parametrize("name", NAMES)
def test_committed_tables_are_well_formed_and_small(name):
    t = load_table(name)
    assert check_table(t) == []
    src = t["source"]
    assert src["licence_id"].startswith("LicenseRef-") and src["attribution"]
    assert "Derived/modified" in src["modification"]
    assert (tables.tables_dir() / f"{name}.json").stat().st_size < 200_000


def test_unknown_table_names_the_known_ones():
    with pytest.raises(FileNotFoundError, match="anthro_ansur2"):
        load_table("ansur3")


def test_check_table_catches_bad_values():
    t = build_quadruped_hindlimb()
    t["species"]["Canis lupus"]["mt_f"]["tag"] = "guessed"
    del t["species"]["Equus caballus"]["mass_kg"]["src"]
    t["donors"]["horse"]["mt_f"]["value"] = 2.0
    problems = check_table(t)
    assert len(problems) == 3
    assert any("tag 'guessed'" in p for p in problems)


def test_anthro_bands_for_hand_and_foot():
    sexes = load_table("anthro_ansur2")["sexes"]
    assert sexes["male"]["n"] == 4082 and sexes["female"]["n"] == 1986
    m = sexes["male"]["measures"]
    for name, p50 in (("foot_length", 0.154), ("hand_length", 0.110)):
        v = m[name]
        assert v["tag"] == "measured" and v["unit"] == "stature"
        assert v["min"] < v["value"] < v["max"]
        assert v["value"] == pytest.approx(p50, abs=0.001)
    assert m["heads_tall"]["tag"] == "derived"
    assert m["heads_tall"]["value"] == pytest.approx(7.43, abs=0.02)


def test_hindlimb_donors_follow_garland_and_janis():
    t = load_table("quadruped_hindlimb")
    assert len(t["species"]) == 49
    d = t["donors"]
    assert (d["wolf"]["species"], d["wolf"]["mt_f"]["value"]) == ("Canis lupus", 0.437)
    assert d["felid"]["mt_f"]["value"] == pytest.approx(0.35, abs=0.005)
    assert d["felid"]["mt_f"]["tag"] == "derived"  # the domestic cat is not in the table
    assert d["horse"]["mt_f"]["value"] == 0.806
    assert [x["name"] for x in d["horse"]["digits"]] == ["pastern", "hoof"]
    assert all(x["x_metatarsal"]["tag"] == "recalled" for v in d.values() for x in v["digits"])
    wolf = t["species"]["Canis lupus"]
    total = sum(wolf[k]["value"] for k in ("femur_cm", "tibia_cm", "metatarsal_cm"))
    assert total == pytest.approx(wolf["hind_leg_cm"]["value"], abs=0.02)


def test_hindlimb_table_is_reproduced_by_its_builder():
    assert build_quadruped_hindlimb() == load_table("quadruped_hindlimb")


def _csv(path: Path, rows: list[dict], subject_col: str) -> None:
    cols = [subject_col, *sorted({"stature", "sittingheight", "eyeheightsitting", "mentonsellionlength",
                                  *tables.ANSUR_MEASURES.values()})]
    lines = [",".join(cols)] + [",".join(str(r.get(c, 100)) for c in cols) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_anthro_builder_on_a_small_csv(tmp_path):
    # 21 subjects whose foot is exactly 0.10 .. 0.20 of stature
    rows = [{"stature": 1000 + i, "footlength": (0.10 + 0.005 * i) * (1000 + i), "sittingheight": 520,
             "eyeheightsitting": 400, "mentonsellionlength": 120} for i in range(21)]
    male = tmp_path / "ANSUR_II_MALE_Public.csv"
    _csv(male, rows, "subjectid")
    t = build_anthro_ansur2(male)
    assert check_table(t) == [] and set(t["sexes"]) == {"male"}
    foot = t["sexes"]["male"]["measures"]["foot_length"]
    assert (foot["min"], foot["value"], foot["max"]) == pytest.approx((0.105, 0.15, 0.195))
    assert t["source"]["files"][0]["subjects"] == 21
    # the female file's header says SubjectId; the CLI builds both into --out
    _csv(tmp_path / "ANSUR_II_FEMALE_Public.csv", rows, "SubjectId")
    assert cli(["data", "build", "--tables", "--ansur", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    built = json.loads((tmp_path / "out" / "anthro_ansur2.json").read_text(encoding="utf-8"))
    assert set(built["sexes"]) == {"male", "female"}
    assert (tmp_path / "out" / "quadruped_hindlimb.json").exists()


@pytest.mark.skipif(not os.environ.get("OPUS_ANSUR_DIR"), reason="set OPUS_ANSUR_DIR to the ANSUR II public CSVs")
def test_anthro_table_is_reproduced_from_the_public_csvs():
    d = Path(os.environ["OPUS_ANSUR_DIR"])
    built = build_anthro_ansur2(d / tables.ANSUR_FILES["male"], d / tables.ANSUR_FILES["female"])
    assert built == load_table("anthro_ansur2")
