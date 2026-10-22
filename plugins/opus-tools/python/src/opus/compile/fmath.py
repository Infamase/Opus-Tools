"""Deterministic math for the compiler (docs/S0B_DESIGN.md §4.3, K3).

The same spec, seed and ``tables_version`` must hash identically on the host and inside
Blender on one machine. Blender ships numpy 2.3.4 and the host another version, and numpy's
transcendentals and BLAS change bits with the CPU dispatch path, so geometry code uses numpy
only for ``+ - * /``, ``sqrt``, ``abs``, ``floor``/``ceil``/``rint``, ``minimum``/``maximum``,
comparisons, indexing, sorting, integer ``bincount``/``cumsum`` and ``cross``. Matrices are
16-tuples of Python floats (row-major) applied with explicit sums, transcendentals and
non-integer powers go through ``math.*`` on scalars, and float reductions that feed geometry
go through :func:`fsum`. ``tests/test_import_rules.py`` enforces this with an AST walk.
"""

from __future__ import annotations

import functools
import hashlib
import math
import random
from collections.abc import Sequence

import numpy as np

IDENTITY16 = (1.0, 0.0, 0.0, 0.0,
              0.0, 1.0, 0.0, 0.0,
              0.0, 0.0, 1.0, 0.0,
              0.0, 0.0, 0.0, 1.0)

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_QUARTER = ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))  # (cos, sin) of k·90°, exact


def apply(M: Sequence[float], P) -> np.ndarray:
    """``M`` (16 floats, row-major) applied to points ``P`` (N,3) -> (N,3) float64, with the sums
    written out in a fixed order (no matmul): x' = ((M0·x + M1·y) + M2·z) + M3, and so on."""
    P = np.asarray(P, dtype=np.float64).reshape(-1, 3)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    out = np.empty_like(P)
    out[:, 0] = x * M[0] + y * M[1] + z * M[2] + M[3]
    out[:, 1] = x * M[4] + y * M[5] + z * M[6] + M[7]
    out[:, 2] = x * M[8] + y * M[9] + z * M[10] + M[11]
    return out


def apply_dir(M: Sequence[float], D) -> np.ndarray:
    """The rotation part of ``M`` applied to directions ``D`` (N,3) (no translation)."""
    D = np.asarray(D, dtype=np.float64).reshape(-1, 3)
    x, y, z = D[:, 0], D[:, 1], D[:, 2]
    out = np.empty_like(D)
    out[:, 0] = x * M[0] + y * M[1] + z * M[2]
    out[:, 1] = x * M[4] + y * M[5] + z * M[6]
    out[:, 2] = x * M[8] + y * M[9] + z * M[10]
    return out


def apply_point(M: Sequence[float], p: Sequence[float]) -> tuple[float, float, float]:
    """``M`` applied to one point, in pure Python floats (same summation order as :func:`apply`)."""
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    return (x * M[0] + y * M[1] + z * M[2] + M[3],
            x * M[4] + y * M[5] + z * M[6] + M[7],
            x * M[8] + y * M[9] + z * M[10] + M[11])


def apply_vec(M: Sequence[float], v: Sequence[float]) -> tuple[float, float, float]:
    """The rotation part of ``M`` applied to one direction, in pure Python floats."""
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return (x * M[0] + y * M[1] + z * M[2],
            x * M[4] + y * M[5] + z * M[6],
            x * M[8] + y * M[9] + z * M[10])


def compose(A: Sequence[float], B: Sequence[float]) -> tuple[float, ...]:
    """The 4x4 product A·B in pure Python floats, each entry summed in a fixed order:
    C[i][j] = ((A[i][0]·B[0][j] + A[i][1]·B[1][j]) + A[i][2]·B[2][j]) + A[i][3]·B[3][j]."""
    out = []
    for i in range(4):
        a0, a1, a2, a3 = (float(A[4 * i + k]) for k in range(4))
        for j in range(4):
            out.append(a0 * B[j] + a1 * B[4 + j] + a2 * B[8 + j] + a3 * B[12 + j])
    return tuple(float(v) for v in out)


def invert_rigid(M: Sequence[float]) -> tuple[float, ...]:
    """Inverse of a rigid matrix [R | t] (R orthonormal, proper or improper): [Rᵀ | -Rᵀ·t]."""
    r = [[float(M[4 * i + j]) for j in range(3)] for i in range(3)]
    t = (float(M[3]), float(M[7]), float(M[11]))
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    tt = [-(rt[i][0] * t[0] + rt[i][1] * t[1] + rt[i][2] * t[2]) for i in range(3)]
    return (rt[0][0], rt[0][1], rt[0][2], tt[0],
            rt[1][0], rt[1][1], rt[1][2], tt[1],
            rt[2][0], rt[2][1], rt[2][2], tt[2],
            0.0, 0.0, 0.0, 1.0)


def from_rt(R: Sequence[Sequence[float]], t: Sequence[float] = (0.0, 0.0, 0.0)) -> tuple[float, ...]:
    """A 16-tuple from a 3x3 rotation (rows) and a translation."""
    return (float(R[0][0]), float(R[0][1]), float(R[0][2]), float(t[0]),
            float(R[1][0]), float(R[1][1]), float(R[1][2]), float(t[1]),
            float(R[2][0]), float(R[2][1]), float(R[2][2]), float(t[2]),
            0.0, 0.0, 0.0, 1.0)


def from_columns(x: Sequence[float], y: Sequence[float], z: Sequence[float],
                 p: Sequence[float] = (0.0, 0.0, 0.0)) -> tuple[float, ...]:
    """A 16-tuple whose rotation columns are ``x``, ``y``, ``z`` and translation ``p`` (an
    anchor frame: x = t, y = n × t, z = n)."""
    return (float(x[0]), float(y[0]), float(z[0]), float(p[0]),
            float(x[1]), float(y[1]), float(z[1]), float(p[1]),
            float(x[2]), float(y[2]), float(z[2]), float(p[2]),
            0.0, 0.0, 0.0, 1.0)


def translation(M: Sequence[float]) -> tuple[float, float, float]:
    return (float(M[3]), float(M[7]), float(M[11]))


def with_translation(M: Sequence[float], t: Sequence[float]) -> tuple[float, ...]:
    """``M`` with its translation replaced by ``t``."""
    out = [float(v) for v in M]
    out[3], out[7], out[11] = float(t[0]), float(t[1]), float(t[2])
    return tuple(out)


def translate(t: Sequence[float]) -> tuple[float, ...]:
    return with_translation(IDENTITY16, t)


def _axis_vec(axis) -> tuple[float, float, float]:
    if isinstance(axis, str):
        word = axis.strip().lower()
        sign = -1.0 if word.startswith("-") else 1.0
        key = word.lstrip("+-")
        if key not in _AXES:
            raise ValueError(f"unknown axis {axis!r}; use x, y, z (optionally signed) or a 3-vector")
        return tuple(sign * c for c in _AXES[key])  # type: ignore[return-value]
    v = tuple(float(c) for c in axis)
    if len(v) != 3:
        raise ValueError(f"an axis is 3 numbers; got {axis!r}")
    return v  # type: ignore[return-value]


def _rodrigues(n: tuple[float, float, float], c: float, s: float) -> tuple[float, ...]:
    """R = c·I + s·[n]x + (1 - c)·n nᵀ for a unit axis n."""
    x, y, z = n
    k = 1.0 - c
    return (c + k * x * x, k * x * y - s * z, k * x * z + s * y, 0.0,
            k * y * x + s * z, c + k * y * y, k * y * z - s * x, 0.0,
            k * z * x - s * y, k * z * y + s * x, c + k * z * z, 0.0,
            0.0, 0.0, 0.0, 1.0)


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n == 0.0:
        raise ValueError("a rotation axis must not be zero")
    if n == 1.0:
        return v
    return (v[0] / n, v[1] / n, v[2] / n)


def rot_axis(axis, quarter_turns: int) -> tuple[float, ...]:
    """Rotation by ``quarter_turns`` × 90° counter-clockwise (right hand) about ``axis``: "x",
    "y", "z" (optionally signed, "-z") or a unit 3-vector. cos and sin are the exact values
    0 and ±1, so a world axis gives exact 0/±1 entries."""
    c, s = _QUARTER[int(quarter_turns) % 4]
    return _rodrigues(_unit(_axis_vec(axis)), c, s)


def rot_about(axis_vec, angle: float) -> tuple[float, ...]:
    """Rotation by ``angle`` radians counter-clockwise about ``axis_vec`` (math.cos/math.sin on
    scalars, Rodrigues' formula)."""
    return _rodrigues(_unit(_axis_vec(axis_vec)), math.cos(angle), math.sin(angle))


@functools.lru_cache(maxsize=256)
def _ring(K: int, n: float, phase: float) -> tuple[tuple[float, ...], tuple[float, ...]]:
    e = 2.0 / n
    cx, sy = [], []
    for k in range(K):
        th = 2.0 * math.pi * k / K + phase
        c, s = math.cos(th), math.sin(th)
        cx.append(math.copysign(math.pow(abs(c), e), c) if c != 0.0 else 0.0)
        sy.append(math.copysign(math.pow(abs(s), e), s) if s != 0.0 else 0.0)
    return tuple(cx), tuple(sy)


def ring_table(K: int, n: float, phase: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Superellipse ring: cx_k = sgn(cos θk)|cos θk|^(2/n), sy_k = sgn(sin θk)|sin θk|^(2/n),
    θk = 2πk/K + phase, computed with math.cos/math.sin/math.pow on scalars, cached. n = 2 is a
    circle, n = 1 a diamond, large n a box. Returns new arrays (the cache holds tuples)."""
    if K < 3:
        raise ValueError(f"a ring needs at least 3 segments; got {K}")
    if not n > 0:
        raise ValueError(f"a section exponent must be > 0; got {n}")
    cx, sy = _ring(int(K), float(n), float(phase))
    return np.array(cx, dtype=np.float64), np.array(sy, dtype=np.float64)


def spow(x, y):
    """Elementwise x**y via math.pow (scalars stay Python floats; arrays go through a list
    comprehension, meant for at most a few thousand values). A negative base with a non-integer
    exponent raises ValueError, as math.pow does."""
    if np.ndim(x) == 0 and np.ndim(y) == 0:
        return math.pow(float(x), float(y))
    xa, ya = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64))
    flat = [math.pow(a, b) for a, b in zip(xa.ravel().tolist(), ya.ravel().tolist())]
    return np.array(flat, dtype=np.float64).reshape(xa.shape)


def fsum(a) -> float:
    """math.fsum over a float64 array (exactly rounded, independent of summation order)."""
    return math.fsum(np.asarray(a, dtype=np.float64).ravel().tolist())


def seeded_uniform(seed: int, key: str, lo: float, hi: float) -> float:
    """A uniform sample in [lo, hi] from its own stream: random.Random seeded with the first 8
    bytes (little-endian) of sha256(f"{seed}:{key}"), so adding a dimension never moves another."""
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    r = random.Random(int.from_bytes(digest[:8], "little")).random()
    return float(lo) + (float(hi) - float(lo)) * r
