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

"""Tests for stable poly diff reports."""

import json
from pathlib import Path

from cxas_scrapi.poly.diffing import DIFF_SCHEMA_VERSION, build_diff_report
from cxas_scrapi.poly.engine import PolymorphismEngine


def test_build_diff_report_surfaces_meaningful_deltas(base_dir: Path):
    engine = PolymorphismEngine(str(base_dir))
    engine.load_base_project()
    engine.load_adapter_cards()
    card, path = engine.adapters["chat"]
    compiled = engine.compile(card, path)

    report = build_diff_report(
        engine=engine,
        card=card,
        card_path=path,
        compiled=compiled,
    )

    assert report["schema_version"] == DIFF_SCHEMA_VERSION
    assert report["channel"] == "chat"
    assert report["adapter_path"] == "adapters/chat.adapter.yaml"
    assert report["summary"]["agents_touched"] == 1
    assert report["summary"]["tools_added"] == 1
    assert report["summary"]["callbacks_added"] == 1
    assert report["summary"]["deployment_changed"] is True
    assert report["tool_definitions_added"][0]["display_name"] == "extra_tool"
    assert report["evaluation_merges"]["evaluations"] == ["Chat_Test_Eval"]
    assert report["deployment"]["channel_type"] == "WEB_UI"
    assert any(delta["type"] == "tool_add" for delta in report["deltas"])
    assert any(
        delta["type"] == "callback_add"
        and delta["callback_type"] == "before_model"
        for delta in report["deltas"]
    )

    json.dumps(report)
