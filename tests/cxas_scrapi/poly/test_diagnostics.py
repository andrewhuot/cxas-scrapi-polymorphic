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

"""Tests for guided poly validation diagnostics."""

from pathlib import Path

from cxas_scrapi.poly.diagnostics import build_validation_explanation_report
from cxas_scrapi.poly.engine import PolymorphismEngine


def test_validation_explanation_points_to_field_and_fix(copied_base: Path):
    (copied_base / "adapters" / "bad.adapter.yaml").write_text(
        "apiVersion: poly.cxas.dev/v1\n"
        "kind: ChannelAdapter\n"
        "metadata:\n"
        "  channel: bad\n"
        "  displayName: Bad\n"
        "instructionDiffs:\n"
        "  - agent: Ghost\n"
        "    mode: append\n"
        "    content: x\n"
    )
    engine = PolymorphismEngine(str(copied_base))
    engine.load_base_project()
    engine.load_adapter_cards()

    report = build_validation_explanation_report(engine, str(copied_base))

    ad002 = next(i for i in report.issues if i.rule_id == "AD002")
    assert ad002.adapter_path == "adapters/bad.adapter.yaml"
    assert ad002.field_path == "instructionDiffs[0]"
    assert "existing agent" in ad002.why_it_failed
    assert "agents/<agent>" in ad002.likely_fix

    ad006 = next(
        i
        for i in report.issues
        if i.rule_id == "AD006"
        and i.adapter_path == "adapters/bad.adapter.yaml"
    )
    assert ad006.severity == "warning"
    assert "adapters/bad_evals" in ad006.related_paths


def test_validation_explanation_report_json_shape(base_dir: Path):
    engine = PolymorphismEngine(str(base_dir))
    engine.load_base_project()
    engine.load_adapter_cards()

    report = build_validation_explanation_report(engine, str(base_dir))
    data = report.to_dict()

    assert data["app_dir"] == str(base_dir.resolve())
    assert data["cards"] == 2
    assert "issues" in data
