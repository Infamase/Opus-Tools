"""Check registry, arming and gate profiles (docs/S0B_DESIGN.md §4.7, §9.1-9.3, K8).

Each check module in ``CHECK_MODULES`` calls :func:`register` at import time. Exact checks
(formats, names, references, licences, counts, hashes, round trips) have ``needs_suite=False`` and
block from day one; thresholded geometric checks have ``needs_suite=True`` and block only once
``data/gates/armed.json`` arms them (written from a passing ``defect_inject`` run). The runner
stamps ``gate``, ``family`` and ``armed`` on every finding. Numpy-only (Blender imports it).
"""

from __future__ import annotations

import copy
import importlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from opus.compile.evalmesh import EvalMesh
from opus.gates.finding import CLASSES, FAMILIES, TIERS, Finding
from opus.paths import data_dir

SCOPES = ("asset", "part", "pair")
STAGES = ("spec", "eval", "emitted", "finished", "export")
OWNERS = ("A", "C", "D", "E")
PROFILES = ("cad_clean", "kitbash", "organic")


@dataclass(frozen=True)
class CheckSpec:
    check: str
    tier: str
    klass: str
    family: str | None
    scope: str                     # "asset" | "part" | "pair"
    stages: tuple[str, ...]        # of "spec", "eval", "emitted", "finished" (read-backs), "export"
    needs_suite: bool              # True: blocks only once armed.json arms it (K8)
    owner: str                     # "A" | "C" | "D" | "E"
    fn: Callable[[GateContext], list[Finding]]
    profiles: tuple[str, ...] = PROFILES

    def __post_init__(self):
        bad = []
        if self.tier not in TIERS:
            bad.append(f"tier {self.tier!r} not in {TIERS}")
        if self.klass not in CLASSES:
            bad.append(f"class {self.klass!r} not in {CLASSES}")
        if self.family is not None and self.family not in FAMILIES:
            bad.append(f"family {self.family!r} not in {FAMILIES}")
        if self.scope not in SCOPES:
            bad.append(f"scope {self.scope!r} not in {SCOPES}")
        if not self.stages or any(s not in STAGES for s in self.stages):
            bad.append(f"stages {self.stages!r} must be a non-empty subset of {STAGES}")
        if self.owner not in OWNERS:
            bad.append(f"owner {self.owner!r} not in {OWNERS}")
        if any(p not in PROFILES for p in self.profiles):
            bad.append(f"profiles {self.profiles!r} must be a subset of {PROFILES}")
        if not callable(self.fn):
            bad.append("fn is not callable")
        if bad:
            raise ValueError(f"check {self.check!r}: " + "; ".join(bad))


REGISTRY: dict[str, CheckSpec] = {}
CHECK_MODULES = ("opus.gates.t0", "opus.gates.t1", "opus.gates.t2", "opus.gates.consistency", "opus.gates.built")


def register(spec: CheckSpec) -> None:
    """Add a check; a duplicate id raises ValueError."""
    if spec.check in REGISTRY:
        raise ValueError(f"check {spec.check!r} is already registered (owner {REGISTRY[spec.check].owner})")
    REGISTRY[spec.check] = spec


def load_checks(modules: tuple[str, ...] | None = None) -> dict[str, str]:
    """Import CHECK_MODULES (or ``modules``); {module: error} for those that fail. The runner adds
    one report-class not_available finding per failed module, so a package can merge before the
    modules it calls."""
    failed = {}
    for name in CHECK_MODULES if modules is None else modules:
        try:
            importlib.import_module(name)
        except Exception as e:  # any import failure is reported, never raised
            failed[name] = f"{type(e).__name__}: {e}"
    return failed


def armed_path() -> Path:
    """data/gates/armed.json, or $OPUS_ARMED_JSON (tests)."""
    env = os.environ.get("OPUS_ARMED_JSON")
    return Path(env) if env else data_dir() / "gates" / "armed.json"


_ARMED_CACHE: dict[str, tuple[float, dict]] = {}


def armed_table(path: Path | None = None) -> dict:
    """armed.json as a dict ({} when the file does not exist), cached by modification time."""
    p = Path(path) if path else armed_path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {}
    hit = _ARMED_CACHE.get(str(p))
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(p.read_text(encoding="utf-8"))
    _ARMED_CACHE[str(p)] = (mtime, data)
    return data


def armed(check: str, path: Path | None = None) -> bool:
    """not needs_suite, or data/gates/armed.json[check]["armed"]. A check that is not registered
    is armed only through armed.json."""
    spec = REGISTRY.get(check)
    if spec is not None and not spec.needs_suite:
        return True
    entry = armed_table(path).get(check)
    return bool(isinstance(entry, dict) and entry.get("armed"))


def gate_profiles() -> dict:
    """data/gates/profiles.json (§9.2): {"version", "defaults", "profiles": {name: thresholds}}."""
    return json.loads((data_dir() / "gates" / "profiles.json").read_text(encoding="utf-8"))


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def profile_thresholds(name: str, *overrides: dict) -> dict:
    """One profile's flat thresholds: defaults < profiles[name] < each override in order (bible,
    then spec), with "profile" = name. This is what dims_resolve writes to resolved["gates"]."""
    data = gate_profiles()
    if name not in data["profiles"]:
        raise ValueError(f"unknown gate profile {name!r}; profiles: {sorted(data['profiles'])}")
    out = _merge(data.get("defaults", {}), data["profiles"][name])
    for o in overrides:
        out = _merge(out, o or {})
    out["profile"] = name
    return out


@dataclass
class GateContext:
    resolved: dict                 # ResolvedSpec
    mesh: EvalMesh                 # evaluator mesh, or the mesh under test (defects)
    spec: dict | None = None
    emitted: EvalMesh | None = None   # read-back before finishing
    built: EvalMesh | None = None     # finished read-back
    profile: dict = field(default_factory=dict)   # = resolved["gates"]
    parts: set[str] | None = None  # local re-run scope; None = all
    evidence_dir: Path | None = None
    blend: Path | None = None
    readback_npz: Path | None = None
    run_task: Callable[[str, dict], dict] | None = None   # injectable Blender runner (tests pass a fake)
    gate: str = "spec_check"       # copied into Finding.gate

    def stage_mesh(self, stage: str) -> EvalMesh | None:
        """The mesh a stage checks: eval = mesh, emitted = emitted, finished = built."""
        return {"eval": self.mesh, "emitted": self.emitted, "finished": self.built}.get(stage)
