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

"""Adapter card validators (AD001-AD010).

Pure local validation run before compilation.  Each function returns a
list of issue dicts shaped like ``LintResult``: ``{rule_id, severity,
message, path}``.  These same checks back the ``adapters`` lint rule
category (see ``utils/lint_rules/adapters.py``) and are the **single source
of truth** the engine relies on — ``engine.compile`` runs them up front so a
card that validates clean always compiles, and a card that would fail to
compile is always reported here first.

Note on rule IDs: the original spec proposed ``A001``-``A007`` but those
collide with the existing ``config`` lint rules, so adapter rules use the
``AD`` prefix.

    AD001  schema / required fields / unknown fields
    AD002  referenced agents exist
    AD003  replace_section sectionTag present and the section exists
    AD004  tool remove targets a tool the base agent actually has  (warning)
    AD005  referenced source missing / tool add has no definition
    AD006  adapter declares at least one evaluations entry          (warning)
    AD007  two adapters target the same channel
    AD008  a referenced path is absolute or escapes the project root
    AD009  deployment channelType/modality/theme is a known value
    AD010  toolDefinitions.toolType is supported
    AD011  appIdentity well-formed (name a valid UUID; displayName non-empty)
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cxas_scrapi.poly.instructions import has_section
from cxas_scrapi.poly.models import (
    CHANNEL_TYPES,
    MODALITIES,
    SUPPORTED_TOOL_TYPES,
    THEMES,
    AdapterCard,
)

ERROR = "error"
WARNING = "warning"

# Runtime-provided tools that are always valid as an agent tool reference,
# even though they have no directory under ``tools/``.  Mirrors
# ``cxas_scrapi.utils.linter.LintContext.platform_tools`` — kept local to avoid
# an import cycle (linter -> lint_rules -> adapters -> validators).
PLATFORM_TOOLS = frozenset({"end_session", "customize_response"})


# ── Filesystem helpers ───────────────────────────────────────────────────


def _agents_dir(app_dir: str) -> Path:
    return Path(app_dir) / "agents"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def resolve_within(app_dir: str, ref: str) -> Tuple[Path, bool]:
    """Resolve an adapter-relative path and report whether it stays in scope.

    Adapter ``sourceDir``/``pythonCode`` references are interpreted relative to
    the project root (``app_dir``).  Returns ``(resolved_path, is_inside)``
    where ``is_inside`` is False for absolute paths or anything that escapes
    the root via ``..`` — the engine and validators both refuse those so cards
    stay portable across machines.
    """
    base = Path(app_dir).resolve()
    raw = Path(ref)
    if raw.is_absolute():
        return raw.resolve(), False
    candidate = (base / ref).resolve()
    try:
        candidate.relative_to(base)
        return candidate, True
    except ValueError:
        return candidate, False


def _agent_dir_for(app_dir: str, agent_name: str) -> Optional[Path]:
    """Resolve an agent reference (display name or dir name) to its dir."""
    agents = _agents_dir(app_dir)
    if not agents.exists():
        return None
    direct = agents / agent_name
    if direct.is_dir() and (direct / f"{agent_name}.json").exists():
        return direct
    for d in sorted(agents.iterdir()):
        if not d.is_dir():
            continue
        cfg = _read_json(d / f"{d.name}.json")
        if cfg and cfg.get("displayName") == agent_name:
            return d
    return None


def _get_agent_display_names(app_dir: str) -> List[str]:
    """List all agent display names from the ``agents/`` directory."""
    agents = _agents_dir(app_dir)
    names: List[str] = []
    if not agents.exists():
        return names
    for d in sorted(agents.iterdir()):
        if not d.is_dir():
            continue
        cfg = _read_json(d / f"{d.name}.json")
        if cfg and cfg.get("displayName"):
            names.append(cfg["displayName"])
        else:
            names.append(d.name)
    return names


def _get_agent_tools(app_dir: str, agent_name: str) -> List[str]:
    """Read an agent's JSON and return its tools list."""
    d = _agent_dir_for(app_dir, agent_name)
    if d is None:
        return []
    cfg = _read_json(d / f"{d.name}.json")
    if not cfg:
        return []
    return list(cfg.get("tools", []) or [])


def _get_instruction_text(app_dir: str, agent_name: str) -> str:
    """Read and return the instruction text for an agent."""
    d = _agent_dir_for(app_dir, agent_name)
    if d is None:
        return ""
    cfg = _read_json(d / f"{d.name}.json")
    ref = (cfg or {}).get("instruction")
    if ref:
        inst = Path(app_dir) / ref
        if inst.exists():
            return inst.read_text()
    fallback = d / "instruction.txt"
    if fallback.exists():
        return fallback.read_text()
    return ""


def _get_project_tool_names(app_dir: str) -> set:
    """All tool names referenceable in the base project.

    Includes each tool's ``displayName`` (the canonical reference, since agent
    ``tools`` lists use display names) plus the directory name as a fallback.
    """
    tools = Path(app_dir) / "tools"
    names: set = set()
    if not tools.exists():
        return names
    for d in sorted(tools.iterdir()):
        if not d.is_dir():
            continue
        names.add(d.name)
        cfg = _read_json(d / f"{d.name}.json")
        if cfg is None:
            for cand in d.glob("*.json"):
                cfg = _read_json(cand)
                if cfg:
                    break
        if cfg and cfg.get("displayName"):
            names.add(cfg["displayName"])
    return names


def _dir_has_json(path: Path) -> bool:
    return path.is_dir() and any(path.rglob("*.json"))


# ── Validation ───────────────────────────────────────────────────────────


def validate_adapter_card(
    adapter: AdapterCard, app_dir: str
) -> List[Dict[str, Any]]:
    """Validate a single adapter card against the project structure.

    Returns a list of issue dicts (may be empty).  Covers AD001-AD006 and
    AD008-AD010; cross-adapter AD007 is handled by
    :func:`validate_all_adapters`.
    """
    issues: List[Dict[str, Any]] = []
    channel = adapter.metadata.channel
    where = f"adapters ({channel})"

    def add(rule_id: str, severity: str, message: str) -> None:
        issues.append(
            {
                "rule_id": rule_id,
                "severity": severity,
                "message": message,
                "path": where,
            }
        )

    # AD001 — required fields / valid types.  The card is already parsed, so we
    # only assert the channel identifier is non-empty here.
    if not channel:
        add("AD001", ERROR, "Adapter metadata.channel must be non-empty.")

    known_agents = set(_get_agent_display_names(app_dir))
    # Also accept directory names so a card may reference either form.
    agents_root = _agents_dir(app_dir)
    if agents_root.exists():
        known_agents |= {d.name for d in agents_root.iterdir() if d.is_dir()}

    def check_agent(agent: str, section: str, idx: int) -> bool:
        if agent not in known_agents:
            add(
                "AD002",
                ERROR,
                f"Agent '{agent}' referenced in {section}[{idx}] does not "
                "exist in agents/ directory",
            )
            return False
        return True

    # AD002 — referenced agents exist.
    for i, diff in enumerate(adapter.instruction_diffs):
        check_agent(diff.agent, "instructionDiffs", i)
    for i, mod in enumerate(adapter.tools):
        check_agent(mod.agent, "tools", i)
    for i, mo in enumerate(adapter.model_overrides):
        check_agent(mo.agent, "modelOverrides", i)
    for i, cb in enumerate(adapter.callbacks):
        check_agent(cb.agent, "callbacks", i)

    # AD003 — replace_section requires sectionTag present in instruction.
    for i, diff in enumerate(adapter.instruction_diffs):
        if diff.mode != "replace_section":
            continue
        if not diff.section_tag:
            add(
                "AD003",
                ERROR,
                f"instructionDiffs[{i}] uses replace_section but has no "
                "sectionTag",
            )
            continue
        if diff.agent not in known_agents:
            continue
        text = _get_instruction_text(app_dir, diff.agent)
        if not has_section(text, diff.section_tag):
            add(
                "AD003",
                ERROR,
                f"Section <{diff.section_tag}> from instructionDiffs[{i}] not "
                f"found in instruction for agent '{diff.agent}'",
            )

    project_tools = _get_project_tool_names(app_dir)
    defined_tools = {td.display_name for td in adapter.tool_definitions}

    # AD004 — removing a tool not present in the base agent's tools list.
    # AD005 — adding a tool with no definition anywhere.
    for i, mod in enumerate(adapter.tools):
        base_tools = set(_get_agent_tools(app_dir, mod.agent))
        for t in mod.remove:
            if t not in base_tools:
                add(
                    "AD004",
                    WARNING,
                    f"tools[{i}] removes '{t}' which is not in agent "
                    f"'{mod.agent}' base tools list",
                )
        for t in mod.add:
            if (
                t not in project_tools
                and t not in defined_tools
                and t not in PLATFORM_TOOLS
            ):
                add(
                    "AD005",
                    ERROR,
                    f"tools[{i}] adds '{t}' which has no definition in tools/, "
                    "no matching toolDefinitions entry, and is not a platform "
                    "tool",
                )

    # AD010 — toolDefinitions declare a supported toolType.
    # AD008/AD005 — toolDefinitions sourceDir is in-scope and present.
    for i, td in enumerate(adapter.tool_definitions):
        if td.tool_type not in SUPPORTED_TOOL_TYPES:
            add(
                "AD010",
                ERROR,
                f"toolDefinitions[{i}] toolType '{td.tool_type}' is not "
                "supported (expected one of "
                f"{', '.join(SUPPORTED_TOOL_TYPES)})",
            )
        path, inside = resolve_within(app_dir, td.source_dir)
        if not inside:
            add(
                "AD008",
                ERROR,
                f"toolDefinitions[{i}] sourceDir '{td.source_dir}' resolves "
                "to an absolute path or outside the project root",
            )
        elif not _dir_has_json(path):
            add(
                "AD005",
                ERROR,
                f"toolDefinitions[{i}] sourceDir '{td.source_dir}' is missing "
                "or contains no JSON definition",
            )

    # AD008/AD005 — callback pythonCode is in-scope and present.
    for i, cb in enumerate(adapter.callbacks):
        path, inside = resolve_within(app_dir, cb.python_code)
        if not inside:
            add(
                "AD008",
                ERROR,
                f"callbacks[{i}] pythonCode '{cb.python_code}' resolves "
                "to an absolute path or outside the project root",
            )
        elif not path.is_file():
            add(
                "AD005",
                ERROR,
                f"callbacks[{i}] pythonCode '{cb.python_code}' was not found "
                f"for agent '{cb.agent}'",
            )

    # AD008/AD005 — evaluation/expectation/dataset sourceDirs.
    for label, refs in (
        ("evaluations", adapter.evaluations),
        ("evaluationExpectations", adapter.evaluation_expectations),
        ("evaluationDatasets", adapter.evaluation_datasets),
    ):
        for i, ev in enumerate(refs):
            path, inside = resolve_within(app_dir, ev.source_dir)
            if not inside:
                add(
                    "AD008",
                    ERROR,
                    f"{label}[{i}] sourceDir '{ev.source_dir}' resolves "
                    "to an absolute path or outside the project root",
                )
            elif not path.is_dir():
                add(
                    "AD005",
                    ERROR,
                    f"{label}[{i}] sourceDir '{ev.source_dir}' does not exist",
                )

    # AD009 — deployment uses known channelType / modality / theme values.
    dep = adapter.deployment
    if dep is not None:
        ct = dep.channel_type
        if ct is not None and ct not in CHANNEL_TYPES:
            add(
                "AD009",
                ERROR,
                f"deployment.channelType '{dep.channel_type}' is not one of "
                f"{', '.join(CHANNEL_TYPES)}",
            )
        if dep.modality is not None and dep.modality not in MODALITIES:
            add(
                "AD009",
                ERROR,
                f"deployment.modality '{dep.modality}' is not one of "
                f"{', '.join(MODALITIES)}",
            )
        wwc = dep.web_widget_config
        if wwc is not None:
            if wwc.theme is not None and wwc.theme not in THEMES:
                add(
                    "AD009",
                    ERROR,
                    f"deployment.webWidgetConfig.theme '{wwc.theme}' is not "
                    f"one of {', '.join(THEMES)}",
                )
            if wwc.modality is not None and wwc.modality not in MODALITIES:
                add(
                    "AD009",
                    ERROR,
                    f"deployment.webWidgetConfig.modality '{wwc.modality}' is "
                    f"not one of {', '.join(MODALITIES)}",
                )

    # AD011 — appIdentity is well-formed when present.
    ident = adapter.app_identity
    if ident is not None:
        if ident.display_name is not None and not ident.display_name.strip():
            add(
                "AD011",
                ERROR,
                "appIdentity.displayName must be non-empty when set.",
            )
        if ident.name is not None:
            try:
                uuid.UUID(str(ident.name))
            except (ValueError, AttributeError, TypeError):
                add(
                    "AD011",
                    ERROR,
                    f"appIdentity.name '{ident.name}' is not a valid UUID.",
                )

    # AD006 — adapter has no evaluations.
    if not adapter.evaluations:
        add(
            "AD006",
            WARNING,
            f"Adapter for channel '{channel}' has no evaluations entries",
        )

    return issues


def validate_all_adapters(
    adapters: List[AdapterCard], app_dir: str
) -> List[Dict[str, Any]]:
    """Validate all adapter cards, including cross-adapter checks (AD007)."""
    issues: List[Dict[str, Any]] = []
    for adapter in adapters:
        issues.extend(validate_adapter_card(adapter, app_dir))

    # AD007 — two adapters targeting the same channel.
    seen: Dict[str, int] = {}
    for adapter in adapters:
        ch = adapter.metadata.channel
        seen[ch] = seen.get(ch, 0) + 1
    for ch, count in seen.items():
        if count > 1:
            issues.append(
                {
                    "rule_id": "AD007",
                    "severity": ERROR,
                    "message": (
                        f"{count} adapter cards target the same channel '{ch}'"
                    ),
                    "path": "adapters",
                }
            )

    return issues
