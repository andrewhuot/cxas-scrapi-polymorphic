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
a human-readable diff of what an adapter changes.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from cxas_scrapi.poly.engine import (
    CompilationError,
    PolymorphismEngine,
)
from cxas_scrapi.poly.models import AdapterCard
from cxas_scrapi.poly.validators import validate_all_adapters

console = Console()


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


# ── poly build ────────────────────────────────────────────────────────────


def poly_build(args: argparse.Namespace) -> None:
    """Handle ``cxas poly build``."""
    app_dir = str(Path(getattr(args, "app_dir", ".")).resolve())
    channel = getattr(args, "channel", "all")
    output_dir = Path(getattr(args, "output_dir", "./output"))

    try:
        engine = _load_engine(app_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not engine.adapters:
        console.print(
            f"[yellow]No adapter cards found in {app_dir}/adapters.[/yellow]"
        )
        sys.exit(1)

    try:
        if channel == "all":
            compiled = engine.compile_all()
        else:
            if channel not in engine.adapters:
                console.print(
                    f"[red]Error:[/red] no adapter for channel '{channel}'. "
                    f"Available: {', '.join(sorted(engine.adapters))}"
                )
                sys.exit(1)
            card, path = engine.adapters[channel]
            # Run validation for the single channel too.
            issues = validate_all_adapters([card], app_dir)
            if _print_issues(issues):
                console.print("\n[red]Build aborted: validation errors.[/red]")
                sys.exit(1)
            compiled = {channel: engine.compile(card, path)}
    except CompilationError as e:
        console.print("[red]Compilation failed:[/red]")
        _print_issues(e.issues)
        sys.exit(1)

    for ch, cfg in compiled.items():
        out = engine.write_output(cfg, str(output_dir / ch))
        console.print(f"[green]Compiled[/green] channel '{ch}' -> {out}")

    console.print(
        f"\n[green]Done.[/green] {len(compiled)} channel(s) written to "
        f"{output_dir.resolve()}"
    )
    sys.exit(0)


# ── poly validate ───────────────────────────────────────────────────────────


def poly_validate(args: argparse.Namespace) -> None:
    """Handle ``cxas poly validate``."""
    app_dir = str(Path(getattr(args, "app_dir", ".")).resolve())

    try:
        engine = PolymorphismEngine(app_dir)
        engine.load_base_project()
        cards = engine.load_adapter_cards()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - surface parse errors clearly
        console.print(f"[red]Failed to parse adapter cards:[/red] {e}")
        sys.exit(1)

    if not cards:
        console.print(
            f"[yellow]No adapter cards found in {app_dir}/adapters.[/yellow]"
        )
        sys.exit(0)

    issues = validate_all_adapters(cards, app_dir)
    if not issues:
        console.print(f"[green]All {len(cards)} adapter card(s) valid.[/green]")
        sys.exit(0)

    console.print(f"Validated {len(cards)} adapter card(s) for {app_dir}:\n")
    errors = _print_issues(issues)
    warnings = len(issues) - errors
    console.print(f"\n  {errors} error(s), {warnings} warning(s)")
    sys.exit(1 if errors else 0)


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
        sys.exit(1)
    card, card_path = entry

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

    # Evaluations.
    if compiled.evaluations:
        console.print("\n[bold cyan]evaluations/[/bold cyan]")
        console.print(
            f"  [green]+ {len(compiled.evaluations)} eval(s):[/green] "
            f"{', '.join(sorted(compiled.evaluations))}"
        )

    # Deployment.
    if compiled.deployment:
        console.print("\n[bold cyan]deployment.json[/bold cyan]")
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
