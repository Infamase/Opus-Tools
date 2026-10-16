"""End-to-end: start the MCP server over stdio like Claude does, list tools, call them."""

import os
import sys

import anyio
import pytest

from mcp import ClientSession, StdioServerParameters, stdio_client
from opus.imaging import save_rgba, upscale
from sprites import blob, with_defects

EXPECTED = {
    "sprite_inspect", "pixel_cleanup", "palette_ramp", "palette_apply", "palette_swap",
    "lookdev_sheet", "mesh_lint", "project_bible", "ledger_record", "make_credits", "opus_doctor",
    "body_blockout", "look_at", "model_report", "proportion_check", "reference_match", "blind_read_sheet",
}


async def _session_call(tmp_path, calls):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "opus.mcp_server"],
        env={**os.environ, "OPUS_PROJECT_DIR": str(tmp_path)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            results = [await session.call_tool(name, args) for name, args in calls]
            return {t.name for t in tools.tools}, results


def test_server_lists_tools_and_returns_images(tmp_path):
    (tmp_path / "project.godot").write_text("")
    sprite = save_rgba(upscale(with_defects(blob(32)), 3), tmp_path / "hero.png")
    names, results = anyio.run(
        _session_call,
        tmp_path,
        [
            ("sprite_inspect", {"path": "hero.png"}),
            ("palette_ramp", {"base_color": "#3a7d44", "steps": 5}),
            ("project_bible", {"action": "init", "project": "Test", "styles": "pixel, lowpoly"}),
            ("project_bible", {}),
        ],
    )
    assert EXPECTED <= names
    inspect_result = results[0]
    assert not inspect_result.is_error
    kinds = [c.type for c in inspect_result.content]
    assert kinds[0] == "image" and "text" in kinds
    assert '"upscale_factor": 3' in inspect_result.content[1].text
    assert results[1].content[0].type == "image"
    assert "Created" in results[2].content[0].text
    assert '"styles": [\n  "pixel",\n  "lowpoly"' in results[3].content[0].text
    assert sprite.exists()


def test_bad_path_is_a_tool_error(tmp_path):
    _, results = anyio.run(_session_call, tmp_path, [("sprite_inspect", {"path": "nope.png"})])
    assert results[0].is_error


def _has_blender() -> bool:
    from opus.blender.runner import BlenderNotFound, find_blender

    try:
        find_blender()
        return True
    except BlenderNotFound:
        return False


@pytest.mark.skipif(not _has_blender(), reason="Blender not found (set OPUS_BLENDER)")
def test_3d_understanding_tools_over_mcp(tmp_path):
    (tmp_path / "project.godot").write_text("")
    _, results = anyio.run(
        _session_call,
        tmp_path,
        [
            ("body_blockout", {"archetype": "humanoid", "preset": "stylized", "target_tris": 3000, "out_path": "bodies/hero.blend"}),
            ("look_at", {"path": "bodies/hero.blend", "views": "30,10; 180,0", "render_pass": "parts"}),
            ("model_report", {"path": "bodies/hero.blend"}),
            ("proportion_check", {"path": "bodies/hero.blend", "preset": "stylized"}),
            ("blind_read_sheet", {"path": "bodies/hero.blend"}),
        ],
    )
    for r in results:
        assert not r.is_error, r.content[0].text
    assert (tmp_path / "bodies" / "hero.blend").exists()
    for r in results[:4]:
        assert r.content[0].type == "image"
    assert '"landmarks_m"' in results[0].content[1].text
    assert "one per bone region" in results[2].content[1].text
    assert "Closest canon: stylized" in results[3].content[1].text
    assert "do not add what the model is" in results[4].content[0].text
    assert "hero" not in results[4].content[0].text.split("Prompt")[0].rsplit("/", 1)[-1]
