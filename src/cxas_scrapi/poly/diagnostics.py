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

"""Guided explanations for adapter validation issues.

This module deliberately does not decide whether a card is valid.  It enriches
issues emitted by ``validators.py`` so ``cxas poly doctor`` can tell developers
where to look and what kind of fix usually resolves each AD rule.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from cxas_scrapi.poly.engine import PolymorphismEngine
from cxas_scrapi.poly.models import AdapterCard
from cxas_scrapi.poly.validators import (
    validate_adapter_card,
    validate_all_adapters,
)


@dataclass(frozen=True)
class RuleGuide:
    """Static, user-facing explanation for one validator rule."""

    what: str
    why: str
    fix: str


@dataclass(frozen=True)
class ExplainedIssue:
    """A validator issue plus concrete debugging guidance."""

    rule_id: str
    severity: str
    message: str
    path: str
    adapter_path: str
    field_path: Optional[str]
    related_paths: List[str] = field(default_factory=list)
    what_failed: str = ""
    why_it_failed: str = ""
    likely_fix: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a stable JSON-serializable representation."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "adapter_path": self.adapter_path,
            "field_path": self.field_path,
            "related_paths": self.related_paths,
            "what_failed": self.what_failed,
            "why_it_failed": self.why_it_failed,
            "likely_fix": self.likely_fix,
        }


@dataclass(frozen=True)
class ValidationExplanationReport:
    """Structured report returned by doctor/explain flows."""

    app_dir: str
    cards: int
    errors: int
    warnings: int
    issues: List[ExplainedIssue]

    def to_dict(self) -> Dict[str, Any]:
        """Return a stable JSON-serializable report."""
        return {
            "app_dir": self.app_dir,
            "cards": self.cards,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues": [issue.to_dict() for issue in self.issues],
        }


RULE_GUIDES: Dict[str, RuleGuide] = {
    "AD001": RuleGuide(
        what="The adapter file could not be parsed as a valid ChannelAdapter.",
        why=(
            "The engine validates schema before compilation so misspelled, "
            "missing, or unknown fields cannot be silently ignored."
        ),
        fix=(
            "Fix the YAML/JSON shape. Start with apiVersion, kind: "
            "ChannelAdapter, and metadata.channel plus metadata.displayName."
        ),
    ),
    "AD002": RuleGuide(
        what="The adapter references an agent that the base app does not have.",
        why=(
            "Instruction diffs, tool changes, model overrides, and callbacks "
            "must target an existing agent directory or displayName."
        ),
        fix=(
            "Use a name from agents/<agent>/<agent>.json displayName or the "
            "agent directory name, or add the missing agent to the base app."
        ),
    ),
    "AD003": RuleGuide(
        what="A replace_section instruction diff cannot be applied.",
        why=(
            "replace_section is only safe when the target instruction has a "
            "stable XML section tag for the compiler to replace."
        ),
        fix=(
            "Add the missing sectionTag, add the XML block to the base "
            "instruction, or switch the diff to append/prepend."
        ),
    ),
    "AD004": RuleGuide(
        what="The adapter tries to remove a tool the base agent does not list.",
        why=(
            "Removing a non-existent tool is a no-op and often means the "
            "target agent or tool name is wrong."
        ),
        fix=(
            "Remove the no-op remove entry, or correct the tool name and "
            "target agent so it matches the base agent JSON."
        ),
    ),
    "AD005": RuleGuide(
        what=(
            "A referenced tool, callback, eval, expectation, or dataset is "
            "missing."
        ),
        why=(
            "The compiler only copies files that exist under the direct app "
            "root, and tool adds must resolve to a base tool, platform tool, "
            "or same-card toolDefinitions entry."
        ),
        fix=(
            "Create the referenced sourceDir/pythonCode path, correct the "
            "relative path from the app root, or add a matching "
            "toolDefinitions entry."
        ),
    ),
    "AD006": RuleGuide(
        what="The adapter has no channel-specific evaluations.",
        why=(
            "Behavior-changing channel deltas should usually carry at least "
            "one eval so chat/voice/API behavior does not drift unnoticed."
        ),
        fix=(
            "Add evaluations: [{sourceDir: adapters/<channel>_evals}], or "
            "intentionally accept the warning for a non-behavioral adapter."
        ),
    ),
    "AD007": RuleGuide(
        what="Two or more adapter cards declare the same metadata.channel.",
        why=(
            "The compiler writes one output directory and deployment id per "
            "channel, so duplicate channel names are ambiguous."
        ),
        fix=(
            "Give each adapter a unique metadata.channel and matching filename."
        ),
    ),
    "AD008": RuleGuide(
        what="An adapter path resolves outside the app root.",
        why=(
            "Adapter sources must be local project files; absolute paths and "
            "'..' escapes would make builds unsafe and non-portable."
        ),
        fix=(
            "Move the file under the app root and reference it with a "
            "project-relative sourceDir or pythonCode path."
        ),
    ),
    "AD009": RuleGuide(
        what="The deployment block uses an unsupported enum value.",
        why=(
            "The poly package stays GCP-free but still limits deployment "
            "values to the enums the current deploy tooling understands."
        ),
        fix=(
            "Use one of the supported channelType, modality, or theme values "
            "from cxas_scrapi.poly.models."
        ),
    ),
    "AD010": RuleGuide(
        what="A channel-only toolDefinition has an unsupported toolType.",
        why=(
            "The compiler currently knows how to normalize python tools and "
            "copy openapi tool directories; other types would not compile "
            "predictably."
        ),
        fix="Use toolType: python or toolType: openapi.",
    ),
    "AD011": RuleGuide(
        what="The adapter's appIdentity block is malformed.",
        why=(
            "Each channel compiles to a distinct deployable app; an explicit "
            "appIdentity.name must be a real UUID and displayName must be "
            "non-empty so the override is usable."
        ),
        fix=(
            "Provide a valid UUID for appIdentity.name (or omit it to let the "
            "engine derive one), and give appIdentity.displayName a non-empty "
            "value or remove it."
        ),
    ),
}


def build_validation_explanation_report(
    engine: PolymorphismEngine,
    app_dir: str,
) -> ValidationExplanationReport:
    """Run current validators and enrich their issues for doctor output."""
    root = Path(app_dir).resolve()
    issues: List[ExplainedIssue] = []

    for raw in engine.adapter_errors:
        issues.append(_explain(raw, root, raw.get("path", "adapters")))

    for card, card_path in engine.adapter_cards:
        adapter_rel = _rel(root, card_path)
        for raw in validate_adapter_card(card, str(root)):
            issues.append(_explain(raw, root, adapter_rel, card))

    cards = [card for card, _path in engine.adapter_cards]
    for raw in _duplicate_channel_issues(cards, str(root)):
        issues.append(_explain(raw, root, raw.get("path", "adapters")))

    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    return ValidationExplanationReport(
        app_dir=str(root),
        cards=len(engine.adapter_cards),
        errors=errors,
        warnings=warnings,
        issues=issues,
    )


def _duplicate_channel_issues(
    cards: Iterable[AdapterCard], app_dir: str
) -> List[Dict[str, Any]]:
    return [
        issue
        for issue in validate_all_adapters(list(cards), app_dir)
        if issue.get("rule_id") == "AD007"
    ]


def _explain(
    issue: Dict[str, Any],
    root: Path,
    adapter_path: str,
    card: Optional[AdapterCard] = None,
) -> ExplainedIssue:
    rule_id = str(issue.get("rule_id", "?"))
    guide = RULE_GUIDES.get(
        rule_id,
        RuleGuide(
            what="The adapter validator reported an issue.",
            why="The card did not satisfy a current validator rule.",
            fix="Inspect the adapter and referenced source files.",
        ),
    )
    message = str(issue.get("message", ""))
    field_path = _field_path(message)
    related_paths = _related_paths(message, root, card)
    return ExplainedIssue(
        rule_id=rule_id,
        severity=str(issue.get("severity", "error")),
        message=message,
        path=str(issue.get("path", adapter_path)),
        adapter_path=adapter_path,
        field_path=field_path,
        related_paths=related_paths,
        what_failed=guide.what,
        why_it_failed=guide.why,
        likely_fix=guide.fix,
    )


def _field_path(message: str) -> Optional[str]:
    field_match = re.search(
        r"(instructionDiffs|tools|toolDefinitions|callbacks|"
        r"evaluations|evaluationExpectations|evaluationDatasets)"
        r"\[\d+\](?:\.[A-Za-z0-9_]+)?",
        message,
    )
    if field_match:
        return field_match.group(0)
    dep_match = re.search(
        r"deployment(?:\.webWidgetConfig)?\.[A-Za-z0-9_]+",
        message,
    )
    if dep_match:
        return dep_match.group(0)
    if "metadata.channel" in message:
        return "metadata.channel"
    return None


def _related_paths(
    message: str,
    root: Path,
    card: Optional[AdapterCard],
) -> List[str]:
    paths: List[str] = []
    for ref in _quoted_path_refs(message):
        paths.append(ref)

    agent = _agent_ref(message)
    if agent is not None:
        instruction_path = _instruction_path_for(root, agent)
        if instruction_path is not None:
            paths.append(_rel(root, instruction_path))

    # For missing evaluation warnings, point developers at the conventional
    # starter path even when no concrete sourceDir appears in the message.
    if "no evaluations" in message and card is not None:
        paths.append(f"adapters/{card.metadata.channel}_evals")

    seen: set[str] = set()
    unique: List[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _quoted_path_refs(message: str) -> List[str]:
    refs: List[str] = []
    for quoted in re.findall(r"'([^']+)'", message):
        if "/" in quoted or quoted.endswith(".py"):
            refs.append(quoted)
    return refs


def _agent_ref(message: str) -> Optional[str]:
    match = re.search(r"agent '([^']+)'", message)
    if match:
        return match.group(1)
    return None


def _instruction_path_for(root: Path, agent_ref: str) -> Optional[Path]:
    agents_dir = root / "agents"
    if not agents_dir.exists():
        return None

    for agent_dir in sorted(agents_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        config_path = agent_dir / f"{agent_dir.name}.json"
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text())
        except (OSError, ValueError):
            continue
        if agent_ref not in (agent_dir.name, config.get("displayName")):
            continue
        ref = config.get("instruction")
        if isinstance(ref, str):
            return root / ref
        fallback = agent_dir / "instruction.txt"
        return fallback if fallback.exists() else None
    return None


def _rel(root: Path, path: Path | str) -> str:
    candidate = Path(path)
    try:
        return str(candidate.relative_to(root))
    except ValueError:
        return str(candidate)
