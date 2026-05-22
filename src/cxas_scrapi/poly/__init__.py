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

"""Polymorphism Engine for cxas-scrapi.

Compiles a single base agent project plus channel adapter cards into
channel-optimized agent project directories that are structurally equivalent
to hand-authored projects — indistinguishable to SCRAPI tooling (lint, eval,
deploy all run on the output unchanged).

This package is intentionally GCP-free — it performs pure local file
operations and does not import ``google.cloud.*``.
"""

from cxas_scrapi.poly.engine import (
    CompilationError,
    PolymorphismEngine,
)
from cxas_scrapi.poly.models import (
    AdapterCard,
    AdapterMetadata,
    AppIdentity,
    CallbackDefinition,
    CompiledAgentConfig,
    DeploymentOverride,
    EvalReference,
    InstructionDiff,
    ModelOverride,
    ToolDefinition,
    ToolModification,
    WebWidgetConfig,
)

__all__ = [
    "AdapterCard",
    "AdapterMetadata",
    "AppIdentity",
    "CallbackDefinition",
    "CompilationError",
    "CompiledAgentConfig",
    "DeploymentOverride",
    "EvalReference",
    "InstructionDiff",
    "ModelOverride",
    "PolymorphismEngine",
    "ToolDefinition",
    "ToolModification",
    "WebWidgetConfig",
]
