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

"""Tests for the adapters lint-rule category (AD001-AD007)."""

from pathlib import Path

import pytest

from cxas_scrapi.utils.lint_rules.adapters import (
    AdapterAddUndefinedTool,
    AdapterAgentRefsExist,
    AdapterDeploymentValues,
    AdapterDuplicateChannel,
    AdapterHasEvaluations,
    AdapterPathInScope,
    AdapterReplaceSectionExists,
    AdapterSchemaValid,
    AdapterToolType,
)
from cxas_scrapi.utils.linter import LintContext, build_registry


@pytest.fixture
def ctx(copied_base: Path) -> LintContext:
    return LintContext(
        project_root=copied_base,
        app_dir=copied_base,
        evals_dir=copied_base / "evals",
    )


def _adapter(copied_base: Path, name: str) -> Path:
    return copied_base / "adapters" / name


def test_ad001_valid_schema_passes(ctx, copied_base):
    f = _adapter(copied_base, "chat.adapter.yaml")
    results = AdapterSchemaValid().check(f, f.read_text(), ctx)
    assert results == []


def test_ad001_invalid_schema_reported(ctx, copied_base):
    f = _adapter(copied_base, "broken.adapter.yaml")
    f.write_text("apiVersion: v1\nkind: NotAnAdapter\n")
    results = AdapterSchemaValid().check(f, f.read_text(), ctx)
    assert len(results) == 1
    assert results[0].rule_id == "AD001"


def test_ad002_missing_agent_reported(ctx, copied_base):
    f = _adapter(copied_base, "bad.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: bad, displayName: Bad}\n"
        "instructionDiffs:\n"
        "  - {agent: Ghost, mode: append, content: x}\n"
    )
    results = AdapterAgentRefsExist().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD002" for r in results)


def test_ad003_missing_section_reported(ctx, copied_base):
    f = _adapter(copied_base, "rs.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: rs, displayName: RS}\n"
        "instructionDiffs:\n"
        "  - {agent: Test_Agent, mode: replace_section, "
        "sectionTag: nope, content: x}\n"
    )
    results = AdapterReplaceSectionExists().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD003" for r in results)


def test_ad005_undefined_tool_reported(ctx, copied_base):
    f = _adapter(copied_base, "t.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: t, displayName: T}\n"
        "tools:\n"
        "  - {agent: Test_Agent, add: [ghost_tool]}\n"
    )
    results = AdapterAddUndefinedTool().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD005" for r in results)


def test_ad006_no_evaluations_warns(ctx, copied_base):
    f = _adapter(copied_base, "voice.adapter.yaml")
    results = AdapterHasEvaluations().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD006" for r in results)


def test_ad007_duplicate_channel_reported(ctx, copied_base):
    # Add a second adapter that also targets "chat".
    dup = _adapter(copied_base, "chat2.adapter.yaml")
    dup.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: chat, displayName: Chat2}\n"
        "evaluations:\n"
        "  - {sourceDir: adapters/chat_evals}\n"
    )
    f = _adapter(copied_base, "chat.adapter.yaml")
    results = AdapterDuplicateChannel().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD007" for r in results)


def test_ad008_path_escape_reported(ctx, copied_base):
    f = _adapter(copied_base, "esc.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: esc, displayName: Esc}\n"
        "callbacks:\n"
        "  - {agent: Test_Agent, type: before_model, "
        "pythonCode: ../../../etc/passwd}\n"
    )
    results = AdapterPathInScope().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD008" for r in results)


def test_ad009_bad_deployment_reported(ctx, copied_base):
    f = _adapter(copied_base, "dep.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: dep, displayName: Dep}\n"
        "deployment: {channelType: BOGUS}\n"
    )
    results = AdapterDeploymentValues().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD009" for r in results)


def test_ad010_bad_tooltype_reported(ctx, copied_base):
    f = _adapter(copied_base, "tt.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: tt, displayName: TT}\n"
        "toolDefinitions:\n"
        "  - {displayName: x, toolType: wasm, "
        "sourceDir: adapters/chat_tools/extra_tool}\n"
    )
    results = AdapterToolType().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD010" for r in results)


def test_rules_autoregister_in_registry():
    registry = build_registry()
    ids = {r.id for r in registry.rules_for_category("adapters")}
    assert {
        "AD001",
        "AD002",
        "AD003",
        "AD004",
        "AD005",
        "AD006",
        "AD007",
        "AD008",
        "AD009",
        "AD010",
    } <= ids
