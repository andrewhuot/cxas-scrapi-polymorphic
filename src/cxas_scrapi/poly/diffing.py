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

"""Stable diff reports for ``cxas poly diff``.

The CLI renders both human text and ``--json`` from this report so CI tooling
and reviewers reason from the same compiled delta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cxas_scrapi.poly.engine import PolymorphismEngine
from cxas_scrapi.poly.models import AdapterCard, CompiledAgentConfig

DIFF_SCHEMA_VERSION = "poly-diff/v1"


def build_diff_report(
    *,
    engine: PolymorphismEngine,
    card: AdapterCard,
    card_path: Path,
    compiled: CompiledAgentConfig,
) -> Dict[str, Any]:
    """Build a stable, machine-readable adapter delta report."""
    if engine.base is None:
        engine.load_base_project()
    assert engine.base is not None

    root = engine.app_dir
    display_to_dir = {
        bundle.display_name: name
        for name, bundle in engine.base.agents.items()
    }

    def to_dir(agent_ref: str) -> Optional[str]:
        if agent_ref in engine.base.agents:
            return agent_ref
        return display_to_dir.get(agent_ref)

    touched = set()
    for diff in card.instruction_diffs:
        touched.add(to_dir(diff.agent))
    for tool_change in card.tools:
        touched.add(to_dir(tool_change.agent))
    for model in card.model_overrides:
        touched.add(to_dir(model.agent))
    for callback in card.callbacks:
        touched.add(to_dir(callback.agent))
    touched.discard(None)

    agents: List[Dict[str, Any]] = []
    deltas: List[Dict[str, Any]] = []
    for dir_name in sorted(touched):
        assert dir_name is not None
        base_bundle = engine.base.agents[dir_name]
        compiled_agent = compiled.agents[dir_name]
        agent_report: Dict[str, Any] = {
            "agent": dir_name,
            "display_name": base_bundle.display_name,
            "path": f"agents/{dir_name}",
            "instruction_diffs": [],
            "tools": {"added": [], "removed": []},
            "model": None,
            "callbacks_added": [],
        }

        for diff in card.instruction_diffs:
            if to_dir(diff.agent) != dir_name:
                continue
            item = {
                "mode": diff.mode,
                "section_tag": diff.section_tag,
                "line_count": _line_count(diff.content),
                "preview": _preview(diff.content),
                "path": f"agents/{dir_name}/instruction.txt",
            }
            agent_report["instruction_diffs"].append(item)
            deltas.append(
                {
                    "type": "instruction",
                    "agent": dir_name,
                    **item,
                }
            )

        base_tools = list(base_bundle.config.get("tools", []) or [])
        compiled_tools = list(compiled_agent.get("tools", []) or [])
        added = [tool for tool in compiled_tools if tool not in base_tools]
        removed = [tool for tool in base_tools if tool not in compiled_tools]
        agent_report["tools"] = {
            "before_count": len(base_tools),
            "after_count": len(compiled_tools),
            "added": added,
            "removed": removed,
        }
        for tool in added:
            deltas.append(
                {"type": "tool_add", "agent": dir_name, "tool": tool}
            )
        for tool in removed:
            deltas.append(
                {"type": "tool_remove", "agent": dir_name, "tool": tool}
            )

        before_model = (base_bundle.config.get("modelSettings") or {}).get(
            "model"
        )
        after_model = (compiled_agent.get("modelSettings") or {}).get("model")
        if before_model != after_model:
            model_delta = {
                "before": before_model,
                "after": after_model,
                "changed": True,
            }
            agent_report["model"] = model_delta
            deltas.append(
                {
                    "type": "model_override",
                    "agent": dir_name,
                    **model_delta,
                }
            )

        for callback in card.callbacks:
            if to_dir(callback.agent) != dir_name:
                continue
            item = {
                "type": callback.type,
                "python_code": callback.python_code,
                "description": callback.description,
            }
            agent_report["callbacks_added"].append(item)
            deltas.append(
                {
                    "type": "callback_add",
                    "agent": dir_name,
                    "callback_type": callback.type,
                    "python_code": callback.python_code,
                    "description": callback.description,
                }
            )

        agents.append(agent_report)

    tools_added = [
        {
            "display_name": td.display_name,
            "tool_type": td.tool_type,
            "source_dir": td.source_dir,
        }
        for td in card.tool_definitions
    ]
    for tool in tools_added:
        deltas.append({"type": "tool_definition_add", **tool})

    evals = {
        "evaluations": sorted(compiled.evaluations),
        "evaluation_expectations": sorted(compiled.evaluation_expectations),
        "evaluation_datasets": sorted(compiled.evaluation_datasets),
    }
    for kind, names in evals.items():
        for name in names:
            deltas.append({"type": f"{kind}_merge", "name": name})

    deployment = compiled.deployment or {}
    if deployment:
        deltas.append({"type": "deployment", "values": deployment})

    gecx_config = card.gecx_config
    if gecx_config:
        deltas.append({"type": "gecx_config_overlay", "values": gecx_config})

    return {
        "schema_version": DIFF_SCHEMA_VERSION,
        "channel": card.metadata.channel,
        "adapter_path": _rel(root, card_path),
        "app_dir": str(root),
        "summary": {
            "agents_touched": len(agents),
            "instruction_diffs": sum(
                len(agent["instruction_diffs"]) for agent in agents
            ),
            "tools_added": sum(
                len(agent["tools"]["added"]) for agent in agents
            ),
            "tools_removed": sum(
                len(agent["tools"]["removed"]) for agent in agents
            ),
            "tool_definitions_added": len(tools_added),
            "callbacks_added": sum(
                len(agent["callbacks_added"]) for agent in agents
            ),
            "evaluations_added": len(evals["evaluations"]),
            "evaluation_expectations_added": len(
                evals["evaluation_expectations"]
            ),
            "evaluation_datasets_added": len(evals["evaluation_datasets"]),
            "deployment_changed": bool(deployment),
            "gecx_config_changed": bool(gecx_config),
        },
        "agents": agents,
        "tool_definitions_added": tools_added,
        "evaluation_merges": evals,
        "gecx_config_overlay": gecx_config,
        "deployment": deployment,
        "deltas": deltas,
    }


def _line_count(content: str) -> int:
    stripped = content.strip()
    if not stripped:
        return 0
    return len(stripped.splitlines())


def _preview(content: str, limit: int = 3) -> List[str]:
    return content.strip().splitlines()[:limit]


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
