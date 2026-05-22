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

"""Pydantic data models for the Polymorphism Engine.

Defines the schema for channel adapter cards — declarative deltas applied
to a base agent project to produce channel-optimized variants — plus the
in-memory shape of a compiled project (``CompiledAgentConfig``).  Unknown
adapter fields are rejected so misspelled deltas do not disappear silently.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Both ``populate_by_name`` (so YAML camelCase aliases work alongside
# snake_case Python attribute access) and ``protected_namespaces=()`` (to
# allow field names like ``model_overrides`` and ``model`` without Pydantic
# v2 warnings about the reserved ``model_`` namespace) are needed on every
# model in this module.
_MODEL_CONFIG = ConfigDict(
    populate_by_name=True,
    protected_namespaces=(),
    extra="forbid",
)

# Logical callback types accepted in adapter cards.  These map to JSON
# field names like ``beforeModelCallbacks`` at compile time — see
# ``poly.engine.CALLBACK_TYPE_TO_FIELD``.
CallbackType = Literal[
    "before_model",
    "after_model",
    "before_tool",
    "after_tool",
    "before_agent",
    "after_agent",
]

# Allowed adapter ``deployment`` values.  These mirror the enums in
# ``cxas_scrapi.core.deployments.Deployments`` (ChannelType / Modality / Theme)
# but are hardcoded here on purpose: the ``poly`` package stays GCP-free and
# must not import ``google.cloud.*``.  Keep these lists in sync with that class.
CHANNEL_TYPES = (
    "WEB_UI",
    "API",
    "TWILIO",
    "GOOGLE_TELEPHONY_PLATFORM",
    "CONTACT_CENTER_AS_A_SERVICE",
    "FIVE9",
    "CONTACT_CENTER_INTEGRATION",
)
MODALITIES = (
    "CHAT_AND_VOICE",
    "VOICE_ONLY",
    "CHAT_ONLY",
    "CHAT_VOICE_AND_VIDEO",
)
THEMES = ("LIGHT", "DARK")

# Tool definition types the engine knows how to compile.
SUPPORTED_TOOL_TYPES = ("python", "openapi")


class AdapterMetadata(BaseModel):
    """Metadata about the channel adapter."""

    model_config = _MODEL_CONFIG

    channel: str
    display_name: str = Field(alias="displayName")
    description: str = ""


class InstructionDiff(BaseModel):
    """A modification to an agent's instruction text."""

    model_config = _MODEL_CONFIG

    agent: str
    mode: Literal["append", "prepend", "replace_section"]
    section_tag: Optional[str] = Field(default=None, alias="sectionTag")
    content: str


class ToolModification(BaseModel):
    """Tools to add or remove from an agent's tool list."""

    model_config = _MODEL_CONFIG

    agent: str
    add: List[str] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """A new tool definition only available in this channel.

    ``source_dir`` points at a directory under the adapter card's parent
    containing ``<display_name>.json`` and ``python_code.py`` (or the
    standard ``python_function/python_code.py`` layout).
    """

    model_config = _MODEL_CONFIG

    display_name: str = Field(alias="displayName")
    tool_type: str = Field(alias="toolType")
    source_dir: str = Field(alias="sourceDir")


class ModelOverride(BaseModel):
    """Override the model for a specific agent in this channel."""

    model_config = _MODEL_CONFIG

    agent: str
    model: str


class CallbackDefinition(BaseModel):
    """A channel-specific callback to add to an agent.

    ``python_code`` is a path (relative to the adapter card's parent
    directory) to a ``.py`` file whose contents will be copied into the
    compiled output and referenced from the agent JSON.
    """

    model_config = _MODEL_CONFIG

    agent: str
    type: CallbackType
    python_code: str = Field(alias="pythonCode")
    description: str = ""


class EvalReference(BaseModel):
    """Reference to a directory of channel-specific evaluations."""

    model_config = _MODEL_CONFIG

    source_dir: str = Field(alias="sourceDir")


class WebWidgetConfig(BaseModel):
    """Web widget configuration for deployment."""

    model_config = _MODEL_CONFIG

    theme: Optional[str] = None
    modality: Optional[str] = None
    web_widget_title: Optional[str] = Field(
        default=None, alias="webWidgetTitle"
    )


class DeploymentOverride(BaseModel):
    """Channel-specific deployment configuration."""

    model_config = _MODEL_CONFIG

    channel_type: Optional[str] = Field(default=None, alias="channelType")
    modality: Optional[str] = None
    disable_barge_in_control: Optional[bool] = Field(
        default=None, alias="disableBargeInControl"
    )
    disable_dtmf: Optional[bool] = Field(default=None, alias="disableDtmf")
    web_widget_config: Optional[WebWidgetConfig] = Field(
        default=None, alias="webWidgetConfig"
    )


class AdapterCard(BaseModel):
    """Complete channel adapter card definition."""

    model_config = _MODEL_CONFIG

    api_version: str = Field(alias="apiVersion")
    kind: Literal["ChannelAdapter"]
    metadata: AdapterMetadata
    instruction_diffs: List[InstructionDiff] = Field(
        default_factory=list, alias="instructionDiffs"
    )
    tools: List[ToolModification] = Field(default_factory=list)
    tool_definitions: List[ToolDefinition] = Field(
        default_factory=list, alias="toolDefinitions"
    )
    model_overrides: List[ModelOverride] = Field(
        default_factory=list, alias="modelOverrides"
    )
    callbacks: List[CallbackDefinition] = Field(default_factory=list)
    evaluations: List[EvalReference] = Field(default_factory=list)
    evaluation_expectations: List[EvalReference] = Field(
        default_factory=list, alias="evaluationExpectations"
    )
    evaluation_datasets: List[EvalReference] = Field(
        default_factory=list, alias="evaluationDatasets"
    )
    gecx_config: Dict[str, Any] = Field(
        default_factory=dict, alias="gecxConfig"
    )
    deployment: Optional[DeploymentOverride] = None


class CompiledAgentConfig(BaseModel):
    """The fully compiled, channel-specific agent project state.

    A pure-data snapshot of what ``PolymorphismEngine.write_output`` will
    serialize to disk.  Holding it as a model — rather than writing files
    directly during ``compile()`` — lets callers introspect or transform
    the output before writing.
    """

    model_config = _MODEL_CONFIG

    channel: str
    app_config: Dict[str, Any]
    gecx_config: Dict[str, Any] = Field(default_factory=dict)
    agents: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    agent_instructions: Dict[str, str] = Field(default_factory=dict)
    tools: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    tool_code: Dict[str, str] = Field(default_factory=dict)
    # Channel tool name -> absolute source directory, for tool types that are
    # copied verbatim (e.g. ``openapi``) rather than reconstructed from a
    # single JSON + ``python_code.py``.  In-memory only.
    tool_source_dirs: Dict[str, str] = Field(default_factory=dict)
    evaluations: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    evaluation_expectations: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict
    )
    evaluation_datasets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # The resolved per-channel deployment block.  Also stored under
    # ``gecx_config["deployment"]`` (the file deploy tooling reads); kept here
    # too so callers like ``cxas poly diff`` can introspect it directly.
    deployment: Optional[Dict[str, Any]] = None
    # Callback code keyed by ``(agent, cb_dir_name, cb_index)`` ->
    # python source text.  Written to disk under each agent's standard
    # callback directory tree.
    callback_code: Dict[str, str] = Field(default_factory=dict)
