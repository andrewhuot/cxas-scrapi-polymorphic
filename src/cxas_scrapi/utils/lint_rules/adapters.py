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

"""Channel adapter card lint rules (AD001-AD007).

Fires when the linter discovers an ``adapters/`` directory containing
``*.adapter.{yaml,yml,json}`` files.  These rules reuse the validation
logic in ``cxas_scrapi.poly.validators`` so the linter and
``cxas poly validate`` stay in lockstep.

Rule-ID note: the original spec proposed ``A001``-``A007`` but the
``config`` category already owns those, so adapter rules use the ``AD``
prefix.
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

import yaml
from pydantic import ValidationError

from cxas_scrapi.poly.models import AdapterCard
from cxas_scrapi.poly.validators import (
    validate_adapter_card,
    validate_all_adapters,
)
from cxas_scrapi.utils.linter import (
    LintContext,
    LintResult,
    Rule,
    Severity,
    rule,
)


def _parse_raw(content: str, file_path: Path):
    if file_path.suffix == ".json":
        return json.loads(content)
    return yaml.safe_load(content)


def _parse_card(
    content: str, file_path: Path
) -> Tuple[Optional[AdapterCard], Optional[str]]:
    """Parse an adapter file into an ``AdapterCard``.

    Returns ``(card, None)`` on success or ``(None, message)`` on a parse
    or schema error.
    """
    try:
        data = _parse_raw(content, file_path)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        return None, f"Adapter card is not valid {file_path.suffix}: {e}"
    if not isinstance(data, dict):
        return None, "Adapter card must be a mapping/object."
    try:
        return AdapterCard.model_validate(data), None
    except ValidationError as e:
        return None, f"Adapter card schema invalid: {e}"


def _app_dir_for(file_path: Path) -> str:
    """Project root for an adapter file at ``<app>/adapters/<file>``."""
    return str(file_path.parent.parent)


def _issues_for(file_path: Path, content: str, rule_id: str) -> List[str]:
    card, err = _parse_card(content, file_path)
    if err is not None or card is None:
        return []
    issues = validate_adapter_card(card, _app_dir_for(file_path))
    return [i["message"] for i in issues if i["rule_id"] == rule_id]


@rule("adapters")
class AdapterSchemaValid(Rule):
    id = "AD001"
    name = "adapter-schema-valid"
    description = "Adapter card has required fields and valid types"
    default_severity = Severity.ERROR

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        _card, err = _parse_card(content, file_path)
        if err is not None:
            return [self.make_result(file=rel, message=err)]
        return []


@rule("adapters")
class AdapterAgentRefsExist(Rule):
    id = "AD002"
    name = "adapter-agent-refs-exist"
    description = "Adapter references only agents that exist in agents/"
    default_severity = Severity.ERROR

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        return [
            self.make_result(file=rel, message=m)
            for m in _issues_for(file_path, content, "AD002")
        ]


@rule("adapters")
class AdapterReplaceSectionExists(Rule):
    id = "AD003"
    name = "adapter-replace-section-exists"
    description = (
        "replace_section diffs set sectionTag and the tag exists in the "
        "target instruction"
    )
    default_severity = Severity.ERROR

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        return [
            self.make_result(file=rel, message=m)
            for m in _issues_for(file_path, content, "AD003")
        ]


@rule("adapters")
class AdapterRemoveUnknownTool(Rule):
    id = "AD004"
    name = "adapter-remove-unknown-tool"
    description = "Tool remove references a tool in the base agent's list"
    default_severity = Severity.WARNING

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        return [
            self.make_result(file=rel, message=m)
            for m in _issues_for(file_path, content, "AD004")
        ]


@rule("adapters")
class AdapterAddUndefinedTool(Rule):
    id = "AD005"
    name = "adapter-add-undefined-tool"
    description = (
        "Tool add references a tool defined in tools/ or toolDefinitions"
    )
    default_severity = Severity.ERROR

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        return [
            self.make_result(file=rel, message=m)
            for m in _issues_for(file_path, content, "AD005")
        ]


@rule("adapters")
class AdapterHasEvaluations(Rule):
    id = "AD006"
    name = "adapter-has-evaluations"
    description = "Adapter declares at least one evaluations entry"
    default_severity = Severity.WARNING

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        return [
            self.make_result(file=rel, message=m)
            for m in _issues_for(file_path, content, "AD006")
        ]


@rule("adapters")
class AdapterDuplicateChannel(Rule):
    id = "AD007"
    name = "adapter-duplicate-channel"
    description = "No two adapter cards target the same metadata.channel"
    default_severity = Severity.ERROR

    def check(
        self, file_path: Path, content: str, context: LintContext
    ) -> List[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        this_card, err = _parse_card(content, file_path)
        if err is not None or this_card is None:
            return []

        adapters_dir = file_path.parent
        cards: List[AdapterCard] = []
        for p in sorted(adapters_dir.iterdir()):
            if not (
                p.name.endswith(".adapter.yaml")
                or p.name.endswith(".adapter.yml")
                or p.name.endswith(".adapter.json")
            ):
                continue
            card, perr = _parse_card(p.read_text(), p)
            if perr is None and card is not None:
                cards.append(card)

        channel = this_card.metadata.channel
        count = sum(1 for c in cards if c.metadata.channel == channel)
        if count > 1:
            issues = validate_all_adapters(cards, _app_dir_for(file_path))
            for i in issues:
                if i["rule_id"] == "AD007" and channel in i["message"]:
                    return [self.make_result(file=rel, message=i["message"])]
        return []
