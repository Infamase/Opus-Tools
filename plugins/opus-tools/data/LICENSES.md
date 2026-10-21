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
- **Derived:** licence IDs, flags, aliases and notes; the facts about each licence come from its linked terms
- **Credit:** "Opus Tools contributors, GPL-3.0-or-later" (the repo's notice; keep it with copies)

### `tables/anthro_ansur2.json`
- **Source:** ANSUR II public CSVs (`ANSUR_II_MALE_Public.csv`, `ANSUR_II_FEMALE_Public.csv`),
  US Army Natick Soldier Research, Development and Engineering Center, 2012 survey;
  https://www.openlab.psu.edu/ansur2/
- **Licence:** `LicenseRef-US-Gov-Public-Release`: "cleared for unlimited public release"
  (US Army memorandum). A US Government work and likely public domain, but no licence is stated.
- **Derived:** stature-normalised percentiles (p5, p50, p95) by sex. The raw CSVs are not
  committed. Military sample: no children, and heavy bodies are truncated.
- **Credit:** none required; cited as "ANSUR II, US Army Natick Soldier RD&E Center (2012)"

### `tables/quadruped_hindlimb.json`
- **Source:** Garland, T. Jr. and Janis, C. M. (1993). Does metatarsal/femur ratio predict
  maximal running speed in cursorial mammals? *Journal of Zoology* 229: 133–151.
  https://biologyfiles.ucr.edu/people/faculty/Garland/GarlandJanis1993.pdf
- **Licence:** `LicenseRef-Facts`: measurements transcribed from the paper's table; the
  paper itself is not redistributed
- **Derived:** per-species limb-segment ratios (metatarsal/femur among them) computed from
  the table's measurements
- **Credit:** none required; cited as Garland & Janis (1993)
