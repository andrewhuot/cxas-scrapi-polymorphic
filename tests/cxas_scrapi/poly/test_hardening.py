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

"""Production-hardening tests for the Polymorphism Engine.

Covers the guarantees that make the output safe to lint/eval/deploy: the
compiled project actually lints clean (round-trip), the writer never destroys
unrelated data, malformed cards never crash, paths can't escape the project,
and the half-built features (toolType, eval expectations/datasets) work.
"""

import json
from pathlib import Path

import pytest

from cxas_scrapi.poly.engine import PolymorphismEngine
from cxas_scrapi.poly.models import AdapterCard
from cxas_scrapi.utils.linter import (
    Discovery,
    LintConfig,
    LintReport,
    build_context,
    build_registry,
    run_rules,
)

# ── Round-trip: compiled output lints clean ───────────────────────────────


def _lint_errors(app_dir: Path):
    """Run the real linter on a project in-process; return error results."""
    registry = build_registry()
    project_root = app_dir.resolve()
    config = LintConfig.load(project_root)
    a_dir = project_root / config.app_dir
    e_dir = project_root / config.evals_dir
    discovery = Discovery(a_dir, e_dir)
    assert discovery.app_root, f"no app root discovered under {a_dir}"
    context = build_context(project_root, config, discovery)
    report = LintReport()
    run_rules(registry, config, context, discovery, report)
    return report.errors


def test_compiled_output_lints_clean(bella_notte_dir: Path, tmp_path: Path):
    """The headline guarantee: every compiled channel lints with zero errors."""
    eng = PolymorphismEngine(str(bella_notte_dir))
    compiled = eng.compile_all()
    assert set(compiled) == {"chat", "voice"}
    for channel, cfg in compiled.items():
        out = eng.write_output(cfg, str(tmp_path / channel))
        errors = _lint_errors(out)
        assert errors == [], (
            f"channel '{channel}' output has lint errors: "
            + "; ".join(f"{e.rule_id} {e.file}" for e in errors)
        )


def test_polymorphic_pizza_showcases_channel_specific_runtime_config(
    polymorphic_pizza_dir: Path,
):
    """The product demo proves model/runtime config differs by channel."""
    eng = PolymorphismEngine(str(polymorphic_pizza_dir))
    compiled = eng.compile_all()
    chat = compiled["chat"]
    voice = compiled["voice"]

    assert chat.gecx_config["model"] == "gemini-3-pro"
    assert chat.gecx_config["modality"] == "text"
    assert (
        chat.agents["Order_Agent"]["modelSettings"]["model"]
        == "gemini-3-pro"
    )
    assert "send_order_card" in chat.agents["Order_Agent"]["tools"]

    assert voice.gecx_config["model"] == "gemini-3-flash"
    assert voice.gecx_config["modality"] == "audio"
    assert (
        voice.agents["Order_Agent"]["modelSettings"]["model"]
        == "gemini-3-flash"
    )
    assert "send_order_card" not in voice.agents["Order_Agent"]["tools"]


# ── Safe output writer ─────────────────────────────────────────────────────


def _chat(eng: PolymorphismEngine):
    card, path = eng.adapters["chat"]
    return eng.compile(card, path)


def _engine(base: Path) -> PolymorphismEngine:
    eng = PolymorphismEngine(str(base))
    eng.load_base_project()
    eng.load_adapter_cards()
    return eng


def test_write_refuses_to_clobber_foreign_dir(base_dir: Path, tmp_path: Path):
    eng = _engine(base_dir)
    compiled = _chat(eng)
    out = tmp_path / "chat"
    out.mkdir()
    (out / "precious.txt").write_text("do not delete")
    with pytest.raises(FileExistsError):
        eng.write_output(compiled, str(out))
    assert (out / "precious.txt").exists()  # untouched


def test_write_force_overwrites(base_dir: Path, tmp_path: Path):
    eng = _engine(base_dir)
    compiled = _chat(eng)
    out = tmp_path / "chat"
    out.mkdir()
    (out / "precious.txt").write_text("do not delete")
    eng.write_output(compiled, str(out), force=True)
    assert not (out / "precious.txt").exists()
    assert (out / "app.json").exists()


def test_write_rebuild_ok_when_poly_owned(base_dir: Path, tmp_path: Path):
    eng = _engine(base_dir)
    compiled = _chat(eng)
    out = tmp_path / "chat"
    eng.write_output(compiled, str(out))  # first build writes the marker
    assert (out / ".poly_build.json").is_file()
    # Second build into the same (poly-owned) dir succeeds without force.
    eng.write_output(compiled, str(out))
    assert (out / "app.json").exists()


def test_write_refuses_overlap_with_app_dir(base_dir: Path):
    eng = _engine(base_dir)
    compiled = _chat(eng)
    with pytest.raises(ValueError):
        eng.write_output(compiled, str(base_dir / "inside"))
    with pytest.raises(ValueError):
        eng.write_output(compiled, str(base_dir))


# ── Malformed cards never crash ────────────────────────────────────────────


def test_malformed_card_collected_not_raised(copied_base: Path):
    (copied_base / "adapters" / "broken.adapter.yaml").write_text(
        "apiVersion: v1\nkind: ChannelAdapter\nmetadata:\n  displayName: X\n"
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    cards = eng.load_adapter_cards()  # must not raise
    channels = {c.metadata.channel for c in cards}
    assert channels == {"chat", "voice"}  # good cards still parsed
    assert any(e["rule_id"] == "AD001" for e in eng.adapter_errors)


def test_invalid_yaml_card_collected(copied_base: Path):
    (copied_base / "adapters" / "bad.adapter.yaml").write_text(
        "this: : not: valid: yaml: ["
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    eng.load_adapter_cards()
    assert any(e["rule_id"] == "AD001" for e in eng.adapter_errors)


# ── toolType handling ──────────────────────────────────────────────────────


def test_openapi_tool_copied_verbatim(copied_base: Path):
    # Create a non-python tool source dir with an aux spec file.
    src = copied_base / "adapters" / "api_tools" / "lookup_api"
    src.mkdir(parents=True)
    (src / "lookup_api.json").write_text(
        json.dumps({"displayName": "lookup_api", "openApiSpec": "spec.yaml"})
    )
    (src / "spec.yaml").write_text("openapi: 3.0.0\n")
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "api", "displayName": "Api"},
            "toolDefinitions": [
                {
                    "displayName": "lookup_api",
                    "toolType": "openapi",
                    "sourceDir": "adapters/api_tools/lookup_api",
                }
            ],
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    compiled = eng.compile(card)
    out = eng.write_output(compiled, str(copied_base.parent / "api_out"))
    # Both the JSON and the aux spec file are present, unchanged.
    assert (out / "tools" / "lookup_api" / "lookup_api.json").exists()
    assert (out / "tools" / "lookup_api" / "spec.yaml").exists()


# ── Eval expectations / datasets ───────────────────────────────────────────


def test_eval_expectations_and_datasets_merged(copied_base: Path):
    exp = copied_base / "adapters" / "chat_exp" / "Chat_Exp"
    exp.mkdir(parents=True)
    (exp / "Chat_Exp.json").write_text(
        json.dumps({"displayName": "Chat_Exp", "llmCriteria": {"prompt": "ok"}})
    )
    ds = copied_base / "adapters" / "chat_ds" / "Chat_DS"
    ds.mkdir(parents=True)
    (ds / "Chat_DS.json").write_text(
        json.dumps({"displayName": "Chat_DS", "evaluations": []})
    )
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "displayName": "Chat"},
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
            "evaluationExpectations": [{"sourceDir": "adapters/chat_exp"}],
            "evaluationDatasets": [{"sourceDir": "adapters/chat_ds"}],
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    compiled = eng.compile(card)
    assert "Chat_Exp" in compiled.evaluation_expectations
    assert "Chat_DS" in compiled.evaluation_datasets
    out = eng.write_output(compiled, str(copied_base.parent / "ev_out"))
    assert (
        out / "evaluationExpectations" / "Chat_Exp" / "Chat_Exp.json"
    ).exists()
    assert (out / "evaluationDatasets" / "Chat_DS" / "Chat_DS.json").exists()


# ── Platform tools & attribute sections (engine side) ──────────────────────


def test_platform_tool_add_allowed(copied_base: Path):
    card = AdapterCard.model_validate(
        {
            "apiVersion": "v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "p", "displayName": "P"},
            "tools": [{"agent": "Test_Agent", "add": ["customize_response"]}],
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    compiled = eng.compile(card)  # must not raise on the platform tool
    assert "customize_response" in compiled.agents["Test_Agent"]["tools"]


def test_replace_section_with_attributes(copied_base: Path):
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
            "metadata": {"channel": "rs", "displayName": "RS"},
            "instructionDiffs": [
                {
                    "agent": "Test_Agent",
                    "mode": "replace_section",
                    "sectionTag": "channel_behavior",
                    "content": "new voice text",
                }
            ],
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    eng = PolymorphismEngine(str(copied_base))
    eng.load_base_project()
    compiled = eng.compile(card)  # previously a false AD003 / crash
    text = compiled.agent_instructions["Test_Agent"]
    assert "new voice text" in text
    assert "Default channel behavior here." not in text


def test_provenance_marker_is_enriched(
    tmp_path: Path, polymorphic_pizza_dir: Path
):
    eng = PolymorphismEngine(str(polymorphic_pizza_dir))
    eng.load_base_project()
    compiled = eng.compile_all()
    out = eng.write_output(compiled["chat"], str(tmp_path / "chat"))

    marker = json.loads((out / ".poly_build.json").read_text())
    assert marker["channel"] == "chat"
    assert marker["adapter_card"].endswith("chat.adapter.yaml")
    assert len(marker["adapter_sha256"]) == 64
    assert "Order_Agent" in marker["base_agents"]
    assert marker["base_agents"] == sorted(marker["base_agents"])
    assert marker["applied_deltas"]["tools_added"] == 1
    assert marker["applied_deltas"]["deployment"] is True
    assert isinstance(marker["engine_version"], str)
