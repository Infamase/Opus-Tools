"""EvalMesh, the .npz exchange file and the hashes (docs/S0B_DESIGN.md §4.5, K4).

One mesh object per part, emitted with local vertices plus a world matrix. ``geom_hash``
covers part names, matrices, local vertices and triangles, float32-cast and quantized to 1e-6;
``eval_hash`` = ``geom_hash`` + anchors + sockets. Determinism compares ``eval_hash`` (host vs
Blender evaluator); ``emit_hash`` compares ``geom_hash`` of a read-back with the evaluator's.

**.npz exchange** (host <-> Blender, both directions): arrays ``verts_local`` (float64), ``verts``
(float64), ``tris`` (int32), ``part_id`` (int16), ``uv`` (float32), ``edge_flags`` (uint8),
``quad_mate`` (int32), optional ``frames`` (float64) and ``field_<name>``, and ``meta``: a uint8
array holding UTF-8 JSON ``{"format", "source", "parts", "anchors", "sockets", "relations",
"extra"}``. No object arrays; always ``allow_pickle=False``. A quad read back from Blender is split
(a,b,c),(a,c,d) in polygon order, which reproduces the evaluator's triangle order because builders
emit quads only through :func:`quads_to_tris`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from opus.compile import fmath
from opus.compile.conventions import GROUND

FORMAT = "opus.evalmesh/1"
Q = 1e-6
EDGE_SHARP, EDGE_BEVEL, EDGE_CUTTING, EDGE_SEAM = 1, 2, 4, 8
UNIT_TOL = 1e-9  # |‖n‖ − 1|, |‖t‖ − 1| and |t·n| allowed on anchors
ARRAYS = {"verts_local": np.float64, "verts": np.float64, "tris": np.int32, "part_id": np.int16,
          "uv": np.float32, "edge_flags": np.uint8, "quad_mate": np.int32}


@dataclass
class Anchor:
    p: tuple[float, float, float]                 # point (m)
    n: tuple[float, float, float]                 # unit normal (frame z)
    t: tuple[float, float, float]                 # unit tangent (frame x)
    attrs: dict[str, float] = field(default_factory=dict)  # radius | a, b, n | w, h, d


@dataclass
class Mate:                        # one placement contact, re-checkable from matrices (anchor_error)
    part: str                      # the other part ("ground" allowed)
    kind: str                      # "attach" | "squeeze" | "translate" | "contact" (relation; no points)
    self_anchor: str = ""          # names, for messages
    other_anchor: str = ""
    p_self: tuple | None = None    # this part's anchor point, canonical local
    p_other: tuple | None = None   # the other part's anchor point (+ offset·n), its canonical local
    xf: tuple | None = None        # 16 floats applied to the other's world point (reflect mirror, array turn)


@dataclass
class PartInfo:
    name: str
    src: str                       # JSON pointer into the spec, e.g. "/parts/2"
    builder: str                   # box | superquadric | extrude | lathe | station_loft | fixture
    v0: int                        # slices of verts / tris
    v1: int
    t0: int
    t1: int
    matrix: tuple[float, ...]      # 16 floats row-major, canonical local -> world (includes R_b)
    material: str = ""
    parent: str | None = None      # placement parent ("ground" allowed); reflect: the source's parent's
                                   # mirror partner if it has one, else the same parent; array copy: the template's
    mates: list[Mate] = field(default_factory=list)
    mirror_of: str | None = None   # reflect source
    array_of: str | None = None    # array template name
    joint: dict | None = None      # joint root only: {"name","type":"revolute|prismatic","origin":[3],"axis":[3],"limits_deg":[2]} world
    joint_root: str | None = None  # name of the joint whose subtree holds this part
    closed: bool = True            # closed 2-manifold by construction
    post_eval: bool = False
    measures: dict[str, dict] = field(default_factory=dict)  # key -> {"spec": float | None, "built": float} (§4.6)
    deps: tuple[str, ...] = ()     # transitive closure of dims and parts this part depends on (§10.2)


@dataclass
class EvalMesh:
    verts_local: np.ndarray        # (V,3) float64, canonical frames
    verts: np.ndarray              # (V,3) float64 = fmath.apply(part.matrix, verts_local) per part
    tris: np.ndarray               # (T,3) int32, CCW seen from outside; parts never share vertices
    part_id: np.ndarray            # (T,) int16
    uv: np.ndarray                 # (T,3,2) float32 corner UVs
    edge_flags: np.ndarray         # (T,3) uint8; edge k joins tris[:,k] and tris[:,(k+1)%3]
    quad_mate: np.ndarray          # (T,) int32: the other triangle of a quad, -1 if none (canonical form below)
    parts: list[PartInfo]
    anchors: dict[str, Anchor]     # "part:anchor" (literal spec strings) -> world frame; placements, sockets, joints
    sockets: dict[str, dict]       # name -> {"ref": "part:anchor"} | {"grip", "center", "palm", "up", "hand"} (§5.5, §11.1)
    relations: list[dict]          # expanded: reflect-mirrored and array-expanded copies of the spec's relations
    source: dict                   # {"spec_id","rev","seed","tables_version","level","evaluator","kind",
                                   #  "origin_offset": [x, y, z] applied by the origin rule}
    extra: dict = field(default_factory=dict)     # JSON; read-backs: {"objects","stamps","socket_empties"}
    fields: dict[str, np.ndarray] = field(default_factory=dict)  # named arrays (heightfields, SDF grids; S2+)
    frames: np.ndarray | None = None              # (F, P, 16) per-part world matrices per frame (motion, joints)

    def part(self, name: str) -> PartInfo:
        for p in self.parts:
            if p.name == name:
                return p
        raise KeyError(f"no part {name!r}; parts: {[p.name for p in self.parts]}")

    def part_index(self, name: str) -> int:
        for i, p in enumerate(self.parts):
            if p.name == name:
                return i
        raise KeyError(f"no part {name!r}; parts: {[p.name for p in self.parts]}")

    def part_verts(self, name: str, local: bool = False) -> np.ndarray:
        p = self.part(name)
        return (self.verts_local if local else self.verts)[p.v0:p.v1]

    def part_tris(self, name: str) -> np.ndarray:
        """The part's triangles with vertex indices from 0 (part-local)."""
        p = self.part(name)
        return self.tris[p.t0:p.t1] - p.v0

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """(min, max) of the world vertices; zeros for a mesh without vertices."""
        if len(self.verts) == 0:
            return np.zeros(3), np.zeros(3)
        return self.verts.min(axis=0), self.verts.max(axis=0)

    def validate(self) -> list[str]:
        """Problems, or [] for a well-formed mesh: shapes and dtypes; part slices contiguous and
        covering; ids in range; unit n/t, |t·n| < 1e-9; quads canonical (for quad_mate[i] = j >= 0,
        j == i+1 (i is the first half) or j == i-1; first half (a,b,c), second half (a,c,d):
        tris[j,0] == tris[i,0] and tris[j,1] == tris[i,2]); mates reference existing parts;
        frames (if any) shaped (F, len(parts), 16)."""
        errs: list[str] = []
        V = len(self.verts_local) if self.verts_local.ndim == 2 else -1
        T = len(self.tris) if self.tris.ndim == 2 else -1
        want = {"verts_local": (V, 3), "verts": (V, 3), "tris": (T, 3), "part_id": (T,), "uv": (T, 3, 2),
                "edge_flags": (T, 3), "quad_mate": (T,)}
        for name, dtype in ARRAYS.items():
            a = getattr(self, name)
            if not isinstance(a, np.ndarray):
                errs.append(f"{name}: not a numpy array")
                continue
            if a.dtype != dtype:
                errs.append(f"{name}: dtype {a.dtype}, want {np.dtype(dtype)}")
            if a.shape != want[name]:
                errs.append(f"{name}: shape {a.shape}, want {want[name]}")
        if errs:
            return errs
        names = [p.name for p in self.parts]
        if len(set(names)) != len(names):
            errs.append(f"duplicate part names: {sorted({n for n in names if names.count(n) > 1})}")
        v_at, t_at = 0, 0
        for i, p in enumerate(self.parts):
            if p.v0 != v_at or p.t0 != t_at or p.v1 < p.v0 or p.t1 < p.t0:
                errs.append(f"part {p.name}: slices v[{p.v0}:{p.v1}] t[{p.t0}:{p.t1}] are not contiguous "
                            f"(expected v0={v_at}, t0={t_at})")
            v_at, t_at = max(p.v1, v_at), max(p.t1, t_at)
            if len(p.matrix) != 16:
                errs.append(f"part {p.name}: matrix has {len(p.matrix)} values, want 16")
            if p.t1 > p.t0:
                pt = self.tris[p.t0:p.t1]
                if pt.min() < p.v0 or pt.max() >= p.v1:
                    errs.append(f"part {p.name}: triangles reference vertices outside v[{p.v0}:{p.v1}]")
                if (self.part_id[p.t0:p.t1] != i).any():
                    errs.append(f"part {p.name}: part_id is not {i} on t[{p.t0}:{p.t1}]")
            for m in p.mates:
                if m.part != GROUND and m.part not in names:
                    errs.append(f"part {p.name}: mate references unknown part {m.part!r}")
        if v_at != V or t_at != T:
            errs.append(f"part slices cover v[0:{v_at}] t[0:{t_at}], arrays have V={V} T={T}")
        if T > 0 and (self.tris.min() < 0 or self.tris.max() >= V):
            errs.append("tris: vertex index out of range")
        if T > 0 and (self.part_id.min() < 0 or self.part_id.max() >= len(self.parts)):
            errs.append("part_id: out of range")
        errs += _quad_errors(self.tris, self.quad_mate, self.part_id)
        for key, a in self.anchors.items():
            n, t = np.asarray(a.n, float), np.asarray(a.t, float)
            if n.shape != (3,) or t.shape != (3,) or np.asarray(a.p, float).shape != (3,):
                errs.append(f"anchor {key}: p, n and t are 3 numbers each")
                continue
            ln, lt = math.sqrt(fmath.fsum(n * n)), math.sqrt(fmath.fsum(t * t))
            dot = fmath.fsum(n * t)
            if abs(ln - 1.0) > UNIT_TOL or abs(lt - 1.0) > UNIT_TOL or abs(dot) >= UNIT_TOL:
                errs.append(f"anchor {key}: n and t must be unit and perpendicular (|n|={ln!r}, |t|={lt!r}, t·n={dot!r})")
        if self.frames is not None:
            fr = np.asarray(self.frames)
            if fr.ndim != 3 or fr.shape[1:] != (len(self.parts), 16):
                errs.append(f"frames: shape {fr.shape}, want (F, {len(self.parts)}, 16)")
        for name, a in self.fields.items():
            if not isinstance(a, np.ndarray) or a.dtype == object:
                errs.append(f"field {name}: not a numeric numpy array")
        return errs


def _quad_errors(tris: np.ndarray, mate: np.ndarray, part_id: np.ndarray) -> list[str]:
    errs = []
    T = len(tris)
    idx = np.arange(T)
    has = mate >= 0
    bad = has & ((mate >= T) | ((mate != idx + 1) & (mate != idx - 1)))
    if bad.any():
        i = int(np.nonzero(bad)[0][0])
        errs.append(f"quad_mate: triangle {i} is paired with {int(mate[i])}, not an adjacent triangle "
                    f"({int(bad.sum())} such)")
        return errs
    j = np.where(has, mate, 0)
    unmutual = has & (mate[j] != idx)
    if unmutual.any():
        i = int(np.nonzero(unmutual)[0][0])
        errs.append(f"quad_mate: triangle {i} names {int(mate[i])} as its mate but not the reverse")
        return errs
    first = has & (mate == idx + 1)
    i = np.nonzero(first)[0]
    if len(i):
        k = i + 1
        wrong = (tris[k, 0] != tris[i, 0]) | (tris[k, 1] != tris[i, 2]) | (part_id[k] != part_id[i])
        if wrong.any():
            a = int(i[np.nonzero(wrong)[0][0]])
            errs.append(f"quad_mate: triangles {a},{a + 1} are not a canonical quad (a,b,c),(a,c,d) "
                        f"({int(wrong.sum())} such)")
    return errs


def quads_to_tris(quads: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(Q,4) quads [a,b,c,d] -> (2Q,3) tris [(a,b,c),(a,c,d)] interleaved, and quad_mate. Every builder uses it.
    quad_mate indexes the returned array; offset it (where >= 0) when concatenating."""
    q = np.asarray(quads, dtype=np.int64).reshape(-1, 4)
    tris = np.empty((2 * len(q), 3), dtype=np.int32)
    tris[0::2] = q[:, [0, 1, 2]]
    tris[1::2] = q[:, [0, 2, 3]]
    mate = np.empty(2 * len(q), dtype=np.int32)
    mate[0::2] = np.arange(1, 2 * len(q), 2, dtype=np.int32)
    mate[1::2] = np.arange(0, 2 * len(q), 2, dtype=np.int32)
    return tris, mate


# ---------------------------------------------------------------- hashes

def q(a) -> bytes:
    """float32-cast, quantized to Q, little-endian int64 bytes."""
    return np.rint(np.asarray(a, np.float32).astype(np.float64) / Q).astype("<i8").tobytes()


def geom_hash(m: EvalMesh) -> str:
    h = hashlib.sha256(FORMAT.encode() + b"\0")
    for p in sorted(m.parts, key=lambda p: p.name.encode()):
        h.update(p.name.encode() + b"\0")
        h.update(q(p.matrix))
        h.update(q(m.verts_local[p.v0:p.v1]))
        h.update((m.tris[p.t0:p.t1] - p.v0).astype("<i4").tobytes())
    return h.hexdigest()


def canonical_json(data) -> str:
    """Sorted keys, no spaces, ASCII; numpy scalars as Python numbers."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_json_default)


def _anchor_bytes(key: str, a: Anchor, offset=(0.0, 0.0, 0.0)) -> bytes:
    p = (a.p[0] - offset[0], a.p[1] - offset[1], a.p[2] - offset[2])
    return key.encode() + b"\0" + q(p) + q(a.n) + q(a.t)


def eval_hash(m: EvalMesh) -> str:
    """geom_hash, then anchors (sorted keys: key, q(p, n, t)) and sockets (sorted, canonical JSON)."""
    h = hashlib.sha256(b"opus.evalhash/1\0" + geom_hash(m).encode() + b"\0")
    for key in sorted(m.anchors, key=str.encode):
        h.update(_anchor_bytes(key, m.anchors[key]))
    h.update(canonical_json(m.sockets).encode())
    return h.hexdigest()


def part_hash(m: EvalMesh, name: str, root_frame: bool = True) -> str:
    """The geom recipe for one part plus its anchors (keys "name:..."). ``root_frame`` subtracts
    source["origin_offset"] from the matrix translation AND from those anchor points, so
    re-centring the asset after an edit does not count as a change (locality, §10.2)."""
    p = m.part(name)
    off = [float(v) for v in (m.source.get("origin_offset") or (0.0, 0.0, 0.0))] if root_frame else [0.0, 0.0, 0.0]
    mat = list(p.matrix)
    mat[3], mat[7], mat[11] = mat[3] - off[0], mat[7] - off[1], mat[11] - off[2]
    h = hashlib.sha256(b"opus.parthash/1\0" + p.name.encode() + b"\0")
    h.update(q(mat))
    h.update(q(m.verts_local[p.v0:p.v1]))
    h.update((m.tris[p.t0:p.t1] - p.v0).astype("<i4").tobytes())
    prefix = name + ":"
    for key in sorted((k for k in m.anchors if k.startswith(prefix)), key=str.encode):
        h.update(_anchor_bytes(key, m.anchors[key], off))
    return h.hexdigest()


# ---------------------------------------------------------------- .npz exchange

def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (tuple, set, frozenset)):
        return list(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def _tuple(v, n: int | None = None):
    if v is None:
        return None
    t = tuple(float(x) for x in v)
    if n is not None and len(t) != n:
        raise ValueError(f"expected {n} numbers, got {len(t)}")
    return t


def part_to_dict(p: PartInfo) -> dict:
    return json.loads(json.dumps(asdict(p), default=_json_default))


def part_from_dict(d: dict) -> PartInfo:
    mates = [Mate(part=x["part"], kind=x["kind"], self_anchor=x.get("self_anchor", ""),
                  other_anchor=x.get("other_anchor", ""), p_self=_tuple(x.get("p_self")),
                  p_other=_tuple(x.get("p_other")), xf=_tuple(x.get("xf"))) for x in d.get("mates", [])]
    return PartInfo(name=d["name"], src=d["src"], builder=d["builder"], v0=int(d["v0"]), v1=int(d["v1"]),
                    t0=int(d["t0"]), t1=int(d["t1"]), matrix=_tuple(d["matrix"], 16), material=d.get("material", ""),
                    parent=d.get("parent"), mates=mates, mirror_of=d.get("mirror_of"), array_of=d.get("array_of"),
                    joint=d.get("joint"), joint_root=d.get("joint_root"), closed=bool(d.get("closed", True)),
                    post_eval=bool(d.get("post_eval", False)), measures=dict(d.get("measures") or {}),
                    deps=tuple(d.get("deps") or ()))


def anchor_to_dict(a: Anchor) -> dict:
    return {"p": [float(v) for v in a.p], "n": [float(v) for v in a.n], "t": [float(v) for v in a.t],
            "attrs": {k: float(v) for k, v in a.attrs.items()}}


def anchor_from_dict(d: dict) -> Anchor:
    return Anchor(p=_tuple(d["p"], 3), n=_tuple(d["n"], 3), t=_tuple(d["t"], 3),
                  attrs={k: float(v) for k, v in (d.get("attrs") or {}).items()})


def meta_dict(m: EvalMesh) -> dict:
    return {"format": FORMAT, "source": m.source, "parts": [part_to_dict(p) for p in m.parts],
            "anchors": {k: anchor_to_dict(a) for k, a in m.anchors.items()}, "sockets": m.sockets,
            "relations": m.relations, "extra": m.extra}


def save_npz(m: EvalMesh, path) -> None:
    """Write ``m`` as an uncompressed .npz (exactly at ``path``; numpy adds no suffix)."""
    arrays = {name: np.ascontiguousarray(getattr(m, name), dtype=dtype) for name, dtype in ARRAYS.items()}
    if m.frames is not None:
        arrays["frames"] = np.ascontiguousarray(m.frames, dtype=np.float64)
    for name, a in m.fields.items():
        a = np.asarray(a)
        if a.dtype == object:
            raise ValueError(f"field {name}: object arrays cannot be exchanged")
        arrays[f"field_{name}"] = a
    meta = json.dumps(meta_dict(m), default=_json_default, ensure_ascii=False).encode("utf-8")
    arrays["meta"] = np.frombuffer(meta, dtype=np.uint8)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        np.savez(f, **arrays)


def load_npz(path) -> EvalMesh:
    """Read an EvalMesh .npz (``allow_pickle=False``; the file is closed on return, for Windows)."""
    with np.load(path, allow_pickle=False) as z:
        data = {k: np.array(z[k]) for k in z.files}
    if "meta" not in data:
        raise ValueError(f"{path}: not an EvalMesh file (no meta)")
    meta = json.loads(data.pop("meta").tobytes().decode("utf-8"))
    if meta.get("format") != FORMAT:
        raise ValueError(f"{path}: format {meta.get('format')!r}, expected {FORMAT!r}")
    missing = [k for k in ARRAYS if k not in data]
    if missing:
        raise ValueError(f"{path}: missing arrays {missing}")
    return EvalMesh(**{k: data[k] for k in ARRAYS},
                    parts=[part_from_dict(p) for p in meta["parts"]],
                    anchors={k: anchor_from_dict(a) for k, a in meta.get("anchors", {}).items()},
                    sockets=meta.get("sockets", {}), relations=meta.get("relations", []),
                    source=meta.get("source", {}), extra=meta.get("extra", {}),
                    fields={k[6:]: v for k, v in data.items() if k.startswith("field_")},
                    frames=data.get("frames"))


# ---------------------------------------------------------------- assembly helpers and fixtures

# box vertex k = ix + 2·iy + 4·iz (i = 0 at the minus side); faces CCW seen from outside
BOX_QUADS = np.array([[0, 2, 3, 1],   # bottom (-z)
                      [4, 5, 7, 6],   # top (+z)
                      [0, 1, 5, 4],   # front (-y)
                      [2, 6, 7, 3],   # back (+y)
                      [1, 3, 7, 5],   # left (+x)
                      [0, 4, 6, 2]],  # right (-x)
                     dtype=np.int32)
QUAD_UV = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)


def empty() -> EvalMesh:
    """An EvalMesh without parts (a container for kinds whose level has no triangles)."""
    return EvalMesh(verts_local=np.zeros((0, 3)), verts=np.zeros((0, 3)), tris=np.zeros((0, 3), np.int32),
                    part_id=np.zeros(0, np.int16), uv=np.zeros((0, 3, 2), np.float32),
                    edge_flags=np.zeros((0, 3), np.uint8), quad_mate=np.zeros(0, np.int32),
                    parts=[], anchors={}, sockets={}, relations=[], source={})


def assemble(local_parts: list[tuple[PartInfo, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
             anchors: dict[str, Anchor], sockets: dict, relations: list, source: dict) -> EvalMesh:
    """Concatenate parts given as (PartInfo with name/matrix/metadata, verts_local, part-local
    tris, uv, edge_flags, part-local quad_mate) in order: fills slices and part ids, offsets tris
    and quad_mate, and computes ``verts = fmath.apply(matrix, verts_local)``."""
    vl, vw, tr, pid, uv, ef, qm, parts = [], [], [], [], [], [], [], []
    v_at = t_at = 0
    for i, (info, verts, tris, uvs, flags, mate) in enumerate(local_parts):
        verts = np.asarray(verts, np.float64).reshape(-1, 3)
        tris = np.asarray(tris, np.int64).reshape(-1, 3)
        info.v0, info.v1, info.t0, info.t1 = v_at, v_at + len(verts), t_at, t_at + len(tris)
        vl.append(verts)
        vw.append(fmath.apply(info.matrix, verts))
        tr.append(tris + v_at)
        pid.append(np.full(len(tris), i, np.int16))
        uv.append(np.asarray(uvs, np.float32).reshape(-1, 3, 2))
        ef.append(np.asarray(flags, np.uint8).reshape(-1, 3))
        mate = np.asarray(mate, np.int64).reshape(-1)
        qm.append(np.where(mate >= 0, mate + t_at, -1))
        parts.append(info)
        v_at, t_at = info.v1, info.t1
    cat = (lambda xs, shape, dt: np.concatenate(xs).astype(dt) if xs else np.zeros(shape, dt))
    return EvalMesh(verts_local=cat(vl, (0, 3), np.float64), verts=cat(vw, (0, 3), np.float64),
                    tris=cat(tr, (0, 3), np.int32), part_id=cat(pid, (0,), np.int16),
                    uv=cat(uv, (0, 3, 2), np.float32), edge_flags=cat(ef, (0, 3), np.uint8),
                    quad_mate=cat(qm, (0,), np.int32), parts=parts, anchors=anchors, sockets=sockets,
                    relations=relations, source=source)


def _box_local(sx: float, sy: float, sz: float):
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    verts = np.array([[(-hx, hx)[k & 1], (-hy, hy)[(k >> 1) & 1], (-hz, hz)[(k >> 2) & 1]] for k in range(8)],
                     dtype=np.float64)
    tris, mate = quads_to_tris(BOX_QUADS)
    flags = np.tile(np.array([[EDGE_SHARP | EDGE_BEVEL, EDGE_SHARP | EDGE_BEVEL, 0],
                              [0, EDGE_SHARP | EDGE_BEVEL, EDGE_SHARP | EDGE_BEVEL]], np.uint8), (6, 1))
    uv = np.tile(np.stack([QUAD_UV[[0, 1, 2]], QUAD_UV[[0, 2, 3]]]), (6, 1, 1))
    return verts, tris, uv, flags, mate


def _box_anchors(name: str, M, sx: float, sy: float, sz: float) -> dict[str, Anchor]:
    """World top_c / bottom_c of a box part with an axis-aligned rotation."""
    out = {}
    for key, z, n in (("top_c", sz / 2.0, (0.0, 0.0, 1.0)), ("bottom_c", -sz / 2.0, (0.0, 0.0, -1.0))):
        p = fmath.apply_point(M, (0.0, 0.0, z))
        out[f"{name}:{key}"] = Anchor(p=p, n=fmath.apply_vec(M, n), t=fmath.apply_vec(M, (1.0, 0.0, 0.0)),
                                      attrs={"w": sx, "h": sy, "d": sz})
    return out


def fixture_boxes() -> EvalMesh:
    """base_C 0.4x0.4x0.1 on ground, post_C 0.1x0.1x0.5 on it, top_C 0.3x0.3x0.05 on that (face
    attach, bottom_c on top_c); anchors top_c/bottom_c (and ground:top_c); sockets
    {"top": {"ref": "top_C:top_c"}}. tests/fixtures/s0b/resolved_box3.json is its resolved spec."""
    sizes = {"base_C": (0.4, 0.4, 0.1), "post_C": (0.1, 0.1, 0.5), "top_C": (0.3, 0.3, 0.05)}
    parents = {"base_C": "ground", "post_C": "base_C", "top_C": "post_C"}
    deps = {"base_C": (), "post_C": ("base_C",), "top_C": ("base_C", "post_C")}
    anchors = {"ground:top_c": Anchor(p=(0.0, 0.0, 0.0), n=(0.0, 0.0, 1.0), t=(1.0, 0.0, 0.0))}
    local, z = [], 0.0
    for i, (name, (sx, sy, sz)) in enumerate(sizes.items()):
        M = fmath.translate((0.0, 0.0, z + sz / 2.0))
        parent = parents[name]
        p_other = (0.0, 0.0, 0.0) if parent == "ground" else (0.0, 0.0, sizes[parent][2] / 2.0)
        mates = [Mate(part=parent, kind="attach", self_anchor="bottom_c", other_anchor="top_c",
                      p_self=(0.0, 0.0, -sz / 2.0), p_other=p_other)]
        measures = {k: {"spec": v, "built": v} for k, v in (("extent_x", sx), ("extent_y", sy), ("extent_z", sz))}
        info = PartInfo(name=name, src=f"/parts/{i}", builder="box", v0=0, v1=0, t0=0, t1=0, matrix=M,
                        parent=parent, mates=mates, measures=measures, deps=deps[name])
        local.append((info, *_box_local(sx, sy, sz)))
        anchors.update(_box_anchors(name, M, sx, sy, sz))
        z += sz
    source = {"spec_id": "box3", "rev": 1, "seed": 0, "tables_version": "t-000000000000", "level": "build",
              "evaluator": "fixture_boxes", "kind": "assembly", "origin_offset": [0.0, 0.0, 0.0]}
    return assemble(local, anchors, {"top": {"ref": "top_C:top_c"}}, [], source)
