"""Committed fact tables (``data/tables/<name>.json``): loading them, and rebuilding them.

Every value is ``{value, min, max, unit, src, tag}``. ``tag`` is ``measured`` (read from
the source), ``derived`` (computed from measured values by a stated rule) or ``recalled``
(not checked against a primary source; such values only ever produce warnings). Each table
carries a top-level ``source`` block with its citation, licence and attribution.

Maintainers rebuild the tables with ``opus data build --tables`` and review the diff before
committing. Source files (the ANSUR II CSVs) stay local; only the derived tables are
committed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from opus.paths import data_dir

TAGS = ("measured", "derived", "recalled")
VALUE_KEYS = ("value", "min", "max", "unit", "src", "tag")


def tables_dir() -> Path:
    return data_dir() / "tables"


def load_table(name: str) -> dict:
    """A committed table by name (``anthro_ansur2``, ``quadruped_hindlimb``)."""
    path = tables_dir() / f"{name}.json"
    if not path.exists():
        known = sorted(p.stem for p in tables_dir().glob("*.json"))
        raise FileNotFoundError(f"no fact table {name!r}; known: {known}")
    return json.loads(path.read_text(encoding="utf-8"))


def fact(value: float, lo: float, hi: float, unit: str, src: str, tag: str) -> dict:
    if tag not in TAGS:
        raise ValueError(f"tag must be one of {TAGS}")
    return {"value": value, "min": lo, "max": hi, "unit": unit, "src": src, "tag": tag}


def check_table(table: dict) -> list[str]:
    """Format problems: values missing a key, a bad tag, or min > value > max."""
    problems = []
    if not {"citation", "licence_id", "url", "attribution", "modification"} <= set(table.get("source", {})):
        problems.append("source block needs citation, licence_id, url, attribution and modification")

    def walk(node, where):
        if isinstance(node, dict) and "value" in node:
            missing = [k for k in VALUE_KEYS if k not in node]
            if missing:
                problems.append(f"{where}: missing {missing}")
            elif node["tag"] not in TAGS:
                problems.append(f"{where}: tag {node['tag']!r}")
            elif not node["min"] <= node["value"] <= node["max"]:
                problems.append(f"{where}: value outside [min, max]")
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{where}.{k}" if where else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")

    walk({k: v for k, v in table.items() if k != "source"}, "")
    return problems


def _write(table: dict, path: Path) -> Path:
    problems = check_table(table)
    if problems:
        raise ValueError(f"{path.name}: " + "; ".join(problems[:5]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- ANSUR II

ANSUR_URL = "https://www.openlab.psu.edu/ansur2/"
ANSUR_FILES = {"male": "ANSUR_II_MALE_Public.csv", "female": "ANSUR_II_FEMALE_Public.csv"}
# measure name -> ANSUR II column (all in mm, as fractions of stature in the table). The
# landmarks body.py places (shoulder, chest, waist, hip, crotch, knee, ankle) and the
# segments it sizes (upper arm, forearm, hand, foot) come first.
ANSUR_MEASURES = {
    "acromial_height": "acromialheight",
    "chest_height": "chestheight",
    "waist_height": "waistheightomphalion",
    "trochanterion_height": "trochanterionheight",
    "crotch_height": "crotchheight",
    "knee_height": "kneeheightmidpatella",
    "ankle_height": "lateralmalleolusheight",
    "upper_arm": "acromionradialelength",
    "forearm": "radialestylionlength",
    "hand_length": "handlength",
    "hand_breadth": "handbreadth",
    "palm_length": "palmlength",
    "foot_length": "footlength",
    "foot_breadth": "footbreadthhorizontal",
    "ball_of_foot_length": "balloffootlength",
    "cervicale_height": "cervicaleheight",
    "suprasternale_height": "suprasternaleheight",
    "axilla_height": "axillaheight",
    "iliocristale_height": "iliocristaleheight",
    "tibial_height": "tibialheight",
    "wrist_height": "wristheight",
    "shoulder_elbow": "shoulderelbowlength",
    "forearm_hand": "forearmhandlength",
    "span": "span",
    "sitting_height": "sittingheight",
    "biacromial_breadth": "biacromialbreadth",
    "bideltoid_breadth": "bideltoidbreadth",
    "chest_breadth": "chestbreadth",
    "chest_depth": "chestdepth",
    "waist_breadth": "waistbreadth",
    "waist_depth": "waistdepth",
    "hip_breadth": "hipbreadth",
    "head_breadth": "headbreadth",
    "head_length": "headlength",
}
ANSUR_SOURCE = {
    "citation": "Gordon CC, Blackwell CL, Bradtmiller B, et al. (2014). 2012 Anthropometric Survey of U.S. Army "
                "Personnel: Methods and Summary Statistics. Technical Report NATICK/TR-15/007, U.S. Army Natick "
                "Soldier Research, Development and Engineering Center. Public working databases described in the "
                "NSRDEC Memorandum for Record RDNS-SEW-THA, 14 April 2017.",
    "licence_id": "LicenseRef-USGov-Unlimited-Public-Release",
    "licence_url": ANSUR_URL,
    "licence_text": "\"These databases and this memorandum have been reviewed and cleared for UNLIMITED PUBLIC "
                    "RELEASE.\" (NSRDEC Memorandum for Record, 14 April 2017). U.S. Government work; no other "
                    "licence is stated.",
    "url": ANSUR_URL,
    "attribution": "Contains data derived from the 2012 U.S. Army Anthropometric Survey (ANSUR II) public working "
                   "databases, U.S. Army Natick Soldier Research, Development and Engineering Center.",
    "modification": "Derived/modified: per-subject ratios of each measurement to stature, summarised as the 5th, "
                    "50th and 95th percentiles (numpy linear interpolation). Head height is derived as sitting "
                    "height - eye height sitting + menton-sellion length. No subject rows are included.",
    "caveats": "Military sample: adults only (no children), heavy bodies truncated by fitness standards. "
               "Sellion sits a few mm above the pupil, so derived head height is about +-5 mm.",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_ansur(path: Path) -> dict[str, np.ndarray]:
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    head = [h.strip().lower() for h in rows[0]]
    cols = {}
    for name in {"stature", "sittingheight", "eyeheightsitting", "mentonsellionlength", *ANSUR_MEASURES.values()}:
        i = head.index(name)
        cols[name] = np.array([float(r[i]) for r in rows[1:] if len(r) == len(head)])
    return cols


def _band(x: np.ndarray, unit: str, src: str, tag: str, nd: int = 4) -> dict:
    p5, p50, p95 = (round(float(v), nd) for v in np.percentile(x, [5, 50, 95]))
    return fact(p50, p5, p95, unit, src, tag)


def ansur_sex(path: Path, sex: str) -> dict:
    """Stature-normalised p5/p50/p95 bands for one ANSUR II CSV."""
    c = _read_ansur(path)
    stature = c["stature"]
    n = len(stature)
    tag_src = f"ANSUR II {sex} (n={n})"
    out = {
        "n": n,
        "stature_mm": _band(stature, "mm", f"{tag_src}: stature", "measured", nd=1),
        "measures": {},
    }
    for name, col in ANSUR_MEASURES.items():
        out["measures"][name] = _band(c[col] / stature, "stature", f"{tag_src}: {col} / stature", "measured")
    head = c["sittingheight"] - c["eyeheightsitting"] + c["mentonsellionlength"]
    expr = "(sittingheight - eyeheightsitting + mentonsellionlength)"
    m = out["measures"]
    m["head_height"] = _band(head / stature, "stature", f"{tag_src}: {expr} / stature", "derived")
    m["chin_height"] = _band(1 - head / stature, "stature", f"{tag_src}: 1 - {expr} / stature", "derived")
    m["heads_tall"] = _band(stature / head, "heads", f"{tag_src}: stature / {expr}", "derived", nd=3)
    return out


def build_anthro_ansur2(male_csv: str | Path, female_csv: str | Path | None = None) -> dict:
    """The ``anthro_ansur2`` table from the ANSUR II public CSVs (female optional)."""
    files, sexes = [], {}
    for sex, path in (("male", male_csv), ("female", female_csv)):
        if path is None:
            continue
        path = Path(path)
        sexes[sex] = ansur_sex(path, sex)
        files.append({"name": ANSUR_FILES[sex], "sha256": _sha256(path), "subjects": sexes[sex]["n"]})
    return {
        "table": "anthro_ansur2",
        "version": 1,
        "description": "Adult body landmarks and segments as fractions of stature: value = p50, min = p5, max = p95 "
                       "of the per-subject ratio. Unit 'stature' means a fraction of standing height.",
        "source": {**ANSUR_SOURCE, "files": files},
        "sexes": sexes,
    }


# ---------------------------------------------------------------- Garland & Janis 1993

GJ_URL = "https://biologyfiles.ucr.edu/people/faculty/Garland/GarlandJanis1993.pdf"
GJ_SOURCE = {
    "citation": "Garland T Jr, Janis CM (1993). Does metatarsal/femur ratio predict maximal running speed in "
                "cursorial mammals? Journal of Zoology, London 229: 133-151. Data from Fig. 1 (p. 136).",
    "licence_id": "LicenseRef-Facts",
    "licence_url": GJ_URL,
    "licence_text": "Numeric facts transcribed from a published figure; facts are not copyrightable. The paper "
                    "itself is not redistributed.",
    "url": GJ_URL,
    "attribution": "Hindlimb data from Garland T Jr & Janis CM (1993), J. Zool. Lond. 229: 133-151, Fig. 1.",
    "modification": "Derived/modified: the 49 rows of Fig. 1 transcribed and checked against a render of p. 136. "
                    "Femur, tibia and metatarsal lengths are derived from hind leg length and MT/F assuming tibia "
                    "= femur; donor bands are the family ranges in the same figure; digit lengths are recalled "
                    "values (warnings only).",
    "caveats": "Limb lengths are maximum articular lengths (Scott 1985) of mostly wild-shot museum specimens; hind "
               "leg = femur + tibia + metatarsal and excludes the digits. Domestic dog and cat are not in the table.",
}
# Fig. 1, top to bottom: species, family, sprint speed (km/h), body mass (kg), hind leg
# (femur + tibia + metatarsal, cm), metatarsal/femur ratio.
GJ_ROWS = [
    ("Ursus maritimus", "Ursidae", 40, 265, 84.24, 0.214),
    ("Ursus horribilis", "Ursidae", 48, 251.3, 65.20, 0.220),
    ("Ursus americanus", "Ursidae", 48, 93.4, 66.83, 0.200),
    ("Nasua narica", "Procyonidae", 27, 4.4, 22.89, 0.265),
    ("Procyon lotor", "Procyonidae", 24, 7, 26.15, 0.294),
    ("Mephitis mephitis", "Mustelidae", 16, 2.5, 14.65, 0.265),
    ("Meles meles", "Mustelidae", 30, 11.6, 25.11, 0.313),
    ("Canis lupus", "Canidae", 64, 35.3, 59.02, 0.437),
    ("Canis latrans", "Canidae", 65, 13.3, 43.73, 0.426),
    ("Lycaon pictus", "Canidae", 70, 20, 52.29, 0.395),
    ("Canis aureus", "Canidae", 56, 8.8, 35.42, 0.434),
    ("Urocyon cinereoargenteus", "Canidae", 64, 3.7, 27.14, 0.473),
    ("Vulpes fulva", "Canidae", 72, 4.8, 34.48, 0.483),
    ("Hyaena hyaena", "Hyaenidae", 50, 26.8, 54.83, 0.313),
    ("Crocuta crocuta", "Hyaenidae", 65, 52, 52.85, 0.365),
    ("Acinonyx jubatus", "Felidae", 110, 58.8, 66.44, 0.438),
    ("Panthera pardus", "Felidae", 60, 52.4, 53.58, 0.401),
    ("Panthera tigris", "Felidae", 56, 161, 73.69, 0.345),
    ("Panthera leo", "Felidae", 59, 155.8, 74.42, 0.348),
    ("Tapirus bairdii", "Tapiridae", 40, 250, 74.55, 0.305),
    ("Diceros bicornis", "Rhinocerotidae", 45, 1200, 92.53, 0.360),
    ("Ceratotherium simum", "Rhinocerotidae", 25, 2000, 101.2, 0.327),
    ("Equus hemionus", "Equidae", 70, 200, 77.06, 0.872),
    ("Equus caballus", "Equidae", 70, 350, 87.54, 0.806),
    ("Equus burchelli", "Equidae", 70, 235, 83.65, 0.784),
    ("Camelus dromedarius", "Camelidae", 32, 550, 132.6, 0.677),
    ("Lama guanicoe", "Camelidae", 56, 95, 77.09, 0.706),
    ("Giraffa camelopardalis", "Giraffidae", 60, 1075, 159.7, 1.416),
    ("Syncerus caffer", "Bovidae", 57, 620, 101.1, 0.572),
    ("Bison bison", "Bovidae", 56, 865, 96.61, 0.680),
    ("Taurotragus oryx", "Bovidae", 70, 511, 100.9, 0.813),
    ("Gazella granti", "Bovidae", 81, 62.5, 66.21, 1.105),
    ("Gazella thomsonii", "Bovidae", 81, 20.5, 53.01, 1.138),
    ("Antilope cervicapra", "Bovidae", 105, 37.5, 60.72, 1.051),
    ("Madoqua kirki", "Bovidae", 42, 5, 30.11, 0.780),
    ("Oreamnos americanus", "Bovidae", 33, 113.5, 65.65, 0.448),
    ("Ovis canadensis nelsoni", "Bovidae", 48, 85, 72.19, 0.780),
    ("Hippotragus equinus", "Bovidae", 56, 226.5, 84.40, 0.762),
    ("Aepyceros melampus", "Bovidae", 47, 53.25, 74.06, 1.128),
    ("Connochaetes taurinus", "Bovidae", 80, 216, 90.00, 0.818),
    ("Damaliscus lunatus", "Bovidae", 70, 130, 84.60, 1.004),
    ("Alcelaphus buselaphus", "Bovidae", 80, 136, 84.70, 0.924),
    ("Antilocapra americana", "Antilocapridae", 100, 50, 66.44, 1.000),
    ("Cervus canadensis", "Cervidae", 72, 300, 97.00, 0.956),
    ("Dama dama", "Cervidae", 65, 55, 64.09, 0.971),
    ("Alces alces", "Cervidae", 56, 384, 123.8, 0.933),
    ("Rangifer tarandus", "Cervidae", 80, 100, 101.2, 0.947),
    ("Odocoileus virginianus", "Cervidae", 64, 57, 80.85, 1.002),
    ("Odocoileus hemionus", "Cervidae", 61, 74, 78.20, 0.963),
]
CARNIVORA = {"Ursidae", "Procyonidae", "Mustelidae", "Canidae", "Hyaenidae", "Felidae"}
# Donors for body_blockout's quadrupeds: the species whose ratio splits the hind leg, and the
# phalanx segments after the metatarsal as (name, x metatarsal length, min, max). The digit
# lengths are recalled from general anatomy, not from a checked source.
GJ_DONORS = {
    "wolf": ("Canis lupus", "Canidae", "dog", [("toes", 0.5, 0.4, 0.7)],
             "Domestic dogs are Canis lupus familiaris; the wild wolf is the table's nearest row."),
    "felid": ("Panthera leo", "Felidae", "cat", [("toes", 0.5, 0.4, 0.7)],
              "Felis catus is not in the table. Felid long-bone lengths scale isometrically and felids keep a "
              "crouched posture at every size (Cuff et al. 2016, J. Anat., PMC5341591), so the lion's ratio "
              "stands in for the cat; check against domestic-cat skeletons when one is fetched."),
    "horse": ("Equus caballus", "Equidae", "horse", [("pastern", 0.48, 0.42, 0.55), ("hoof", 0.3, 0.25, 0.35)],
              "Pastern = fetlock to coffin joint (P1 + P2); hoof = coffin joint to the toe on the ground (P3)."),
}


def _power_fit(rows: list) -> dict:
    """hind leg (cm) = a * mass (kg) ** b, least squares in log-log, with +-1.96 SE bands."""
    x = np.log([r[3] for r in rows])
    y = np.log([r[4] for r in rows])
    A = np.column_stack([np.ones_like(x), x])
    coef = np.linalg.lstsq(A, y, rcond=None)[0]
    dof = len(x) - 2
    s2 = float(((y - A @ coef) ** 2).sum()) / dof
    se = np.sqrt(np.diag(s2 * np.linalg.inv(A.T @ A)))
    src = f"least squares on log(hind leg) vs log(mass), n={len(rows)}, band +-1.96 SE"
    a, b = math.exp(coef[0]), float(coef[1])
    return {
        "n": len(rows),
        "a_cm": fact(round(a, 3), round(math.exp(coef[0] - 1.96 * se[0]), 3), round(math.exp(coef[0] + 1.96 * se[0]), 3),
                     "cm", src, "derived"),
        "b": fact(round(b, 4), round(b - 1.96 * float(se[1]), 4), round(b + 1.96 * float(se[1]), 4), "exponent", src,
                  "derived"),
        "residual_sd_log": round(math.sqrt(s2), 4),
    }


def build_quadruped_hindlimb() -> dict:
    """The ``quadruped_hindlimb`` table from the transcription of Garland & Janis Fig. 1."""
    src = "Garland & Janis 1993, Fig. 1"
    species = {}
    for name, family, speed, mass, leg, r in GJ_ROWS:
        femur = leg / (2 + r)
        dsrc = f"{src}: hind leg {leg} cm split by MT/F {r} with tibia = femur"
        species[name] = {
            "family": family,
            "sprint_speed_kmh": fact(speed, speed, speed, "km/h", src, "measured"),
            "mass_kg": fact(mass, mass, mass, "kg", src, "measured"),
            "hind_leg_cm": fact(leg, leg, leg, "cm", src + " (femur + tibia + metatarsal)", "measured"),
            "mt_f": fact(r, r, r, "ratio", src, "measured"),
            "femur_cm": fact(round(femur, 2), round(femur, 2), round(femur, 2), "cm", dsrc, "derived"),
            "tibia_cm": fact(round(femur, 2), round(femur, 2), round(femur, 2), "cm", dsrc, "derived"),
            "metatarsal_cm": fact(round(r * femur, 2), round(r * femur, 2), round(r * femur, 2), "cm", dsrc, "derived"),
        }
    donors = {}
    for key, (sp, family, preset, digits, note) in GJ_DONORS.items():
        fam = [r[5] for r in GJ_ROWS if r[1] == family]
        r = species[sp]["mt_f"]["value"]
        donors[key] = {
            "species": sp,
            "preset": preset,
            "mt_f": fact(r, min(fam), max(fam), "ratio",
                         f"{src}: {sp}; band = {family} range over {len(fam)} species",
                         "measured" if key != "felid" else "derived"),
            "tibia_f": fact(1.0, 0.9, 1.1, "ratio", "OVERHAUL.md section 4.3 (femur ~ tibia)", "recalled"),
            "digits": [{"name": n, "x_metatarsal": fact(v, lo, hi, "ratio", "general mammal anatomy, unchecked",
                                                         "recalled")} for n, v, lo, hi in digits],
            "note": note,
        }
    return {
        "table": "quadruped_hindlimb",
        "version": 1,
        "description": "Hindlimb proportions of 49 Carnivora and ungulates: MT/F = metatarsal / femur, hind leg = "
                       "femur + tibia + metatarsal (digits excluded). Donors map body_blockout presets to species.",
        "source": dict(GJ_SOURCE),
        "species": species,
        "donors": donors,
        "power_fit": {
            "all": _power_fit(GJ_ROWS),
            "carnivora": _power_fit([r for r in GJ_ROWS if r[1] in CARNIVORA]),
            "ungulates": _power_fit([r for r in GJ_ROWS if r[1] not in CARNIVORA]),
        },
    }


def build_tables(ansur_dir: str | Path | None = None, out_dir: str | Path | None = None) -> dict[str, str]:
    """Rebuild the committed tables. ``ansur_dir`` holds the ANSUR II public CSVs; without
    it only the tables that need no local source files are rebuilt."""
    out = Path(out_dir) if out_dir else tables_dir()
    written = {"quadruped_hindlimb": str(_write(build_quadruped_hindlimb(), out / "quadruped_hindlimb.json"))}
    if ansur_dir:
        d = Path(ansur_dir).expanduser()
        male, female = (d / ANSUR_FILES[s] for s in ("male", "female"))
        if not male.exists():
            raise FileNotFoundError(f"{male} not found; download it from {ANSUR_URL}")
        table = build_anthro_ansur2(male, female if female.exists() else None)
        written["anthro_ansur2"] = str(_write(table, out / "anthro_ansur2.json"))
    return written
