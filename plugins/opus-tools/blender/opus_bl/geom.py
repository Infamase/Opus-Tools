"""Signed distance and penetration for triangle meshes.

Signed distance is negative inside. A BVH finds the nearest triangle; the closest point is
then recomputed in double precision on that triangle, which also says which feature it lies
on: a vertex, an edge or the face interior. The sign is the side of that feature's
angle-weighted pseudonormal (Baerentzen & Aanaes 2005), exact for closed, consistently
oriented meshes; the face normal alone flips near sharp edges and for points in the plane of
a face. Loose parts that are open or non-manifold use the generalized winding number
instead (Jacobson et al. 2013). Loose parts are a union: a point inside any of them is inside.

Penetration between two parts is BVH triangle overlap plus a depth: how far each surface
reaches into the other part and, for a thin part (plate, blade, shell), how far the other
part went past the plate's sheets. A body pushed right through a plate has no vertex inside
it, so the closest-point sign alone reads it as outside.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

# the feature of triangle (a, b, c) a closest point lies on
FACE, VA, VB, VC, EAB, EBC, ECA = range(7)
CORNERS = ((VA, 0), (VB, 1), (VC, 2))
EDGES = ((EAB, 0), (EBC, 1), (ECA, 2))


def world_triangles(obj) -> tuple[np.ndarray, np.ndarray]:
    """Evaluated world-space vertices (N x 3) and Blender's own triangulation (M x 3)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tris)
    ev.to_mesh_clear()
    m = np.array(obj.matrix_world)
    tris = tris.reshape(-1, 3).astype(np.int64)
    if np.linalg.det(m[:3, :3]) < 0:  # mirrored: keep faces turned outward in world space
        tris = tris[:, ::-1]
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3], tris


def _dot(u, v):
    return np.einsum("...i,...i->...", u, v)


def _norm(v):
    return np.sqrt(_dot(v, v))


def _labels(n: int, edges: np.ndarray) -> np.ndarray:
    """Connected-component label (0, 1, ...) of each of ``n`` nodes joined by ``edges``."""
    lab = np.arange(n)
    while len(edges):
        m = np.minimum(lab[edges[:, 0]], lab[edges[:, 1]])
        new = lab.copy()
        np.minimum.at(new, edges[:, 0], m)
        np.minimum.at(new, edges[:, 1], m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    return np.unique(lab, return_inverse=True)[1].reshape(-1)


def closest_on_triangles(p, a, b, c):
    """Closest points on triangles (a, b, c) to points ``p`` (all K x 3) and the feature each
    lies on (Ericson, Real-Time Collision Detection, 5.1.5)."""
    ab, ac = b - a, c - a
    ap, bp, cp = p - a, p - b, p - c
    d1, d2, d3, d4, d5, d6 = _dot(ab, ap), _dot(ac, ap), _dot(ab, bp), _dot(ac, bp), _dot(ab, cp), _dot(ac, cp)
    vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
    feat = np.select(
        [(d1 <= 0) & (d2 <= 0), (d3 >= 0) & (d4 <= d3), (vc <= 0) & (d1 >= 0) & (d3 <= 0),
         (d6 >= 0) & (d5 <= d6), (vb <= 0) & (d2 >= 0) & (d6 <= 0), (va <= 0) & (d4 >= d3) & (d5 >= d6)],
        [VA, VB, EAB, VC, ECA, EBC], FACE)
    with np.errstate(divide="ignore", invalid="ignore"):
        den = 1.0 / (va + vb + vc)
        q = a + ab * (vb * den)[:, None] + ac * (vc * den)[:, None]
        for f, t, o, e in ((EAB, d1 / (d1 - d3), a, ab), (ECA, d2 / (d2 - d6), a, ac),
                           (EBC, (d4 - d3) / ((d4 - d3) + (d5 - d6)), b, c - b)):
            m = feat == f
            q[m] = o[m] + e[m] * t[m, None]
    for f, pt in ((VA, a), (VB, b), (VC, c)):
        m = feat == f
        q[m] = pt[m]
    return q, feat


def _closest1(p, a, b, c):
    """closest_on_triangles for one point, in plain floats (faster than numpy for one)."""
    abx, aby, abz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    acx, acy, acz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    x, y, z = p[0] - a[0], p[1] - a[1], p[2] - a[2]
    d1, d2 = abx * x + aby * y + abz * z, acx * x + acy * y + acz * z
    if d1 <= 0 and d2 <= 0:
        return a, VA
    x, y, z = p[0] - b[0], p[1] - b[1], p[2] - b[2]
    d3, d4 = abx * x + aby * y + abz * z, acx * x + acy * y + acz * z
    if d3 >= 0 and d4 <= d3:
        return b, VB
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        t = d1 / (d1 - d3)
        return (a[0] + abx * t, a[1] + aby * t, a[2] + abz * t), EAB
    x, y, z = p[0] - c[0], p[1] - c[1], p[2] - c[2]
    d5, d6 = abx * x + aby * y + abz * z, acx * x + acy * y + acz * z
    if d6 >= 0 and d5 <= d6:
        return c, VC
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        t = d2 / (d2 - d6)
        return (a[0] + acx * t, a[1] + acy * t, a[2] + acz * t), ECA
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 >= d3 and d5 >= d6:
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return (b[0] + (c[0] - b[0]) * t, b[1] + (c[1] - b[1]) * t, b[2] + (c[2] - b[2]) * t), EBC
    den = 1.0 / (va + vb + vc)
    v, w = vb * den, vc * den
    return (a[0] + abx * v + acx * w, a[1] + aby * v + acy * w, a[2] + abz * v + acz * w), FACE


class Solid:
    """A triangle mesh, possibly in several loose parts, with exact closest points and an
    inside/outside sign that holds at edges and corners.

    ``groups`` (per vertex, e.g. the object index) keeps coincident vertices of different
    objects apart; ``flags`` (per vertex) marks vertices for callers (``tflag`` marks the
    triangles that use one)."""

    def __init__(self, co, tris, groups=None, flags=None):
        co = np.asarray(co, dtype=float).reshape(-1, 3)
        tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
        span = float(np.ptp(co, axis=0).max()) if len(co) else 1.0
        self.size = max(span, 1e-9)
        q = self.size * 1e-9
        # weld coincident vertices: importers split them at UV seams and hard edges
        key = np.round(co / q).astype(np.int64)
        if groups is not None:
            key = np.column_stack([key, np.asarray(groups, dtype=np.int64)])
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        V, T = co[first], inv[tris]
        self.vflag = np.zeros(len(V), bool)
        if flags is not None:
            np.logical_or.at(self.vflag, inv, np.asarray(flags, bool))
        cr = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        area2 = _norm(cr)
        keep = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 2] != T[:, 0]) & (area2 > 1e-14 * self.size**2)
        T, cr, area2 = T[keep], cr[keep], area2[keep]
        if not len(T):
            raise ValueError("no triangles")
        # loose parts, with their triangles stored together
        vlab = _labels(len(V), np.concatenate([T[:, :2], T[:, 1:], T[:, ::2]]))
        tcomp = np.unique(vlab[T[:, 0]], return_inverse=True)[1].reshape(-1)
        order = np.argsort(tcomp, kind="stable")
        T, cr, area2, tcomp = T[order], cr[order], area2[order], tcomp[order]
        self.ncomp = int(tcomp[-1]) + 1
        self.start = np.searchsorted(tcomp, np.arange(self.ncomp + 1))
        # a part whose faces all point inward (negative volume) is turned outward
        cen = V[T].mean(axis=1)
        c0 = np.add.reduceat(cen, self.start[:-1]) / np.diff(self.start)[:, None]
        rel = V[T] - c0[tcomp, None]
        vol = np.bincount(tcomp, weights=_dot(rel[:, 0], np.cross(rel[:, 1], rel[:, 2])), minlength=self.ncomp)
        inward = (vol < 0)[tcomp]
        T[inward] = T[inward][:, ::-1]
        cr[inward] = -cr[inward]
        self.V, self.T, self.tcomp = V, T, tcomp
        self.FN = cr / area2[:, None]
        self.area = area2 / 2
        a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
        # angle-weighted vertex pseudonormals
        VN = np.zeros_like(V)
        for k, (u, v, w) in enumerate(((a, b, c), (b, c, a), (c, a, b))):
            e1, e2 = v - u, w - u
            np.add.at(VN, T[:, k], self.FN * np.arctan2(_norm(np.cross(e1, e2)), _dot(e1, e2))[:, None])
        self.VN = VN / np.maximum(_norm(VN), 1e-300)[:, None]
        # edges ab, bc, ca of each triangle; an edge is good when exactly two triangles use
        # it, in opposite directions (closed and consistently oriented there)
        E = np.stack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], axis=1)
        ekey, eid = np.unique((E.min(axis=2) * len(V) + E.max(axis=2)).reshape(-1), return_inverse=True)
        self.eid = eid.reshape(-1, 3)
        self.edges = np.column_stack([ekey // len(V), ekey % len(V)])
        cnt = np.bincount(eid, minlength=len(ekey))
        turn = np.bincount(eid, weights=np.where(E[:, :, 0] < E[:, :, 1], 1.0, -1.0).reshape(-1), minlength=len(ekey))
        self.good = (cnt == 2) & (turn == 0)
        EN = np.zeros((len(ekey), 3))
        np.add.at(EN, eid, np.repeat(self.FN, 3, axis=0))
        self.EN = EN / np.maximum(_norm(EN), 1e-300)[:, None]
        bad = ~self.good[self.eid]
        self.open = np.zeros(self.ncomp, bool)
        np.logical_or.at(self.open, tcomp, bad.any(axis=1))
        self.vedge = np.zeros(len(V), bool)  # vertex on an open or non-manifold edge
        for k, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
            self.vedge[T[bad[:, k], i]] = True
            self.vedge[T[bad[:, k], j]] = True
        self.tflag = self.vflag[T].any(axis=1)
        tmin, tmax = np.minimum(np.minimum(a, b), c), np.maximum(np.maximum(a, b), c)
        self.lo = np.minimum.reduceat(tmin, self.start[:-1])
        self.hi = np.maximum.reduceat(tmax, self.start[:-1])
        self.box = (self.lo.min(axis=0), self.hi.max(axis=0))
        # loose parts whose boxes meet another's: a point may be inside one while another's
        # surface is nearer
        self.pad = pad = q * 10
        self.shared = []
        for i in range(0, self.ncomp if self.ncomp > 1 else 0, 256):
            meet = np.all((self.lo[i : i + 256, None] <= self.hi[None] + pad) & (self.hi[i : i + 256, None] + pad >= self.lo[None]), axis=2)
            meet[np.arange(len(meet)), np.arange(i, i + len(meet))] = False
            self.shared += [i + int(k) for k in np.nonzero(meet.any(axis=1))[0]]
        self._shared1 = [(j, tuple(self.lo[j] - pad), tuple(self.hi[j] + pad)) for j in self.shared]
        self.bvh = BVHTree.FromPolygons(V.tolist(), T.tolist(), all_triangles=True)
        self._tcomp1, self._open1 = tcomp.tolist(), self.open.tolist()
        self._cbvh, self._tri1, self._shell = {}, {}, False

    @classmethod
    def from_objects(cls, objs, flags=None) -> Solid | None:
        """Solid of the mesh objects in ``objs`` (world space, modifiers applied); None if
        they have no faces. ``flags``: {object: per-vertex bools}."""
        cos, tris, groups, fl, n = [], [], [], [], 0
        for i, o in enumerate(objs):
            if o.type != "MESH":
                continue
            co, t = world_triangles(o)
            if not len(t):
                continue
            cos.append(co)
            tris.append(t + n)
            groups.append(np.full(len(co), i))
            f = (flags or {}).get(o)
            fl.append(np.zeros(len(co), bool) if f is None or len(f) != len(co) else np.asarray(f, bool))
            n += len(co)
        if not tris:
            return None
        return cls(np.concatenate(cos), np.concatenate(tris), np.concatenate(groups), np.concatenate(fl))

    # ------------------------------------------------------------ queries

    def _comp_bvh(self, j: int):
        """BVH of loose part ``j`` alone, and the index of its first triangle."""
        if j not in self._cbvh:
            s, e = self.start[j], self.start[j + 1]
            used, local = np.unique(self.T[s:e], return_inverse=True)
            self._cbvh[j] = (BVHTree.FromPolygons(self.V[used].tolist(), local.reshape(-1, 3).tolist(), all_triangles=True), s)
        return self._cbvh[j]

    def _nearest(self, pts, bvh=None, base: int = 0):
        """Distance, closest point, triangle and feature for each point."""
        bvh = bvh or self.bvh
        t = np.array([bvh.find_nearest(p)[2] for p in pts.tolist()], dtype=np.int64) + base
        T = self.T[t]
        q, f = closest_on_triangles(pts, self.V[T[:, 0]], self.V[T[:, 1]], self.V[T[:, 2]])
        return _norm(pts - q), q, t, f

    def pseudonormal(self, t, f):
        """Pseudonormal of feature ``f`` of triangles ``t``: face normal, the sum of the two
        face normals at an edge, the angle-weighted sum around a vertex."""
        n = self.FN[t].copy()
        for code, k in CORNERS:
            m = f == code
            n[m] = self.VN[self.T[t[m], k]]
        for code, k in EDGES:
            m = f == code
            n[m] = self.EN[self.eid[t[m], k]]
        return n

    def _inside(self, pts, q, t, f):
        inside = _dot(pts - q, self.pseudonormal(t, f)) < 0
        comp = self.tcomp[t]
        for j in np.unique(comp[self.open[comp]]):
            m = comp == j
            # outside a part's box its winding number stays within +-1/2: no need to sum it
            box = np.all((pts[m] >= self.lo[j]) & (pts[m] <= self.hi[j]), axis=1)
            w = np.zeros(int(m.sum()))
            w[box] = self.winding(pts[m][box], j)
            inside[m] = w > 0.5
        return inside

    def signed(self, pts, tri: bool = False):
        """Signed distances (negative inside) of points (K x 3); with ``tri``, also the
        nearest triangle of each."""
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        if not len(pts):
            return (np.empty(0), np.empty(0, np.int64)) if tri else np.empty(0)
        d, q, t, f = self._nearest(pts)
        out = np.where(self._inside(pts, q, t, f), -d, d)
        comp = self.tcomp[t]
        for j in self.shared:  # inside another loose part than the nearest one
            m = np.all((pts >= self.lo[j] - self.pad) & (pts <= self.hi[j] + self.pad), axis=1) & (comp != j)
            if m.any():
                bvh, s = self._comp_bvh(j)
                dj, qj, tj, fj = self._nearest(pts[m], bvh, s)
                sj = np.where(self._inside(pts[m], qj, tj, fj), -dj, dj)
                out[m] = np.where(sj < 0, np.minimum(np.minimum(out[m], 0.0), sj), out[m])
        return (out, t) if tri else out

    def _one(self, p, t: int):
        c = self._tri1.get(t)
        if c is None:
            T, eid = self.T[t], self.eid[t]
            pn = [self.FN[t], *self.VN[T], *self.EN[eid]]  # FACE, VA, VB, VC, EAB, EBC, ECA
            c = self._tri1[t] = (*(tuple(v) for v in self.V[T].tolist()), [tuple(n) for n in np.asarray(pn).tolist()])
        q, f = _closest1(p, c[0], c[1], c[2])
        x, y, z = p[0] - q[0], p[1] - q[1], p[2] - q[2]
        d = math.sqrt(x * x + y * y + z * z)
        j = self._tcomp1[t]
        if self._open1[j]:
            lo, hi = self.lo[j], self.hi[j]
            if not (lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] and lo[2] <= p[2] <= hi[2]):
                return d, False, j
            return d, bool(self.winding(np.array([p]), j)[0] > 0.5), j
        n = c[3][f]
        return d, x * n[0] + y * n[1] + z * n[2] < 0, j

    def signed1(self, p) -> float:
        """signed() for one point (a Vector or 3 numbers); quick, for solver inner loops."""
        p = (float(p[0]), float(p[1]), float(p[2]))
        d, inside, j = self._one(p, self.bvh.find_nearest(p)[2])
        out = -d if inside else d
        for k, lo, hi in self._shared1:
            if k != j and lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] and lo[2] <= p[2] <= hi[2]:
                bvh, s = self._comp_bvh(k)
                dk, ink, _ = self._one(p, bvh.find_nearest(p)[2] + s)
                if ink:
                    out = min(out, 0.0, -dk)
        return out

    def winding(self, pts, j: int | None = None) -> np.ndarray:
        """Generalized winding number of loose part ``j`` (all parts if None) at points:
        about 1 inside a closed part, 0 outside, in between near holes."""
        T = self.T if j is None else self.T[self.start[j] : self.start[j + 1]]
        A, B, C = self.V[T[:, 0]], self.V[T[:, 1]], self.V[T[:, 2]]
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        out = np.zeros(len(pts))
        step = max(1, 200_000 // len(T))
        for i in range(0, len(pts), step):
            p = pts[i : i + step, None]
            a, b, c = A - p, B - p, C - p
            la, lb, lc = _norm(a), _norm(b), _norm(c)
            den = la * lb * lc + _dot(a, b) * lc + _dot(b, c) * la + _dot(c, a) * lb
            out[i : i + step] = np.arctan2(_dot(a, np.cross(b, c)), den).sum(axis=1) / (2 * np.pi)
        return out

    def facing(self, pts):
        """For an open sheet: signed distance by the pseudonormal (negative behind the sheet),
        and whether the closest point lies within the sheet rather than on its border."""
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        d, q, t, f = self._nearest(pts)
        s = np.where(_dot(pts - q, self.pseudonormal(t, f)) < 0, -d, d)
        within = np.ones(len(pts), bool)
        for code, k in CORNERS:
            m = f == code
            within[m] = ~self.vedge[self.T[t[m], k]]
        for code, k in EDGES:
            m = f == code
            within[m] = self.good[self.eid[t[m], k]]
        return s, within

    def shell(self) -> dict | None:
        """A thin part's wall thickness and sheets (the surfaces either side of the wall, as
        open meshes); None for a solid part. Measured by casting a ray inward from every
        triangle to the opposite wall."""
        if self._shell is not False:
            return self._shell
        self._shell = None
        cen = self.V[self.T].mean(axis=1)
        off = self.size * 1e-6
        h = np.full(len(self.T), np.inf)
        for i, (o, n) in enumerate(zip((cen - self.FN * off).tolist(), (-self.FN).tolist())):
            loc, nh, _, dist = self.bvh.ray_cast(o, n)
            if loc is not None and nh.dot(n) > 0.5:  # the opposite wall faces back
                h[i] = dist + off
        ok = np.isfinite(h) & ~self.open[self.tcomp]
        total = self.area.sum()
        if self.area[ok].sum() < 0.5 * total:
            return None
        o = np.argsort(h[ok])
        cum = np.cumsum(self.area[ok][o])
        thick = float(h[ok][o][np.searchsorted(cum, cum[-1] / 2)])
        if thick > 0.2 * math.sqrt(total / 2):
            return None
        sheet = ok & (h <= 2.5 * thick)
        # sheets: sheet triangles joined across the good edges they share
        te, ee = np.repeat(np.arange(len(self.T)), 3), self.eid.reshape(-1)
        o = np.argsort(ee, kind="stable")
        te, ee = te[o], ee[o]
        same = ee[1:] == ee[:-1]
        pa, pb, e = te[:-1][same], te[1:][same], ee[:-1][same]
        link = sheet[pa] & sheet[pb] & self.good[e]
        lab = _labels(len(self.T), np.column_stack([pa[link], pb[link]]))
        sides = []
        sheet_area = self.area[sheet].sum()
        for g in np.unique(lab[sheet]):
            m = sheet & (lab == g)
            if self.area[m].sum() >= 0.1 * sheet_area:
                sides.append(Solid(self.V, self.T[m]))
        self._shell = {"thickness": thick, "sides": sides} if sides else None
        return self._shell


# ---------------------------------------------------------------- penetration

def _segment_hits(p0, p1, a, b, c):
    """Where segments p0-p1 pierce triangles (a, b, c) (Moller-Trumbore); points and a mask."""
    d, e1, e2 = p1 - p0, b - a, c - a
    h = np.cross(d, e2)
    det = _dot(e1, h)
    ok = np.abs(det) > 1e-9 * _norm(d) * _norm(e1) * _norm(e2)
    f = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = p0 - a
    qv = np.cross(s, e1)
    u, v, t = f * _dot(s, h), f * _dot(d, qv), f * _dot(e2, qv)
    ok &= (u >= 0) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= 1)
    return p0 + d * t[:, None], ok


def crossings(a: Solid, b: Solid, pairs: np.ndarray) -> np.ndarray:
    """Points on the curve where the surfaces of ``a`` and ``b`` cross: every edge of one
    triangle of an overlapping pair that pierces the other."""
    if not len(pairs):
        return np.empty((0, 3))
    PA, PB = a.V[a.T[pairs[:, 0]]], b.V[b.T[pairs[:, 1]]]
    out = []
    for P, Q in ((PA, PB), (PB, PA)):
        for i, j in ((0, 1), (1, 2), (2, 0)):
            x, ok = _segment_hits(P[:, i], P[:, j], Q[:, 0], Q[:, 1], Q[:, 2])
            out.append(x[ok])
    return np.concatenate(out)


def _samples(s: Solid, tris, lo, hi, h: float, limit: int = 20000) -> np.ndarray:
    """Points spread over triangles ``tris`` of ``s`` about ``h`` apart, within a box."""
    P = s.V[s.T[np.asarray(tris, dtype=np.int64)]]
    if not len(P):
        return np.empty((0, 3))
    L = np.max(_norm(P - np.roll(P, 1, axis=1)), axis=1)
    n = np.clip(np.ceil(L / max(h, 1e-12)), 3, 24).astype(int)
    out = []
    for k in np.unique(n):
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1))
        m = i + j <= k
        u, v = i[m] / k, j[m] / k
        W = np.stack([1 - u - v, u, v], axis=1)  # barycentric weights
        out.append(np.einsum("wk,tkd->twd", W, P[n == k]).reshape(-1, 3))
    pts = np.concatenate(out)
    pts = pts[np.all((pts >= lo) & (pts <= hi), axis=1)]
    return pts[:: len(pts) // limit + 1]


def _past_sheet(side: Solid, other: Solid, cand: np.ndarray, seeds: np.ndarray) -> float:
    """How far ``other`` reaches behind a plate's sheet, within the sheet's outline,
    counting only vertices joined (through vertices also behind it) to where the surfaces
    cross. Skin wrapped around the plate's rim does not count."""
    idx = np.nonzero(cand)[0]
    if not len(idx):
        return 0.0
    s, within = side.facing(other.V[idx])
    behind = np.zeros(len(other.V), bool)
    behind[idx] = within & (s < 0)
    depth = np.zeros(len(other.V))
    depth[idx] = np.where(behind[idx], -s, 0.0)
    reach = seeds & behind
    e0, e1 = other.edges[:, 0], other.edges[:, 1]
    while True:
        g0, g1 = reach[e1] & behind[e0] & ~reach[e0], reach[e0] & behind[e1] & ~reach[e1]
        if not (g0.any() or g1.any()):
            break
        reach[e0[g0]] = True
        reach[e1[g1]] = True
    return float(depth[reach].max()) if reach.any() else 0.0


def penetration(a: Solid, b: Solid, skip_b: bool = False) -> dict | None:
    """How ``a`` and ``b`` interpenetrate, or None when their surfaces don't cross and
    neither holds a vertex of the other.

    Returns {"triangles": overlapping triangle pairs, "depth": m, "at": point, "points":
    crossing points, "kind": "crossing" | "embedded" | "through"}, "inside" ("a" or "b") for
    an embedded part, and, when a thin part is involved, "thin" ("a" or "b"), "thickness" and
    "sheet" (how far the other part went past the plate's sheets, toward whichever side is
    shallower). Faces that merely touch give a depth near 0; the caller decides the
    tolerance. ``skip_b`` leaves out ``b``'s flagged vertices and the triangles that use them
    (a hand that should touch, measured elsewhere).
    """
    if np.any(a.box[0] > b.box[1]) or np.any(b.box[0] > a.box[1]):
        return None
    pairs = np.array(a.bvh.overlap(b.bvh), dtype=np.int64).reshape(-1, 2)
    if skip_b and len(pairs):
        pairs = pairs[~b.tflag[pairs[:, 1]]]
    # vertices of one part inside the other
    ma = np.all((a.V >= b.box[0]) & (a.V <= b.box[1]), axis=1)
    sa, ta = b.signed(a.V[ma], tri=True)
    if skip_b:
        sa = np.where(b.tflag[ta], 0.0, sa)
    mb = np.all((b.V >= a.box[0]) & (b.V <= a.box[1]), axis=1)
    if skip_b:
        mb &= ~b.vflag
    sb = a.signed(b.V[mb])
    deep = np.concatenate([a.V[ma][sa < 0], b.V[mb][sb < 0]])
    if not len(pairs) and not len(deep):
        return None
    pts = crossings(a, b, pairs)
    if not len(pts) and len(pairs):  # faces lying in one plane
        pts = np.concatenate([a.V[a.T[pairs[:, 0]]].mean(axis=1), b.V[b.T[pairs[:, 1]]].mean(axis=1)])
    ref = pts if len(pts) else deep
    lo, hi = ref.min(axis=0), ref.max(axis=0)
    diag = float(_norm(hi - lo))
    pad = diag + max(a.size, b.size) * 1e-6
    lo, hi = lo - pad, hi + pad
    depth = max(0.0, -float(sa.min(initial=0.0)), -float(sb.min(initial=0.0)))
    # how far each surface reaches into the other near the crossing
    if len(pairs):
        h = max(diag, pad) / 8
        s, t = b.signed(_samples(a, np.unique(pairs[:, 0]), lo, hi, h), tri=True)
        if skip_b:
            s = s[~b.tflag[t]]
        depth = max(depth, -float(s.min(initial=0.0)))
        depth = max(depth, -float(a.signed(_samples(b, np.unique(pairs[:, 1]), lo, hi, h)).min(initial=0.0)))
    out = {"triangles": int(len(pairs)), "at": ref.mean(axis=0), "points": pts,
           "kind": "crossing" if len(pairs) else "embedded"}
    if not len(pairs):  # surfaces don't cross, so one part is wholly inside the other
        out["inside"] = "a" if (sa < 0).any() else "b"
    # a thin part: how far the other part went past the plate, to its shallower side
    for name, x, y, ytris in (("a", a, b, pairs[:, 1]), ("b", b, a, pairs[:, 0])):
        sh = x.shell() if len(pairs) else None
        if sh is None:
            continue
        reach = max(diag * 4, y.size * 0.25)
        cand = np.all((y.V >= x.box[0] - reach) & (y.V <= x.box[1] + reach), axis=1)
        if skip_b and y is b:
            cand &= ~b.vflag
        seeds = np.zeros(len(y.V), bool)
        seeds[y.T[ytris].reshape(-1)] = True
        past = min(_past_sheet(side, y, cand, seeds) for side in sh["sides"])
        if past > out.get("sheet", -1.0):
            out.update(thin=name, thickness=sh["thickness"], sheet=past)
            if past > sh["thickness"]:
                out["kind"] = "through"
        depth = max(depth, past)
    out["depth"] = depth
    return out
