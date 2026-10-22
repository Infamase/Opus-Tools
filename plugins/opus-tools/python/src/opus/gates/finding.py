"""The finding contract (docs/S0B_DESIGN.md §4.7; OVERHAUL §2.5).

JSON form: ``{"gate","check","class","tier","target":{...},"value","expected","unit","noise_tol",
"pass","family","armed","evidence","fix":{"spec_path","suggest","dial_unit"},"message"}``;
schema ``data/schema/finding.schema.json``. The same failure has the same ``key()`` whichever
tool reports it. Numpy-only (Blender imports it).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, fields

import numpy as np

CLASSES = ("hard", "soft", "report")
TIERS = ("T0", "T1", "T2", "T2b", "T3", "T4", "T5", "T6")
FAMILIES = ("contact", "floating", "manifold", "sheet", "naming", "relation", "overlap", "consistency")
UNITS = ("m", "px", "deg", "count", "ratio", "")
DIAL_UNITS = ("m", "ratio", "deg", "count", "anchor", "name")
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[-+]?inf"
_LE = re.compile(rf"^<=\s*({_NUM})$")
_GE = re.compile(rf"^>=\s*({_NUM})$")
_EQ = re.compile(rf"^==\s*({_NUM})$")
_IN = re.compile(rf"^in\[\s*({_NUM})\s*,\s*({_NUM})\s*\]$")


@dataclass
class Target:
    part: str | None = None
    other: str | None = None
    view: str | None = None
    path: str | None = None
    bone: str | None = None
    frames: list | None = None
    pose: str | None = None
    cell: list | None = None


@dataclass
class Fix:
    spec_path: str | None          # JSON pointer that fixes it
    suggest: str                   # one line, imperative
    dial_unit: str | None = None   # "m" | "ratio" | "deg" | "count" | "anchor" | "name"


def _plain(v):
    """numpy scalars -> Python (np.bool_ -> bool, np.integer -> int, np.floating -> float);
    NaN/inf -> None; containers walked."""
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, np.ndarray):
        return _plain(v.tolist())
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def _is_nan(v) -> bool:
    return isinstance(v, (float, np.floating)) and math.isnan(float(v))


@dataclass
class Finding:
    gate: str                      # the calling tool ("spec_check", "spec_validate", "spec_build", "export_asset")
    check: str                     # registry id, e.g. "contact_gap"
    klass: str                     # JSON key "class"
    tier: str
    target: Target
    value: float | int | str | bool | None
    expected: str                  # "<=0.002" | ">=0.99" | "==0" | "in[0.9,1.1]" | "true"
    unit: str                      # "m" | "px" | "deg" | "count" | "ratio" | ""
    noise_tol: float               # ε for spec_edit (§10.3); 0 for exact checks
    passed: bool                   # JSON key "pass"; a NaN value never passes
    family: str | None = None      # stamped by the runner from the registry
    armed: bool = True             # stamped by the runner from armed(); False: reports, never blocks
    evidence: str | None = None    # path to an image or npz
    fix: Fix | None = None
    message: str = ""

    def __post_init__(self):
        if self.klass not in CLASSES:
            raise ValueError(f"finding {self.check}: class {self.klass!r} is not one of {CLASSES}")
        if self.tier not in TIERS:
            raise ValueError(f"finding {self.check}: tier {self.tier!r} is not one of {TIERS}")
        if self.family is not None and self.family not in FAMILIES:
            raise ValueError(f"finding {self.check}: family {self.family!r} is not one of {FAMILIES}")
        if isinstance(self.target, dict):
            self.target = Target(**self.target)
        if isinstance(self.fix, dict):
            self.fix = Fix(**self.fix)
        self.passed = bool(self.passed) and not _is_nan(self.value)
        self.armed = bool(self.armed)

    def key(self) -> tuple:
        return (self.check, self.target.part, self.target.other, self.target.view)

    def blocking(self) -> bool:
        return self.klass == "hard" and self.armed and not self.passed

    def magnitude(self) -> float:
        """0 when passed. "<=x": (v-x)/max(|x|,1e-9); ">=x": (x-v)/max(|x|,1e-9); "in[a,b]": distance
        outside /(b-a); "==x" numeric: |v-x|/max(|x|,1); booleans, strings, None: 1. A NaN value
        counts 1; never negative."""
        if self.passed:
            return 0.0
        v = self.value
        if v is None or isinstance(v, (bool, np.bool_, str)) or _is_nan(v):
            return 1.0
        v = float(v)
        exp = self.expected.strip()
        if m := _LE.match(exp):
            x = float(m.group(1))
            return max(0.0, (v - x) / max(abs(x), 1e-9))
        if m := _GE.match(exp):
            x = float(m.group(1))
            return max(0.0, (x - v) / max(abs(x), 1e-9))
        if m := _IN.match(exp):
            a, b = float(m.group(1)), float(m.group(2))
            out = a - v if v < a else (v - b if v > b else 0.0)
            return max(0.0, out / max(b - a, 1e-9))
        if m := _EQ.match(exp):
            x = float(m.group(1))
            return abs(v - x) / max(abs(x), 1.0)
        return 1.0

    def to_json(self) -> dict:
        """The JSON form; numpy scalars -> Python, NaN/inf -> None."""
        t = {f.name: _plain(getattr(self.target, f.name)) for f in fields(Target)}
        fx = None if self.fix is None else {"spec_path": self.fix.spec_path, "suggest": self.fix.suggest,
                                            "dial_unit": self.fix.dial_unit}
        return {"gate": self.gate, "check": self.check, "class": self.klass, "tier": self.tier, "target": t,
                "value": _plain(self.value), "expected": self.expected, "unit": self.unit,
                "noise_tol": _plain(self.noise_tol), "pass": bool(self.passed), "family": self.family,
                "armed": bool(self.armed), "evidence": None if self.evidence is None else str(self.evidence),
                "fix": fx, "message": self.message}

    @staticmethod
    def from_json(d) -> Finding:
        fx = d.get("fix")
        return Finding(gate=d["gate"], check=d["check"], klass=d["class"], tier=d["tier"],
                       target=Target(**(d.get("target") or {})), value=d.get("value"), expected=d["expected"],
                       unit=d.get("unit", ""), noise_tol=0.0 if d.get("noise_tol") is None else float(d["noise_tol"]),
                       passed=bool(d["pass"]), family=d.get("family"), armed=bool(d.get("armed", True)),
                       evidence=d.get("evidence"), fix=None if fx is None else Fix(**fx), message=d.get("message", ""))


def findings_json(findings: list[Finding]) -> list[dict]:
    return [f.to_json() for f in findings]
