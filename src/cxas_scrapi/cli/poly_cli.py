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

"""Argparse handlers for ``cxas poly`` (build, validate, diff).

Drives the Polymorphism Engine from the command line: compile base agent
projects into channel-optimized variants, validate adapter cards, and show
a human-readable diff of what an adapter changes.  All error paths render
clean, rule-ID-formatted messages — never a Python traceback.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console

from cxas_scrapi.poly.engine import (
    CompilationError,
    PolymorphismEngine,
)
from cxas_scrapi.poly.models import AdapterCard
from cxas_scrapi.poly.validators import (
    validate_adapter_card,
    validate_all_adapters,
)

console = Console()


def _counts(issues: List[dict]) -> Tuple[int, int]:
    """Return ``(errors, warnings)`` for a list of issue dicts."""
    errors = sum(1 for i in issues if i.get("severity") == "error")
    warnings = sum(1 for i in issues if i.get("severity") == "warning")
    return errors, warnings


def _print_issues(issues: List[dict]) -> int:
    """Print issue dicts; return the number of errors."""
    errors = 0
    for issue in sorted(
        issues, key=lambda i: (i.get("severity", ""), i.get("rule_id", ""))
    ):
        sev = issue.get("severity", "error")
        rule_id = issue.get("rule_id", "?")
        path = issue.get("path", "")
        msg = issue.get("message", "")
        if sev == "error":
            errors += 1
            color = "red"
            label = "ERROR"
        elif sev == "warning":
            color = "yellow"
            label = "WARN "
        else:
            color = "cyan"
            label = "INFO "
        console.print(f"  [{color}]{label}[/{color}] [{rule_id}] {path}: {msg}")
    return errors


def _load_engine(app_dir: str) -> PolymorphismEngine:
    engine = PolymorphismEngine(app_dir)
    engine.load_base_project()
    engine.load_adapter_cards()
    return engine


def _all_issues(engine: PolymorphismEngine, app_dir: str) -> List[dict]:
    """Parse errors plus validation issues for every loaded adapter."""
    cards = [c for c, _ in engine.adapter_cards]
    return list(engine.adapter_errors) + validate_all_adapters(cards, app_dir)


# ── poly build ────────────────────────────────────────────────────────────


def poly_build(args: argparse.Namespace) -> None:
    """Handle ``cxas poly build``."""
    app_dir = str(Path(getattr(args, "app_dir", ".")).resolve())
    channel = getattr(args, "channel", "all")
    output_dir = Path(getattr(args, "output_dir", "./output"))
    force = getattr(args, "force", False)
    strict = getattr(args, "strict", False)

    try:
        engine = _load_engine(app_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not engine.adapters and not engine.adapter_errors:
        console.print(
            f"[yellow]No adapter cards found in {app_dir}/adapters.[/yellow]"
        )
        sys.exit(1)

    # Decide which channels to build and gather issues to gate on.
    if channel == "all":
        issues = _all_issues(engine, app_dir)
        targets = list(engine.adapter_cards)
    else:
        if channel not in engine.adapters:
            console.print(
                f"[red]Error:[/red] no adapter for channel '{channel}'. "
                f"Available: {', '.join(sorted(engine.adapters)) or '(none)'}"
            )
            if engine.adapter_errors:
                _print_issues(engine.adapter_errors)
            sys.exit(1)
        card, path = engine.adapters[channel]
        targets = [(card, path)]
        issues = validate_adapter_card(card, app_dir)
        issues.extend(
            i
            for i in _all_issues(engine, app_dir)
            if i.get("rule_id") == "AD007"
            and f"'{channel}'" in i.get("message", "")
        )

    errors, warnings = _counts(issues)
    if issues:
        _print_issues(issues)
    if errors or (strict and warnings):
        console.print("\n[red]Build aborted: validation errors.[/red]")
        sys.exit(1)

    try:
        for card, path in targets:
            ch = card.metadata.channel
            compiled = engine.compile(card, path, validate=False)
            out = engine.write_output(
                compiled, str(output_dir / ch), force=force
            )
            console.print(f"[green]Compiled[/green] channel '{ch}' -> {out}")
    except CompilationError as e:
        console.print("[red]Compilation failed:[/red]")
        _print_issues(e.issues)
        sys.exit(1)
    except (FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(
        f"\n[green]Done.[/green] {len(targets)} channel(s) written to "
        f"{output_dir.resolve()}"
    )
    sys.exit(0)


# ── poly validate ───────────────────────────────────────────────────────────


def poly_validate(args: argparse.Namespace) -> None:
    """Handle ``cxas poly validate``."""
    app_dir = str(Path(getattr(args, "app_dir", ".")).resolve())
    fmt = getattr(args, "format", "text")
    strict = getattr(args, "strict", False)

    try:
        engine = PolymorphismEngine(app_dir)
        engine.load_base_project()
        cards = engine.load_adapter_cards()
    except FileNotFoundError as e:
        if fmt == "json":
            print(json.dumps({"error": str(e), "issues": []}, indent=2))
        else:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    issues = list(engine.adapter_errors) + validate_all_adapters(cards, app_dir)
    errors, warnings = _counts(issues)

    if fmt == "json":
        print(
            json.dumps(
                {
                    "app_dir": app_dir,
                    "cards": len(cards),
                    "errors": errors,
                    "warnings": warnings,
                    "issues": issues,
                },
                indent=2,
            )
        )
        sys.exit(1 if (errors or (strict and warnings)) else 0)

    if not cards and not engine.adapter_errors:
        console.print(
            f"[yellow]No adapter cards found in {app_dir}/adapters.[/yellow]"
        )
        sys.exit(0)

    if not issues:
        console.print(f"[green]All {len(cards)} adapter card(s) valid.[/green]")
        sys.exit(0)

    console.print(f"Validated {len(cards)} adapter card(s) for {app_dir}:\n")
    _print_issues(issues)
    console.print(f"\n  {errors} error(s), {warnings} warning(s)")
    sys.exit(1 if (errors or (strict and warnings)) else 0)


# ── poly diff ────────────────────────────────────────────────────────────────


def _find_card(
    engine: PolymorphismEngine, channel: str
) -> Optional[AdapterCard]:
    entry = engine.adapters.get(channel)
    return entry[0] if entry else None


def poly_diff(args: argparse.Namespace) -> None:
    """Handle ``cxas poly diff <channel>``."""
    app_dir = str(Path(getattr(args, "app_dir", ".")).resolve())
    channel = args.channel

    try:
        engine = _load_engine(app_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    entry = engine.adapters.get(channel)
    if entry is None:
        console.print(
            f"[red]Error:[/red] no adapter for channel '{channel}'. "
            f"Available: {', '.join(sorted(engine.adapters)) or '(none)'}"
        )
        if engine.adapter_errors:
            _print_issues(engine.adapter_errors)
        sys.exit(1)
    card, card_path = entry
    duplicate_issues = [
        i
        for i in _all_issues(engine, app_dir)
        if i.get("rule_id") == "AD007"
        and f"'{channel}'" in i.get("message", "")
    ]
    if duplicate_issues:
        console.print("[red]Error:[/red] duplicate adapter channel:")
        _print_issues(duplicate_issues)
        sys.exit(1)

    try:
        compiled = engine.compile(card, card_path)
    except CompilationError as e:
        console.print("[red]Compilation failed:[/red]")
        _print_issues(e.issues)
        sys.exit(1)

    rel_card = (
        Path(card_path).relative_to(Path(app_dir))
        if Path(card_path).is_relative_to(Path(app_dir))
        else card_path
    )
    console.print(f"[bold]Channel: {channel}[/bold]   (adapter: {rel_card})\n")

    base = engine.base
    assert base is not None

    # Build a per-agent view of changes.
    display_to_dir = {b.display_name: name for name, b in base.agents.items()}

    def to_dir(ref: str) -> Optional[str]:
        if ref in base.agents:
            return ref
        return display_to_dir.get(ref)

    touched_agents = set()
    for d in card.instruction_diffs:
        touched_agents.add(to_dir(d.agent))
    for t in card.tools:
        touched_agents.add(to_dir(t.agent))
    for m in card.model_overrides:
        touched_agents.add(to_dir(m.agent))
    for c in card.callbacks:
        touched_agents.add(to_dir(c.agent))
    touched_agents.discard(None)

    for dir_name in sorted(touched_agents):
        console.print(f"[bold cyan]agents/{dir_name}[/bold cyan]")
        base_bundle = base.agents[dir_name]

        # Instruction diffs.
        for d in card.instruction_diffs:
            if to_dir(d.agent) != dir_name:
                continue
            if d.mode == "replace_section":
                console.print(
                    f"  instruction: ~ replace_section <{d.section_tag}>"
                )
            else:
                lines = d.content.strip().splitlines()
                console.print(f"  instruction: + {len(lines)} line(s) {d.mode}")
                for line in lines[:3]:
                    console.print(f"    [green]+ {line}[/green]")
                if len(lines) > 3:
                    console.print("    [green]+ ...[/green]")

        # Tool changes.
        base_tools = list(base_bundle.config.get("tools", []))
        comp_tools = list(compiled.agents[dir_name].get("tools", []))
        added = [t for t in comp_tools if t not in base_tools]
        removed = [t for t in base_tools if t not in comp_tools]
        if added or removed:
            console.print(f"  tools ({len(base_tools)} -> {len(comp_tools)}):")
            for t in added:
                console.print(f"    [green]+ {t}[/green]")
            for t in removed:
                console.print(f"    [red]- {t}[/red]")

        # Model override.
        base_model = (base_bundle.config.get("modelSettings") or {}).get(
            "model"
        )
        comp_model = (compiled.agents[dir_name].get("modelSettings") or {}).get(
            "model"
        )
        if base_model != comp_model:
            console.print(
                f"  modelSettings.model: {base_model or '(default)'} -> "
                f"[green]{comp_model}[/green]"
            )

        # Added callbacks.
        for c in card.callbacks:
            if to_dir(c.agent) != dir_name:
                continue
            console.print(
                f"  callbacks: [green]+ {c.type}[/green] "
                f"({c.description or c.python_code})"
            )

    # New tools.
    if compiled.tools:
        console.print("\n[bold cyan]tools/[/bold cyan]")
        for name in sorted(compiled.tools):
            console.print(f"  [green]+ {name}[/green]")

    # Evaluations / expectations / datasets.
    for label, items in (
        ("evaluations", compiled.evaluations),
        ("evaluationExpectations", compiled.evaluation_expectations),
        ("evaluationDatasets", compiled.evaluation_datasets),
    ):
        if items:
            console.print(f"\n[bold cyan]{label}/[/bold cyan]")
            console.print(
                f"  [green]+ {len(items)} item(s):[/green] "
                f"{', '.join(sorted(items))}"
            )

    # Deployment (folded into gecx-config.json).
    if card.gecx_config:
        console.print("\n[bold cyan]gecx-config.json (channel config)[/bold cyan]")
        for k, v in sorted(card.gecx_config.items()):
            console.print(f"  [green]~ {k}: {v}[/green]")

    if compiled.deployment:
        console.print("\n[bold cyan]gecx-config.json (deployment)[/bold cyan]")
        for k, v in compiled.deployment.items():
            console.print(f"  [green]+ {k}: {v}[/green]")

    sys.exit(0)


# ── Registration ────────────────────────────────────────────────────────────


def register(subparsers: argparse._SubParsersAction) -> None:
    """Add the ``poly`` subcommand tree to the top-level CLI."""
    parser_poly = subparsers.add_parser(
        "poly",
        help=(
            "Polymorphism engine: compile a base agent project into "
            "channel-optimized variants."
        ),
    )
    poly_subparsers = parser_poly.add_subparsers(
        title="poly commands", dest="poly_command", required=True
    )

    # build
    p_build = poly_subparsers.add_parser(
        "build", help="Compile channel-optimized agent projects."
    )
    p_build.add_argument(
        "--app-dir",
        default=".",
        help="Path to the agent project root (default: current directory).",
    )
    p_build.add_argument(
        "--channel",
        default="all",
        help="Specific channel to compile, or 'all' (default: all).",
    )
    p_build.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory (default: ./output).",
    )
    p_build.add_argument(
        "--force",
        action="store_true",
        help="Overwrite a non-empty output directory not created by poly.",
    )
    p_build.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (abort the build).",
    )
    p_build.set_defaults(func=poly_build)

    # validate
    p_validate = poly_subparsers.add_parser(
        "validate", help="Validate adapter cards against the project."
    )
    p_validate.add_argument(
        "--app-dir",
        default=".",
        help="Path to the agent project root (default: current directory).",
    )
    p_validate.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    p_validate.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any warnings are present.",
    )
    p_validate.set_defaults(func=poly_validate)

    # diff
    p_diff = poly_subparsers.add_parser(
        "diff", help="Show what an adapter changes for a channel."
    )
    p_diff.add_argument("channel", help="The channel to diff.")
    p_diff.add_argument(
        "--app-dir",
        default=".",
        help="Path to the agent project root (default: current directory).",
    )
    p_diff.set_defaults(func=poly_diff)
