"""MCP tools and CLI verbs of the spec compiler, one module per work package (docs/S0B_DESIGN.md
§4.9, §15, K13).

Each module in ``MODULES`` defines ``register(tool)`` (registers its MCP tools with the server's
``_tool`` decorator), ``add_cli(sub, groups)`` (adds its verbs to the shared groups, or top-level
commands to ``sub``) and ``run_cli(args) -> int | None`` (runs a parsed command it owns and returns
the exit code, or None when the command is not its own). The shared CLI groups are created here
once, because argparse refuses a second ``spec`` subparser. Tools import their implementation
lazily inside the function, as ``opus.mcp_server`` does.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

MODULES = ("spec", "preview", "build", "check", "edit", "data")
GROUPS = {"spec": "spec_cmd", "gates": "gates_cmd", "data": "data_cmd"}   # group -> argparse dest
GROUP_HELP = {"spec": "the spec compiler: new, validate, resolve, preview, build, check, edit",
              "gates": "gate harness (maintainers): inject, calibrate, fixtures",
              "data": "fact tables and data packs: fetch, build, list"}


def modules() -> list:
    return [importlib.import_module(f"opus.tools.{m}") for m in MODULES]


def register_all(tool) -> None:
    """for m in MODULES: import opus.tools.<m>; m.register(tool)"""
    for m in modules():
        m.register(tool)


def add_cli_all(sub) -> dict:
    """Create each group once (sub.add_parser(g).add_subparsers(dest=GROUPS[g], required=True)),
    then m.add_cli(sub, groups) for every module. Returns the groups."""
    groups = {g: sub.add_parser(g, help=GROUP_HELP[g]).add_subparsers(dest=dest, required=True)
              for g, dest in GROUPS.items()}
    for m in modules():
        m.add_cli(sub, groups)
    return groups


def run_cli(args) -> int | None:
    """The first m.run_cli(args) that returns an int (exit code); None = not ours."""
    for m in modules():
        code = m.run_cli(args)
        if code is not None:
            return int(code)
    return None


def verb(args) -> str:
    """"spec new", "gates inject", "dims": the command a parsed namespace runs (for messages)."""
    cmd = getattr(args, "cmd", "")
    sub = getattr(args, GROUPS[cmd], "") if cmd in GROUPS else ""
    return f"{cmd} {sub}".strip()


# ---------------------------------------------------------------- helpers for the tool modules

def not_built(tool: str, package: str) -> ValueError:
    """The error a stub raises until its package lands."""
    return ValueError(f"{tool} is not built yet ({package})")


def project_path(p: str, must_exist: bool = True) -> Path:
    """``p`` resolved against the project folder ($OPUS_PROJECT_DIR, else the cwd) when relative."""
    q = Path(p).expanduser()
    if not q.is_absolute():
        q = Path(os.environ.get("OPUS_PROJECT_DIR") or os.getcwd()) / q
    q = q.resolve()
    if must_exist and not q.exists():
        raise FileNotFoundError(f"{q} does not exist")
    return q


def to_json(data) -> str:
    return json.dumps(data, indent=1, default=str)


def names(text: str) -> list[str]:
    """"a, b,c" -> ["a", "b", "c"]."""
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def emit(data) -> None:
    """Print a CLI result: text as is, anything else as JSON."""
    print(data if isinstance(data, str) else to_json(data))
