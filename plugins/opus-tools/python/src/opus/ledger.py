"""Provenance ledger: where every asset came from, under which licence.

Entries are appended to ``<project>/.opus/ledger.jsonl``. Each names the asset's licence ID
(SPDX or ``LicenseRef-*``), the inputs it was made from and the tools that made it. Their
flags come from the committed ``data/licences.yaml``, and the union of them decides what
``check`` blocks under the bible's export policy. ``write_credits`` turns the ledger into a
CREDITS.md with the exact attribution strings.
"""

from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from pathlib import Path

import yaml

from opus.bible import load_bible
from opus.paths import data_dir, opus_dir, project_base

FLAGS = ("attribution", "nc", "sa", "nd", "no-redistribute-as-asset", "use-restricted", "unknown")

# flag -> (bible key that makes it block, or None for always; what it means)
BLOCKS = {
    "unknown": (None, "licence not classified"),
    "nc": ("commercial", "non-commercial terms"),
    "use-restricted": ("commercial", "use-restricted terms"),
    "nd": ("publish_assets", "no-derivatives terms"),
    "no-redistribute-as-asset": ("publish_assets", "may not be redistributed as an asset"),
}

MISSING = "not in the ledger"  # note on a lineage input whose asset has no entry yet

_TOKEN = re.compile(r"[a-z0-9]+|\+")
_SPELLING = {"licence": "license", "licences": "licenses", "licenced": "licensed"}


# ---------------------------------------------------------------- licence table


@lru_cache(maxsize=1)
def licences() -> dict[str, dict]:
    """The licence table from ``data/licences.yaml``, keyed by licence ID."""
    raw = yaml.safe_load((data_dir() / "licences.yaml").read_text(encoding="utf-8"))
    table = raw["licences"]
    for lid, e in table.items():
        for key in ("flags", "tool_flags"):
            bad = set(e.get(key) or []) - set(FLAGS)
            if bad:
                raise ValueError(f"licences.yaml: {lid} has unknown {key} {sorted(bad)}")
    return table


def _tokens(text: str) -> tuple[str, ...]:
    """Lowercase word tokens; "licence" reads as "license" and "v1" as "1"."""
    out = []
    for t in _TOKEN.findall(text.lower()):
        t = _SPELLING.get(t, t)
        if len(t) > 1 and t[0] == "v" and t[1:].isdigit():
            t = t[1:]
        out.append(t)
    return tuple(out)


@lru_cache(maxsize=1)
def _aliases() -> tuple[dict[tuple[str, ...], str], int]:
    """Token runs -> licence ID, from every entry's ID, name and aliases."""
    index: dict[tuple[str, ...], str] = {}
    for lid, e in licences().items():
        for phrase in (lid, e.get("name") or "", *(e.get("aliases") or [])):
            key = _tokens(str(phrase))
            if key and index.setdefault(key, lid) != lid:
                raise ValueError(f"licences.yaml: {phrase!r} names both {index[key]} and {lid}")
    return index, max(map(len, index))


@lru_cache(maxsize=1)
def _spellings() -> dict[str, str]:
    return {k.lower(): k for k in licences()}


def _canon(lid: str) -> str | None:
    """The table's spelling of a licence ID (SPDX IDs are case-insensitive)."""
    return _spellings().get(lid.lower())


def _ids(expr: str) -> list[str]:
    """Licence IDs in an SPDX expression. Exceptions after WITH only relax, so they drop."""
    out, skip = [], False
    for w in re.findall(r"[^\s()]+", expr or ""):
        if skip:
            skip = False
        elif w == "WITH":
            skip = True
        elif w not in ("AND", "OR"):
            out.append(w)
    return out


def _ordered(flags) -> list[str]:
    return [f for f in FLAGS if f in set(flags)]


def flags_for(licence_id: str, tool: bool = False) -> list[str]:
    """Flags of a licence ID, or of an SPDX expression of IDs (OR unites them, the cautious
    reading). ``tool`` gives what reaches outputs made with a tool under it. IDs missing
    from licences.yaml are unknown."""
    table = licences()
    flags: set[str] = set()
    for lid in _ids(licence_id) or [""]:
        e = table.get(_canon(lid) or "")
        if e is None:
            flags.add("unknown")
        else:
            flags.update(e.get("tool_flags", e["flags"]) if tool else e["flags"])
    return _ordered(flags)


def classify(text: str) -> tuple[str | None, list[str]]:
    """Licence ID and flags for free licence text, matched only on whole-token aliases.

    Several licences named in one text are joined with AND (OR when only "or" stands between
    them) and their flags united either way. Text that names none gives (None, ["unknown"]).
    """
    index, longest = _aliases()
    toks = _tokens(text or "")
    expr, end, i = "", 0, 0
    while i < len(toks):
        for k in range(min(longest, len(toks) - i), 0, -1):
            lid = index.get(toks[i:i + k])
            if lid:
                if lid not in _ids(expr):
                    expr += (" OR " if toks[end:i] == ("or",) else " AND ") * bool(expr) + lid
                end = i = i + k
                break
        else:
            i += 1
    if not expr:
        return None, ["unknown"]
    return expr, flags_for(expr)


def _resolve(licence_id: str = "", text: str = "", tool: bool = False) -> tuple[str | None, list[str]]:
    """ID and flags from an explicit ID or SPDX expression, else from free text."""
    if licence_id:
        if not any(_canon(i) for i in _ids(licence_id)):
            lid, _ = classify(licence_id)  # an alias such as "CC BY 4.0" given as the ID
            licence_id = lid or licence_id
        expr = re.sub(r"[^\s()]+", lambda m: _canon(m.group()) or m.group(), licence_id)
        return expr, flags_for(expr, tool)
    lid, flags = classify(text)
    return lid, (flags_for(lid, tool) if lid else flags)


# ---------------------------------------------------------------- entries


def _rel(path, root: Path) -> str:
    p = Path(path).expanduser()
    p = (p if p.is_absolute() else root / p).resolve()
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _part(p: dict, tool: bool = False) -> dict:
    """An input or tool with its licence ID and flags resolved; extra flags given with it
    are kept (they can only add restrictions)."""
    p = dict(p)
    if "licence" in p and "license" not in p:
        p["license"] = p.pop("licence")
    lid, flags = _resolve(p.get("licence_id") or "", p.get("license") or "", tool)
    extra = set(p.get("flags") or []) - {"unknown"}
    if extra - set(FLAGS):
        raise ValueError(f"unknown flags {sorted(extra - set(FLAGS))}; use {', '.join(FLAGS)}")
    p["licence_id"] = lid
    p["flags"] = _ordered(set(flags) | extra)
    return p


def _own(e: dict) -> tuple[str | None, list[str]]:
    """The asset's own licence. One made from recorded inputs or tools needs none: their
    flags carry. One with nothing recorded at all is unknown."""
    if not (e.get("licence_id") or e.get("license")) and (e.get("inputs") or e.get("tools")):
        return None, []
    return _resolve(e.get("licence_id") or "", e.get("license") or "")


def _sum(e: dict) -> dict:
    """The union of flags and the share-alike licences the output must carry."""
    own_id, own_flags = _own(e)
    e["licence_id"] = own_id
    flags, stamp = set(own_flags), []
    if "sa" in own_flags and own_id:
        stamp.append(own_id)
    for p in e["inputs"]:
        flags.update(p.get("flags") or [])
        if "asset" in p:
            stamp += p.get("stamp") or []
        elif "sa" in (p.get("flags") or []) and p.get("licence_id"):
            stamp.append(p["licence_id"])
    for t in e["tools"]:
        flags.update(t.get("flags") or [])
        if "sa" in (t.get("flags") or []) and t.get("licence_id"):
            stamp.append(t["licence_id"])
    e["flags"] = _ordered(flags)
    e["stamp"] = list(dict.fromkeys(stamp))
    return e


def _normalise(raw: dict) -> dict:
    """A stored or legacy entry in the current schema. Legacy free-text licences go
    through the classifier, and unclassified parts are classified again on every load."""
    e = dict(raw)
    for key in ("source", "license", "author", "url", "generator", "model", "notes", "attribution"):
        e.setdefault(key, "")
    e.setdefault("licence_id", None)
    e["inputs"] = [dict(p) if "asset" in p else _part(p) for p in e.get("inputs") or []]
    e["tools"] = [_part(t, tool=True) for t in e.get("tools") or []]
    return _sum(e)


def _lineage(items: list[dict]) -> None:
    """Refresh inputs that are ledger assets from those assets' latest entries, so lineage
    follows a later reclassification."""
    latest = {e["asset"]: e for e in items}
    done: set[int] = set()

    def settle(e: dict, stack: frozenset) -> None:
        if id(e) in done:
            return
        for p in e["inputs"]:
            up = latest.get(p.get("asset") or "")
            if up is None or up is e or up["asset"] in stack:
                continue
            settle(up, stack | {e["asset"]})
            p.update(licence_id=up["licence_id"], flags=list(up["flags"]), stamp=list(up["stamp"]))
            if p.get("notes") == MISSING:
                del p["notes"]
        _sum(e)
        done.add(id(e))

    for e in items:
        settle(e, frozenset())


def _read(root: Path) -> list[dict]:
    path = root / ".opus" / "ledger.jsonl"
    if not path.exists():
        return []
    items = [_normalise(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    _lineage(items)
    return items


def entries(near=None) -> list[dict]:
    """Every ledger entry in the current schema, oldest first."""
    return _read(project_base(near))


def current(near=None) -> list[dict]:
    """The latest entry per asset: recording an asset again replaces its earlier entry."""
    return list({e["asset"]: e for e in _read(project_base(near))}.values())


def record(
    asset: str,
    source: str,
    license: str = "",
    author: str = "",
    url: str = "",
    generator: str = "",
    model: str = "",
    notes: str = "",
    licence_id: str = "",
    inputs: list[dict] | None = None,
    tools: list[dict] | None = None,
    attribution: str = "",
) -> dict:
    """Append one provenance entry for ``asset`` (a path inside the project).

    ``licence_id`` is the asset's own licence; free ``license`` text is classified when it
    is missing. ``inputs`` are what the asset was made from: ``{source, licence_id or
    license, role, attribution}``, or ``{asset, role}`` for an asset already in the ledger,
    whose flags carry over. ``tools`` are ``{name, licence_id}``. ``attribution`` is the
    exact credit line, when the terms prescribe one.
    """
    root = project_base(asset)
    latest = {e["asset"]: e for e in _read(root)}
    ins = []
    for p in inputs or []:
        p = {"source": p} if isinstance(p, str) else dict(p)
        if p.get("asset"):
            rel = _rel(p["asset"], root)
            up = latest.get(rel)
            p.update(asset=rel, source=p.get("source") or rel)
            if up is None:
                p.update(licence_id=None, flags=["unknown"], stamp=[], notes=p.get("notes") or MISSING)
            else:
                p.update(licence_id=up["licence_id"], flags=list(up["flags"]), stamp=list(up["stamp"]))
            ins.append(p)
        else:
            ins.append(_part(p))
    entry = _sum({
        "asset": _rel(Path(asset).expanduser().resolve(), root),
        "source": source,
        "license": license,
        "licence_id": licence_id or None,
        "author": author,
        "url": url,
        "generator": generator,
        "model": model,
        "notes": notes,
        "attribution": attribution,
        "inputs": ins,
        "tools": [_part({"name": t} if isinstance(t, str) else t, tool=True) for t in tools or []],
        "recorded": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    with open(opus_dir(root) / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ---------------------------------------------------------------- export policy


def policy(near=None) -> dict:
    """The export policy from the project bible."""
    bible = load_bible(near)
    return {"commercial": bool(bible.get("commercial")), "publish_assets": bool(bible.get("publish_assets", False))}


def _parts(e: dict):
    """(label, licence ID, flags) for the asset's own licence, its inputs and its tools."""
    own_id, own_flags = _own(e)
    text = e.get("license") or ""
    label = f"its licence {own_id}" if own_id else f"its licence text {text!r}" if text else "no licence recorded"
    yield label, own_id, own_flags
    for p in e["inputs"]:
        if "asset" in p:
            label = f"input {p['asset']!r} ({MISSING if p.get('notes') == MISSING else 'see its own ledger entry'})"
        else:
            lid = p.get("licence_id") or (repr(p["license"]) if p.get("license") else "no licence recorded")
            label = f"input {p.get('source') or '?'!r} ({lid})"
        yield label, p.get("licence_id"), p.get("flags") or []
    for t in e["tools"]:
        yield f"tool {t.get('name') or '?'!r} ({t.get('licence_id') or 'no licence recorded'})", t.get("licence_id"), t.get("flags") or []


def reasons(entry: dict, commercial: bool = False, publish_assets: bool = False) -> tuple[list[str], list[str]]:
    """Why ``entry`` blocks an export under the policy, and what to check before shipping."""
    pol = {"commercial": commercial, "publish_assets": publish_assets}
    why, warn = [], []
    for label, lid, flags in _parts(entry):
        for flag in flags:
            if flag not in BLOCKS:
                continue
            key, what = BLOCKS[flag]
            if key is None:
                missing = lid and not all(_canon(i) for i in _ids(lid))
                why.append(f"{what}: {label}; " + ("add it to data/licences.yaml" if missing else "record its licence_id"))
            elif pol[key]:
                why.append(f"{what}: {label}; {key}: true blocks it")
            elif flag == "use-restricted":
                warn.append(f"{what}: {label}; check them before shipping, even for free")
    if len(entry.get("stamp") or []) > 1:
        warn.append(f"share-alike from {' and '.join(entry['stamp'])}: they may not be compatible")
    return why, warn


def check(near=None, commercial: bool | None = None, publish_assets: bool | None = None) -> dict:
    """Every asset in the ledger against the export policy (the bible's unless overridden)."""
    pol = policy(near)
    if commercial is not None:
        pol["commercial"] = bool(commercial)
    if publish_assets is not None:
        pol["publish_assets"] = bool(publish_assets)
    cur = current(near)
    blocked, warnings, share_alike = [], [], []
    for e in cur:
        why, warn = reasons(e, **pol)
        if why:
            blocked.append({"asset": e["asset"], "licence_id": e["licence_id"], "flags": e["flags"], "reasons": why})
        if warn:
            warnings.append({"asset": e["asset"], "warnings": warn})
        if e["stamp"]:
            share_alike.append({"asset": e["asset"], "licence": " AND ".join(e["stamp"])})
    return {"policy": pol, "ok": not blocked, "assets": len(cur), "blocked": blocked, "warnings": warnings,
            "share_alike": share_alike}


# ---------------------------------------------------------------- credits


def _credit_lines(given: str, lid: str | None, flags: list[str], who: str) -> list[str]:
    """The exact attribution string if one was given, else the licence's own credit line,
    else a title-author-source-licence line when the terms require attribution."""
    if given:
        return [given]
    table, out = licences(), []
    for i in _ids(lid or ""):
        e = table.get(_canon(i) or "") or {}
        if e.get("credit"):
            out.append(" ".join(e["credit"].split()))
        elif "attribution" in flags and "attribution" in (e.get("flags") or []):
            out.append(f"{who}, licensed under {_canon(i)}" + (f" ({e['url']})" if e.get("url") else ""))
    return out


def attributions(items: list[dict]) -> list[str]:
    """Every attribution string CREDITS.md must carry, once each, in ledger order."""
    out: list[str] = []
    for e in items:
        who = e["source"] + (f" by {e['author']}" if e.get("author") else "") + (f" ({e['url']})" if e.get("url") else "")
        own_id, own_flags = _own(e)
        out += _credit_lines(e.get("attribution") or "", own_id, own_flags, who)
        for p in e["inputs"]:
            if "asset" in p:
                continue  # credited by its own entry
            pwho = (p.get("source") or "?") + (f" by {p['author']}" if p.get("author") else "") + (f" ({p['url']})" if p.get("url") else "")
            out += _credit_lines(p.get("attribution") or "", p.get("licence_id"), p.get("flags") or [], pwho)
        for t in e["tools"]:
            out += _credit_lines(t.get("attribution") or "", t.get("licence_id"), t.get("flags") or [], t.get("name") or "?")
    return list(dict.fromkeys(out))


def _licence_label(e: dict) -> str:
    lid = e.get("licence_id")
    if lid:
        names = [(licences().get(_canon(i) or "") or {}).get("name") for i in _ids(lid)]
        return f"{' AND '.join(n for n in names if n)} ({lid})" if all(names) else lid
    if e.get("license"):
        return e["license"]
    return "made from the inputs listed" if (e["inputs"] or e["tools"]) else "unspecified"


def write_credits(near=None, out: str | Path | None = None) -> Path:
    root = project_base(near)
    items = current(root)
    lines = ["# Credits", "", "Assets, tools and models used in this game.", ""]
    credits = attributions(items)
    if credits:
        lines += ["## Attribution", ""] + [f"- {c}" for c in credits] + [""]
    stamped = [e for e in items if e["stamp"]]
    if stamped:
        lines += ["## Share-alike", ""]
        lines += [f"- `{e['asset']}` is licensed under {' AND '.join(e['stamp'])}" for e in stamped] + [""]
    lines += ["## Sources", ""]
    groups: dict[tuple, list[dict]] = {}
    for e in items:
        key = (e.get("source") or "unknown", e.get("author") or "", _licence_label(e), e.get("url") or "")
        groups.setdefault(key, []).append(e)
    for (source, author, lic, url), group in sorted(groups.items()):
        who = f" by {author}" if author else ""
        link = f" ({url})" if url else ""
        lines.append(f"- **{source}**{who}{link}: {lic}")
        for e in group[:20]:
            gen = f" · generated with {e['generator']}" + (f" ({e['model']})" if e.get("model") else "") if e.get("generator") else ""
            made = [p.get("source") or p.get("asset") for p in e["inputs"]]
            made = f" · from {', '.join(m for m in made if m)}" if made else ""
            used = f" · made with {', '.join(t.get('name') or '?' for t in e['tools'])}" if e["tools"] else ""
            lines.append(f"  - `{e['asset']}`{gen}{made}{used}")
        if len(group) > 20:
            lines.append(f"  - …and {len(group) - 20} more")
    path = Path(out) if out else root / "CREDITS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
