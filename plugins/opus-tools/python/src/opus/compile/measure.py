"""Sheet measures shared by builders and gates (docs/S0B_DESIGN.md §4.6).

Builders record measures and T1 re-measures them with the same functions, in the part's
canonical frame (§4.1), on ``verts_local`` and part-local triangles (indices from 0).

| Key | Definition |
|---|---|
| ``extent_x``, ``extent_y``, ``extent_z`` | ptp of the local coordinate |
| ``extent_u``, ``extent_v``, ``depth`` | extrude only: ``extent_x``, ``extent_y``, ``extent_z`` |
| ``radius_max`` | max √(x² + y²) |
| ``width_at:f``, ``thick_at:f`` | x-extent and y-extent of the section at height fraction f |
| ``circ_d:f`` | perimeter of the section's outer loop (largest perimeter) / π |

``PartInfo.measures[key] = {"spec": analytic value (None when there is none), "built":
measure(...)}``; builders assert |built − spec| ≤ ``tess_bound`` · |spec| (see there).
"""

from __future__ import annotations

import math
import re

import numpy as np

from opus.compile import fmath

MEASURE_RE = r"^(extent_[xyzuv]|depth|radius_max|(width_at|thick_at|circ_d):(0|1|0\.\d+))$"
_MEASURE = re.compile(MEASURE_RE)
_AXIS = {"extent_x": 0, "extent_y": 1, "extent_z": 2, "extent_u": 0, "extent_v": 1, "depth": 2}
ABS_FLOOR = 1e-12  # m: an absolute floor under every relative tessellation bound


def parse_key(key: str) -> tuple[str, float | None]:
    """"width_at:0.5" -> ("width_at", 0.5); "extent_x" -> ("extent_x", None). Raises ValueError."""
    m = _MEASURE.match(key)
    if not m:
        raise ValueError(f"unknown measure {key!r}; measures: extent_x|y|z|u|v, depth, radius_max, "
                         "width_at:f, thick_at:f, circ_d:f (f = 0, 1 or 0.<digits>)")
    if m.group(2):
        return m.group(2), float(m.group(3))
    return m.group(1), None


def split_part_measure(ref: str) -> tuple[str, str]:
    """A dim's ``measure`` "grip_C:circ_d:0.5" -> ("grip_C", "circ_d:0.5")."""
    part, sep, key = ref.partition(":")
    if not sep:
        raise ValueError(f"a dim's measure is <part>:<measure key>; got {ref!r}")
    parse_key(key)
    return part, key


def _plane_z(verts: np.ndarray, f: float) -> float:
    z0, z1 = float(verts[:, 2].min()), float(verts[:, 2].max())
    return z0 + f * (z1 - z0)


def section(verts_local, tris_local, f: float) -> list[np.ndarray]:
    """Closed loops (each (N,3), not repeating its first point) where the plane z = z0 + f·(z1 − z0)
    cuts the mesh, z0 and z1 being the part's min and max z. A vertex on the plane counts as
    below it for f ≤ 0.5 and above it for f > 0.5, so the end caps (f = 0, f = 1) and station rings
    lying exactly in the plane give their own ring; a crossing at a vertex is that vertex exactly."""
    V = np.asarray(verts_local, dtype=np.float64)
    T = np.asarray(tris_local, dtype=np.int64).reshape(-1, 3)
    if len(V) == 0 or len(T) == 0:
        return []
    z = _plane_z(V, f)
    above = V[:, 2] > z if f <= 0.5 else V[:, 2] >= z
    # directed edges of each triangle; a crossing edge has one endpoint above, one below
    e_a = T.reshape(-1)
    e_b = T[:, [1, 2, 0]].reshape(-1)
    cross = above[e_a] != above[e_b]
    if not cross.any():
        return []
    lo, hi = np.minimum(e_a, e_b), np.maximum(e_a, e_b)
    keys = lo * len(V) + hi
    # per triangle: the two crossing edges form one segment
    cross_t = cross.reshape(-1, 3)
    keys_t = keys.reshape(-1, 3)
    segs = [tuple(int(k) for k in keys_t[i][cross_t[i]]) for i in np.nonzero(cross_t.any(axis=1))[0]]
    point: dict[int, tuple[float, float, float]] = {}
    for k in sorted({k for s in segs for k in s}):
        a, b = divmod(k, len(V))
        za, zb = V[a, 2], V[b, 2]
        if za == z:
            p = V[a]
        elif zb == z:
            p = V[b]
        else:
            t = (z - za) / (zb - za)
            p = V[a] + t * (V[b] - V[a])
        point[k] = (float(p[0]), float(p[1]), float(z))
    nbr: dict[int, list[int]] = {}
    for a, b in segs:
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    seen: set[int] = set()
    loops = []
    for start in sorted(nbr):
        if start in seen:
            continue
        chain = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxt = [n for n in nbr[cur] if n != prev and n not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            chain.append(cur)
            seen.add(cur)
        pts = [point[k] for k in chain]
        dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        if len(dedup) > 1 and dedup[-1] == dedup[0]:
            dedup.pop()
        loops.append(np.array(dedup, dtype=np.float64))
    return loops


def perimeter(loop: np.ndarray) -> float:
    """Closed-loop perimeter (sqrt per segment, fsum)."""
    if len(loop) < 2:
        return 0.0
    d = np.roll(loop, -1, axis=0) - loop
    return fmath.fsum(np.sqrt(d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1] + d[:, 2] * d[:, 2]))


def measure(verts_local, tris_local, key: str) -> float:
    """One sheet measure of a part (see the module table). NaN when a section is empty."""
    name, f = parse_key(key)
    V = np.asarray(verts_local, dtype=np.float64).reshape(-1, 3)
    if len(V) == 0:
        return math.nan
    if name in _AXIS:
        c = V[:, _AXIS[name]]
        return float(c.max() - c.min())
    if name == "radius_max":
        return float(np.sqrt(V[:, 0] * V[:, 0] + V[:, 1] * V[:, 1]).max())
    loops = section(V, tris_local, f)
    if not loops:
        return math.nan
    if name == "circ_d":
        return max(perimeter(lp) for lp in loops) / math.pi
    pts = np.concatenate(loops)
    c = pts[:, 0] if name == "width_at" else pts[:, 1]
    return float(c.max() - c.min())


def tess_bound(key: str, builder: str, params: dict, K: int) -> float:
    """Allowed |built − spec| from tessellation, as a fraction of |spec| (callers add ABS_FLOOR):
    1e-9 for extents, ``radius_max`` and for widths at stations; for ``circ_d`` the inscribed
    K-gon's deficit 1 − K·sin(π/K)/π (+1e-9); for ``width_at``/``thick_at`` between stations the
    builder's linear-interpolation bound, passed as ``params["interp_rel"]`` (``params["stations"]``
    lists the station fractions; a measure at a station needs no bound)."""
    name, f = parse_key(key)
    if name == "circ_d":
        if K < 3:
            raise ValueError(f"circ_d needs K >= 3 ring segments; got {K}")
        return 1.0 - K * math.sin(math.pi / K) / math.pi + 1e-9
    if name in ("width_at", "thick_at"):
        stations = params.get("stations")
        if stations is None or any(abs(float(s) - f) <= 1e-12 for s in stations):
            return 1e-9
        if "interp_rel" not in params:
            raise ValueError(f"{key} on a {builder} lies between stations: pass params['interp_rel'], the "
                             "linear-interpolation bound of that interval")
        return float(params["interp_rel"]) + 1e-9
    return 1e-9


def within_tess(key: str, builder: str, params: dict, K: int, spec: float, built: float) -> bool:
    """|built − spec| ≤ tess_bound · |spec| + ABS_FLOOR (False for a NaN)."""
    if spec is None or not (math.isfinite(spec) and math.isfinite(built)):
        return False
    return abs(built - spec) <= tess_bound(key, builder, params, K) * abs(spec) + ABS_FLOOR
