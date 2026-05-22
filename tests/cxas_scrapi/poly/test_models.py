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

"""Tests for cxas_scrapi.poly.models."""

import pytest
from pydantic import ValidationError

from cxas_scrapi.poly.models import AdapterCard


def _valid_card_dict() -> dict:
    return {
        "apiVersion": "poly.cxas.dev/v1",
        "kind": "ChannelAdapter",
        "metadata": {
            "channel": "chat",
            "displayName": "Chat Adapter",
            "description": "Chat optimization.",
        },
        "instructionDiffs": [
            {
                "agent": "Host",
                "mode": "append",
                "content": "Be brief.",
            }
        ],
        "tools": [{"agent": "Host", "add": ["x"], "remove": ["y"]}],
        "toolDefinitions": [
            {
                "displayName": "x",
                "toolType": "python",
                "sourceDir": "adapters/tools/x",
            }
        ],
        "modelOverrides": [{"agent": "Host", "model": "gemini-3-pro"}],
        "callbacks": [
            {
                "agent": "Host",
                "type": "before_model",
                "pythonCode": "adapters/cb/x.py",
                "description": "hint",
            }
        ],
        "evaluations": [{"sourceDir": "adapters/evals"}],
        "deployment": {
            "channelType": "WEB_UI",
            "modality": "CHAT_ONLY",
            "webWidgetConfig": {"theme": "LIGHT", "webWidgetTitle": "Hi"},
        },
    }


def test_parses_valid_card_with_camelcase_aliases():
    card = AdapterCard.model_validate(_valid_card_dict())
    assert card.api_version == "poly.cxas.dev/v1"
    assert card.metadata.channel == "chat"
    assert card.metadata.display_name == "Chat Adapter"
    assert card.instruction_diffs[0].mode == "append"
    assert card.tool_definitions[0].source_dir == "adapters/tools/x"
    assert card.model_overrides[0].model == "gemini-3-pro"
    assert card.callbacks[0].python_code == "adapters/cb/x.py"
    assert card.evaluations[0].source_dir == "adapters/evals"
    assert card.deployment.channel_type == "WEB_UI"
    assert card.deployment.web_widget_config.web_widget_title == "Hi"


def test_minimal_card_defaults_are_empty():
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "voice", "displayName": "V"},
        }
    )
    assert card.instruction_diffs == []
    assert card.tools == []
    assert card.tool_definitions == []
    assert card.model_overrides == []
    assert card.callbacks == []
    assert card.evaluations == []
    assert card.deployment is None


def test_missing_required_fields_raises():
    with pytest.raises(ValidationError):
        AdapterCard.model_validate(
            {"kind": "ChannelAdapter", "metadata": {"channel": "chat"}}
        )


def test_wrong_kind_raises():
    data = _valid_card_dict()
    data["kind"] = "SomethingElse"
    with pytest.raises(ValidationError):
        AdapterCard.model_validate(data)


def test_invalid_instruction_mode_raises():
    data = _valid_card_dict()
    data["instructionDiffs"][0]["mode"] = "bogus"
    with pytest.raises(ValidationError):
        AdapterCard.model_validate(data)


def test_populate_by_name_accepts_snake_case():
    # populate_by_name=True means Python field names also work as input keys.
    card = AdapterCard.model_validate(
        {
            "api_version": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "display_name": "C"},
        }
    )
    assert card.api_version == "v1"
    assert card.metadata.display_name == "C"


def test_unknown_adapter_fields_raise():
    data = _valid_card_dict()
    data["gecxCongif"] = {"modality": "audio"}
    with pytest.raises(ValidationError):
        AdapterCard.model_validate(data)


def test_unknown_nested_adapter_fields_raise():
    data = _valid_card_dict()
    data["deployment"]["webWidgetConfig"]["webWidgitTitle"] = "Typo"
    with pytest.raises(ValidationError):
        AdapterCard.model_validate(data)


def test_gecx_config_overlay_parses_as_delta():
    data = _valid_card_dict()
    data["gecxConfig"] = {
        "model": "gemini-3-pro",
        "runtime": {"turnTimeoutMs": 800},
    }
    card = AdapterCard.model_validate(data)
    assert card.gecx_config["model"] == "gemini-3-pro"
    assert card.gecx_config["runtime"]["turnTimeoutMs"] == 800
