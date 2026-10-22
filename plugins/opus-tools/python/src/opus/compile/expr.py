"""Spec expressions (docs/S0B_DESIGN.md §4.4).

An expression is a Python expression parsed with ``ast.parse(mode="eval")`` that may use only:

| Node      | Allowed |
|-----------|---------|
| Constant  | int, float (the validator requires the dim's ``src`` for a literal other than 0.5, 1, 2) |
| Name      | dim names; ``s`` (station 0..1, station-loft params only); ``pi`` |
| Attribute | ``wielder.<measure>``, ``camera.ppm_close``, ``camera.ppm_typical``, ``camera.ppm_far``, ``camera.bevel_close`` (looked up as dotted keys) |
| BinOp     | ``+ - * / **`` (``**`` goes through ``fmath.spow``) |
| UnaryOp   | ``+ -`` |
| Call      | ``min max clamp(x,a,b) lerp(a,b,t) sqrt abs floor ceil`` (positional arguments only) |

Everything else (comparisons, subscripts, lambdas, other attributes, keywords, strings,
booleans) is an ``ExprError``. Values may be floats or numpy arrays (``s`` inside a loft);
arithmetic on arrays stays elementwise and uses only the operations fmath allows.
"""

from __future__ import annotations

import ast
import functools
import math
from collections.abc import Mapping

import numpy as np

from opus.compile import fmath


class ExprError(ValueError):
    """A malformed or disallowed expression, or one that cannot be evaluated."""


CAMERA_ATTRS = ("ppm_close", "ppm_typical", "ppm_far", "bevel_close")
ATTR_BASES = ("wielder", "camera")
FUNCTIONS = {"min": (2, None), "max": (2, None), "clamp": (3, 3), "lerp": (3, 3),
             "sqrt": (1, 1), "abs": (1, 1), "floor": (1, 1), "ceil": (1, 1)}   # name -> (min args, max args)
CONSTANTS = {"pi": math.pi}
STATION = "s"
FREE_LITERALS = (0.5, 1.0, 2.0)  # literals that need no src (§5.3)
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_UNARY = (ast.UAdd, ast.USub)


def _dotted(node: ast.Attribute, text: str) -> str:
    if not isinstance(node.value, ast.Name):
        raise ExprError(f"{text!r}: only wielder.<measure> and camera.<{'|'.join(CAMERA_ATTRS)}> are allowed")
    base, attr = node.value.id, node.attr
    if base == "wielder" and not attr.startswith("_"):
        return f"wielder.{attr}"
    if base == "camera" and attr in CAMERA_ATTRS:
        return f"camera.{attr}"
    raise ExprError(f"{text!r}: attribute {base}.{attr} is not allowed; use wielder.<measure> or "
                    f"camera.<{'|'.join(CAMERA_ATTRS)}>")


def _check(node: ast.AST, text: str) -> None:
    if isinstance(node, ast.Expression):
        _check(node.body, text)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExprError(f"{text!r}: only numbers are allowed as constants, not {node.value!r}")
    elif isinstance(node, ast.Name):
        if node.id in FUNCTIONS:
            raise ExprError(f"{text!r}: {node.id} is a function; call it as {node.id}(...)")
        if node.id.startswith("_"):
            raise ExprError(f"{text!r}: name {node.id!r} is not allowed")
    elif isinstance(node, ast.Attribute):
        _dotted(node, text)
    elif isinstance(node, ast.BinOp):
        if not isinstance(node.op, _BINOPS):
            raise ExprError(f"{text!r}: operator {type(node.op).__name__} is not allowed (+ - * / ** only)")
        _check(node.left, text)
        _check(node.right, text)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _UNARY):
            raise ExprError(f"{text!r}: unary {type(node.op).__name__} is not allowed (+ - only)")
        _check(node.operand, text)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise ExprError(f"{text!r}: only the functions {', '.join(FUNCTIONS)} may be called")
        if node.keywords:
            raise ExprError(f"{text!r}: {node.func.id}() takes positional arguments only")
        lo, hi = FUNCTIONS[node.func.id]
        n = len(node.args)
        if any(isinstance(a, ast.Starred) for a in node.args) or n < lo or (hi is not None and n > hi):
            want = f"{lo}" if lo == hi else f"at least {lo}"
            raise ExprError(f"{text!r}: {node.func.id}() takes {want} argument(s), got {n}")
        for a in node.args:
            _check(a, text)
    else:
        raise ExprError(f"{text!r}: {type(node).__name__} is not allowed in an expression")


@functools.lru_cache(maxsize=4096)
def parse(text: str) -> ast.Expression:
    """The checked AST of ``text`` (cached; never mutate it). Raises ExprError."""
    if not isinstance(text, str) or not text.strip():
        raise ExprError(f"an expression is a non-empty string; got {text!r}")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"{text!r}: {e.msg}") from None
    _check(tree, text)
    return tree


def _walk_names(node: ast.AST, out: set[str]) -> None:
    if isinstance(node, ast.Attribute):
        out.add(_dotted(node, ""))
        return
    if isinstance(node, ast.Name):
        if node.id not in CONSTANTS:
            out.add(node.id)
        return
    if isinstance(node, ast.Call):
        for a in node.args:
            _walk_names(a, out)
        return
    for child in ast.iter_child_nodes(node):
        _walk_names(child, out)


def names(text: str) -> set[str]:
    """Dotted names used (dims, ``s``, ``wielder.x``, ``camera.y``); function names and the
    constant ``pi`` are not names."""
    out: set[str] = set()
    _walk_names(parse(text), out)
    return out


def literals(text: str) -> list[float]:
    """The numeric literals in ``text`` (a unary minus is not part of the literal), in order."""
    return [float(n.value) for n in ast.walk(parse(text)) if isinstance(n, ast.Constant)]


def unsourced_literals(text: str) -> list[float]:
    """Literals other than 0.5, 1 and 2 (they need the dim's ``src``, §5.3)."""
    return [v for v in literals(text) if v not in FREE_LITERALS]


def _isarr(v) -> bool:
    return isinstance(v, np.ndarray)


def _num(v):
    return v if _isarr(v) else float(v)


def _call(name: str, args: list):
    arr = any(_isarr(a) for a in args)
    if name in ("min", "max"):
        if not arr:
            return float(min(args) if name == "min" else max(args))
        fn = np.minimum if name == "min" else np.maximum
        out = np.asarray(args[0], dtype=np.float64)
        for a in args[1:]:
            out = fn(out, a)
        return out
    if name == "clamp":
        x, a, b = args
        if not arr:
            return float(min(max(x, a), b))
        return np.minimum(np.maximum(x, a), b)
    if name == "lerp":
        a, b, t = args
        return _num(a + (b - a) * t)
    (x,) = args
    if name == "abs":
        return np.abs(x) if arr else float(abs(x))
    if name == "sqrt":
        if arr:
            if np.any(x < 0):
                raise ExprError("sqrt of a negative number")
            return np.sqrt(x)
        if x < 0:
            raise ExprError(f"sqrt of a negative number ({x})")
        return math.sqrt(x)
    if name == "floor":
        return np.floor(x) if arr else float(math.floor(x))
    if name == "ceil":
        return np.ceil(x) if arr else float(math.ceil(x))
    raise ExprError(f"unknown function {name}")  # unreachable after _check


def _eval(node: ast.AST, env: Mapping, text: str):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env, text)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, (ast.Name, ast.Attribute)):
        key = node.id if isinstance(node, ast.Name) else _dotted(node, text)
        if key in CONSTANTS:
            return CONSTANTS[key]
        if key not in env:
            raise ExprError(f"{text!r}: unknown name {key!r}")
        v = env[key]
        return np.asarray(v, dtype=np.float64) if _isarr(v) else float(v)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, env, text)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, env, text), _eval(node.right, env, text)
        op = node.op
        if isinstance(op, ast.Add):
            return a + b
        if isinstance(op, ast.Sub):
            return a - b
        if isinstance(op, ast.Mult):
            return a * b
        if isinstance(op, ast.Div):
            if not _isarr(b) and b == 0.0:
                raise ExprError(f"{text!r}: division by zero")
            if _isarr(b) and np.any(b == 0.0):
                raise ExprError(f"{text!r}: division by zero")
            return a / b
        try:
            return fmath.spow(a, b)
        except (ValueError, OverflowError) as e:
            raise ExprError(f"{text!r}: {e}") from None
    if isinstance(node, ast.Call):
        return _call(node.func.id, [_eval(a, env, text) for a in node.args])
    raise ExprError(f"{text!r}: {type(node).__name__} is not allowed")  # unreachable after _check


def evaluate(text: str, env: Mapping[str, float | np.ndarray]) -> float | np.ndarray:
    """Evaluate ``text`` with ``env`` (dim names and dotted keys such as "wielder.hand_length"
    -> float or array). Scalars come back as Python floats, arrays as float64 arrays."""
    tree = parse(text)
    try:
        out = _eval(tree, env, text)
    except ExprError:
        raise
    except (ArithmeticError, ValueError, TypeError) as e:
        raise ExprError(f"{text!r}: {e}") from None
    return np.asarray(out, dtype=np.float64) if _isarr(out) else float(out)
