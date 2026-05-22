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

"""Scaffold planner for ``cxas poly init``.

The planner builds a deterministic list of files before anything is written.
That keeps the CLI honest about exactly which current adapter-card fields it
uses, lets tests validate the result without shelling out, and gives future
template work one small seam to extend.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from cxas_scrapi.poly.engine import CALLBACK_TYPE_TO_DIR, PolymorphismEngine
from cxas_scrapi.poly.models import CHANNEL_TYPES, MODALITIES, CallbackType

DEFAULT_DISPLAY_NAME_TEMPLATE = "{app} - {channel_title}"

_CHANNEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_CHANNEL_DEFAULTS: Dict[str, Tuple[str, str]] = {
    "api": ("API", "CHAT_ONLY"),
    "chat": ("WEB_UI", "CHAT_ONLY"),
    "phone": ("GOOGLE_TELEPHONY_PLATFORM", "VOICE_ONLY"),
    "telephony": ("GOOGLE_TELEPHONY_PLATFORM", "VOICE_ONLY"),
    "voice": ("GOOGLE_TELEPHONY_PLATFORM", "VOICE_ONLY"),
    "web": ("WEB_UI", "CHAT_ONLY"),
}

_CALLBACK_FUNCTIONS: Dict[str, str] = {
    "before_model": "before_model_callback",
    "after_model": "after_model_callback",
    "before_tool": "before_tool_callback",
    "after_tool": "after_tool_callback",
    "before_agent": "before_agent_callback",
    "after_agent": "after_agent_callback",
}


@dataclass(frozen=True)
class ScaffoldFile:
    """One file that ``cxas poly init`` intends to materialize."""

    path: Path
    content: str


@dataclass(frozen=True)
class ChannelScaffold:
    """Scaffold metadata for a single adapter channel."""

    channel: str
    adapter_path: Path
    display_name: str
    deployment_target: Optional[str]
    modality: Optional[str]


@dataclass(frozen=True)
class ScaffoldPlan:
    """A complete, writable scaffold plan for one base project."""

    app_dir: Path
    target_agent: str
    channels: List[ChannelScaffold]
    files: List[ScaffoldFile] = field(default_factory=list)


@dataclass(frozen=True)
class ScaffoldOptions:
    """Options accepted by the scaffold planner.

    The CLI converts flags and prompts into this type so validation and file
    generation stay independent of argparse.
    """

    app_dir: Path
    channels: Sequence[str]
    target_agent: Optional[str] = None
    display_name: Optional[str] = None
    display_name_template: str = DEFAULT_DISPLAY_NAME_TEMPLATE
    deployment_target: str = "auto"
    modality: str = "auto"
    include_eval: bool = True
    tools: Sequence[str] = ()
    callback_types: Sequence[CallbackType] = ()


def build_scaffold_plan(options: ScaffoldOptions) -> ScaffoldPlan:
    """Build a deterministic scaffold plan from an existing base app.

    The plan only includes fields supported by the current ``AdapterCard``
    model, which prevents the init flow from promising runtime behavior the
    engine cannot compile today.
    """
    app_dir = options.app_dir.resolve()
    engine = PolymorphismEngine(str(app_dir))
    base = engine.load_base_project()
    app_name = str(base.app_json.get("displayName") or app_dir.name)
    target_agent = _resolve_target_agent(engine, options.target_agent)

    channels = [_normalize_channel(c) for c in options.channels]
    if not channels:
        raise ValueError("At least one channel is required.")
    if len(set(channels)) != len(channels):
        raise ValueError("Channel names must be unique.")

    tools = [_normalize_tool_name(t) for t in options.tools]
    callback_types = list(options.callback_types)
    files: List[ScaffoldFile] = []
    channel_plans: List[ChannelScaffold] = []

    for channel in channels:
        display_name = _display_name_for(options, app_name, channel, channels)
        deployment_target, modality = _resolve_deployment(
            channel, options.deployment_target, options.modality
        )
        adapter = _adapter_dict(
            channel=channel,
            display_name=display_name,
            app_name=app_name,
            target_agent=target_agent,
            deployment_target=deployment_target,
            modality=modality,
            include_eval=options.include_eval,
            tools=tools,
            callback_types=callback_types,
        )
        adapter_path = app_dir / "adapters" / f"{channel}.adapter.yaml"
        files.append(
            ScaffoldFile(
                path=adapter_path,
                content=yaml.safe_dump(adapter, sort_keys=False),
            )
        )

        if options.include_eval:
            eval_name = f"{_title_token(channel)}_Smoke"
            eval_path = (
                app_dir
                / "adapters"
                / f"{channel}_evals"
                / eval_name
                / f"{eval_name}.yaml"
            )
            files.append(
                ScaffoldFile(
                    path=eval_path,
                    content=yaml.safe_dump(
                        _eval_dict(channel, display_name),
                        sort_keys=False,
                    ),
                )
            )

        for tool in tools:
            files.extend(_tool_files(app_dir, app_name, channel, tool))

        for callback_type in callback_types:
            files.append(
                _callback_file(app_dir, channel, callback_type, target_agent)
            )

        channel_plans.append(
            ChannelScaffold(
                channel=channel,
                adapter_path=adapter_path,
                display_name=display_name,
                deployment_target=deployment_target,
                modality=modality,
            )
        )

    return ScaffoldPlan(
        app_dir=app_dir,
        target_agent=target_agent,
        channels=channel_plans,
        files=files,
    )


def write_scaffold_plan(
    plan: ScaffoldPlan,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> List[Path]:
    """Write a scaffold plan without clobbering user files by default."""
    existing = [f.path for f in plan.files if f.path.exists()]
    if existing and not force:
        rels = ", ".join(str(p.relative_to(plan.app_dir)) for p in existing)
        raise FileExistsError(
            "Refusing to overwrite existing scaffold file(s): "
            f"{rels}. Re-run with --force to replace them."
        )

    written: List[Path] = []
    if dry_run:
        return [f.path for f in plan.files]

    for file in plan.files:
        file.path.parent.mkdir(parents=True, exist_ok=True)
        file.path.write_text(file.content)
        written.append(file.path)
    return written


def _resolve_target_agent(
    engine: PolymorphismEngine, requested: Optional[str]
) -> str:
    assert engine.base is not None
    agents = engine.base.agents
    display_to_dir = {b.display_name: name for name, b in agents.items()}
    if requested:
        if requested in agents:
            return requested
        if requested in display_to_dir:
            return display_to_dir[requested]
        raise ValueError(
            f"Agent '{requested}' was not found. Available agents: "
            f"{', '.join(sorted(agents)) or '(none)'}"
        )

    root = engine.base.app_json.get("rootAgent")
    if isinstance(root, str):
        if root in agents:
            return root
        if root in display_to_dir:
            return display_to_dir[root]
    if agents:
        return sorted(agents)[0]
    raise ValueError("No agents found under agents/.")


def _normalize_channel(channel: str) -> str:
    cleaned = channel.strip()
    if not cleaned:
        raise ValueError("Channel names may not be empty.")
    if not _CHANNEL_RE.match(cleaned):
        raise ValueError(
            "Channel names must start with a letter or number and contain "
            "only letters, numbers, underscores, or hyphens."
        )
    return cleaned


def _normalize_tool_name(tool_name: str) -> str:
    cleaned = tool_name.strip()
    if not _TOOL_RE.match(cleaned):
        raise ValueError(
            "Tool names scaffolded by poly init must be snake_case, start "
            "with a lowercase letter, and contain only lowercase letters, "
            "numbers, or underscores."
        )
    return cleaned


def _display_name_for(
    options: ScaffoldOptions,
    app_name: str,
    channel: str,
    all_channels: Sequence[str],
) -> str:
    if options.display_name is not None:
        if len(all_channels) > 1:
            raise ValueError(
                "--display-name can only be used with one channel."
            )
        return options.display_name
    return options.display_name_template.format(
        app=app_name,
        channel=channel,
        channel_title=_title(channel),
        channel_slug=channel,
    )


def _resolve_deployment(
    channel: str, deployment_target: str, modality: str
) -> Tuple[Optional[str], Optional[str]]:
    resolved_target: Optional[str]
    resolved_modality: Optional[str]

    if deployment_target == "none":
        resolved_target = None
    elif deployment_target == "auto":
        default_target, _default_modality = _CHANNEL_DEFAULTS.get(
            channel.lower(), (None, None)
        )
        resolved_target = default_target
    else:
        if deployment_target not in CHANNEL_TYPES:
            raise ValueError(
                "--deployment-target must be 'auto', 'none', or one of "
                f"{', '.join(CHANNEL_TYPES)}."
            )
        resolved_target = deployment_target

    if modality == "none":
        resolved_modality = None
    elif modality == "auto" and deployment_target == "none":
        resolved_modality = None
    elif modality == "auto":
        _default_target, default_modality = _CHANNEL_DEFAULTS.get(
            channel.lower(), (None, None)
        )
        resolved_modality = default_modality
    else:
        if modality not in MODALITIES:
            raise ValueError(
                "--modality must be 'auto', 'none', or one of "
                f"{', '.join(MODALITIES)}."
            )
        resolved_modality = modality

    return resolved_target, resolved_modality


def _adapter_dict(
    *,
    channel: str,
    display_name: str,
    app_name: str,
    target_agent: str,
    deployment_target: Optional[str],
    modality: Optional[str],
    include_eval: bool,
    tools: Sequence[str],
    callback_types: Sequence[str],
) -> Dict[str, Any]:
    adapter: Dict[str, Any] = {
        "apiVersion": "poly.cxas.dev/v1",
        "kind": "ChannelAdapter",
        "metadata": {
            "channel": channel,
            "displayName": display_name,
            "description": (
                f"Starter {channel} adapter for {app_name}. Replace the "
                "scaffolded notes with channel-specific behavior."
            ),
        },
        "instructionDiffs": [
            {
                "agent": target_agent,
                "mode": "append",
                "content": _instruction_block(channel),
            }
        ],
    }

    if tools:
        adapter["tools"] = [{"agent": target_agent, "add": list(tools)}]
        adapter["toolDefinitions"] = [
            {
                "displayName": tool,
                "toolType": "python",
                "sourceDir": f"adapters/{channel}_tools/{tool}",
            }
            for tool in tools
        ]

    if callback_types:
        adapter["callbacks"] = [
            {
                "agent": target_agent,
                "type": callback_type,
                "pythonCode": (
                    f"adapters/{channel}_callbacks/{callback_type}.py"
                ),
                "description": (
                    f"Starter {channel} {callback_type} callback. Replace "
                    "with channel-specific runtime hints."
                ),
            }
            for callback_type in callback_types
        ]

    if include_eval:
        adapter["evaluations"] = [
            {"sourceDir": f"adapters/{channel}_evals"}
        ]

    if deployment_target is not None or modality is not None:
        deployment: Dict[str, Any] = {}
        if deployment_target is not None:
            deployment["channelType"] = deployment_target
        if modality is not None:
            deployment["modality"] = modality
        if deployment_target == "WEB_UI":
            deployment["webWidgetConfig"] = {
                "theme": "LIGHT",
                "webWidgetTitle": display_name,
            }
        adapter["deployment"] = deployment

    return adapter


def _instruction_block(channel: str) -> str:
    tag = f"channel_{_xml_token(channel)}"
    return (
        f"<{tag}>\n"
        f"Starter {channel} channel notes:\n"
        "- Replace this block with behavior that belongs only in this "
        "channel.\n"
        "- Keep shared business logic in the base agent.\n"
        f"</{tag}>\n"
    )


def _eval_dict(channel: str, display_name: str) -> Dict[str, Any]:
    return {
        "displayName": f"{_title(channel)} Smoke",
        "description": (
            f"Starter {channel} evaluation generated for {display_name}. "
            "Replace with a real channel-specific golden."
        ),
        "tags": ["polymorphism", channel, "scaffold"],
        "golden": {
            "turns": [
                {
                    "steps": [
                        {"userInput": {"text": "hello"}},
                        {
                            "expectation": {
                                "note": (
                                    f"Check_{_title_token(channel)}_Response"
                                )
                            }
                        },
                    ]
                }
            ]
        },
    }


def _tool_files(
    app_dir: Path, app_name: str, channel: str, tool_name: str
) -> List[ScaffoldFile]:
    tool_dir = app_dir / "adapters" / f"{channel}_tools" / tool_name
    tool_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{app_name}:{channel}:{tool_name}"
    )
    tool_json = {
        "name": str(tool_id),
        "displayName": tool_name,
        "pythonFunction": {
            "name": tool_name,
            "pythonCode": f"tools/{tool_name}/python_function/python_code.py",
            "description": (
                f"Starter {channel}-only tool. Replace the implementation "
                "and description with the channel-specific action this "
                "adapter needs."
            ),
        },
    }
    return [
        ScaffoldFile(
            path=tool_dir / f"{tool_name}.json",
            content=json.dumps(tool_json, indent=2) + "\n",
        ),
        ScaffoldFile(
            path=tool_dir / "python_code.py",
            content=_tool_code(tool_name, channel),
        ),
    ]


def _tool_code(tool_name: str, channel: str) -> str:
    return (
        '"""Starter channel-only tool generated by cxas poly init."""\n\n'
        "from typing import Any\n\n\n"
        f"def {tool_name}(summary: str = \"\") -> dict[str, Any]:\n"
        f"  \"\"\"Return a starter payload for the {channel} channel.\"\"\"\n"
        "  return {\n"
        '      "stored": True,\n'
        f'      "channel": "{channel}",\n'
        '      "summary": summary,\n'
        "  }\n"
    )


def _callback_file(
    app_dir: Path, channel: str, callback_type: str, target_agent: str
) -> ScaffoldFile:
    callback_dir = CALLBACK_TYPE_TO_DIR[callback_type]
    path = app_dir / "adapters" / f"{channel}_callbacks" / f"{callback_type}.py"
    function_name = _CALLBACK_FUNCTIONS[callback_type]
    content = (
        "# pylint: disable=unused-argument,broad-exception-caught\n"
        f'"""Starter {callback_type} callback for the {channel} adapter."""\n\n'
        "from typing import Any, Optional\n\n\n"
        f"def {function_name}(\n"
        "    callback_context: Any,\n"
        "    llm_request: Any,\n"
        ") -> Optional[Any]:\n"
        f"  \"\"\"Inject starter {channel} hints for {target_agent}.\"\"\"\n"
        "  hint = (\n"
        f'      "Starter {channel} channel hint. Replace this callback with "\n'
        '      "real channel-specific runtime behavior, or delete it if "\n'
        '      "static instruction diffs are enough."\n'
        "  )\n"
        "  try:\n"
        "    llm_request.append_instructions([hint])\n"
        "  except Exception:\n"
        "    return None\n"
        "  return None\n"
    )
    # The directory name is referenced in comments for maintainers, while the
    # adapter card references only the project-relative pythonCode path.
    if callback_dir not in CALLBACK_TYPE_TO_DIR.values():
        raise ValueError(f"Unsupported callback type: {callback_type}")
    return ScaffoldFile(path=path, content=content)


def _title(channel: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", channel))


def _title_token(channel: str) -> str:
    return "_".join(part.capitalize() for part in re.split(r"[-_]+", channel))


def _xml_token(channel: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", channel).strip("_") or "channel"


def split_channels(values: Iterable[str]) -> List[str]:
    """Split comma-delimited ``--channel`` values while preserving order."""
    channels: List[str] = []
    for value in values:
        channels.extend(p.strip() for p in value.split(",") if p.strip())
    return channels
