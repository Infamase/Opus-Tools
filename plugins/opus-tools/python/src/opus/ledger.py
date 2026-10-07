"""Provenance ledger: where every asset came from, under which license.

Entries are appended to ``<project>/.opus/ledger.jsonl``. ``write_credits`` turns them
into a CREDITS.md for the game, and ``license_flags`` lists what would block a public or
commercial release.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from opus.paths import find_project_root, opus_dir

NON_COMMERCIAL = ("nc", "non-commercial", "noncommercial", "research", "personal")
NEEDS_ATTRIBUTION = ("cc-by", "cc by", "attribution", "ofl", "mit", "apache")


def _root(near) -> Path:
    return find_project_root(near) or Path(near or os.getcwd()).expanduser().resolve()


def record(
    asset: str,
    source: str,
    license: str = "",
    author: str = "",
    url: str = "",
    generator: str = "",
    model: str = "",
    notes: str = "",
) -> dict:
    """Append one provenance entry for ``asset`` (a path inside the project)."""
    root = _root(asset)
    p = Path(asset).expanduser().resolve()
    try:
        rel = str(p.relative_to(root))
    except ValueError:
        rel = str(p)
    entry = {
        "asset": rel.replace("\\", "/"),
        "source": source,
        "license": license,
        "author": author,
        "url": url,
        "generator": generator,
        "model": model,
        "notes": notes,
        "recorded": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(opus_dir(root) / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def entries(near=None) -> list[dict]:
    path = _root(near) / ".opus" / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def license_flags(near=None) -> list[dict]:
    """Entries whose license would block a commercial or public release."""
    return [e for e in entries(near) if any(t in (e.get("license") or "").lower() for t in NON_COMMERCIAL)]


def write_credits(near=None, out: str | Path | None = None) -> Path:
    root = _root(near)
    groups: dict[tuple, list[dict]] = {}
    for e in entries(root):
        key = (e.get("source") or "unknown", e.get("author") or "", e.get("license") or "unspecified", e.get("url") or "")
        groups.setdefault(key, []).append(e)
    lines = ["# Credits", "", "Assets, tools and models used in this game.", ""]
    for (source, author, lic, url), items in sorted(groups.items()):
        who = f" by {author}" if author else ""
        link = f" ({url})" if url else ""
        lines.append(f"- **{source}**{who}{link}: {lic}")
        for e in items[:20]:
            gen = f" · generated with {e['generator']}" + (f" ({e['model']})" if e.get("model") else "") if e.get("generator") else ""
            lines.append(f"  - `{e['asset']}`{gen}")
        if len(items) > 20:
            lines.append(f"  - …and {len(items) - 20} more")
    path = Path(out) if out else root / "CREDITS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
