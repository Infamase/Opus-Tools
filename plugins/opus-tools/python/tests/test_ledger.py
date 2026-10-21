"""Provenance ledger: licence IDs and flags, lineage, export policy and CREDITS.md."""

import json
import os
import sys

import anyio
import pytest

from opus import ledger
from opus.cli import main as cli
from opus.ledger import check, classify, flags_for, record, write_credits


# ---------------------------------------------------------------- classify

def test_the_six_misfiring_strings_classify_correctly():
    # The old substring test flagged all but the last as non-commercial and missed the last.
    assert classify("QAL v1.0 licence") == ("LicenseRef-QAL-1.0", ["no-redistribute-as-asset"])
    assert classify("Copernicus free licence with credit") == ("LicenseRef-Copernicus", ["attribution"])
    # CMU-style wording describes permissions but names no licence, and the same words appear
    # in unrelated terms. A wrong permissive ID would pass export silently, while unknown
    # blocks until someone records the ID, so it stays unknown. CMU's full sentence, which
    # does identify its terms, is an alias.
    assert classify("research and commercial projects") == (None, ["unknown"])
    assert classify("Free for use in research and commercial projects worldwide") == ("LicenseRef-CMU-Mocap", [])
    assert classify("CC BY 4.0 … since 2026") == ("CC-BY-4.0", ["attribution"])
    assert classify("CC BY 4.0, including derived maps since 2026") == ("CC-BY-4.0", ["attribution"])
    assert "nc" not in classify("Royalty-free incl. games")[1]
    assert classify("NVIDIA Source Code License") == ("LicenseRef-NVIDIA-SCL", ["nc"])


def test_aliases_match_whole_tokens_only():
    for text in ("licence", "since", "including", "incl.", "personal research", "Mixamorig skeleton", "BSDF"):
        assert classify(text) == (None, ["unknown"]), text
    assert classify("CC BY-NC 4.0")[1] == ["attribution", "nc"]
    assert classify("cc-by-nc-nd-4.0")[0] == "CC-BY-NC-ND-4.0"
    assert classify("Attribution-NonCommercial-ShareAlike 4.0 International")[0] == "CC-BY-NC-SA-4.0"
    assert classify("CC BY-NC")[0] == "CC-BY-NC-4.0"  # the variant out-lengths "CC BY"
    assert classify("BSD 2-Clause")[0] == "BSD-2-Clause" and classify("BSD")[0] == "BSD-3-Clause"
    assert classify("GPL-2.0+")[0] == "GPL-2.0-or-later" and classify("GPL-2.0")[0] == "GPL-2.0-only"
    assert classify("public domain (US Gov)")[0] == "LicenseRef-US-Gov-PD"
    assert classify('US Gov, "cleared for unlimited public release"')[0] == "LicenseRef-US-Gov-Public-Release"
    assert classify("US Gov public-use data, NCHS data-use terms (statistical use only)")[0] == "LicenseRef-NCHS-Data-Use"
    assert classify("Sonniss GDC bundle") == ("LicenseRef-Sonniss-GDC", ["no-redistribute-as-asset"])


def test_several_licences_in_one_text():
    assert classify("MIT or Apache-2.0") == ("MIT OR Apache-2.0", ["attribution"])
    lid, flags = classify("ESA WorldCover CC BY 4.0 and Copernicus DEM")
    assert lid == "CC-BY-4.0 AND LicenseRef-Copernicus" and flags == ["attribution"]
    assert classify("CC BY 4.0 except the textures, which are CC BY-NC-SA")[1] == ["attribution", "nc", "sa"]


def test_licence_table():
    table = ledger.licences()
    for lid in ("CC0-1.0", "CC-BY-3.0", "CC-BY-4.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0", "MIT",
                "BSD-3-Clause", "Apache-2.0", "GPL-3.0-or-later", "AGPL-3.0-only", "LicenseRef-QAL-1.0",
                "LicenseRef-Copernicus", "LicenseRef-CMU-Mocap", "LicenseRef-Sonniss-GDC", "LicenseRef-NVIDIA-SCL",
                "LicenseRef-US-Gov-PD", "LicenseRef-NCHS-Data-Use", "LicenseRef-Mixamo", "LicenseRef-Unknown"):
        assert lid in table, lid
        assert table[lid]["name"] and isinstance(table[lid]["flags"], list)
        assert classify(lid)[0] == lid and classify(table[lid]["name"])[0] == lid
    for lid, e in table.items():  # the ledger reads flags from here, never from text
        for alias in e.get("aliases") or []:
            assert classify(alias)[0] == lid, (lid, alias)
    assert classify("AGPL-3.0")[0] == "AGPL-3.0-only"
    assert flags_for("CC-BY-NC-4.0 OR MIT") == ["attribution", "nc"]
    assert flags_for("GPL-2.0-or-later WITH Classpath-exception-2.0") == ["attribution", "sa"]
    assert flags_for("LicenseRef-Nope") == ["unknown"] and flags_for("") == ["unknown"]
    # code licences bind copies of the code, not what a tool makes
    assert flags_for("GPL-3.0-or-later", tool=True) == [] and flags_for("LicenseRef-NVIDIA-SCL", tool=True) == ["nc"]


# ---------------------------------------------------------------- ledger

@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.godot").write_text("", encoding="utf-8")
    for name in ("base.glb", "derived.glb", "anim.glb", "dem.png", "font.ttf", "pal.hex", "kit.glb", "clip.fbx"):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def test_record_with_inputs_and_tools_unions_flags(project):
    e = record(str(project / "derived.glb"), "spec_build", licence_id="LicenseRef-Own-Work",
               inputs=[{"source": "Bandai Namco DS1", "licence_id": "CC-BY-NC-4.0", "role": "pose"},
                       {"source": "FABDEM tile", "license": "CC BY-NC-SA 4.0", "role": "terrain"}],
               tools=[{"name": "Blender", "licence_id": "GPL-3.0-or-later"},
                      {"name": "NvidiaWarp-GarmentCode", "licence_id": "LicenseRef-NVIDIA-SCL"}])
    assert e["asset"] == "derived.glb" and e["licence_id"] == "LicenseRef-Own-Work"
    assert e["inputs"][1]["licence_id"] == "CC-BY-NC-SA-4.0"
    assert e["tools"][0]["flags"] == [] and e["tools"][1]["flags"] == ["nc"]
    assert e["flags"] == ["attribution", "nc", "sa"]
    assert e["stamp"] == ["CC-BY-NC-SA-4.0"]
    assert ledger.entries(project)[0]["flags"] == e["flags"]
    with pytest.raises(ValueError, match="unknown flags"):
        record(str(project / "kit.glb"), "x", inputs=[{"source": "y", "licence_id": "MIT", "flags": ["evil"]}])


def test_lineage_follows_the_ledger(project):
    record(str(project / "base.glb"), "itch pack", license="unstated")
    record(str(project / "anim.glb"), "retarget", inputs=[{"source": "ACCAD", "licence_id": "CC-BY-3.0"}])
    e = record(str(project / "derived.glb"), "spec_build",
               inputs=[{"asset": "base.glb", "role": "base"}, {"asset": str(project / "anim.glb")},
                       {"asset": "nowhere.glb"}])
    assert e["inputs"][0]["flags"] == ["unknown"] and e["inputs"][1]["flags"] == ["attribution"]
    assert e["inputs"][2]["notes"] == "not in the ledger"
    assert e["licence_id"] is None and e["flags"] == ["attribution", "unknown"]
    why = {b["asset"]: b["reasons"] for b in check(project)["blocked"]}["derived.glb"]
    assert "licence not classified: input 'nowhere.glb' (not in the ledger); record its licence_id" in why
    # classifying the base later unblocks everything made from it
    record(str(project / "base.glb"), "itch pack", licence_id="LicenseRef-QAL-1.0")
    record(str(project / "nowhere.glb"), "own", licence_id="LicenseRef-Own-Work")
    cur = {x["asset"]: x for x in ledger.current(project)}
    assert len(ledger.entries(project)) == 5 and len(cur) == 4
    assert cur["derived.glb"]["flags"] == ["attribution", "no-redistribute-as-asset"]
    assert "notes" not in cur["derived.glb"]["inputs"][2]
    # share-alike travels through lineage too
    record(str(project / "anim.glb"), "retarget", licence_id="CC-BY-SA-4.0")
    assert {x["asset"]: x for x in ledger.current(project)}["derived.glb"]["stamp"] == ["CC-BY-SA-4.0"]


def test_legacy_entries_load_through_the_classifier(project):
    old = [
        {"asset": "base.glb", "source": "Quaternius", "license": "QAL v1.0 licence", "author": "", "url": "",
         "generator": "", "model": "", "notes": "", "recorded": "2026-01-01T00:00:00"},
        {"asset": "dem.png", "source": "Copernicus", "license": "Copernicus free licence with credit",
         "recorded": "2026-01-01T00:00:00"},
        {"asset": "pal.hex", "source": "Lospec", "license": "", "recorded": "2026-01-01T00:00:00"},
        {"asset": "anim.glb", "source": "Bandai Namco", "license": "CC BY-NC 4.0, including since 2022",
         "recorded": "2026-01-01T00:00:00"},
    ]
    (project / ".opus").mkdir()
    (project / ".opus" / "ledger.jsonl").write_text("".join(json.dumps(x) + "\n" for x in old), encoding="utf-8")
    got = {e["asset"]: e for e in ledger.entries(project)}
    assert got["base.glb"]["licence_id"] == "LicenseRef-QAL-1.0" and "nc" not in got["base.glb"]["flags"]
    assert got["dem.png"]["flags"] == ["attribution"]
    assert got["pal.hex"]["licence_id"] is None and got["pal.hex"]["flags"] == ["unknown"]
    assert got["anim.glb"]["flags"] == ["attribution", "nc"]
    rep = check(project)
    assert [b["asset"] for b in rep["blocked"]] == ["pal.hex"]
    assert "record its licence_id" in rep["blocked"][0]["reasons"][0]
    assert [b["asset"] for b in check(project, commercial=True)["blocked"]] == ["pal.hex", "anim.glb"]
    assert [b["asset"] for b in check(project, publish_assets=True)["blocked"]] == ["base.glb", "pal.hex"]


# ---------------------------------------------------------------- export policy

def test_export_policy_reasons(project):
    record(str(project / "base.glb"), "Kenney", licence_id="CC0-1.0")
    record(str(project / "anim.glb"), "retarget", inputs=[{"source": "MANN dog", "licence_id": "CC-BY-NC-4.0"}])
    record(str(project / "clip.fbx"), "LAFAN1", licence_id="CC-BY-NC-ND-4.0")
    record(str(project / "kit.glb"), "Quaternius pack", licence_id="LicenseRef-QAL-1.0")
    record(str(project / "font.ttf"), "model", tools=[{"name": "Qwen-Image", "licence_id": "LicenseRef-Research-Only"}])
    record(str(project / "pal.hex"), "palette site", licence_id="LicenseRef-Whatever-1.0")

    def blocked(**pol):
        return {b["asset"]: b["reasons"] for b in check(project, **pol)["blocked"]}

    personal = check(project, commercial=False, publish_assets=False)
    assert set(blocked(commercial=False, publish_assets=False)) == {"pal.hex"}
    assert "add it to data/licences.yaml" in blocked()["pal.hex"][0]
    assert personal["warnings"][0]["asset"] == "font.ttf" and "Qwen-Image" in personal["warnings"][0]["warnings"][0]

    sold = blocked(commercial=True)
    assert set(sold) == {"anim.glb", "clip.fbx", "font.ttf", "pal.hex"}
    assert sold["anim.glb"] == ["non-commercial terms: input 'MANN dog' (CC-BY-NC-4.0); commercial: true blocks it"]
    assert any("use-restricted" in r for r in sold["font.ttf"])

    shared = blocked(publish_assets=True)
    assert set(shared) == {"clip.fbx", "kit.glb", "pal.hex"}
    assert any("no-derivatives" in r for r in shared["clip.fbx"])
    assert shared["kit.glb"] == ["may not be redistributed as an asset: its licence LicenseRef-QAL-1.0; "
                                 "publish_assets: true blocks it"]

    # the policy comes from the bible; publish_assets defaults to false until it is set there
    assert ledger.policy(project) == {"commercial": False, "publish_assets": False}
    (project / "opus.project.yaml").write_text("commercial: true\npublish_assets: true\n", encoding="utf-8")
    assert ledger.policy(project) == {"commercial": True, "publish_assets": True}
    assert set(blocked()) == {"anim.glb", "clip.fbx", "font.ttf", "pal.hex", "kit.glb"}
    assert check(project)["ok"] is False


def test_share_alike_is_stamped(project):
    record(str(project / "base.glb"), "terrain", inputs=[{"source": "FABDEM", "licence_id": "CC-BY-NC-SA-4.0"},
                                                        {"source": "Z-Anatomy", "licence_id": "CC-BY-SA-4.0"}])
    rep = check(project)
    assert rep["ok"] and rep["share_alike"] == [{"asset": "base.glb", "licence": "CC-BY-NC-SA-4.0 AND CC-BY-SA-4.0"}]
    assert "may not be compatible" in rep["warnings"][0]["warnings"][0]


# ---------------------------------------------------------------- credits

def test_credits_carry_exact_attribution_strings(project):
    record(str(project / "base.glb"), "Kenney", licence_id="CC0-1.0")
    record(str(project / "dem.png"), "dem_fetch", inputs=[{"source": "Copernicus GLO-30", "licence_id": "LicenseRef-Copernicus"}])
    exact = '"Sword Ice" by Swedish History Museum, CC BY 4.0, via https://example.org/sword'
    record(str(project / "kit.glb"), "spec_build", inputs=[
        {"source": "Swedish History Museum photo", "licence_id": "CC-BY-4.0", "attribution": exact},
        {"source": "ACCAD Motion Capture", "author": "ACCAD", "url": "https://accad.osu.edu", "licence_id": "CC-BY-3.0"},
        {"asset": "dem.png"},
    ])
    record(str(project / "clip.fbx"), "CMU", license="Free for use in research and commercial projects worldwide")
    record(str(project / "anim.glb"), "100STYLE", licence_id="CC-BY-SA-4.0", attribution="100STYLE by Ian Mason, CC BY 4.0")
    text = write_credits(project).read_text(encoding="utf-8")
    attribution = text.split("## Attribution")[1].split("##")[0]
    assert f"- {exact}\n" in attribution
    assert "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014" in attribution
    assert attribution.count("Copernicus WorldDEM-30") == 1  # the lineage input is credited by its own entry
    assert ("- ACCAD Motion Capture by ACCAD (https://accad.osu.edu), licensed under CC-BY-3.0 "
            "(https://creativecommons.org/licenses/by/3.0/)") in attribution
    assert "obtained from mocap.cs.cmu.edu" in attribution and "Kenney" not in attribution
    assert "- `anim.glb` is licensed under CC-BY-SA-4.0" in text
    assert "- **Kenney**: Creative Commons Zero v1.0 Universal (CC0-1.0)\n  - `base.glb`" in text
    assert "`kit.glb` · from Swedish History Museum photo, ACCAD Motion Capture, dem.png" in text


# ---------------------------------------------------------------- MCP and CLI

async def _session_call(tmp_path, calls):
    from mcp import ClientSession, StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "opus.mcp_server"],
                                   env={**os.environ, "OPUS_PROJECT_DIR": str(tmp_path)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return {t.name for t in tools.tools}, [await session.call_tool(n, a) for n, a in calls]


def test_licence_tools_over_mcp(project):
    names, results = anyio.run(_session_call, project, [
        ("ledger_record", {"asset": "kit.glb", "source": "spec_build", "licence_id": "LicenseRef-Own-Work",
                           "inputs": [{"source": "Bandai Namco DS1", "licence_id": "CC-BY-NC-4.0"}],
                           "tools": [{"name": "Blender", "licence_id": "GPL-3.0-or-later"}]}),
        ("ledger_record", {"asset": "pal.hex", "source": "Lospec", "license": "Royalty-free incl. games"}),
        ("licence_check", {"text": "QAL v1.0 licence"}),
        ("licence_check", {}),
        ("licence_check", {"commercial": True}),
        ("make_credits", {}),
    ])
    assert {"ledger_record", "licence_check", "make_credits"} <= names
    for r in results:
        assert not r.is_error, r.content[0].text
    kit = json.loads(results[0].content[0].text)
    assert kit["flags"] == ["attribution", "nc"] and kit["tools"][0]["flags"] == []
    qal = json.loads(results[2].content[0].text)
    assert qal["licence_id"] == "LicenseRef-QAL-1.0" and qal["flags"] == ["no-redistribute-as-asset"]
    assert [b["asset"] for b in json.loads(results[3].content[0].text)["blocked"]] == ["pal.hex"]
    assert [b["asset"] for b in json.loads(results[4].content[0].text)["blocked"]] == ["kit.glb", "pal.hex"]
    credits = json.loads(results[5].content[0].text)
    assert credits["ok"] is False and (project / "CREDITS.md").exists()


def test_licence_check_cli(project, capsys):
    assert cli(["licence-check", "--text", "NVIDIA Source Code License"]) == 0
    assert json.loads(capsys.readouterr().out) == {"licence_id": "LicenseRef-NVIDIA-SCL", "flags": ["nc"]}
    record(str(project / "kit.glb"), "Quaternius pack", licence_id="LicenseRef-QAL-1.0")
    assert cli(["licence-check", "--dir", str(project)]) == 0
    capsys.readouterr()
    assert cli(["licence-check", "--dir", str(project), "--publish-assets", "true"]) == 1
    assert json.loads(capsys.readouterr().out)["blocked"][0]["asset"] == "kit.glb"
