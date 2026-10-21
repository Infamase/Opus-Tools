"""Hands that hold things.

- ``define``: a grip on an object (handle axis, the side the palm goes, the end the thumb
  points to, style). Saved as an empty named ``SOCKET_grip_<name>`` parented to the object;
  Unreal's FBX import turns ``SOCKET_`` empties into static mesh sockets, and glTF keeps it
  as a node for Godot and Unity.
- ``hold``: put the object in a rigged hand. The handle goes against the palm surface
  (found by ray casting the skinned hand mesh), then the fingers close the way a hand does:
  all joints of a finger close together, a joint stops once a segment it moves touches the
  object, the joints past it keep wrapping. The thumb wraps around the other way. Adds a
  ``weapon_r``/``weapon_l`` bone at the object's origin, parents the object to it, and keys
  the pose as a ``Grip_*`` action. Optional arm placement for first-person views.
- ``check``: measure any hand holding anything: how deep the palm and each finger sink into
  the object or how far they float off it, and where the object cuts into the body, with
  contact-colored close-ups. Signed distances come from ``geom`` (right at edges and
  corners); body clipping also tests the surfaces for crossing, which a plate or blade
  through the forearm needs.
"""

from __future__ import annotations

import json
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

from opus_bl import assets, geom
from opus_bl.inspect3d import _world_mesh, aim_direction
from opus_bl.lookdev import _camera, _render_settings, _workbench

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
SIDE_WORDS = {"l": ("l", "left"), "r": ("r", "right")}
# coupled closing speeds and limits (degrees) per joint: knuckle, middle, tip
CLOSE_RATIO = {"default": (1.0, 1.1, 0.8)}
CLOSE_LIMIT = {"default": (90.0, 105.0, 80.0)}
SKIN, BODY, INSIDE, TOUCH, HELD = (0.86, 0.72, 0.62), (0.62, 0.58, 0.55), (0.92, 0.16, 0.12), (0.22, 0.8, 0.32), (0.45, 0.56, 0.72)
REF_PALM = 0.094  # palm length (wrist to knuckles) of a 1.8 m adult, meters
WEAPON_BONES = ("weapon_r", "weapon_l")  # the bones hold() adds for what a hand holds


# ---------------------------------------------------------------- rig discovery

def _norm(name: str) -> str:
    n = "".join(ch for ch in name.lower() if ch.isalnum())
    for prefix in ("mixamorig", "def", "org"):
        if n.startswith(prefix) and len(n) > len(prefix) + 3:
            n = n[len(prefix):]
    return n


def _finger_names(finger: str, i: int, side: str) -> list[str]:
    s, word = SIDE_WORDS[side]
    seg = ("metacarpal", "proximal", "distal") if finger == "thumb" else ("proximal", "intermediate", "distal")  # Godot
    names = [f"{finger}0{i}{s}", f"f{finger}0{i}{s}", f"{word}hand{finger}{i}", f"{word}{finger}{seg[i - 1]}"]
    if finger == "pinky":
        names += [f"{word}little{seg[i - 1]}", f"little0{i}{s}"]
    return names


def find_hand(arm, side: str) -> dict:
    """Bone names of one arm and hand, matched across Unreal, Mixamo, Rigify and the
    Unity/Godot humanoid naming."""
    s, word = SIDE_WORDS[side]
    by_norm = {_norm(b.name): b.name for b in arm.data.bones}

    def pick(*cands):
        return next((by_norm[c] for c in cands if c in by_norm), None)

    info = {
        "side": side,
        "hand": pick(f"hand{s}", f"{word}hand"),
        "lowerarm": pick(f"lowerarm{s}", f"forearm{s}", f"{word}forearm", f"{word}lowerarm"),
        "upperarm": pick(f"upperarm{s}", f"{word}arm", f"{word}upperarm"),
        "head": pick("head"),
        "fingers": {},
    }
    if not info["hand"]:
        raise ValueError(f"no {word} hand bone found (looked for Unreal, Mixamo, Rigify and humanoid names)")
    for f in FINGERS:
        chain = [pick(*_finger_names(f, i, side)) for i in (1, 2, 3)]
        if f == "thumb" and not all(chain) and f"{word}thumbintermediate" in by_norm:  # Unity's thumb
            chain = [by_norm.get(f"{word}thumb{x}") for x in ("proximal", "intermediate", "distal")]
        if all(chain):
            info["fingers"][f] = chain
    if not any(f in info["fingers"] for f in ("index", "middle")):
        raise ValueError(f"the {word} hand has no finger bones the grip tools recognize")
    constrained = [n for chain in info["fingers"].values() for n in chain if arm.pose.bones[n].constraints]
    info["warnings"] = [f"finger bones have constraints (e.g. {constrained[0]}); pose the rig's controls instead"] if constrained else []
    return info


def _armature(objs, name: str = ""):
    arms = [o for o in objs if o.type == "ARMATURE" and (not name or o.name == name)]
    if not arms:
        for o in objs:
            if o.type == "MESH" and o.find_armature():
                return o.find_armature()
        raise ValueError("no armature in the file")
    return arms[0]


def _skinned_meshes(arm) -> list:
    """The body: the meshes ``arm`` deforms, less props skinned rigidly to a bone."""
    return _skin_split(arm)[0]


_SPLIT: dict = {}


def _skin_split(arm) -> tuple[list, list]:
    """The meshes ``arm`` deforms, as (body, held props). A prop is skinned rigidly: 99% or
    more of its vertices led by one bone that is weapon_r or weapon_l or below one, or that
    leads no vertex of the body's other meshes (a sword skinned whole to its own bone)."""
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.find_armature() == arm]
    key = (arm.as_pointer(), tuple((o.as_pointer(), len(o.data.vertices), len(o.vertex_groups)) for o in meshes))
    if key not in _SPLIT:
        lead = {o: _lead_bone(o) for o in meshes}
        rigid = {o for o in meshes if lead[o][0] is not None and lead[o][1] >= 0.99}
        body_bones = set().union(*(lead[o][2] for o in meshes if o not in rigid))

        def prop(o):
            b = arm.data.bones.get(lead[o][0])
            if b is None:
                return False
            if any(x.name in WEAPON_BONES for x in (b, *b.parent_recursive)):
                return True
            return bool(body_bones) and b.name not in body_bones

        props = [o for o in meshes if o in rigid and prop(o)]
        _SPLIT.clear()
        _SPLIT[key] = ([o for o in meshes if o not in props], props)
    return _SPLIT[key]


def _lead_bone(obj) -> tuple[str | None, float, set]:
    """The vertex group that leads (weighs most on) the most vertices of ``obj``, the share of
    vertices it leads, and every group that leads at least one."""
    names = {g.index: g.name for g in obj.vertex_groups}
    counts: dict = {}
    for v in obj.data.vertices:
        best = max(v.groups, key=lambda g: g.weight, default=None)
        name = names.get(best.group) if best is not None and best.weight > 0 else None
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None, 0.0, set()
    top = max(counts, key=counts.get)
    return top, counts[top] / len(obj.data.vertices), {n for n in counts if n}


def _world_bone(arm, name: str):
    pb = arm.pose.bones[name]
    m = arm.matrix_world @ pb.matrix
    return m, arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail


def hand_frame(arm, info: dict) -> dict:
    """Wrist, knuckle direction a, across-the-knuckles direction k (toward the pinky), palm
    normal n (out of the palm) and palm length, from the posed bones."""
    _, wrist, _ = _world_bone(arm, info["hand"])
    fingers = info["fingers"]
    mcps = [_world_bone(arm, fingers[f][0])[1] for f in ("index", "middle", "ring", "pinky") if f in fingers]
    knuckles = sum(mcps, Vector()) / len(mcps)
    a = (knuckles - wrist).normalized()
    first = next(_world_bone(arm, fingers[f][0])[1] for f in ("index", "middle") if f in fingers)
    last = next(_world_bone(arm, fingers[f][0])[1] for f in ("pinky", "ring", "middle") if f in fingers)
    k = last - first
    k = (k - a * k.dot(a)).normalized()
    n = k.cross(a)
    palm_len = (knuckles - wrist).length
    # the thumb sits on the palm side; fall back on the side's handedness when unclear
    side_sign = 1.0 if info["side"] == "l" else -1.0
    if "thumb" in fingers:
        tip = _world_bone(arm, fingers["thumb"][2])[2]
        s = (tip - wrist).dot(n)
        if abs(s) > 0.03 * palm_len:
            side_sign = 1.0 if s > 0 else -1.0
    return {"wrist": wrist, "a": a, "k": k, "n": n * side_sign, "palm_len": palm_len, "knuckles": knuckles}


def _groups_by_vertex(obj, bones: set) -> np.ndarray:
    """Dominant deform bone per vertex (index into ``names``), -1 when none of ``bones``."""
    names = {g.index: g.name for g in obj.vertex_groups}
    dom = np.full(len(obj.data.vertices), -1)
    order = sorted(bones)
    idx = {b: i for i, b in enumerate(order)}
    for v in obj.data.vertices:
        best = max(v.groups, key=lambda g: g.weight, default=None)
        if best is not None and best.weight > 0.05 and names.get(best.group) in idx:
            dom[v.index] = idx[names[best.group]]
    return dom, order


def hand_regions(arm, info: dict, ball_in_palm: bool = True) -> dict:
    """World vertices of the posed hand, split into palm and fingers: {region: (N, 3)}."""
    fingers = dict(info["fingers"])
    palm = [info["hand"]]
    if "thumb" in fingers and ball_in_palm:  # the thumb's metacarpal is the ball of the thumb
        palm.append(fingers["thumb"][0])
        fingers["thumb"] = fingers["thumb"][1:]
    regions = {"palm": palm, **fingers}
    wanted = {b for chain in regions.values() for b in chain}
    out = {r: [] for r in regions}
    for obj in _skinned_meshes(arm):
        co, _ = _world_mesh(obj)
        if len(co) != len(obj.data.vertices):
            continue  # topology-changing modifiers: skip this mesh
        dom, order = _groups_by_vertex(obj, wanted)
        for r, chain in regions.items():
            ids = [order.index(b) for b in chain]
            sel = np.isin(dom, ids)
            if sel.any():
                out[r].append(co[sel])
    return {r: np.concatenate(v) for r, v in out.items() if v}


def _segment_dist(pts: np.ndarray, a, b) -> np.ndarray:
    a, b = np.array(a), np.array(b)
    ab = b - a
    t = np.clip(((pts - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(a + t[:, None] * ab - pts, axis=1)


# ---------------------------------------------------------------- held geometry

def _hierarchy(root) -> list:
    out, stack = [], [root]
    while stack:
        o = stack.pop()
        out.append(o)
        stack.extend(o.children)
    return out


def object_solid(objs) -> geom.Solid | None:
    """The held meshes as one solid for signed distances (negative inside any part)."""
    return geom.Solid.from_objects(objs)


def _grip_empties(objs) -> list:
    return [o for o in objs if o.type == "EMPTY" and (o.name.startswith("SOCKET_grip_") or o.name.startswith("GRIP_"))]


def _grip_name(o) -> str:
    return o.name.split("grip_", 1)[-1] if "grip_" in o.name else o.name.split("GRIP_", 1)[-1]


# ---------------------------------------------------------------- finger closing

def _fk(J: list, ax: Vector, th) -> list:
    """Planar chain: joint i turns by th[i] about ``ax`` (axes stay parallel)."""
    P, cum = [J[0]], 0.0
    for i in range(len(J) - 1):
        cum += th[i]
        P.append(P[-1] + Matrix.Rotation(cum, 3, ax) @ (J[i + 1] - J[i]))
    return P


def _first_hit(P, radii, held, tol: float):
    """Index of the first segment that sinks deeper than ``tol`` into the object, else None."""
    for s in range(len(P) - 1):
        ts = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0) if s < len(P) - 2 else (0.0, 0.2, 0.4, 0.6, 0.8)
        for t in ts:
            if held.signed1(P[s].lerp(P[s + 1], t)) - radii[s] < -tol:
                return s
        if s == len(P) - 2 and held.signed1(P[-1]) - radii[s] * 0.3 < -tol:
            return s
    return None


def _free_start(J, ax, radii, held, tol, n: int, step=math.radians(1.5)):
    """Rest angles, or the knuckle opened just enough to clear the object; None if stuck."""
    th = [0.0] * n
    if _first_hit(_fk(J, ax, th), radii, held, tol) is None:
        return th
    for back in np.arange(step, math.radians(40), step):
        th = [-back] + [0.0] * (n - 1)
        if _first_hit(_fk(J, ax, th), radii, held, tol) is None:
            return th
    return None


def close_chain(J, ax, radii, held, ratio, limit, tol, step=math.radians(1.5)):
    """GraspIt-style auto grasp of one finger. Returns (angles, status)."""
    n = len(J) - 1
    lim = [math.radians(x) for x in limit]
    th = _free_start(J, ax, radii, held, tol, n)
    if th is None:
        return [0.0] * n, "starts inside the object"
    frozen = [False] * n
    while not all(frozen):
        delta = [0.0 if frozen[i] else min(step * ratio[i], lim[i] - th[i]) for i in range(n)]
        for i in range(n):
            if delta[i] <= 1e-9:
                frozen[i] = True
        if all(frozen):
            break
        trial = [th[i] + delta[i] for i in range(n)]
        if _first_hit(_fk(J, ax, trial), radii, held, tol) is None:
            th = trial
            continue
        lo, hi = 0.0, 1.0
        for _ in range(10):
            mid = (lo + hi) / 2
            if _first_hit(_fk(J, ax, [th[i] + delta[i] * mid for i in range(n)]), radii, held, tol) is None:
                lo = mid
            else:
                hi = mid
        hit = _first_hit(_fk(J, ax, [th[i] + delta[i] * hi for i in range(n)]), radii, held, tol)
        th = [th[i] + delta[i] * lo for i in range(n)]
        for i in range(min(hit, n - 1) + 1):
            frozen[i] = True
    return th, "closed"


def _march(J, ax, radii, held, ratio, limit, tol, score, step=math.radians(1.0)):
    """Close with coupled joints until contact or the limits; keep the best-scoring state."""
    lim = [math.radians(x) for x in limit]
    start = _free_start(J, ax, radii, held, tol, len(ratio))
    if start is None:
        return [0.0] * len(ratio), float("inf")
    best, best_th, t = float("inf"), start, 0.0
    while True:
        th = [min(start[i] + t * ratio[i], lim[i]) for i in range(len(ratio))]
        P = _fk(J, ax, th)
        if _first_hit(P, radii, held, tol) is not None:
            break
        sc = score(P)
        if sc < best:
            best, best_th = sc, th
        if all(x >= l - 1e-9 for x, l in zip(th, lim)):
            break
        t += step
    return best_th, best


def _reach_point(J, ax, radii, held, tol, score):
    """Best knuckle and middle-joint angles (tip joint follows at 0.7x) for ``score``,
    without entering the object: a grid, then a finer grid around the best."""
    def search(k0, k1, step):
        best, best_th = float("inf"), None
        for a in np.arange(k0[0], k0[1] + 1e-9, step):
            for b in np.arange(k1[0], k1[1] + 1e-9, step):
                th = [math.radians(a), math.radians(b), math.radians(b * 0.7)]
                P = _fk(J, ax, th)
                sc = score(P)
                if sc < best and _first_hit(P, radii, held, tol) is None:
                    best, best_th = sc, th
        return best, best_th

    best, th = search((-10, 90), (0, 105), 5)
    if th is None:
        return [0.0, 0.0, 0.0], float("inf")
    a, b = math.degrees(th[0]), math.degrees(th[1])
    best2, th2 = search((a - 5, a + 5), (max(0, b - 5), b + 5), 1)
    return (th2, best2) if th2 is not None and best2 < best else (th, best)


def _chain_joints(arm, chain):
    pts = [_world_bone(arm, b)[1] for b in chain]
    pts.append(_world_bone(arm, chain[-1])[2])
    return pts


def _chain_radii(arm, chain, regions_pts, pad_dir: Vector | None = None) -> list:
    """Finger thickness per segment from the skinned mesh, measured on the pad side (the side
    that touches what the hand holds); else a share of the bone length."""
    J = _chain_joints(arm, chain)
    radii = []
    for i in range(3):
        seg_len = (J[i + 1] - J[i]).length
        r = 0.22 * seg_len
        if regions_pts is not None and len(regions_pts):
            a, b = np.array(J[i]), np.array(J[i + 1])
            ab = b - a
            t = np.clip(((regions_pts - a) @ ab) / max(float(ab @ ab), 1e-12), 0.1, 0.9)
            off = regions_pts - (a + t[:, None] * ab)
            d = np.linalg.norm(off, axis=1)
            keep = d < seg_len * 0.8
            if pad_dir is not None:
                pd = np.array(pad_dir - (J[i + 1] - J[i]).normalized() * pad_dir.dot((J[i + 1] - J[i]).normalized()))
                pd /= max(np.linalg.norm(pd), 1e-9)
                keep &= (off @ pd) > d * 0.7  # within ~45 degrees of the pad direction
            if keep.sum() > 4:
                r = float(np.median(d[keep]))
        radii.append(r)
    return radii


def _apply_chain(arm, chain, P_new, ax, th, pre: Quaternion | None = None, pivot: Vector | None = None):
    """Pose a chain so its joints land on ``P_new``: each bone turns by its cumulative angle
    about ``ax`` (after an optional ``pre`` rotation about the chain's base)."""
    olds = [_world_bone(arm, b)[0].copy() for b in chain]
    inv = arm.matrix_world.inverted()
    cum = 0.0
    for i, b in enumerate(chain):
        cum += th[i]
        rot = Matrix.Rotation(cum, 4, ax)
        if pre is not None:
            rot = rot @ pre.to_matrix().to_4x4()
        m = olds[i].copy()
        m.translation = (0, 0, 0)
        new = Matrix.Translation(P_new[i]) @ rot @ m
        arm.pose.bones[b].matrix = inv @ new
        bpy.context.view_layer.update()


def _thumb_fk(J, axes, q):
    """Thumb with a two-axis base joint: q = (swing about b, flex about f at the base,
    flex at the knuckle, flex at the tip). Returns joint positions and bone rotations."""
    f, b = axes
    R0 = Matrix.Rotation(q[1], 3, f) @ Matrix.Rotation(q[0], 3, b)
    R1 = R0 @ Matrix.Rotation(q[2], 3, f)
    R2 = R1 @ Matrix.Rotation(q[3], 3, f)
    P = [J[0], J[0] + R0 @ (J[1] - J[0])]
    P.append(P[1] + R1 @ (J[2] - J[1]))
    P.append(P[2] + R2 @ (J[3] - J[2]))
    return P, [R0, R1, R2]


def _capsule_clear(P, radii, capsules, tol, segments=(1, 2)) -> bool:
    for s in segments:
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            p = np.array(P[s].lerp(P[s + 1], t))
            for a, b, r in capsules:
                if _segment_dist(p[None], a, b)[0] < radii[s] + r - tol:
                    return False
    return True


def solve_thumb(J, radii, frame, held, capsules, target: Vector, tol: float, give: float = 0.0, skin=None):
    """Hill-climb the thumb's pad onto ``target`` without entering the object or the fingers.
    The metacarpal sits inside the palm's flesh, so only the two phalanges are tested."""
    t = (J[1] - J[0]).normalized()
    bend = frame["k"] + frame["n"]
    bend = (bend - t * bend.dot(t)).normalized()
    f = t.cross(bend).normalized()  # +angle bends toward the palm and the pinky
    axes = (f, bend)
    lo = [math.radians(x) for x in (-40, -30, 0, 0)]
    hi = [math.radians(x) for x in (60, 60, 70, 85)]

    skin = skin or []
    state = {}

    def ok(P):
        for s in (1, 2):
            ts = (0.0, 0.25, 0.5, 0.75, 1.0) if s == 1 else (0.0, 0.25, 0.5, 0.75)
            for u in ts:
                if held.signed1(P[s].lerp(P[s + 1], u)) - radii[s] < -tol:
                    return False
        # every vertex the thumb moves (its ball, the web), skinned the way the rig will skin
        # it, may press into the object by ``give`` and no further
        rots = state.get("rots")
        if skin and rots is not None:
            D = [Matrix.Translation(P[i]) @ rots[i].to_4x4() @ Matrix.Translation(-J[i]) for i in range(3)]
            for v, ws in skin:
                if held.signed1(v + sum(((D[i] @ v - v) * w for i, w in ws), Vector())) < -(tol + give):
                    return False
        return _capsule_clear(P, radii, capsules, tol)

    def fk(q):
        P, rots = _thumb_fk(J, axes, q)
        state["rots"] = rots
        return P

    def cost(P):
        pad = P[2].lerp(P[3], 0.55)
        return (pad - target).length

    # coarse search for the best collision-free start, then refine
    q, best = [0.0, 0.0, 0.0, 0.0], float("inf")
    for sw in range(-40, 61, 10):
        for fl in range(-30, 61, 10):
            for k1 in (0, 30, 60):
                for k2 in (0, 40, 80):
                    trial = [math.radians(x) for x in (sw, fl, k1, k2)]
                    P = fk(trial)
                    c = cost(P)
                    if c < best and ok(P):
                        q, best = trial, c
    for step in (math.radians(x) for x in (8, 4, 2, 1)):
        improved = True
        while improved:
            improved = False
            for i in range(4):
                for sgn in (1, -1):
                    trial = list(q)
                    trial[i] = min(max(trial[i] + sgn * step, lo[i]), hi[i])
                    if trial[i] == q[i]:
                        continue
                    P = fk(trial)
                    c = cost(P)
                    if c < best - 1e-6 and ok(P):
                        q, best, improved = trial, c, True
    # settle: keep bending the thumb until it rests on the handle or the fingers
    step = math.radians(1.0)
    for _ in range(90):
        trial = [q[0], min(q[1] + step * 0.5, hi[1]), min(q[2] + step, hi[2]), min(q[3] + step, hi[3])]
        if trial == q or not ok(fk(trial)):
            break
        q = trial
    P, rots = _thumb_fk(J, axes, q)
    return q, P, rots, cost(P)


def _finger_skin(arm, chain) -> np.ndarray:
    pts = []
    for obj in _skinned_meshes(arm):
        co, _ = _world_mesh(obj)
        if len(co) != len(obj.data.vertices):
            continue
        dom, _ = _groups_by_vertex(obj, set(chain))
        pts.append(co[dom >= 0])
    return np.concatenate(pts) if pts else np.empty((0, 3))


def _weighted_skin(arm, chain, held, reach: float, limit: int = 80) -> list:
    """Vertices the chain's bones move (weight > 0.1) within ``reach`` of the object, with
    their weights per chain bone: [(position, [(bone index, weight)])]."""
    cand = []
    for obj in _skinned_meshes(arm):
        co, _ = _world_mesh(obj)
        if len(co) != len(obj.data.vertices):
            continue
        names = {g.index: g.name for g in obj.vertex_groups}
        idx = {b: i for i, b in enumerate(chain)}
        for v, p in zip(obj.data.vertices, co):
            total = sum(g.weight for g in v.groups)
            ws = [(idx[names[g.group]], g.weight / total) for g in v.groups if names.get(g.group) in idx and total > 0]
            if sum(w for _, w in ws) > 0.1:
                cand.append((p, ws))
    if not cand:
        return []
    d = held.signed([p for p, _ in cand])
    near = sorted((d[i], i) for i in np.nonzero(d < reach)[0])
    return [(Vector(cand[i][0]), cand[i][1]) for _, i in near[:limit]]


def refine_on_skin(arm, chain, ax, held, gap: float, max_inside: float, step=math.radians(1.0), steps: int = 25) -> int:
    """Keep curling a finger (mostly its outer joints) until its actual skin, not the capsule
    estimate, touches the object. Returns the number of steps taken."""
    ratio = (0.3, 1.0, 0.8)
    done = 0
    for _ in range(steps):  # first open up if the real skin already sinks in
        skin = _finger_skin(arm, chain)
        if not len(skin) or held.signed(skin).min() >= -max_inside:
            break
        J = _chain_joints(arm, chain)
        th = [-step * r for r in ratio]
        _apply_chain(arm, chain, _fk(J, ax, th), ax, th)
        done -= 1
    if done:
        return done
    for _ in range(steps):
        skin = _finger_skin(arm, chain)
        if not len(skin):
            break
        closest = held.signed(skin).min()
        if closest <= gap:
            break
        J = _chain_joints(arm, chain)
        th = [step * r for r in ratio]
        olds = [arm.pose.bones[b].matrix.copy() for b in chain]
        _apply_chain(arm, chain, _fk(J, ax, th), ax, th)
        skin = _finger_skin(arm, chain)
        if held.signed(skin).min() < -max_inside:
            for b, m in zip(chain, olds):  # went too far: undo and stop
                arm.pose.bones[b].matrix = m
                bpy.context.view_layer.update()
            break
        done += 1
    return done


def _apply_rotations(arm, chain, P_new, rots):
    olds = [_world_bone(arm, b)[0].copy() for b in chain]
    inv = arm.matrix_world.inverted()
    for i, b in enumerate(chain):
        m = olds[i].copy()
        m.translation = (0, 0, 0)
        arm.pose.bones[b].matrix = inv @ (Matrix.Translation(P_new[i]) @ rots[i].to_4x4() @ m)
        bpy.context.view_layer.update()


def close_hand(arm, info, frame, held, grip: dict) -> dict:
    """Close every finger and the thumb on the object. Returns per-finger results."""
    regions = hand_regions(arm, info, ball_in_palm=False)
    n_palm = frame["n"]
    s_hand = frame["palm_len"] / REF_PALM
    tol = 0.0004 * s_hand
    results = {}
    axis_d = grip["axis_world"]
    center = grip["center_world"]
    capsules = []
    for f in [x for x in FINGERS if x != "thumb"] + ["thumb"]:
        if f not in info["fingers"]:
            continue
        chain = info["fingers"][f]
        J = _chain_joints(arm, chain)
        radii = _chain_radii(arm, chain, regions.get(f), None if f == "thumb" else n_palm)
        if f == "thumb":
            mode = grip.get("thumb", "wrap")
            target = _thumb_target(arm, info, mode, axis_d, center, radii, capsules)
            skin = _weighted_skin(arm, chain, held, frame["palm_len"] * 0.5)
            q, P, rots, miss = solve_thumb(J, radii, frame, held, capsules, target, tol, give=0.002 * s_hand, skin=skin)
            _apply_rotations(arm, chain, P, rots)
            results[f] = {"angles_deg": [round(math.degrees(x), 1) for x in q],
                          "status": f"{mode}, pad {miss * 1000:.0f} mm from its ideal spot"}
            continue
        d0 = (J[1] - J[0]).normalized()
        ax = d0.cross(n_palm).normalized()
        mode = grip.get("index", "curl") if f == "index" else "curl"
        ratio, limit = CLOSE_RATIO["default"], CLOSE_LIMIT["default"]
        if mode == "extended":
            th, _ = _march(J, ax, radii, held, ratio, (6.0, 4.0, 2.0), tol, lambda P: -(P[-1] - J[-1]).length)
            status = "extended"
        elif mode == "trigger" and grip.get("trigger_world") is not None:
            trig = grip["trigger_world"]

            def pad_distance(P):
                d = _segment_dist(np.array([tuple(trig)]), P[2], P[3])[0]
                return abs(d - radii[2])

            th, best = _reach_point(J, ax, radii, held, tol, pad_distance)
            status = f"on trigger ({best * 1000:.1f} mm off)"
        else:
            th, status = close_chain(J, ax, radii, held, ratio, limit, tol)
        P = _fk(J, ax, th)
        _apply_chain(arm, chain, P, ax, th)
        if mode == "curl":
            extra = refine_on_skin(arm, chain, ax, held, 0.0005 * s_hand, 0.0005 * s_hand)
            if extra:
                status += f", {extra:+d} deg on the skin"
                P = _chain_joints(arm, chain)
        capsules += [(np.array(P[i]), np.array(P[i + 1]), radii[i]) for i in range(3)]
        results[f] = {"angles_deg": [round(math.degrees(x), 1) for x in th], "status": status}
    return results


# ---------------------------------------------------------------- placing and reaching

def _thumb_target(arm, info, mode, axis_d, center, radii, capsules) -> Vector:
    """Where the thumb pad should rest. wrap: on the outside of the index finger's middle
    segment (around the far side of the handle); along: on the handle's surface, pointing
    toward the thumb end."""
    J = _chain_joints(arm, info["fingers"]["thumb"])
    if mode == "wrap" and "index" in info["fingers"]:
        _, a, b = _world_bone(arm, info["fingers"]["index"][1])
        r_index = capsules[1][2] if len(capsules) > 1 else radii[1]
        mid = a.lerp(b, 0.5)
        axis_pt = center + axis_d * (mid - center).dot(axis_d)
        out = mid - axis_pt
        out = (out - axis_d * out.dot(axis_d)).normalized()
        return mid + out * (r_index + radii[2] * 0.9) + axis_d * (radii[2] * 0.6)
    mcp = _world_bone(arm, info["fingers"]["index"][0])[1] if "index" in info["fingers"] else J[1]
    axis_pt = center + axis_d * (mcp - center).dot(axis_d)
    side = J[0] - axis_pt
    side = (side - axis_d * side.dot(axis_d)).normalized()
    thumb_len = sum((J[i + 1] - J[i]).length for i in range(1, 3))
    hit_r = radii[2]
    return axis_pt + axis_d * (thumb_len * 0.6) + side * hit_r * 2.0


def seat(arm, info, frame, root, held, gap: float, tol: float, give: float, max_iter: int = 6) -> float:
    """Slide the object along the palm normal until the palm just touches it. The thumb's
    ball may sink in by up to ``give`` (soft tissue); beyond that it holds the object off.
    Returns the distance moved toward the palm (m)."""
    thumb_base = {info["fingers"]["thumb"][0]} if "thumb" in info["fingers"] else set()
    moved = 0.0
    for _ in range(max_iter):
        solid = object_solid(held)
        palm, ball = float("inf"), float("inf")
        for obj in _skinned_meshes(arm):
            co, _ = _world_mesh(obj)
            if len(co) != len(obj.data.vertices):
                continue
            dom, order = _groups_by_vertex(obj, {info["hand"]} | thumb_base)
            sel = np.nonzero(dom >= 0)[0]
            d = solid.signed(co[sel])
            is_palm = np.array([order[k] == info["hand"] for k in dom[sel]], bool)
            palm = min(palm, float(d[is_palm].min(initial=np.inf)))
            ball = min(ball, float(d[~is_palm].min(initial=np.inf)))
        step = min(palm - gap, ball + give)  # > 0 moves the object toward the palm
        if not math.isfinite(step) or abs(step) <= tol:
            break
        root.matrix_world = Matrix.Translation(-frame["n"] * step) @ root.matrix_world
        bpy.context.view_layer.update()
        moved += step
    return moved


def align_trigger(arm, info, frame, root, empty) -> float:
    """Slide the object along its handle so the trigger lies in the index finger's curling
    plane. Returns the slide distance (m)."""
    if "index" not in info["fingers"]:
        return 0.0
    props = grip_props(empty)
    J = _chain_joints(arm, info["fingers"]["index"])
    ax = (J[1] - J[0]).normalized().cross(frame["n"]).normalized()
    along = props["axis_world"]
    c = along.dot(ax)
    if abs(c) < 0.3:
        return 0.0
    off = (props["trigger_world"] - J[0]).dot(ax)
    slide = -off / c
    root.matrix_world = Matrix.Translation(along * slide) @ root.matrix_world
    bpy.context.view_layer.update()
    return slide


def palm_surface(arm, info, frame, at: float = 0.72) -> Vector:
    """Point on the palm skin, ``at`` of the way from the wrist to the knuckles."""
    base = frame["wrist"] + frame["a"] * (frame["palm_len"] * at)
    bvh = _hand_bvh(arm, info)
    if bvh is not None:
        origin = base + frame["n"] * frame["palm_len"] * 1.5
        hit, *_ = bvh.ray_cast(origin, -frame["n"], frame["palm_len"] * 3)
        if hit is not None:
            return hit
    return base + frame["n"] * (frame["palm_len"] * 0.12)


def _hand_bvh(arm, info) -> BVHTree | None:
    """BVH of the posed hand's faces only (palm and fingers), so nothing else gets in the way."""
    wanted = {info["hand"], *[b for c in info["fingers"].values() for b in c]}
    verts, polys = [], []
    for obj in _skinned_meshes(arm):
        co, ps = _world_mesh(obj)
        if len(co) != len(obj.data.vertices):
            continue
        dom, _ = _groups_by_vertex(obj, wanted)
        base = len(verts)
        verts.extend(Vector(v) for v in co)
        polys.extend(tuple(i + base for i in p) for p in ps if all(dom[i] >= 0 for i in p))
    return BVHTree.FromPolygons(verts, polys) if polys else None


def grip_props(empty) -> dict:
    raw = empty.get("opus_grip")
    props = json.loads(raw) if raw else {}
    m = empty.matrix_world
    rot = m.to_quaternion()
    props["axis_world"] = (rot @ Vector((0, 1, 0))).normalized()
    props["palm_dir_world"] = (rot @ Vector((0, 0, 1))).normalized()
    props["center_world"] = m.translation.copy()
    if props.get("trigger") is not None:
        props["trigger_world"] = m @ Vector(props["trigger"])
    return props


def placement(arm, info, frame, root, empty, props) -> Matrix:
    """World matrix for ``root`` that puts its grip against the palm: handle axis across the
    palm on a diagonal toward the index finger, palm-side surface touching the palm skin."""
    S = palm_surface(arm, info, frame)
    a, k, n = frame["a"], frame["k"], frame["n"]
    diag = math.radians(props.get("diagonal", 20.0))
    y = (-k * math.cos(diag) + a * math.sin(diag)).normalized()  # handle axis, thumb end toward the index
    z = -n  # from the handle toward the palm
    x = y.cross(z).normalized()
    C = S + n * props.get("palm_offset", props.get("radius", 0.02))
    H = Matrix.Translation(C) @ Matrix((x, y, z)).transposed().to_4x4()
    g_local = root.matrix_world.inverted() @ empty.matrix_world
    loc, rot, _ = g_local.decompose()
    g_local = Matrix.LocRotScale(loc, rot, None)
    return H @ g_local.inverted()


def _set_direction(arm, bone: str, new_dir: Vector, head: Vector | None = None):
    m, h, t = _world_bone(arm, bone)
    q = (t - h).normalized().rotation_difference(new_dir.normalized())
    rot = m.copy()
    rot.translation = (0, 0, 0)
    arm.pose.bones[bone].matrix = arm.matrix_world.inverted() @ (Matrix.Translation(head or h) @ q.to_matrix().to_4x4() @ rot)
    bpy.context.view_layer.update()


def reach(arm, info, hand_target: Matrix, pole: Vector) -> float:
    """Two-bone IK for upper arm and forearm, then the hand's full orientation. The elbow
    goes where the wrist bends least (never up), leaning toward ``pole``. Returns how far (m)
    the wrist ends from the target (0 when reachable)."""
    if not info["upperarm"] or not info["lowerarm"]:
        raise ValueError("arm placement needs upper arm and forearm bones")
    _, S, _ = _world_bone(arm, info["upperarm"])
    _, E0, _ = _world_bone(arm, info["lowerarm"])
    _, W0, _ = _world_bone(arm, info["hand"])
    l1, l2 = (E0 - S).length, (W0 - E0).length
    Wt = hand_target.translation
    dvec = Wt - S
    dist = min(max(dvec.length, abs(l1 - l2) + 1e-4), (l1 + l2) * 0.999)
    dirv = dvec.normalized()
    a1 = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(l1 * l1 - a1 * a1, 0.0))
    # the hand's knuckle direction once it reaches the target
    m_hand = _world_bone(arm, info["hand"])[0]
    frame = hand_frame(arm, info)
    hand_a = (hand_target.to_3x3().normalized() @ m_hand.to_3x3().normalized().inverted()) @ frame["a"]
    u = pole - dirv * pole.dot(dirv)
    u = u.normalized() if u.length > 1e-6 else dirv.orthogonal().normalized()
    v = dirv.cross(u)
    best, E = float("inf"), S + dirv * a1 + u * h
    for deg in range(0, 360, 5):
        p = u * math.cos(math.radians(deg)) + v * math.sin(math.radians(deg))
        cand = S + dirv * a1 + p * h
        forearm = (S + dirv * dist - cand).normalized()
        cost = forearm.angle(hand_a) + 1.5 * max(0.0, p.z) + 0.3 * (1 - p.dot(u))
        if cost < best:
            best, E = cost, cand
    Wn = S + dirv * dist
    _set_direction(arm, info["upperarm"], E - S)
    _set_direction(arm, info["lowerarm"], Wn - E)
    _, Wcur, _ = _world_bone(arm, info["hand"])
    loc, rot, scale = hand_target.decompose()
    _, _, cur_scale = _world_bone(arm, info["hand"])[0].decompose()
    arm.pose.bones[info["hand"]].matrix = arm.matrix_world.inverted() @ Matrix.LocRotScale(Wcur, rot, cur_scale)
    bpy.context.view_layer.update()
    return (Wt - Wcur).length


AXES = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


def _eye(arm, info, objs) -> tuple[Vector, float]:
    """Eye position and body height scale (1.0 = 1.8 m)."""
    cams = [o for o in bpy.context.scene.objects if o.type == "CAMERA" and "fp" in o.name.lower()]
    lo, hi = assets.world_bounds([o for o in _skinned_meshes(arm)] or [arm])
    scale = max(hi.z - lo.z, 0.1) / 1.8
    if cams:
        return cams[0].matrix_world.translation.copy(), scale
    if not info["head"]:
        raise ValueError("first-person placement needs a head bone or a camera named like 'fp_camera'")
    _, h, t = _world_bone(arm, info["head"])
    return h.lerp(t, 0.45) + Vector((0, -0.09 * scale, 0)), scale


def object_target(arm, info, root, pose: str, aim_axis: str, up_axis: str, props, offset=None) -> Matrix:
    """Where the held object should be for a first-person or front pose."""
    F, U = Vector((0, -1, 0)), Vector((0, 0, 1))  # characters face -Y
    R = Vector((-1, 0, 0)) if info["side"] == "r" else Vector((1, 0, 0))  # the character's right is -X
    eye, s = _eye(arm, info, None)
    aim_l, up_l = Vector(AXES[aim_axis]), Vector(AXES[up_axis])
    # rotation taking the object's aim/up axes to forward/up
    src = Matrix((aim_l, up_l, aim_l.cross(up_l))).transposed()
    dst = Matrix((F, U, F.cross(U))).transposed()
    rot = (dst @ src.inverted()).to_4x4() @ Matrix.Diagonal((*root.matrix_world.to_scale(), 1.0))
    if pose == "fp_ads":  # offset: [forward], the eye to the sight (m at 1.8 m height)
        if offset and any(abs(float(x)) > 1e-9 for x in list(offset)[1:]):
            raise ValueError("fp_ads keeps the sight on the eye line: give offset as [forward, 0, 0]")
        sights = [o for o in _hierarchy(root) if o.type == "EMPTY" and o.name.lower().startswith(("socket_sight", "sight"))]
        if not sights:
            raise ValueError("fp_ads needs an empty named SOCKET_sight on the object, on the sight line")
        sight_local = root.matrix_world.inverted() @ sights[0].matrix_world.translation
        target = eye + F * (float(offset[0]) if offset else 0.2) * s
        return Matrix.Translation(target - (rot @ sight_local.to_4d()).xyz) @ rot
    if pose == "fp_hip":  # offset: forward, right, down from the eye (m at 1.8 m height)
        fwd, right, down = offset or (0.5, 0.2, 0.18)
        grip_at = eye + F * (fwd * s) + R * (right * s) - U * (down * s)
    elif pose == "front":
        _, sh, _ = _world_bone(arm, info["upperarm"])
        grip_at = Vector((sh.x * 0.5, sh.y, sh.z)) + F * (0.38 * s) - U * (0.18 * s)
    else:
        raise ValueError("pose must be rest, front, fp_hip or fp_ads")
    g_world_now = props["center_world"]
    g_local = root.matrix_world.inverted() @ g_world_now
    return Matrix.Translation(grip_at - (rot @ g_local.to_4d()).xyz) @ rot


def _weapon_bone(arm, info, root) -> str:
    """A bone at the object's origin, child of the hand, so engines can attach the object to
    it with no offset."""
    name = f"weapon_{info['side']}"
    hand = info["hand"]
    # the object's place relative to the posed hand, carried over to the rest pose
    obj_arm = arm.matrix_world.inverted() @ root.matrix_world
    bone_arm = arm.data.bones[hand].matrix_local @ arm.pose.bones[hand].matrix.inverted() @ obj_arm
    loc, rot, _ = bone_arm.decompose()
    active = bpy.context.view_layer.objects.active
    if active is not None and active.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.scene.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones.get(name) or arm.data.edit_bones.new(name)
    length = 0.6 * REF_PALM * info.get("scale", 1.0) / max(arm.matrix_world.to_scale().x, 1e-9)
    eb.head, eb.tail = (0, 0, 0), (0, length, 0)
    eb.matrix = Matrix.LocRotScale(loc, rot, None)
    eb.parent = arm.data.edit_bones[hand]
    eb.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    world = root.matrix_world.copy()
    root.parent = arm
    root.parent_type = "BONE"
    root.parent_bone = name
    bpy.context.view_layer.update()
    root.matrix_world = world
    bpy.context.view_layer.update()
    return name


def _key_pose(arm, bones: list, action_name: str):
    for b in bones:
        pb = arm.pose.bones[b]
        path = "rotation_quaternion" if pb.rotation_mode == "QUATERNION" else (
            "rotation_axis_angle" if pb.rotation_mode == "AXIS_ANGLE" else "rotation_euler")
        pb.keyframe_insert(data_path=path, frame=1)
        pb.keyframe_insert(data_path="location", frame=1)
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action.name = action_name


# ---------------------------------------------------------------- measuring

def measure(arm, info, held_objs) -> dict:
    """Signed distances (mm) from the palm and each finger to the held object."""
    held = object_solid(held_objs)
    if held is None:
        raise ValueError("the held object has no mesh")
    frame = hand_frame(arm, info)
    s_hand = frame["palm_len"] / REF_PALM
    pen_tol, touch_tol = 0.0015 * s_hand, 0.003 * s_hand
    soft_tol = 0.0025 * s_hand  # the palm's flesh gives a little
    regions = hand_regions(arm, info)
    out = {}
    for r, pts in regions.items():
        sd = held.signed(pts)
        inside = sd < -(soft_tol if r == "palm" else pen_tol)
        mn = float(sd.min())
        if inside.any():
            status = "inside"
        elif mn <= touch_tol:
            status = "touching"
        else:
            status = "gap"
        out[r] = {"status": status, "closest_mm": round(mn * 1000, 1),
                  "depth_mm": round(max(0.0, -mn) * 1000, 1), "verts_inside": int(inside.sum())}
    touching = [r for r, v in out.items() if v["status"] == "touching" and r != "palm"]
    inside = [r for r, v in out.items() if v["status"] == "inside"]
    palm = out.get("palm", {}).get("status")
    body = body_clipping(arm, info, held, soft_tol)
    if body["verts_inside"] or body["crossing_triangles"]:
        verdict = "clips the body" if not inside else "sinks in and clips the body"
    elif inside:
        verdict = "sinks in"
    elif palm == "touching" and len(touching) >= 3:
        verdict = "good grip"
    elif palm == "gap" and not touching:
        verdict = "floating"
    else:
        verdict = "loose"
    return {"regions": out, "verdict": verdict, "fingers_touching": touching, "body": body,
            "tolerance_mm": {"inside": round(pen_tol * 1000, 1), "palm_inside": round(soft_tol * 1000, 1),
                             "touching": round(touch_tol * 1000, 1)}}


def body_clipping(arm, info, held, tol: float) -> dict:
    """Skin outside this hand (arms, chest, head) that ends up inside the held object, or
    that the object's surface cuts through: a blade or plate through the forearm leaves no
    skin vertex inside it, so the two surfaces are tested for crossing too."""
    hand_bones = {info["hand"], *[b for c in info["fingers"].values() for b in c]}
    lo, hi = held.box[0] - tol * 4, held.box[1] + tol * 4
    count, crossing, depth, where = 0, 0, 0.0, {}
    for obj in _skinned_meshes(arm):
        co, tris = geom.world_triangles(obj)
        if len(co) != len(obj.data.vertices):
            continue
        names = {g.index: g.name for g in obj.vertex_groups}
        bones = [names.get(max(v.groups, key=lambda g: g.weight).group) if len(v.groups) else None for v in obj.data.vertices]
        hand = np.array([b in hand_bones for b in bones], bool)
        box = np.nonzero(np.all((co >= lo) & (co <= hi), axis=1) & ~hand)[0]
        d = held.signed(co[box])
        for i in box[d < -tol]:
            count += 1
            where[bones[i]] = where.get(bones[i], 0) + 1
        if (d < -tol).any():
            depth = max(depth, -float(d.min()))
        pen = geom.penetration(held, geom.Solid(co, tris, flags=hand), skip_b=True)
        # depth only from what is counted: an object vertex in the fist, nearest a wrist
        # triangle rather than a hand one, reads as embedded with nothing crossing
        if pen is not None and pen["depth"] > tol and pen["triangles"]:
            crossing += pen["triangles"]
            depth = max(depth, pen["depth"])
            skin = np.nonzero(~hand)[0]
            for p in pen["points"][:: max(1, len(pen["points"]) // 50)]:
                b = bones[skin[np.argmin(np.linalg.norm(co[skin] - p, axis=1))]]
                where[b] = where.get(b, 0) + 1
    return {"verts_inside": count, "crossing_triangles": crossing, "depth_mm": round(depth * 1000, 1),
            "where": [b for b, _ in sorted(where.items(), key=lambda x: -x[1]) if b][:4]}


def summarize(m: dict, side: str) -> list[str]:
    word = SIDE_WORDS[side][1]
    lines = [f"{word.capitalize()} hand: {m['verdict']}"]
    for r in ("palm",) + FINGERS:
        v = m["regions"].get(r)
        if not v:
            continue
        if v["status"] == "inside":
            lines.append(f"  {r}: INSIDE the object by {v['depth_mm']} mm ({v['verts_inside']} verts)")
        elif v["status"] == "touching":
            lines.append(f"  {r}: touching")
        else:
            lines.append(f"  {r}: {v['closest_mm']} mm gap")
    b = m.get("body", {})
    if b.get("verts_inside") or b.get("crossing_triangles"):
        lines.append(f"  the object passes through the body by {b['depth_mm']} mm (at {', '.join(b['where'])})")
    return lines


# ---------------------------------------------------------------- rendering

def _paint_contact(arm, info, held_objs):
    """Color the skinned meshes: hand red where inside the object, green where touching."""
    held = object_solid(held_objs)
    frame = hand_frame(arm, info)
    s_hand = frame["palm_len"] / REF_PALM
    pen_tol, touch_tol = 0.0015 * s_hand, 0.003 * s_hand
    hand_bones = {info["hand"], *[b for c in info["fingers"].values() for b in c]}
    for obj in _skinned_meshes(arm):
        co, _ = _world_mesh(obj)
        me = obj.data
        if len(co) != len(me.vertices):
            continue
        dom, _ = _groups_by_vertex(obj, hand_bones)
        colors = np.tile(np.array([*BODY, 1.0]), (len(co), 1))
        near = np.nonzero(np.linalg.norm(co - np.array(frame["wrist"]), axis=1) < frame["palm_len"] * 4)[0]
        for i, sd in zip(near, held.signed(co[near])):
            if sd < -pen_tol:
                colors[i] = (*INSIDE, 1.0)
            elif sd <= touch_tol:
                colors[i] = (*TOUCH, 1.0)
            elif dom[i] >= 0:
                colors[i] = (*SKIN, 1.0)
        loops = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", loops)
        attr = me.color_attributes.get("opus_contact") or me.color_attributes.new("opus_contact", "FLOAT_COLOR", "CORNER")
        attr.data.foreach_set("color", colors[loops].ravel())
        me.color_attributes.active_color = attr
    for o in held_objs:
        if o.type == "MESH":
            me = o.data
            attr = me.color_attributes.get("opus_contact") or me.color_attributes.new("opus_contact", "FLOAT_COLOR", "CORNER")
            attr.data.foreach_set("color", np.tile(np.array([*HELD, 1.0]), len(me.loops)))
            me.color_attributes.active_color = attr


def render_views(arm, info, held_objs, out_dir: str, prefix: str, size: int = 420, fp: bool = False) -> list[dict]:
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    _paint_contact(arm, info, held_objs)
    frame = hand_frame(arm, info)
    a, k, n = frame["a"], frame["k"], frame["n"]
    regions = hand_regions(arm, info)
    hand_pts = np.concatenate(list(regions.values()))
    center = hand_pts.mean(axis=0)
    obj_pts = [_world_mesh(o)[0] for o in held_objs if o.type == "MESH"]
    obj_pts = np.concatenate(obj_pts) if obj_pts else np.empty((0, 3))
    near = obj_pts[np.linalg.norm(obj_pts - center, axis=1) < frame["palm_len"] * 2.2] if len(obj_pts) else obj_pts
    pts = np.concatenate([hand_pts, near]) if len(near) else hand_pts
    _render_settings(size)
    _workbench(light="STUDIO", color_type="VERTEX", cavity=True, outline=True)
    cam = _camera()
    shots = [
        ("thumb side", -k + n * 0.5 - a * 0.25, False),
        ("back of hand", -n - k * 0.3 - a * 0.3, False),
        ("pinky side", k + n * 0.3 - a * 0.2, False),
        ("palm side, object hidden", n + a * 0.15 - k * 0.2, True),
    ]
    tiles = []
    for i, (label, d, hide) in enumerate(shots):
        for o in held_objs:
            o.hide_render = hide
        aim_direction(cam, d, pts, zoom=1.0)
        fp_path = os.path.join(out_dir, f"{prefix}_{i}.png")
        scene.render.filepath = fp_path
        bpy.ops.render.render(write_still=True)
        tiles.append({"path": fp_path, "label": label})
    for o in held_objs:
        o.hide_render = False
    if fp:
        eye, s = _eye(arm, info, held_objs)
        cam.data.type = "PERSP"
        cam.data.sensor_fit = "HORIZONTAL"
        cam.data.sensor_width = 36.0
        cam.data.lens = 18.0  # 90 degrees horizontal, a common first-person field of view
        cam.location = eye
        cam.rotation_euler = Vector((0, -1, 0)).to_track_quat("-Z", "Y").to_euler()
        cam.data.clip_start = 0.01 * s
        cam.data.clip_end = 100
        scene.render.resolution_x, scene.render.resolution_y = 640, 360
        scene.display.shading.show_backface_culling = True  # the camera sits inside the head
        fp_path = os.path.join(out_dir, f"{prefix}_fp.png")
        scene.render.filepath = fp_path
        bpy.ops.render.render(write_still=True)
        scene.display.shading.show_backface_culling = False
        tiles.append({"path": fp_path, "label": "first-person view (90° FOV)"})
    return tiles


# ---------------------------------------------------------------- tasks

def _vec(v) -> Vector | None:
    return Vector(v) if v is not None else None


def define(
    path: str,
    object: str,
    name: str = "main",
    part: str = "",
    start: list | None = None,
    end: list | None = None,
    palm_side: list | None = None,
    up: list | None = None,
    center: float = 0.5,
    style: str = "power",
    index: str = "curl",
    thumb: str = "wrap",
    trigger: list | None = None,
    diagonal: float = 0.0,
    point_axis: str = "",
    hand: str = "r",
    out_blend: str = "",
    out_dir: str = "",
    size: int = 420,
) -> dict:
    """Add a grip to ``object``. Points and directions are in world space (meters).

    For pistol-style grips give ``point_axis`` (the object's local axis that should point
    along the forearm: a barrel, a nozzle) and ``hand``; the palm side then follows."""
    assets.load(path)
    scene = bpy.context.scene
    root = scene.objects.get(object)
    if root is None:
        raise ValueError(f"no object named {object!r}; objects: {[o.name for o in scene.objects][:40]}")
    src = scene.objects.get(part) if part else root
    if src is None:
        raise ValueError(f"no object named {part!r} for the handle")
    pts, polys = _world_mesh(src) if src.type == "MESH" else (np.empty((0, 3)), [])
    if start is not None and end is not None:
        p0, p1 = Vector(start), Vector(end)
    else:
        if len(pts) < 4:
            raise ValueError("give start and end points, or a mesh part to fit the handle to")
        c = pts.mean(axis=0)
        evals, evecs = np.linalg.eigh(np.cov((pts - c).T))
        e1 = evecs[:, np.argmax(evals)]
        proj = (pts - c) @ e1
        p0, p1 = Vector(c + e1 * proj.min()), Vector(c + e1 * proj.max())
    hint = Vector(up) if up is not None else Vector((0, 0, 1))
    if (p1 - p0).dot(hint) < 0:
        p0, p1 = p1, p0
    d = (p1 - p0).normalized()
    length = (p1 - p0).length
    C = p0.lerp(p1, center)
    if palm_side is None and point_axis:
        # the object's x axis maps to the forearm direction for a right hand and against it
        # for a left hand (the hand frames are mirror images)
        aim = (root.matrix_world.to_quaternion() @ Vector(AXES[point_axis])).normalized()
        x_want = aim - d * aim.dot(d)
        if x_want.length < 1e-3:
            raise ValueError("point_axis runs along the handle; give palm_side instead")
        x_want.normalize()
        palm_side = list(x_want.cross(d) * (1 if hand == "r" else -1))
    ps = Vector(palm_side) if palm_side is not None else Vector((0, 1, 0))
    p = ps - d * ps.dot(d)
    if p.length < 1e-3:
        p = Vector((1, 0, 0)) - d * d.x
    p.normalize()
    radius, palm_offset = 0.02, None
    if len(pts) and polys:
        t = (pts - np.array(p0)) @ np.array(d)
        mid = (t > length * 0.15) & (t < length * 0.85)
        radial = _segment_dist(pts[mid], p0, p1) if mid.any() else _segment_dist(pts, p0, p1)
        radius = float(np.median(radial)) if len(radial) else radius
        bvh = BVHTree.FromPolygons([Vector(v) for v in pts], polys)
        hit, *_ = bvh.ray_cast(C, p, length * 4)
        if hit is not None:
            palm_offset = (hit - C).length
    x = d.cross(p).normalized()
    for o in list(scene.objects):
        if o.type == "EMPTY" and o.name.startswith(f"SOCKET_grip_{name}") and o.parent == root:
            bpy.data.objects.remove(o)
    empty = bpy.data.objects.new(f"SOCKET_grip_{name}", None)
    empty.empty_display_type = "ARROWS"
    empty.empty_display_size = max(length * 0.5, 0.02)
    for coll in root.users_collection:
        coll.objects.link(empty)
    empty.parent = root
    empty.matrix_parent_inverse = root.matrix_world.inverted()
    empty.matrix_world = Matrix.Translation(C) @ Matrix((x, d, p)).transposed().to_4x4()
    bpy.context.view_layer.update()
    diagonal = diagonal or (10.0 if style == "pistol" else 20.0)
    props = {"radius": round(radius, 5), "palm_offset": round(palm_offset or radius, 5), "length": round(length, 5),
             "style": style, "index": index, "thumb": thumb, "diagonal": diagonal, "hand": hand}
    if trigger is not None:
        props["trigger"] = list(empty.matrix_world.inverted() @ Vector(trigger))
    empty["opus_grip"] = json.dumps(props)
    out_blend = out_blend or (path if path.lower().endswith(".blend") else os.path.splitext(path)[0] + "_grips.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    tiles = _render_grip(root, C, d, p, length, radius, props, empty, out_dir, size) if out_dir else []
    return {"object": root.name, "grip": empty.name, "file": out_blend, "center_m": [round(v, 4) for v in C],
            "axis": [round(v, 3) for v in d], "palm_side": [round(v, 3) for v in p], **props, "tiles": tiles}


def _render_grip(root, C, d, p, length, radius, props, empty, out_dir, size) -> list[dict]:
    """Show the grip: handle axis (blue), palm side (red arrow), thumb end (green arrow)."""
    import bmesh

    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    markers = []

    def marker(name, color, build):
        bm = bmesh.new()
        build(bm)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        scene.collection.objects.link(o)
        o.color = (*color, 1.0)
        markers.append(o)

    def cyl(bm, a, b, r):
        v = b - a
        rot = v.to_track_quat("Z", "Y").to_matrix().to_4x4()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=r, radius2=r, depth=v.length,
                              matrix=Matrix.Translation((a + b) / 2) @ rot)

    def arrow(bm, a, b, r):
        v = b - a
        cyl(bm, a, a + v * 0.7, r)
        rot = v.to_track_quat("Z", "Y").to_matrix().to_4x4()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=r * 2.5, radius2=0, depth=v.length * 0.3,
                              matrix=Matrix.Translation(a + v * 0.85) @ rot)

    w = max(radius * 0.08, length * 0.008)
    half = d * (length / 2)
    marker("opus_axis", (0.2, 0.45, 1.0), lambda bm: cyl(bm, C - half * 1.15, C + half * 1.15, w))
    marker("opus_palm", (1.0, 0.25, 0.2), lambda bm: arrow(bm, C, C + p * (props["palm_offset"] + length * 0.35), w))
    marker("opus_up", (0.25, 0.85, 0.3), lambda bm: arrow(bm, C + half, C + half + d * length * 0.35, w))
    if props.get("trigger") is not None:
        T = empty.matrix_world @ Vector(props["trigger"])
        marker("opus_trigger", (1.0, 0.85, 0.1),
               lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=w * 2.5, matrix=Matrix.Translation(T)))
    objs = [o for o in _hierarchy(root) if o.type == "MESH"]
    for o in objs:
        o.color = (0.78, 0.78, 0.8, 1.0)
    pts = np.concatenate([_world_mesh(o)[0] for o in objs + markers])
    near = pts[np.linalg.norm(pts - np.array(C), axis=1) < length * 1.6]
    _render_settings(size)
    _workbench(light="STUDIO", color_type="OBJECT", cavity=True, outline=True)
    scene.display.shading.show_xray = True
    scene.display.shading.xray_alpha = 0.55
    cam = _camera()
    x = d.cross(p)
    tiles = []
    for i, (label, view) in enumerate([("side", x), ("palm side", p + x * 0.4), ("3/4", x + p * 0.6 + d * 0.4)]):
        aim_direction(cam, view, near if len(near) > 10 else pts)
        fp = os.path.join(out_dir, f"grip_{i}.png")
        scene.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        tiles.append({"path": fp, "label": label})
    scene.display.shading.show_xray = False
    return tiles


def _append_objects(path: str) -> list:
    """Bring every object of another file into this scene; returns the new objects."""
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.context.scene.objects)
    had = set(bpy.data.materials), set(bpy.data.images)
    coll = bpy.data.collections.new("held")
    bpy.context.scene.collection.children.link(coll)
    if ext == ".blend":
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None and o.type not in ("CAMERA", "LIGHT"):
                coll.objects.link(o)
    else:
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=path)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=path)
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=path)
        else:
            raise ValueError(f"unsupported file type: {ext}")
    _merge_copies(bpy.data.images, had[1], _image_key)
    _merge_copies(bpy.data.materials, had[0], _material_key)
    bpy.context.view_layer.update()
    return [o for o in bpy.context.scene.objects if o not in before]


def _merge_copies(blocks, had: set, key) -> None:
    """Fold each new ``<name>.NNN`` datablock into the ``<name>`` this file already had when the
    two are the same (``key``): appending a prop that shares a material with the rig would
    otherwise leave both, and the material budget counts two."""
    for new in [b for b in blocks if b not in had]:
        base, dot, num = new.name.rpartition(".")
        old = blocks.get(base) if dot and num.isdigit() and len(num) >= 3 else None
        if old is not None and old in had and key(old) == key(new):
            new.user_remap(old)
            blocks.remove(new)


def _image_key(img) -> tuple:
    path = os.path.normcase(os.path.normpath(bpy.path.abspath(img.filepath))) if img.filepath else ""
    packed = img.packed_file.size if img.packed_file is not None else None
    return img.source, path, packed, tuple(img.size)


def _value(v):
    if isinstance(v, float):
        return round(v, 5)
    if hasattr(v, "__len__") and not isinstance(v, str):
        return tuple(_value(x) for x in v)
    return v if isinstance(v, (int, bool, str)) else None


def _material_key(mat) -> tuple:
    """What a material looks like: its node types, the images they use and their settings."""
    nodes = []
    if mat.node_tree is not None:
        for n in mat.node_tree.nodes:
            ins = tuple(_value(getattr(s, "default_value", None)) for s in n.inputs if not s.is_linked)
            img = getattr(n, "image", None)
            nodes.append((n.bl_idname, img.as_pointer() if img is not None else 0, ins))
        links = len(mat.node_tree.links)
    else:
        links = 0
    return tuple(sorted(nodes, key=repr)), links, _value(tuple(mat.diffuse_color))


def hold(
    rig_path: str,
    object_path: str = "",
    object: str = "",
    grip: str = "",
    side: str = "r",
    pose: str = "rest",
    move: str = "object",
    aim_axis: str = "-Y",
    up_axis: str = "+Z",
    offset: list | None = None,
    index: str = "",
    thumb: str = "",
    armature: str = "",
    out_blend: str = "",
    out_dir: str = "",
    size: int = 420,
) -> dict:
    """Put ``object`` in the ``side`` hand of the rig. ``move`` "object" brings the object to
    the hand; "hand" reaches the hand to the object where it is (a second, supporting hand)."""
    if side not in SIDE_WORDS:
        raise ValueError("side must be r or l")
    assets.load(rig_path)
    scene = bpy.context.scene
    new_objs = _append_objects(object_path) if object_path and os.path.abspath(object_path) != os.path.abspath(rig_path) else []
    pool = new_objs or list(scene.objects)
    empties = _grip_empties(pool)
    if object:
        root = scene.objects.get(object)
        if root is None:
            raise ValueError(f"no object named {object!r}")
        empties = [e for e in empties if root in _ancestors(e)]
    if grip:
        empties = [e for e in empties if _grip_name(e) == grip]
    if not empties:
        raise ValueError("no grip found: add one with grip_define (an empty named SOCKET_grip_<name> on the object)")
    empty = empties[0]
    root = scene.objects.get(object) if object else _top(empty)
    arm = _armature(scene.objects, armature)
    info = find_hand(arm, side)
    held = [o for o in _hierarchy(root) if o.type == "MESH"]
    props = grip_props(empty)
    if index:
        props["index"] = index
    if thumb:
        props["thumb"] = thumb
    frame = hand_frame(arm, info)
    info["scale"] = frame["palm_len"] / REF_PALM
    report = {"side": side, "object": root.name, "grip": empty.name, "pose": pose, "warnings": list(info["warnings"])}
    # where the object sits relative to the hand, worked out on the current pose
    hand_now = _world_bone(arm, info["hand"])[0]
    placed = placement(arm, info, frame, root, empty, props)
    rel = hand_now.inverted() @ placed
    if move == "hand":
        report["reach_error_m"] = round(reach(arm, info, root.matrix_world @ rel.inverted(), _pole(info, side)), 4)
    else:
        if pose != "rest":
            root.matrix_world = placed
            bpy.context.view_layer.update()
            target = object_target(arm, info, root, pose, aim_axis, up_axis, grip_props(empty), offset)
            report["reach_error_m"] = round(reach(arm, info, target @ rel.inverted(), _pole(info, side)), 4)
        hand_now = _world_bone(arm, info["hand"])[0]
        root.matrix_world = hand_now @ rel
    bpy.context.view_layer.update()
    props = grip_props(empty)
    if index:
        props["index"] = index
    if thumb:
        props["thumb"] = thumb
    sc = info["scale"]
    frame = hand_frame(arm, info)
    if move != "hand" and props.get("index") == "trigger" and props.get("trigger") is not None:
        report["trigger_slide_mm"] = round(align_trigger(arm, info, frame, root, empty) * 1000, 1)
    # seat and close twice: closing moves the skin around the palm a little, so the second
    # pass settles the handle back onto the palm and re-closes the fingers from there
    report["seated_mm"] = 0.0
    for attempt in range(4):
        frame = hand_frame(arm, info)
        if move != "hand":  # later seats are measured with the fingers closed
            report["seated_mm"] += round(seat(arm, info, frame, root, held, 0.0005 * sc, 0.0003 * sc, 0.002 * sc) * 1000, 1)
        if attempt:
            _reset_fingers(arm, info)
        props = grip_props(empty) | {k: v for k, v in (("index", index), ("thumb", thumb)) if v}
        report["fingers"] = close_hand(arm, info, hand_frame(arm, info), object_solid(held), props)
        if move == "hand" or measure(arm, info, held)["regions"]["palm"]["closest_mm"] <= 1.5 * sc:
            break
    report["seated_mm"] = round(report["seated_mm"], 1)
    if move != "hand":
        report["weapon_bone"] = _weapon_bone(arm, info, root)
    posed = [b for c in info["fingers"].values() for b in c]
    if pose != "rest" or move == "hand":
        posed += [b for b in (info["upperarm"], info["lowerarm"], info["hand"]) if b]
    frame = hand_frame(arm, info)
    aim_world = (root.matrix_world.to_quaternion() @ Vector(AXES[aim_axis])).normalized()
    report["aim_vs_hand_deg"] = round(math.degrees(frame["a"].angle(aim_world)), 1)
    if info["lowerarm"]:
        fa = (_world_bone(arm, info["hand"])[1] - _world_bone(arm, info["lowerarm"])[1]).normalized()
        report["wrist_bend_deg"] = round(math.degrees(fa.angle(frame["a"])), 1)
    action = f"Grip_{root.name}_{side}"
    _key_pose(arm, posed, action)
    report["action"] = action
    m = measure(arm, info, held)
    report["contact"] = m
    lines = summarize(m, side)
    if report.get("reach_error_m", 0) > 0.01 * info["scale"]:
        lines.insert(1, f"  the arm can't reach: the hand stops {report['reach_error_m'] * 100:.0f} cm short of the grip")
    report["text"] = "\n".join(lines)
    out_blend = out_blend or os.path.splitext(rig_path)[0] + f"_holding_{root.name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    report["file"] = out_blend
    if out_dir:
        report["tiles"] = render_views(arm, info, held, out_dir, "hold", size, fp=pose.startswith("fp"))
    return report


def _reset_fingers(arm, info):
    for chain in info["fingers"].values():
        for b in chain:
            pb = arm.pose.bones[b]
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
            pb.rotation_axis_angle = (0, 0, 1, 0)
    bpy.context.view_layer.update()


def _ancestors(o) -> list:
    out = []
    while o is not None:
        out.append(o)
        o = o.parent
    return out


def _top(o):
    while o.parent is not None and o.parent.type != "ARMATURE":
        o = o.parent
    return o


def _pole(info, side) -> Vector:
    """Elbows point down and out."""
    out = Vector((-1, 0, 0)) if side == "r" else Vector((1, 0, 0))
    return out * 0.5 + Vector((0, 0, -1))


def check(path: str, side: str = "r", object: str = "", armature: str = "", out_dir: str = "", size: int = 420, fp: bool = False) -> dict:
    """Measure how a hand holds an object in any file (rig and object already placed)."""
    assets.load(path)
    scene = bpy.context.scene
    arm = _armature(scene.objects, armature)
    sides = ["r", "l"] if side == "both" else [side]
    skinned = set(_skinned_meshes(arm))
    report = {"sides": {}}
    for sd in sides:
        info = find_hand(arm, sd)
        if object:
            root = scene.objects.get(object)
            if root is None:
                raise ValueError(f"no object named {object!r}")
        else:
            root = _nearest_object(arm, info, skinned)
        held = [o for o in _hierarchy(root) if o.type == "MESH" and o not in skinned]
        m = measure(arm, info, held)
        entry = {"object": root.name, "contact": m, "text": "\n".join(summarize(m, sd)), "warnings": info["warnings"]}
        if out_dir:
            entry["tiles"] = render_views(arm, info, held, out_dir, f"check_{sd}", size, fp=fp)
        report["sides"][sd] = entry
    report["text"] = "\n".join(e["text"] for e in report["sides"].values())
    return report


def _nearest_object(arm, info, skinned):
    frame = hand_frame(arm, info)
    palm = frame["wrist"] + frame["a"] * frame["palm_len"] * 0.6
    best, best_d = None, float("inf")
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o in skinned or o.hide_render:
            continue
        solid = object_solid([o])
        if solid is None:
            continue
        loc, *_ = solid.bvh.find_nearest(palm)
        if loc is not None and (loc - palm).length < best_d:
            best, best_d = o, (loc - palm).length
    if best is None:
        raise ValueError("no object near the hand; name it with object=")
    return _top(best)
