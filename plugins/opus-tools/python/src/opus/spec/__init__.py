"""The spec language (docs/S0B_DESIGN.md §5). This file must never import anything (K1): Blender
has no pydantic, and a package __init__ that imports it breaks every submodule import there."""
