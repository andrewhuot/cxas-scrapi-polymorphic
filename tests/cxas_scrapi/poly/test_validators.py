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

"""Tests for cxas_scrapi.poly.validators (AD001-AD007)."""

from pathlib import Path

from cxas_scrapi.poly.models import AdapterCard
from cxas_scrapi.poly.validators import (
    validate_adapter_card,
    validate_all_adapters,
)


def _card(**overrides) -> AdapterCard:
    data = {
        "apiVersion": "v1",
        "kind": "ChannelAdapter",
        "metadata": {"channel": "chat", "displayName": "Chat"},
        "evaluations": [{"sourceDir": "adapters/chat_evals"}],
    }
    data.update(overrides)
    return AdapterCard.model_validate(data)


def _ids(issues) -> set:
    return {i["rule_id"] for i in issues}


def test_valid_chat_adapter_passes(base_dir: Path):
    card = _card(
        instructionDiffs=[
            {"agent": "Test_Agent", "mode": "append", "content": "x"}
        ],
        tools=[{"agent": "Test_Agent", "add": ["test_tool"]}],
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert issues == []


def test_ad002_missing_agent(base_dir: Path):
    card = _card(
        instructionDiffs=[
            {"agent": "Nonexistent", "mode": "append", "content": "x"}
        ]
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD002" in _ids(issues)
    assert any("Nonexistent" in i["message"] for i in issues)


def test_ad003_replace_section_missing_tag(base_dir: Path):
    card = _card(
        instructionDiffs=[
            {
                "agent": "Test_Agent",
                "mode": "replace_section",
                "sectionTag": "does_not_exist",
                "content": "x",
            }
        ]
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD003" in _ids(issues)


def test_ad003_replace_section_present_tag_ok(base_dir: Path):
    card = _card(
        instructionDiffs=[
            {
                "agent": "Test_Agent",
                "mode": "replace_section",
                "sectionTag": "channel_behavior",
                "content": "x",
            }
        ]
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD003" not in _ids(issues)


def test_ad004_remove_unknown_tool_warns(base_dir: Path):
    card = _card(tools=[{"agent": "Test_Agent", "remove": ["not_a_tool"]}])
    issues = validate_adapter_card(card, str(base_dir))
    ad004 = [i for i in issues if i["rule_id"] == "AD004"]
    assert ad004 and ad004[0]["severity"] == "warning"


def test_ad005_add_undefined_tool_errors(base_dir: Path):
    card = _card(tools=[{"agent": "Test_Agent", "add": ["ghost_tool"]}])
    issues = validate_adapter_card(card, str(base_dir))
    ad005 = [i for i in issues if i["rule_id"] == "AD005"]
    assert ad005 and ad005[0]["severity"] == "error"


def test_ad005_add_tool_with_definition_ok(base_dir: Path):
    card = _card(
        tools=[{"agent": "Test_Agent", "add": ["brand_new"]}],
        toolDefinitions=[
            {
                "displayName": "brand_new",
                "toolType": "python",
                "sourceDir": "adapters/chat_tools/extra_tool",
            }
        ],
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD005" not in _ids(issues)


def test_ad006_no_evaluations_warns(base_dir: Path):
    card = _card(evaluations=[])
    issues = validate_adapter_card(card, str(base_dir))
    ad006 = [i for i in issues if i["rule_id"] == "AD006"]
    assert ad006 and ad006[0]["severity"] == "warning"


def test_ad007_duplicate_channel(base_dir: Path):
    a = _card()
    b = _card()  # same channel "chat"
    issues = validate_all_adapters([a, b], str(base_dir))
    ad007 = [i for i in issues if i["rule_id"] == "AD007"]
    assert ad007 and ad007[0]["severity"] == "error"


def test_ad007_distinct_channels_ok(base_dir: Path):
    a = _card()
    b = _card(metadata={"channel": "voice", "displayName": "Voice"})
    issues = validate_all_adapters([a, b], str(base_dir))
    assert "AD007" not in _ids(issues)


def test_ad005_platform_tool_add_ok(base_dir: Path):
    card = _card(tools=[{"agent": "Test_Agent", "add": ["customize_response"]}])
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD005" not in _ids(issues)


def test_ad005_missing_callback_source(base_dir: Path):
    card = _card(
        callbacks=[
            {
                "agent": "Test_Agent",
                "type": "before_model",
                "pythonCode": "adapters/chat_callbacks/nope.py",
            }
        ]
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert any(
        i["rule_id"] == "AD005" and "pythonCode" in i["message"] for i in issues
    )


def test_ad005_missing_eval_sourcedir(base_dir: Path):
    card = _card(evaluations=[{"sourceDir": "adapters/does_not_exist"}])
    issues = validate_adapter_card(card, str(base_dir))
    assert any(
        i["rule_id"] == "AD005" and "evaluations" in i["message"]
        for i in issues
    )


def test_ad008_path_escapes_project(base_dir: Path):
    card = _card(
        callbacks=[
            {
                "agent": "Test_Agent",
                "type": "before_model",
                "pythonCode": "../../../../etc/passwd",
            }
        ]
    )
    issues = validate_adapter_card(card, str(base_dir))
    ad008 = [i for i in issues if i["rule_id"] == "AD008"]
    assert ad008 and ad008[0]["severity"] == "error"


def test_ad008_absolute_path_inside_project_is_not_portable(base_dir: Path):
    callback = (
        base_dir / "adapters" / "chat_callbacks" / "inject_context.py"
    ).resolve()
    card = _card(
        callbacks=[
            {
                "agent": "Test_Agent",
                "type": "before_model",
                "pythonCode": str(callback),
            }
        ]
    )
    issues = validate_adapter_card(card, str(base_dir))
    ad008 = [i for i in issues if i["rule_id"] == "AD008"]
    assert ad008 and ad008[0]["severity"] == "error"


def test_ad009_invalid_channel_type(base_dir: Path):
    card = _card(deployment={"channelType": "NOT_A_CHANNEL"})
    issues = validate_adapter_card(card, str(base_dir))
    assert any(
        i["rule_id"] == "AD009" and "channelType" in i["message"]
        for i in issues
    )


def test_ad009_invalid_modality(base_dir: Path):
    card = _card(deployment={"modality": "SUPER_HD"})
    issues = validate_adapter_card(card, str(base_dir))
    assert any(
        i["rule_id"] == "AD009" and "modality" in i["message"] for i in issues
    )


def test_ad009_valid_deployment_ok(base_dir: Path):
    card = _card(
        deployment={
            "channelType": "WEB_UI",
            "modality": "CHAT_ONLY",
            "webWidgetConfig": {"theme": "LIGHT"},
        }
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD009" not in _ids(issues)


def test_ad010_unsupported_tool_type(base_dir: Path):
    card = _card(
        tools=[{"agent": "Test_Agent", "add": ["x"]}],
        toolDefinitions=[
            {
                "displayName": "x",
                "toolType": "wasm",
                "sourceDir": "adapters/chat_tools/extra_tool",
            }
        ],
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert any(
        i["rule_id"] == "AD010" and "wasm" in i["message"] for i in issues
    )


def test_replace_section_with_attributes_passes(copied_base: Path):
    inst = copied_base / "agents" / "Test_Agent" / "instruction.txt"
    inst.write_text(
        inst.read_text().replace(
            "<channel_behavior>", '<channel_behavior priority="high">'
        )
    )
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "displayName": "Chat"},
            "instructionDiffs": [
                {
                    "agent": "Test_Agent",
                    "mode": "replace_section",
                    "sectionTag": "channel_behavior",
                    "content": "x",
                }
            ],
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    issues = validate_adapter_card(card, str(copied_base))
    assert "AD003" not in _ids(issues)


def test_ad011_bad_uuid_name(base_dir: Path):
    card = _card(appIdentity={"name": "not-a-uuid"})
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD011" in _ids(issues)


def test_ad011_empty_display_name(base_dir: Path):
    card = _card(appIdentity={"displayName": "   "})
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD011" in _ids(issues)


def test_ad011_valid_identity_clean(base_dir: Path):
    card = _card(
        appIdentity={
            "displayName": "X — Chat",
            "name": "f6e9c2a1-0000-5000-8000-000000000000",
        }
    )
    issues = validate_adapter_card(card, str(base_dir))
    assert "AD011" not in _ids(issues)
