# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for cxas_scrapi.poly.engine."""

import json
from pathlib import Path

import pytest

from cxas_scrapi.poly.engine import CompilationError, PolymorphismEngine
from cxas_scrapi.poly.models import AdapterCard


def _engine(base: Path) -> PolymorphismEngine:
    eng = PolymorphismEngine(str(base))
    eng.load_base_project()
    eng.load_adapter_cards()
    return eng


def _compiled(eng: PolymorphismEngine, channel: str):
    card, path = eng.adapters[channel]
    return eng.compile(card, path)


# ── Loading ──────────────────────────────────────────────────────────────


def test_load_base_project(base_dir: Path):
    eng = PolymorphismEngine(str(base_dir))
    base = eng.load_base_project()
    assert base.app_json["displayName"] == "Poly Test App"
    assert "Test_Agent" in base.agents
    agent = base.agents["Test_Agent"]
    assert agent.display_name == "Test_Agent"
    assert agent.config["tools"] == ["test_tool", "end_session"]
    assert "<channel_behavior>" in agent.instruction
    assert "test_tool" in base.tools
    # Base callback code is loaded keyed by its rel path.
    assert any("before_model_callbacks_01" in k for k in agent.callback_code)


def test_load_base_project_requires_app_json(tmp_path: Path):
    (tmp_path / "agents").mkdir()
    eng = PolymorphismEngine(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        eng.load_base_project()


def test_load_adapter_cards(base_dir: Path):
    eng = PolymorphismEngine(str(base_dir))
    eng.load_base_project()
    cards = eng.load_adapter_cards()
    channels = {c.metadata.channel for c in cards}
    assert channels == {"chat", "voice"}
    assert set(eng.adapters) == {"chat", "voice"}
    assert all(isinstance(c, AdapterCard) for c in cards)


# ── Instruction diffs ──────────────────────────────────────────────────────


def test_instruction_append(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    text = compiled.agent_instructions["Test_Agent"]
    assert text.endswith("Chat-specific: use markdown and numbered lists.\n")
    # Base content preserved.
    assert "You are a test agent." in text


def test_instruction_prepend(copied_base: Path):
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "pre", "displayName": "Pre"},
            "instructionDiffs": [
                {
                    "agent": "Test_Agent",
                    "mode": "prepend",
                    "content": "PREPENDED LINE",
                }
            ],
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    compiled = eng.compile(card)
    text = compiled.agent_instructions["Test_Agent"]
    assert text.startswith("PREPENDED LINE")
    assert "You are a test agent." in text


def test_instruction_replace_section(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "voice")
    text = compiled.agent_instructions["Test_Agent"]
    assert "Default channel behavior here." not in text
    assert "Voice channel: keep responses short" in text
    # Tags preserved around replacement.
    assert "<channel_behavior>" in text and "</channel_behavior>" in text


def test_replace_section_missing_tag_raises(copied_base: Path):
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "x", "displayName": "X"},
            "instructionDiffs": [
                {
                    "agent": "Test_Agent",
                    "mode": "replace_section",
                    "sectionTag": "no_such_tag",
                    "content": "y",
                }
            ],
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    with pytest.raises(CompilationError):
        eng.compile(card)


# ── Tools ──────────────────────────────────────────────────────────────────


def test_tool_add(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    assert "extra_tool" in compiled.agents["Test_Agent"]["tools"]
    # The new tool definition is captured for output.
    assert "extra_tool" in compiled.tools


def test_tool_remove(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "voice")
    assert "test_tool" not in compiled.agents["Test_Agent"]["tools"]


def test_tool_definition_pythoncode_normalized(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    cfg = compiled.tools["extra_tool"]
    assert (
        cfg["pythonFunction"]["pythonCode"]
        == "tools/extra_tool/python_function/python_code.py"
    )


# ── Model overrides & callbacks ───────────────────────────────────────────


def test_model_override(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    assert (
        compiled.agents["Test_Agent"]["modelSettings"]["model"]
        == "gemini-3-pro"
    )


def test_callback_append_next_index(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    cbs = compiled.agents["Test_Agent"]["beforeModelCallbacks"]
    assert len(cbs) == 2
    assert cbs[1]["pythonCode"].endswith(
        "before_model_callbacks/before_model_callbacks_02/python_code.py"
    )
    assert cbs[1]["pythonCode"] in compiled.callback_code


def test_base_callback_preserved(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "voice")
    # Base before_model_callbacks_01 still present and its code carried.
    paths = [
        c["pythonCode"]
        for c in compiled.agents["Test_Agent"]["beforeModelCallbacks"]
    ]
    assert any("before_model_callbacks_01" in p for p in paths)


# ── Deployment & evaluations ──────────────────────────────────────────────


def test_deployment_built(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    # snake_case block matching Deployments.create_deployment kwargs.
    assert compiled.deployment["channel_type"] == "WEB_UI"
    assert compiled.deployment["modality"] == "CHAT_ONLY"
    assert compiled.deployment["theme"] == "LIGHT"
    assert compiled.deployment["deployment_id"] == "chat"
    # Folded into gecx-config.json (the file deploy tooling reads).
    assert compiled.gecx_config["deployment"] == compiled.deployment


def test_deployment_voice_sets_audio_modality(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "voice")
    assert compiled.deployment["channel_type"] == "GOOGLE_TELEPHONY_PLATFORM"
    assert compiled.gecx_config["modality"] == "audio"


def test_gecx_config_overlay_deep_merges_before_channel_defaults(copied_base: Path):
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "voice", "displayName": "Voice"},
            "gecxConfig": {
                "model": "gemini-3-flash-lite",
                "default_channel": "wrong",
                "runtime": {"turnTimeoutMs": 800},
            },
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
            "deployment": {
                "channelType": "GOOGLE_TELEPHONY_PLATFORM",
                "modality": "VOICE_ONLY",
            },
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    compiled = eng.compile(card)
    assert compiled.gecx_config["model"] == "gemini-3-flash-lite"
    assert compiled.gecx_config["runtime"]["turnTimeoutMs"] == 800
    assert compiled.gecx_config["default_channel"] == "voice"
    assert compiled.gecx_config["app_dir"] == "."
    assert compiled.gecx_config["modality"] == "audio"


def test_evaluations_merged(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    assert "Chat_Test_Eval" in compiled.evaluations


# ── compile_all ────────────────────────────────────────────────────────────


def test_compile_all_one_config_per_channel(base_dir: Path):
    eng = PolymorphismEngine(str(base_dir))
    result = eng.compile_all()
    assert set(result) == {"chat", "voice"}


def test_compile_all_raises_on_bad_adapter(copied_base: Path):
    bad = copied_base / "adapters" / "broken.adapter.yaml"
    bad.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata:\n"
        "  channel: broken\n"
        "  displayName: Broken\n"
        "instructionDiffs:\n"
        "  - agent: Nonexistent_Agent\n"
        "    mode: append\n"
        "    content: x\n"
    )
    eng = PolymorphismEngine(str(copied_base))
    with pytest.raises(CompilationError) as exc:
        eng.compile_all()
    assert any(i["rule_id"] == "AD002" for i in exc.value.issues)


def test_compile_all_raises_on_duplicate_channels(copied_base: Path):
    dup = copied_base / "adapters" / "duplicate_chat.adapter.yaml"
    dup.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata:\n"
        "  channel: chat\n"
        "  displayName: Duplicate Chat\n"
        "evaluations:\n"
        "  - sourceDir: adapters/chat_evals\n"
    )
    eng = PolymorphismEngine(str(copied_base))
    with pytest.raises(CompilationError) as exc:
        eng.compile_all()
    assert any(i["rule_id"] == "AD007" for i in exc.value.issues)


def test_base_not_mutated_across_compiles(base_dir: Path):
    eng = _engine(base_dir)
    _compiled(eng, "chat")  # adds extra_tool to a copy
    # The base bundle's tools list must be untouched.
    assert eng.base.agents["Test_Agent"].config["tools"] == [
        "test_tool",
        "end_session",
    ]


# ── write_output ───────────────────────────────────────────────────────────


def test_write_output_structure(base_dir: Path, tmp_path: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    out = eng.write_output(compiled, str(tmp_path / "chat"))

    assert (out / "app.json").exists()
    assert (out / "gecx-config.json").exists()
    # Deployment now lives inside gecx-config.json, not a standalone file.
    assert not (out / "deployment.json").exists()
    gecx = json.loads((out / "gecx-config.json").read_text())
    assert gecx["deployment"]["channel_type"] == "WEB_UI"
    agent_json = out / "agents" / "Test_Agent" / "Test_Agent.json"
    assert agent_json.exists()
    assert (out / "agents" / "Test_Agent" / "instruction.txt").exists()
    # New callback file written.
    assert (
        out
        / "agents"
        / "Test_Agent"
        / "before_model_callbacks"
        / "before_model_callbacks_02"
        / "python_code.py"
    ).exists()
    # Base tool copied verbatim, new tool written.
    assert (out / "tools" / "test_tool" / "test_tool.json").exists()
    assert (
        out / "tools" / "extra_tool" / "python_function" / "python_code.py"
    ).exists()
    # Channel eval merged.
    assert (
        out / "evaluations" / "Chat_Test_Eval" / "Chat_Test_Eval.json"
    ).exists()


def test_write_output_agent_json_valid(base_dir: Path, tmp_path: Path):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "chat")
    out = eng.write_output(compiled, str(tmp_path / "chat"))

    cfg = json.loads(
        (out / "agents" / "Test_Agent" / "Test_Agent.json").read_text()
    )
    # Every callback pythonCode path resolves to a real file.
    for cb in cfg["beforeModelCallbacks"]:
        assert (out / cb["pythonCode"]).exists()
    # Every listed tool has a directory in the output.
    for tool in cfg["tools"]:
        if tool == "end_session":
            continue  # platform tool, no directory
        assert (out / "tools" / tool).is_dir()
    # gecx app_dir normalized to "." for lintability.
    gecx = json.loads((out / "gecx-config.json").read_text())
    assert gecx["app_dir"] == "."
    assert gecx["default_channel"] == "chat"


def test_write_output_voice_excludes_removed_tool_from_list(
    base_dir: Path, tmp_path: Path
):
    eng = _engine(base_dir)
    compiled = _compiled(eng, "voice")
    out = eng.write_output(compiled, str(tmp_path / "voice"))
    cfg = json.loads(
        (out / "agents" / "Test_Agent" / "Test_Agent.json").read_text()
    )
    assert "test_tool" not in cfg["tools"]
