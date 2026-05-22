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

"""Tests for cxas_scrapi.poly.scaffold."""

from pathlib import Path

import pytest
import yaml

from cxas_scrapi.poly.engine import CALLBACK_TYPE_TO_DIR, PolymorphismEngine
from cxas_scrapi.poly.scaffold import (
    ScaffoldOptions,
    build_scaffold_plan,
    write_scaffold_plan,
)
from cxas_scrapi.poly.validators import validate_adapter_card
from cxas_scrapi.utils.lint_rules.callbacks import (
    InvalidPythonSyntax,
    MissingTypingImport,
    WrongArgCount,
    WrongCallbackSignature,
)
from cxas_scrapi.utils.linter import LintContext


def test_scaffold_writes_valid_adapter_assets(copied_base: Path):
    plan = build_scaffold_plan(
        ScaffoldOptions(
            app_dir=copied_base,
            channels=["sms"],
            deployment_target="TWILIO",
            modality="VOICE_ONLY",
            tools=["send_sms_card"],
            callback_types=["before_model"],
        )
    )

    written = write_scaffold_plan(plan)
    rels = {str(path.relative_to(copied_base)) for path in written}

    assert "adapters/sms.adapter.yaml" in rels
    assert "adapters/sms_evals/Sms_Smoke/Sms_Smoke.yaml" in rels
    assert "adapters/sms_tools/send_sms_card/send_sms_card.json" in rels
    assert "adapters/sms_tools/send_sms_card/python_code.py" in rels
    assert "adapters/sms_callbacks/before_model.py" in rels

    engine = PolymorphismEngine(str(copied_base))
    engine.load_base_project()
    engine.load_adapter_cards()
    card, path = engine.adapters["sms"]
    assert validate_adapter_card(card, str(copied_base)) == []

    compiled = engine.compile(card, path)
    assert compiled.deployment["channel_type"] == "TWILIO"
    assert compiled.deployment["modality"] == "VOICE_ONLY"
    assert "send_sms_card" in compiled.agents["Test_Agent"]["tools"]
    assert "send_sms_card" in compiled.tools
    assert "Sms_Smoke" in compiled.evaluations


def test_scaffold_refuses_to_overwrite_existing_files(copied_base: Path):
    plan = build_scaffold_plan(
        ScaffoldOptions(app_dir=copied_base, channels=["sms"])
    )
    write_scaffold_plan(plan)

    with pytest.raises(FileExistsError):
        write_scaffold_plan(plan)


def test_scaffold_dry_run_does_not_write(copied_base: Path):
    plan = build_scaffold_plan(
        ScaffoldOptions(app_dir=copied_base, channels=["sms"])
    )

    planned = write_scaffold_plan(plan, dry_run=True)

    assert planned
    assert not (copied_base / "adapters" / "sms.adapter.yaml").exists()


def test_scaffold_deployment_none_omits_deployment(copied_base: Path):
    plan = build_scaffold_plan(
        ScaffoldOptions(
            app_dir=copied_base,
            channels=["chatbot"],
            deployment_target="none",
        )
    )

    adapter_file = next(
        file for file in plan.files if file.path.name == "chatbot.adapter.yaml"
    )
    adapter = yaml.safe_load(adapter_file.content)

    assert "deployment" not in adapter


def test_scaffold_callback_stubs_match_each_hook_signature(
    copied_base: Path, tmp_path: Path
):
    callback_types = tuple(CALLBACK_TYPE_TO_DIR)
    plan = build_scaffold_plan(
        ScaffoldOptions(
            app_dir=copied_base,
            channels=["sms"],
            callback_types=callback_types,
        )
    )
    context = LintContext(
        project_root=tmp_path,
        app_dir=tmp_path,
        evals_dir=tmp_path / "evaluations",
    )
    rules = [
        WrongArgCount(),
        MissingTypingImport(),
        WrongCallbackSignature(),
        InvalidPythonSyntax(),
    ]

    for callback_type in callback_types:
        scaffold_file = next(
            f for f in plan.files if f.path.name == f"{callback_type}.py"
        )
        callback_dir = CALLBACK_TYPE_TO_DIR[callback_type]
        lint_path = (
            tmp_path
            / "agents"
            / "Test_Agent"
            / callback_dir
            / f"{callback_dir}_01"
            / "python_code.py"
        )
        lint_path.parent.mkdir(parents=True, exist_ok=True)
        lint_path.write_text(scaffold_file.content)

        messages = [
            f"{result.rule_id}: {result.message}"
            for rule in rules
            for result in rule.check(lint_path, scaffold_file.content, context)
        ]
        assert messages == []
