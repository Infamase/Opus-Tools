"""Repo licence files (OVERHAUL.md §2.7): LICENSE, THIRD_PARTY_NOTICES.md and data/LICENSES.md.

The CI check: every ported module (a ``ported-from:`` header) has a notice entry under the
porting rule, and every committed table or profile has a LICENSES.md entry.
"""

import json
import re
from pathlib import Path

from opus.ledger import flags_for, licences
from opus.paths import data_dir, plugin_root

REPO = plugin_root().parents[1]
CODE = (plugin_root() / "python" / "src", plugin_root() / "blender")
# MIT, BSD, Apache-2.0 or GPL-3-compatible; never AGPL, ND, NC or unlicensed (§2.7)
PORTABLE = {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "Zlib", "CC0-1.0", "Unlicense",
            "LGPL-2.1-or-later", "LGPL-3.0-or-later", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later"}
HEADER = re.compile(r"ported-from:\s*(\S+@[0-9A-Za-z._-]+)\s+\(([^)\s]+)\)")
NOT_COMMITTABLE = {"nc", "nd", "no-redistribute-as-asset", "use-restricted", "unknown"}


def _sections(text: str) -> dict[str, str]:
    """Heading -> body for the ``### `...` `` sections under ``## Entries``."""
    entries = text.split("\n## Entries", 1)[1] if "\n## Entries" in text else ""
    parts = re.split(r"^### `?([^`\n]+?)`?\s*$", entries, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def port_problems(roots, notices: str) -> list[str]:
    """Ported modules without a notice entry, or under a licence the porting rule forbids."""
    sections = _sections(notices)
    out = []
    for root in roots:
        for py in sorted(Path(root).rglob("*.py")):
            for line in py.read_text(encoding="utf-8").splitlines()[:40]:
                if "ported-from:" not in line:
                    continue
                m = HEADER.search(line)
                if not m:
                    out.append(f"{py.name}: malformed header {line.strip()!r}")
                    continue
                repo_at, spdx = m.groups()
                if spdx not in PORTABLE:
                    out.append(f"{py.name}: {spdx} may not be ported")
                body = next((b for b in sections.values() if f"`{repo_at}`" in b), None)
                if body is None:
                    out.append(f"{py.name}: no THIRD_PARTY_NOTICES.md entry for {repo_at}")
                elif f"`{spdx}`" not in body or "**Copyright:**" not in body or "```text" not in body:
                    out.append(f"{py.name}: the {repo_at} entry needs its SPDX id, copyright line and licence text")
    return out


def table_problems(data: Path, licences_md: str) -> list[str]:
    """Committed tables and profiles without a LICENSES.md entry, and entries whose licence
    is unknown or not allowed in the repo."""
    sections = _sections(licences_md)
    out = []
    for sub in ("tables", "profiles"):
        for p in sorted((data / sub).rglob("*")) if (data / sub).exists() else []:
            rel = p.relative_to(data).as_posix()
            if p.is_file() and rel not in sections and not any(rel.startswith(k) for k in sections if k.endswith("/")):
                out.append(f"{rel}: no data/LICENSES.md entry")
    for path, body in sections.items():
        m = re.search(r"\*\*Licence:\*\*\s*`([^`]+)`", body)
        if not m:
            out.append(f"{path}: no **Licence:** `<id>` line")
            continue
        flags = set(flags_for(m.group(1)))
        if flags & NOT_COMMITTABLE:
            out.append(f"{path}: {m.group(1)} ({', '.join(sorted(flags & NOT_COMMITTABLE))}) may not be committed")
        if "attribution" in flags and re.search(r"\*\*Credit:\*\*\s*none required", body):
            out.append(f"{path}: {m.group(1)} needs its exact credit line")
    return out


def test_gpl_licence_at_the_repo_root():
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert text.lstrip().startswith("GNU GENERAL PUBLIC LICENSE")
    assert "Version 3, 29 June 2007" in text and "END OF TERMS AND CONDITIONS" in text
    assert len(text) > 30000  # the full text, not a pointer to it


def test_every_ported_module_has_a_notice():
    notices = (REPO / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "## Porting rule" in notices and "ported-from: <repo>@<commit> (<SPDX>)" in notices
    assert port_problems(CODE, notices) == []


def test_every_data_table_has_a_licences_entry():
    text = (data_dir() / "LICENSES.md").read_text(encoding="utf-8")
    assert "licences.yaml" in _sections(text)
    assert table_problems(data_dir(), text) == []


def test_each_table_names_the_licence_its_entry_names():
    """A table's own source.licence_id is a licences.yaml ID and matches its LICENSES.md entry."""
    sections = _sections((data_dir() / "LICENSES.md").read_text(encoding="utf-8"))
    known = licences()
    tables = sorted((data_dir() / "tables").glob("*.json"))
    assert tables
    for p in tables:
        lid = json.loads(p.read_text(encoding="utf-8"))["source"]["licence_id"]
        assert lid in known, f"{p.name}: {lid} is not in licences.yaml"
        m = re.search(r"\*\*Licence:\*\*\s*`([^`]+)`", sections[f"tables/{p.name}"])
        assert m and m.group(1) == lid, f"{p.name}: LICENSES.md says {m and m.group(1)}, the table says {lid}"


def test_the_checks_catch_planted_problems(tmp_path):
    code = tmp_path / "src"
    code.mkdir()
    (code / "fit.py").write_text('"""Fit."""\n# ported-from: github.com/acme/fitlib@0123abc (MIT)\n', encoding="utf-8")
    (code / "agpl.py").write_text("# ported-from: github.com/acme/mblab@9f9f9f9 (AGPL-3.0-only)\n", encoding="utf-8")
    (code / "bad.py").write_text("# ported-from: somewhere\n", encoding="utf-8")
    entry = ("\n## Entries\n\n### Fitlib\n- **Repo:** `github.com/acme/fitlib@0123abc`\n- **Licence:** `MIT`\n"
             "- **Copyright:** Copyright (c) 2024 Acme\n\n```text\nMIT License ...\n```\n")
    problems = port_problems([code], "# Notices\n" + entry)
    assert len(problems) == 3 and not any("fit.py" in p for p in problems)
    assert any("AGPL-3.0-only may not be ported" in p for p in problems)
    assert any("malformed" in p for p in problems)
    assert any("fit.py: no THIRD_PARTY_NOTICES.md entry" in p for p in port_problems([code], "# Notices\n"))

    data = tmp_path / "data"
    (data / "tables").mkdir(parents=True)
    (data / "profiles" / "swords").mkdir(parents=True)
    for rel in ("tables/a.json", "tables/b.json", "profiles/swords/arming.json"):
        (data / rel).write_text("{}", encoding="utf-8")
    md = ("\n## Entries\n\n### `tables/a.json`\n- **Licence:** `CC-BY-4.0`\n- **Credit:** none required\n"
          "\n### `profiles/`\n- **Licence:** `CC0-1.0`\n"
          "\n### `tables/c.json`\n- **Licence:** `LicenseRef-QAL-1.0`\n")
    assert table_problems(data, md) == [
        "tables/b.json: no data/LICENSES.md entry",
        "tables/a.json: CC-BY-4.0 needs its exact credit line",
        "tables/c.json: LicenseRef-QAL-1.0 (no-redistribute-as-asset) may not be committed",
    ]
