# Data licences

Every file committed under `plugins/opus-tools/data/` is listed here: where it came from,
its licence ID (from [licences.yaml](licences.yaml)), what was derived from it, and the
exact credit when the source asks for one.

- Committed tables come only from CC0, public-domain, factual or CC BY sources
  (docs/OVERHAUL.md §7). Each table also carries its own citation and measured, derived or
  recalled tags.
- Anything derived from NC, SA, ND, QAL or unlicensed sources stays in the local library
  (`data_fetch`) and is never committed.
- Ported code is listed in [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md), not here.

A test (`python/tests/test_licences.py`) fails when a file under `tables/` or `profiles/`
has no entry, or when an entry names a licence ID missing from `licences.yaml`.

## Entry format

One section per file, or per folder with a trailing slash, with the path relative to `data/`:

```markdown
### `tables/<file>`
- **Source:** who published it, and where (URL or citation)
- **Licence:** `<licence ID>`, plus the source's own words when it has no standard licence
- **Derived:** what was computed from the source, and what was left out
- **Credit:** the exact attribution string when the licence requires one, else "none required"
```

## Entries

### `licences.yaml`
- **Source:** own work (Opus Tools), compiled from the licence pages each entry links
- **Licence:** `GPL-3.0-or-later` (the repo's licence)
- **Derived:** licence IDs, flags, aliases, restriction phrases and notes; the facts about each licence come from its linked terms
- **Credit:** "Opus Tools contributors, GPL-3.0-or-later" (the repo's notice; keep it with copies)

### `tables/anthro_ansur2.json`
- **Source:** 2012 U.S. Army Anthropometric Survey (ANSUR II) public working databases,
  `ANSUR_II_MALE_Public.csv` (4,082 subjects) and `ANSUR_II_FEMALE_Public.csv` (1,986 subjects).
  Gordon CC, Blackwell CL, Bradtmiller B, et al. (2014), *2012 Anthropometric Survey of U.S. Army
  Personnel: Methods and Summary Statistics*, NATICK/TR-15/007; NSRDEC Memorandum for Record
  RDNS-SEW-THA, 14 April 2017. https://www.openlab.psu.edu/ansur2/ (files at
  https://tools.openlab.psu.edu/publicData/). The sha256 of each CSV is in the table's `source` block.
- **Licence:** `LicenseRef-US-Gov-Public-Release` (https://www.openlab.psu.edu/ansur2/): "These
  databases and this memorandum have been reviewed and cleared for UNLIMITED PUBLIC RELEASE."
  A U.S. Government work; no other licence is stated.
- **Derived:** per-subject ratios of each measurement to stature, summarised as the 5th, 50th
  and 95th percentiles by sex; head height derived as sitting height minus eye height sitting
  plus menton-sellion length. No subject rows are included and the CSVs are not committed
  (`opus data build --tables --ansur DIR` rebuilds the table). Military sample: adults only,
  heavy bodies truncated.
- **Credit:** "Contains data derived from the 2012 U.S. Army Anthropometric Survey (ANSUR II)
  public working databases, U.S. Army Natick Soldier Research, Development and Engineering Center."

### `tables/quadruped_hindlimb.json`
- **Source:** Garland T Jr, Janis CM (1993). Does metatarsal/femur ratio predict maximal running
  speed in cursorial mammals? *Journal of Zoology, London* 229: 133-151, Fig. 1 (p. 136).
  https://biologyfiles.ucr.edu/people/faculty/Garland/GarlandJanis1993.pdf
- **Licence:** `LicenseRef-Facts`: numeric facts transcribed from a published figure; the paper
  is not redistributed
- **Derived:** the 49 rows of Fig. 1 transcribed and checked against the page; femur, tibia and
  metatarsal lengths derived assuming tibia = femur; log-log fits of hind-leg length on body
  mass; donor bands (dog -> wolf, cat -> lion, horse -> horse) are family ranges from the same
  figure; digit lengths are recalled values (warnings only)
- **Credit:** "Hindlimb data from Garland T Jr & Janis CM (1993), J. Zool. Lond. 229: 133-151, Fig. 1."
