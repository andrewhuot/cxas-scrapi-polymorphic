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

"""Polymorphism compilation engine.

Reads a base agent project from disk plus channel adapter cards, then
compiles channel-optimized agent project directories.  Pure local file
I/O — no ``google.cloud.*`` imports and no network access.
"""

import copy
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import ValidationError

from cxas_scrapi.poly.instructions import apply_instruction_diff
from cxas_scrapi.poly.models import (
    AdapterCard,
    CompiledAgentConfig,
    DeploymentOverride,
)
from cxas_scrapi.poly.validators import (
    resolve_within,
    validate_adapter_card,
    validate_all_adapters,
)

# Marker file written into every compiled channel directory.  Its presence
# tells a later build that the directory is a poly artifact and is therefore
# safe to overwrite (see ``write_output``).
_POLY_MARKER = ".poly_build.json"

# Logical callback type -> agent-JSON field name (camelCase).
CALLBACK_TYPE_TO_FIELD: Dict[str, str] = {
    "before_model": "beforeModelCallbacks",
    "after_model": "afterModelCallbacks",
    "before_tool": "beforeToolCallbacks",
    "after_tool": "afterToolCallbacks",
    "before_agent": "beforeAgentCallbacks",
    "after_agent": "afterAgentCallbacks",
}

# Logical callback type -> on-disk directory name (snake_case).
CALLBACK_TYPE_TO_DIR: Dict[str, str] = {
    "before_model": "before_model_callbacks",
    "after_model": "after_model_callbacks",
    "before_tool": "before_tool_callbacks",
    "after_tool": "after_tool_callbacks",
    "before_agent": "before_agent_callbacks",
    "after_agent": "after_agent_callbacks",
}

# Top-level base-project items that the engine reconstructs (rather than
# copying verbatim) when writing output.
_RECONSTRUCTED_ITEMS = {"adapters", "agents", "app.json", "gecx-config.json"}


def _format_validation_error(e: ValidationError) -> str:
    """Render a pydantic ``ValidationError`` as a short field-pointed string."""
    parts: List[str] = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or str(e)


def _is_relative_to(a: Path, b: Path) -> bool:
    """True if path ``a`` is ``b`` or lives somewhere under ``b``."""
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False


class CompilationError(Exception):
    """Raised when compilation cannot proceed.

    Carries the full list of validation/compilation issue dicts (each with
    ``rule_id``, ``severity``, ``message``, ``path``) so callers can render
    every problem at once instead of failing on the first.
    """

    def __init__(self, issues: List[Dict[str, Any]]):
        self.issues = issues
        n = len(issues)
        super().__init__(
            f"{n} compilation error(s):\n"
            + "\n".join(
                f"  [{i.get('severity', 'error')}] {i.get('rule_id', '?')} "
                f"{i.get('path', '')}: {i.get('message', '')}"
                for i in issues
            )
        )


@dataclass
class AgentBundle:
    """In-memory representation of one base agent."""

    dir_name: str
    display_name: str
    config: Dict[str, Any]
    instruction: str
    # rel_path (from project root) -> python source for every existing
    # callback referenced by this agent's JSON.
    callback_code: Dict[str, str] = field(default_factory=dict)


@dataclass
class ToolBundle:
    """In-memory representation of one base tool."""

    dir_name: str
    config: Dict[str, Any]
    code_rel_path: Optional[str] = None
    code: Optional[str] = None


@dataclass
class BaseProject:
    """Loaded state of the base agent project."""

    app_json: Dict[str, Any]
    gecx_config: Dict[str, Any]
    agents: Dict[str, AgentBundle]
    tools: Dict[str, ToolBundle]


class PolymorphismEngine:
    """Compiles a base agent project plus adapter cards into per-channel
    output projects."""

    def __init__(self, app_dir: str):
        """Initialize the engine.

        Args:
            app_dir: Path to the root of the base agent project (the
                directory that directly contains ``app.json``, ``agents/``,
                ``tools/``, etc.).  The nested gecx-skills layout is not
                supported for poly base projects.
        """
        self.app_dir = Path(app_dir).resolve()
        self.base: Optional[BaseProject] = None
        # channel -> (card, card_path)
        self.adapters: Dict[str, Tuple[AdapterCard, Path]] = {}
        self.adapter_cards: List[Tuple[AdapterCard, Path]] = []
        # Per-file parse / schema errors collected by ``load_adapter_cards``
        # (issue dicts).  A malformed card is recorded here instead of raising,
        # so one bad card never blocks compiling the others.
        self.adapter_errors: List[Dict[str, Any]] = []

    # ── Loading ──────────────────────────────────────────────────────────

    def load_base_project(self) -> BaseProject:
        """Read the base project from disk into memory.

        Reads ``app.json``, every agent (config + instruction + callback
        code), and every tool (config + code).  Stores the result on
        ``self.base`` and returns it.
        """
        if not (self.app_dir / "app.json").exists():
            raise FileNotFoundError(
                f"No app.json found in {self.app_dir}. The poly engine "
                "requires a direct project layout."
            )

        app_json = self._read_json(self.app_dir / "app.json")
        gecx_config: Dict[str, Any] = {}
        gecx_path = self.app_dir / "gecx-config.json"
        if gecx_path.exists():
            gecx_config = self._read_json(gecx_path)

        agents: Dict[str, AgentBundle] = {}
        agents_dir = self.app_dir / "agents"
        if agents_dir.exists():
            for agent_dir in sorted(agents_dir.iterdir()):
                if not agent_dir.is_dir():
                    continue
                bundle = self._load_agent(agent_dir)
                if bundle is not None:
                    agents[bundle.dir_name] = bundle

        tools: Dict[str, ToolBundle] = {}
        tools_dir = self.app_dir / "tools"
        if tools_dir.exists():
            for tool_dir in sorted(tools_dir.iterdir()):
                if not tool_dir.is_dir():
                    continue
                bundle = self._load_tool(tool_dir)
                if bundle is not None:
                    tools[bundle.dir_name] = bundle

        self.base = BaseProject(
            app_json=app_json,
            gecx_config=gecx_config,
            agents=agents,
            tools=tools,
        )
        return self.base

    def _load_agent(self, agent_dir: Path) -> Optional[AgentBundle]:
        config_path = agent_dir / f"{agent_dir.name}.json"
        if not config_path.exists():
            return None
        config = self._read_json(config_path)
        display_name = config.get("displayName", agent_dir.name)

        instruction = ""
        inst_ref = config.get("instruction")
        if inst_ref:
            inst_path = self.app_dir / inst_ref
            if inst_path.exists():
                instruction = inst_path.read_text()

        callback_code: Dict[str, str] = {}
        for field_name in CALLBACK_TYPE_TO_FIELD.values():
            for entry in config.get(field_name, []) or []:
                rel = entry.get("pythonCode")
                if not rel:
                    continue
                code_path = self.app_dir / rel
                if code_path.exists():
                    callback_code[rel] = code_path.read_text()

        return AgentBundle(
            dir_name=agent_dir.name,
            display_name=display_name,
            config=config,
            instruction=instruction,
            callback_code=callback_code,
        )

    def _load_tool(self, tool_dir: Path) -> Optional[ToolBundle]:
        json_path = tool_dir / f"{tool_dir.name}.json"
        if not json_path.exists():
            candidates = list(tool_dir.glob("*.json"))
            if not candidates:
                return None
            json_path = candidates[0]
        config = self._read_json(json_path)

        code_rel_path = None
        code = None
        py_fn = config.get("pythonFunction") or {}
        ref = py_fn.get("pythonCode")
        if ref:
            code_path = self.app_dir / ref
            if code_path.exists():
                code_rel_path = ref
                code = code_path.read_text()

        return ToolBundle(
            dir_name=tool_dir.name,
            config=config,
            code_rel_path=code_rel_path,
            code=code,
        )

    def load_adapter_cards(self) -> List[AdapterCard]:
        """Glob and parse all adapter cards under ``adapters/``.

        Recognizes ``*.adapter.yaml``, ``*.adapter.yml`` and
        ``*.adapter.json``.  Populates ``self.adapters`` keyed by channel and
        returns the successfully parsed cards in filename order.  A card that
        fails to parse or validate is recorded in ``self.adapter_errors`` (as
        an ``AD001`` issue dict) and skipped — it never raises.
        """
        adapters_dir = self.app_dir / "adapters"
        cards: List[AdapterCard] = []
        self.adapters = {}
        self.adapter_cards = []
        self.adapter_errors = []
        if not adapters_dir.exists():
            return cards

        paths = sorted(
            list(adapters_dir.glob("*.adapter.yaml"))
            + list(adapters_dir.glob("*.adapter.yml"))
            + list(adapters_dir.glob("*.adapter.json"))
        )
        for path in paths:
            rel = path.name
            try:
                raw = path.read_text()
                data = (
                    json.loads(raw)
                    if path.suffix == ".json"
                    else yaml.safe_load(raw)
                )
            except (OSError, json.JSONDecodeError, yaml.YAMLError) as e:
                self._record_card_error(
                    rel, f"Adapter card is not valid {path.suffix}: {e}"
                )
                continue
            if not isinstance(data, dict):
                self._record_card_error(
                    rel, "Adapter card must be a mapping/object."
                )
                continue
            try:
                card = AdapterCard.model_validate(data)
            except ValidationError as e:
                self._record_card_error(
                    rel,
                    "Adapter card schema invalid: "
                    + _format_validation_error(e),
                )
                continue
            cards.append(card)
            self.adapter_cards.append((card, path))
            self.adapters[card.metadata.channel] = (card, path)
        return cards

    def _record_card_error(self, rel: str, message: str) -> None:
        self.adapter_errors.append(
            {
                "rule_id": "AD001",
                "severity": "error",
                "message": message,
                "path": f"adapters/{rel}",
            }
        )

    # ── Compilation ──────────────────────────────────────────────────────

    def compile(
        self,
        adapter: AdapterCard,
        card_path: Optional[Path] = None,
        validate: bool = True,
    ) -> CompiledAgentConfig:
        """Compile the base project against one adapter card.

        Validation (:func:`validate_adapter_card`) runs first and is the single
        source of truth: a card that validates clean always compiles.  The apply
        steps below therefore trust the validated card and do not re-implement
        existence/section checks.

        Args:
            adapter: The parsed adapter card.
            card_path: Path to the adapter card file (currently informational;
                all adapter paths resolve relative to the project root).
            validate: Run ``validate_adapter_card`` first and raise on errors.
                ``compile_all`` sets this False after running the full
                cross-adapter validation pass once.

        Returns:
            A fully resolved ``CompiledAgentConfig``.

        Raises:
            CompilationError: if validation finds any error-severity issue.
        """
        if self.base is None:
            self.load_base_project()
        assert self.base is not None

        channel = adapter.metadata.channel

        if validate:
            errors = [
                i
                for i in validate_adapter_card(adapter, str(self.app_dir))
                if i.get("severity") == "error"
            ]
            if errors:
                raise CompilationError(errors)

        def resolve_path(ref: str) -> Path:
            path, _inside = resolve_within(str(self.app_dir), ref)
            return path

        # Step 1: deep copy mutable base state.
        agent_configs: Dict[str, Dict[str, Any]] = {
            name: copy.deepcopy(b.config)
            for name, b in self.base.agents.items()
        }
        instructions: Dict[str, str] = {
            name: b.instruction for name, b in self.base.agents.items()
        }
        callback_code: Dict[str, str] = {}
        for b in self.base.agents.values():
            callback_code.update(copy.deepcopy(b.callback_code))

        display_to_dir = {
            b.display_name: name for name, b in self.base.agents.items()
        }

        def resolve_agent(ref: str) -> str:
            # Validated card: the agent always resolves.
            return ref if ref in agent_configs else display_to_dir[ref]

        # Step 2: instruction diffs.
        for diff in adapter.instruction_diffs:
            dir_name = resolve_agent(diff.agent)
            instructions[dir_name] = apply_instruction_diff(
                instructions[dir_name], diff
            )

        # Step 3: tool add / remove.
        for mod in adapter.tools:
            cfg = agent_configs[resolve_agent(mod.agent)]
            tool_list = list(cfg.get("tools", []))
            for t in mod.add:
                if t not in tool_list:
                    tool_list.append(t)
            tool_list = [t for t in tool_list if t not in set(mod.remove)]
            cfg["tools"] = tool_list

        # Step 4: channel-specific tool definitions.
        new_tools: Dict[str, Dict[str, Any]] = {}
        new_tool_code: Dict[str, str] = {}
        tool_source_dirs: Dict[str, str] = {}
        for td in adapter.tool_definitions:
            src = resolve_path(td.source_dir)
            if td.tool_type == "python":
                cfg, _rel, code = self._read_tool_dir(src, td.display_name)
                if cfg is not None:
                    new_tools[td.display_name] = cfg
                    if code is not None:
                        new_tool_code[td.display_name] = code
            else:
                # Non-python (e.g. openapi): copy the source directory verbatim
                # so any spec/aux files come along unchanged.
                cfg = self._read_tool_config(src, td.display_name)
                if cfg is not None:
                    new_tools[td.display_name] = cfg
                tool_source_dirs[td.display_name] = str(src)

        # Step 5: model overrides.
        for mo in adapter.model_overrides:
            cfg = agent_configs[resolve_agent(mo.agent)]
            cfg.setdefault("modelSettings", {})["model"] = mo.model

        # Step 6: channel-specific callbacks.
        for cb in adapter.callbacks:
            dir_name = resolve_agent(cb.agent)
            code_path = resolve_path(cb.python_code)
            cfg = agent_configs[dir_name]
            field_name = CALLBACK_TYPE_TO_FIELD[cb.type]
            dir_kind = CALLBACK_TYPE_TO_DIR[cb.type]
            idx = self._next_callback_index(cfg.get(field_name, []))
            sub = f"{dir_kind}_{idx:02d}"
            rel = f"agents/{dir_name}/{dir_kind}/{sub}/python_code.py"
            cfg.setdefault(field_name, []).append(
                {"pythonCode": rel, "description": cb.description}
            )
            callback_code[rel] = code_path.read_text()

        # Step 7: merge channel evaluations / expectations / datasets.
        evaluations: Dict[str, Dict[str, Any]] = {}
        for ev in adapter.evaluations:
            evaluations.update(self._read_eval_dir(resolve_path(ev.source_dir)))
        expectations: Dict[str, Dict[str, Any]] = {}
        for ev in adapter.evaluation_expectations:
            expectations.update(
                self._read_eval_dir(resolve_path(ev.source_dir))
            )
        datasets: Dict[str, Dict[str, Any]] = {}
        for ev in adapter.evaluation_datasets:
            datasets.update(self._read_eval_dir(resolve_path(ev.source_dir)))

        # Step 8: deployment + gecx config.
        gecx_config = copy.deepcopy(self.base.gecx_config)
        self._deep_merge(gecx_config, adapter.gecx_config)
        gecx_config["default_channel"] = channel
        # The compiled output is always a direct-layout project rooted at
        # the channel directory, so the linter's app_dir must be ".".
        gecx_config["app_dir"] = "."
        deployment: Optional[Dict[str, Any]] = None
        if adapter.deployment is not None:
            deployment = self._build_deployment(
                adapter.deployment, adapter.metadata.display_name, channel
            )
            # Fold the per-channel deployment block into gecx-config.json — the
            # file deploy/lint tooling reads — rather than an orphan file.
            gecx_config["deployment"] = deployment
            modality = adapter.deployment.modality or (
                adapter.deployment.web_widget_config.modality
                if adapter.deployment.web_widget_config
                else None
            )
            if modality:
                gecx_config["modality"] = (
                    "audio" if "VOICE" in modality.upper() else "text"
                )

        return CompiledAgentConfig(
            channel=channel,
            app_config=copy.deepcopy(self.base.app_json),
            gecx_config=gecx_config,
            agents=agent_configs,
            agent_instructions=instructions,
            tools=new_tools,
            tool_code=new_tool_code,
            tool_source_dirs=tool_source_dirs,
            evaluations=evaluations,
            evaluation_expectations=expectations,
            evaluation_datasets=datasets,
            deployment=deployment,
            callback_code=callback_code,
        )

    def compile_all(self) -> Dict[str, CompiledAgentConfig]:
        """Validate and compile every adapter card.

        Returns:
            A dict mapping channel name to its ``CompiledAgentConfig``.

        Raises:
            CompilationError: if validation produces any ERROR-severity
                issues.
        """
        if self.base is None:
            self.load_base_project()
        self.load_adapter_cards()

        adapters = [c for c, _ in self.adapter_cards]
        issues = list(self.adapter_errors)
        issues += validate_all_adapters(adapters, str(self.app_dir))
        errors = [i for i in issues if i.get("severity") == "error"]
        if errors:
            raise CompilationError(errors)

        result: Dict[str, CompiledAgentConfig] = {}
        for card, path in self.adapter_cards:
            result[card.metadata.channel] = self.compile(
                card, path, validate=False
            )
        return result

    # ── Output ───────────────────────────────────────────────────────────

    def write_output(
        self,
        compiled: CompiledAgentConfig,
        output_dir: str,
        force: bool = False,
    ) -> Path:
        """Write a compiled config as a complete agent project directory.

        Untouched base items (tools/, evaluations/, evaluationExpectations/,
        evaluationDatasets/, cxaslint.yaml, etc.) are copied verbatim;
        agents, app.json and gecx-config.json are reconstructed from the
        compiled state; channel-specific tools/evaluations/runtime config are
        added.

        Safety: the target is replaced only when it is empty, was produced by a
        previous ``cxas poly build`` (carries the ``.poly_build.json`` marker),
        or ``force`` is True.  It never overlaps the source project directory.

        Returns:
            The output directory path.

        Raises:
            ValueError: if ``output_dir`` overlaps the base project directory.
            FileExistsError: if the target exists, is non-empty, was not
                produced by poly, and ``force`` is False.
        """
        out = Path(output_dir).resolve()

        if (
            out == self.app_dir
            or _is_relative_to(out, self.app_dir)
            or _is_relative_to(self.app_dir, out)
        ):
            raise ValueError(
                f"Refusing to write output to '{out}': it overlaps the base "
                f"project '{self.app_dir}'. Choose an --output-dir outside the "
                "project."
            )

        if out.exists():
            is_empty = not any(out.iterdir())
            is_poly = (out / _POLY_MARKER).is_file()
            if not (force or is_empty or is_poly):
                raise FileExistsError(
                    f"Refusing to overwrite '{out}': it is not empty and was "
                    "not created by 'cxas poly build'. Re-run with "
                    "force/--force to overwrite it."
                )
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)

        # 1. Verbatim copy of untouched base items.
        for item in sorted(self.app_dir.iterdir()):
            if item.name in _RECONSTRUCTED_ITEMS or item.name.startswith("."):
                continue
            dest = out / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # 2. Reconstruct agents (configs + instructions + callbacks).
        for dir_name, cfg in compiled.agents.items():
            agent_out = out / "agents" / dir_name
            agent_out.mkdir(parents=True, exist_ok=True)
            self._write_json(agent_out / f"{dir_name}.json", cfg)
            inst = compiled.agent_instructions.get(dir_name)
            if inst is not None:
                inst_ref = cfg.get("instruction")
                inst_path = (
                    out / inst_ref
                    if inst_ref
                    else agent_out / "instruction.txt"
                )
                inst_path.parent.mkdir(parents=True, exist_ok=True)
                inst_path.write_text(inst)

        for rel, code in compiled.callback_code.items():
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(code)

        # 3. Channel-specific tool definitions (base tools already copied).
        for tool_name, cfg in compiled.tools.items():
            src_dir = compiled.tool_source_dirs.get(tool_name)
            tool_out = out / "tools" / tool_name
            if src_dir is not None:
                # Non-python tool: copy the whole source dir verbatim.
                shutil.copytree(Path(src_dir), tool_out, dirs_exist_ok=True)
                continue
            tool_out.mkdir(parents=True, exist_ok=True)
            self._write_json(tool_out / f"{tool_name}.json", cfg)
            code = compiled.tool_code.get(tool_name)
            if code is not None:
                ref = (cfg.get("pythonFunction") or {}).get("pythonCode")
                if not ref:
                    ref = f"tools/{tool_name}/python_function/python_code.py"
                code_path = out / ref
                code_path.parent.mkdir(parents=True, exist_ok=True)
                code_path.write_text(code)

        # 4. Channel-specific evals / expectations / datasets (base copied).
        for subdir, items in (
            ("evaluations", compiled.evaluations),
            ("evaluationExpectations", compiled.evaluation_expectations),
            ("evaluationDatasets", compiled.evaluation_datasets),
        ):
            for name, data in items.items():
                item_out = out / subdir / name
                item_out.mkdir(parents=True, exist_ok=True)
                self._write_json(item_out / f"{name}.json", data)

        # 5. Root config files.  Per-channel deployment settings live inside
        # gecx-config.json (compiled.gecx_config["deployment"]).
        self._write_json(out / "app.json", compiled.app_config)
        if compiled.gecx_config:
            self._write_json(out / "gecx-config.json", compiled.gecx_config)

        # 6. Build marker (dotfile, not copied into the next build's source).
        self._write_json(
            out / _POLY_MARKER,
            {
                "channel": compiled.channel,
                "source": str(self.app_dir),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        return out

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text())

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    @staticmethod
    def _deep_merge(target: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        """Recursively merge ``overlay`` into ``target`` in place."""
        for key, value in overlay.items():
            if (
                isinstance(value, dict)
                and isinstance(target.get(key), dict)
            ):
                PolymorphismEngine._deep_merge(target[key], value)
            else:
                target[key] = copy.deepcopy(value)

    @staticmethod
    def _next_callback_index(entries: List[Dict[str, Any]]) -> int:
        indices: List[int] = []
        for entry in entries or []:
            ref = entry.get("pythonCode", "")
            m = re.search(r"_(\d+)/python_code\.py$", ref)
            if m:
                indices.append(int(m.group(1)))
        if indices:
            return max(indices) + 1
        return len(entries or []) + 1

    def _read_tool_dir(
        self, src: Path, display_name: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Read a tool definition directory.

        Returns ``(config, code_rel_path, code)``.  The config's
        ``pythonFunction.pythonCode`` is normalized to the canonical output
        location ``tools/<name>/python_function/python_code.py``.
        """
        if not src.exists() or not src.is_dir():
            return None, None, None
        json_path = src / f"{display_name}.json"
        if not json_path.exists():
            candidates = list(src.glob("*.json"))
            if not candidates:
                return None, None, None
            json_path = candidates[0]
        config = self._read_json(json_path)

        canonical = f"tools/{display_name}/python_function/python_code.py"
        code = None
        # Prefer the path the JSON references; fall back to a bare
        # python_code.py in the source dir.
        py_fn = config.get("pythonFunction") or {}
        ref = py_fn.get("pythonCode")
        candidate_paths = []
        if ref:
            candidate_paths.append(src / Path(ref).name)
            candidate_paths.append(self.app_dir / ref)
        candidate_paths.append(src / "python_code.py")
        candidate_paths.append(src / "python_function" / "python_code.py")
        for cp in candidate_paths:
            if cp.exists():
                code = cp.read_text()
                break

        if "pythonFunction" in config:
            config["pythonFunction"]["pythonCode"] = canonical

        return config, canonical, code

    def _read_tool_config(
        self, src: Path, display_name: str
    ) -> Optional[Dict[str, Any]]:
        """Read a non-python tool's JSON config verbatim (no normalization)."""
        if not src.exists() or not src.is_dir():
            return None
        json_path = src / f"{display_name}.json"
        if not json_path.exists():
            candidates = list(src.glob("*.json"))
            if not candidates:
                return None
            json_path = candidates[0]
        return self._read_json(json_path)

    def _read_eval_dir(self, src: Path) -> Dict[str, Dict[str, Any]]:
        """Read all evaluation files under a source directory.

        Each immediate subdirectory is treated as one evaluation named
        ``<dir>`` containing ``<dir>.{yaml,yml,json}``.  Loose files at the
        top level are also accepted.
        """
        result: Dict[str, Dict[str, Any]] = {}
        if not src.exists() or not src.is_dir():
            return result
        for child in sorted(src.iterdir()):
            if child.is_dir():
                for cand in (
                    child / f"{child.name}.json",
                    child / f"{child.name}.yaml",
                    child / f"{child.name}.yml",
                ):
                    if cand.exists():
                        result[child.name] = self._load_data_file(cand)
                        break
                else:
                    files = (
                        list(child.glob("*.json"))
                        + list(child.glob("*.yaml"))
                        + list(child.glob("*.yml"))
                    )
                    if files:
                        result[child.name] = self._load_data_file(files[0])
            elif child.suffix in (".json", ".yaml", ".yml"):
                result[child.stem] = self._load_data_file(child)
        return result

    @staticmethod
    def _load_data_file(path: Path) -> Dict[str, Any]:
        raw = path.read_text()
        if path.suffix == ".json":
            return json.loads(raw)
        return yaml.safe_load(raw)

    @staticmethod
    def _build_deployment(
        override: DeploymentOverride, display_name: str, channel: str
    ) -> Dict[str, Any]:
        """Build the gecx-config ``deployment`` block.

        Keys use snake_case to match both ``gecx-config.json`` convention and
        the kwargs of ``cxas_scrapi.core.deployments.Deployments`` so a deploy
        step can consume it directly.
        """
        out: Dict[str, Any] = {
            "deployment_id": channel,
            "display_name": display_name,
        }
        if override.channel_type is not None:
            out["channel_type"] = override.channel_type
        if override.modality is not None:
            out["modality"] = override.modality
        if override.disable_dtmf is not None:
            out["disable_dtmf"] = override.disable_dtmf
        if override.disable_barge_in_control is not None:
            out["disable_barge_in_control"] = override.disable_barge_in_control
        wwc = override.web_widget_config
        if wwc is not None:
            if wwc.theme is not None:
                out["theme"] = wwc.theme
            if wwc.web_widget_title is not None:
                out["web_widget_title"] = wwc.web_widget_title
            if wwc.modality is not None and "modality" not in out:
                out["modality"] = wwc.modality
        return out
