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
    "grip_define", "grip_hold", "grip_check", "readability_check", "lineup_sheet", "ab_sheet",
    "licence_check", "run_log", "run_stats",
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
    assert EXPECTED == names  # every tool, so a new one is documented here and in the README
    inspect_result = results[0]
    assert not inspect_result.is_error
    kinds = [c.type for c in inspect_result.content]
    assert kinds[0] == "image" and "text" in kinds
    assert '"upscale_factor": 3' in inspect_result.content[1].text
    assert results[1].content[0].type == "image"
    assert "Created" in results[2].content[0].text
    assert '"styles": [\n  "pixel",\n  "lowpoly"' in results[3].content[0].text
    assert '"camera_active"' in results[3].content[0].text and '"FALLBACK view-model' in results[3].content[0].text
    assert sprite.exists()


def test_bad_path_is_a_tool_error(tmp_path):
    _, results = anyio.run(_session_call, tmp_path, [("sprite_inspect", {"path": "nope.png"})])
    assert results[0].is_error


def test_bad_arguments_reach_the_caller_with_their_message(tmp_path):
    """Any exception but ToolError reaches the client only as "Error executing tool <name>"."""
    (tmp_path / "project.godot").write_text("")
    save_rgba(blob(16), tmp_path / "a.png")
    (tmp_path / "opus.project.yaml").write_text("camera: {distances: {godot_tp: [1, 2]}}\n", encoding="utf-8")
    _, results = anyio.run(_session_call, tmp_path, [
        ("lineup_sheet", {"images": "a.png", "exemplars": ""}),
        ("lineup_sheet", {"images": "a.png", "exemplars": "a.png, a.png", "camera": "ue_tp_108", "size_m": 1.0}),
        ("ledger_record", {"asset": "a.png", "source": "x", "inputs": [{"source": "y", "licence_id": "MIT",
                                                                       "flags": ["noncommercial"]}]}),
        ("project_bible", {}),
        ("sprite_inspect", {"path": "nope.png"}),
    ])
    texts = [r.content[0].text for r in results]
    assert results[0].is_error and "give 2-3 human-made exemplars" in texts[0]
    assert results[1].is_error and "unknown camera profile 'ue_tp_108'" in texts[1]
    assert results[2].is_error and "unknown flags ['noncommercial']" in texts[2]
    assert not results[3].is_error  # a malformed camera block leaves the rest of the bible readable
    assert '"camera_active"' in texts[3] and "[close, typical, far]" in texts[3]
    assert results[4].is_error and "does not exist" in texts[4]


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
            ("readability_check", {"path": "bodies/hero.blend", "distances": "3.5, 15", "defining": "head, hand_l"}),
            ("blind_read_sheet", {"path": "bodies/hero.blend", "game_size": True, "distances": "15"}),
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
    assert results[5].content[0].type == "image"
    assert "Camera godot_tp" in results[5].content[1].text and "* head:" in results[5].content[1].text
    assert "do not add what the model is" in results[6].content[0].text


def test_grip_tools_take_axis_names(tmp_path, monkeypatch):
    """up="+Z" reaches Blender as [0, 0, 1]; a direction that is neither an axis nor x,y,z is a
    message the caller can act on."""
    from PIL import Image as PILImage

    from mcp.server.mcpserver.exceptions import ToolError
    from opus import mcp_server
    from opus.threed import grip

    monkeypatch.delenv("OPUS_PROJECT_DIR", raising=False)
    (tmp_path / "project.godot").write_text("")
    blend = tmp_path / "axe.blend"
    blend.write_bytes(b"")
    tile = tmp_path / "tile.png"
    PILImage.new("RGB", (32, 32)).save(tile)
    calls = []

    def fake_run_task(task, params, timeout=0):
        calls.append((task, params))
        return {"object": "axe", "grip": "SOCKET_grip_main", "length": 0.4, "radius": 0.015, "index": "curl",
                "thumb": "wrap", "contact": {"verdict": "good grip"}, "text": "good grip", "file": str(blend),
                "tiles": [{"path": str(tile), "label": "front"}]}

    monkeypatch.setattr(grip, "run_task", fake_run_task)
    mcp_server.grip_define(path=str(blend), object="haft", up="+Z", palm_side="-X", trigger="0,-0.05,0.1")
    assert calls[-1][1]["up"] == [0, 0, 1] and calls[-1][1]["palm_side"] == [-1, 0, 0]
    assert calls[-1][1]["trigger"] == [0, -0.05, 0.1]
    mcp_server.grip_hold(rig=str(blend), object_path=str(blend), pose="fp_hip", aim_axis="x", offset="0.1, 0.15, 0.25")
    assert calls[-1][1]["offset"] == [0.1, 0.15, 0.25] and calls[-1][1]["aim_axis"] == "+X"
    with pytest.raises(ToolError, match=r"up: give an axis such as \+Z or -X, or x,y,z"):
        mcp_server.grip_define(path=str(blend), object="haft", up="+W")
    with pytest.raises(ToolError, match="offset: give three numbers"):
        mcp_server.grip_hold(rig=str(blend), offset="-Y")


def test_docstrings_say_what_callers_need():
    from opus import mcp_server

    assert "LicenseRef-Own-Work" in mcp_server.ledger_record.__doc__
    assert "run=<id from run_start>" in mcp_server.run_log.__doc__
    assert "ear tips for" in mcp_server.body_blockout.__doc__ and "withers_m" in mcp_server.body_blockout.__doc__
    assert "eye-to-sight distance" in mcp_server.grip_hold.__doc__
