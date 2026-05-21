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

"""Adapter card validators (AD001-AD007).

Pure local validation run before compilation.  Each function returns a
list of issue dicts shaped like ``LintResult``: ``{rule_id, severity,
message, path}``.  These same checks back the ``adapters`` lint rule
category (see ``utils/lint_rules/adapters.py``).

Note on rule IDs: the original spec proposed ``A001``-``A007`` but those
collide with the existing ``config`` lint rules, so adapter rules use the
``AD`` prefix.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from cxas_scrapi.poly.models import AdapterCard

ERROR = "error"
WARNING = "warning"


# ── Filesystem helpers ───────────────────────────────────────────────────


def _agents_dir(app_dir: str) -> Path:
    return Path(app_dir) / "agents"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


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


def _get_project_tool_names(app_dir: str) -> List[str]:
    """List all tool display names from the ``tools/`` directory."""
    tools = Path(app_dir) / "tools"
    if not tools.exists():
        return []
    return [d.name for d in sorted(tools.iterdir()) if d.is_dir()]


# ── Validation ───────────────────────────────────────────────────────────


def validate_adapter_card(
    adapter: AdapterCard, app_dir: str
) -> List[Dict[str, Any]]:
    """Validate a single adapter card against the project structure.

    Returns a list of issue dicts (may be empty).  Covers AD001-AD006;
    cross-adapter AD007 is handled by :func:`validate_all_adapters`.
    """
    issues: List[Dict[str, Any]] = []
    channel = adapter.metadata.channel
    where = f"adapters ({channel})"

    # AD001 — required fields / valid types.  The card is already parsed,
    # so we only assert the channel identifier is non-empty here.
    if not channel:
        issues.append(
            {
                "rule_id": "AD001",
                "severity": ERROR,
                "message": "Adapter metadata.channel must be non-empty.",
                "path": where,
            }
        )

    known_agents = set(_get_agent_display_names(app_dir))
    # Also accept directory names so a card may reference either form.
    agents_root = _agents_dir(app_dir)
    if agents_root.exists():
        known_agents |= {d.name for d in agents_root.iterdir() if d.is_dir()}

    def check_agent(agent: str, section: str, idx: int) -> bool:
        if agent not in known_agents:
            issues.append(
                {
                    "rule_id": "AD002",
                    "severity": ERROR,
                    "message": (
                        f"Agent '{agent}' referenced in {section}[{idx}] does "
                        "not exist in agents/ directory"
                    ),
                    "path": where,
                }
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
            issues.append(
                {
                    "rule_id": "AD003",
                    "severity": ERROR,
                    "message": (
                        f"instructionDiffs[{i}] uses replace_section but has "
                        "no sectionTag"
                    ),
                    "path": where,
                }
            )
            continue
        if diff.agent not in known_agents:
            continue
        text = _get_instruction_text(app_dir, diff.agent)
        if f"<{diff.section_tag}>" not in text:
            issues.append(
                {
                    "rule_id": "AD003",
                    "severity": ERROR,
                    "message": (
                        f"Section <{diff.section_tag}> from "
                        f"instructionDiffs[{i}] not found in instruction for "
                        f"agent '{diff.agent}'"
                    ),
                    "path": where,
                }
            )

    project_tools = set(_get_project_tool_names(app_dir))
    defined_tools = {td.display_name for td in adapter.tool_definitions}

    # AD004 — removing a tool not present in the base agent's tools list.
    # AD005 — adding a tool with no definition anywhere.
    for i, mod in enumerate(adapter.tools):
        base_tools = set(_get_agent_tools(app_dir, mod.agent))
        for t in mod.remove:
            if t not in base_tools:
                issues.append(
                    {
                        "rule_id": "AD004",
                        "severity": WARNING,
                        "message": (
                            f"tools[{i}] removes '{t}' which is not in agent "
                            f"'{mod.agent}' base tools list"
                        ),
                        "path": where,
                    }
                )
        for t in mod.add:
            if t not in project_tools and t not in defined_tools:
                issues.append(
                    {
                        "rule_id": "AD005",
                        "severity": ERROR,
                        "message": (
                            f"tools[{i}] adds '{t}' which has no definition in "
                            "tools/ and no matching toolDefinitions entry"
                        ),
                        "path": where,
                    }
                )

    # AD006 — adapter has no evaluations.
    if not adapter.evaluations:
        issues.append(
            {
                "rule_id": "AD006",
                "severity": WARNING,
                "message": (
                    f"Adapter for channel '{channel}' has no evaluations "
                    "entries"
                ),
                "path": where,
            }
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
