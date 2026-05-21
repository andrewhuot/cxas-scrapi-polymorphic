# CX Agent Studio Scripting API (CXAS SCRAPI)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE.txt)
[![PyPI](https://img.shields.io/pypi/v/cxas-scrapi)](https://pypi.org/project/cxas-scrapi/)
[![Python Unit Tests](https://github.com/GoogleCloudPlatform/cxas-scrapi/actions/workflows/ci.yml/badge.svg)](https://github.com/GoogleCloudPlatform/cxas-scrapi/actions/workflows/ci.yml)

<html>
    <h2 align="center">
      <img src="assets/cxas-scrapi-logo.png" width="256" alt="CXAS SCRAPI Logo"/>
    </h2>
    <h3 align="center">
      Author one agent at the center. Compile channel-optimized variants at the edges.
    </h3>
    <h3 align="center">
      Important Links:
      <a href="https://googlecloudplatform.github.io/cxas-scrapi/stable/">Docs</a>,
      <a href="examples/">Examples</a>,
      <a href="docs/guides/polymorphism.md">Polymorphism Guide</a>,
      <a href="docs/cli/poly.md"><code>cxas poly</code> CLI</a>
    </h3>
</html>

CXAS SCRAPI is a Python API, CLI, and set of Agent Skills for CX Agent Studio.
This README focuses on its **architecture** and on the feature this repository is
built around: **polymorphism** — authoring an agent project once and compiling a
complete, channel-optimized project (chat, voice, …) for each target.

> New to the project's auth, install, and core SDK? See the
> [official docs](https://googlecloudplatform.github.io/cxas-scrapi/stable/).
> This document assumes you just want to understand how the pieces fit together
> and how to use polymorphism.

---

## Table of contents

1. [The core idea](#the-core-idea)
2. [Architecture at a glance](#architecture-at-a-glance)
3. [Inside the polymorphism engine](#inside-the-polymorphism-engine)
4. [Using polymorphism, step by step](#using-polymorphism-step-by-step)
5. [Adapter card reference](#adapter-card-reference)
6. [The compilation pipeline](#the-compilation-pipeline)
7. [Driving the engine from Python](#driving-the-engine-from-python)
8. [Validation rules](#validation-rules)
9. [When to use adapters vs. separate agents](#when-to-use-adapters-vs-separate-agents)
10. [Where to go next](#where-to-go-next)

---

## The core idea

A reservation agent that works beautifully in a web chat widget rarely works
well on a phone call. Chat wants Markdown, numbered lists, and rich confirmation
cards. Voice wants two-sentence turns, spelled-out numbers, and filler phrases so
the line is never silent. The behavior is *mostly* the same — same tools, same
flow, same business rules — but the surface differs.

The naive answer is to **fork**: maintain `bella_notte_chat/` and
`bella_notte_voice/` as two full projects. They immediately drift. A bug fixed in
one isn't fixed in the other; a tool added to one is forgotten in the other.

**Polymorphism** is the alternative:

> **Author the agent once at the center, describe the per-channel _deltas_
> declaratively, and _compile_ a complete, channel-optimized project for each
> target.**

The polymorphism happens entirely at **build time**. There is no special
"polymorphic runtime" — what you deploy is an ordinary SCRAPI project.

```
              base project                      cxas poly build           one project per channel
  ┌───────────────────────────────┐                                  ┌──────────────────────────┐
  │ app.json · agents/ · tools/    │                                  │ output/chat/   (Markdown, │
  │ evaluations/ (channel-neutral) │  ──────────────────────────►    │   rich cards, WEB_UI)     │
  │                                │        compile + validate        ├──────────────────────────┤
  │ adapters/                      │                                  │ output/voice/  (terse,    │
  │   chat.adapter.yaml   (deltas) │                                  │   spoken, TELEPHONY)      │
  │   voice.adapter.yaml  (deltas) │                                  └──────────────────────────┘
  └───────────────────────────────┘
```

### The three primitives

| Primitive | What it is | Where it lives |
|---|---|---|
| **Canonical Agent Card** | Your ordinary, channel-neutral agent project — `app.json`, `agents/`, `tools/`, `evaluations/`. Nothing new to learn. | The project root |
| **Channel Adapter Card** | A small YAML/JSON file describing what changes for one channel: instruction edits, tool add/remove, model overrides, extra callbacks, channel evals, and deployment settings. | `adapters/<channel>.adapter.yaml` |
| **Polymorphism Engine** | The compiler. Reads the base project + adapter cards and writes one complete project directory per channel. | `cxas poly` / `cxas_scrapi.poly` |

---

## Architecture at a glance

The library is organized by responsibility. Each top-level package under
`src/cxas_scrapi/` owns one concern:

| Package | Responsibility |
|---|---|
| [`core/`](src/cxas_scrapi/core) | High-level building blocks mapped to CXAS resource types — `Apps`, `Agents`, `Tools`, `Guardrails`, `Deployments`, `Sessions`, etc. The main public SDK surface. |
| [`poly/`](src/cxas_scrapi/poly) | **The polymorphism engine** — adapter-card models, validators, and the compiler. Pure local file I/O; intentionally **GCP-free** (no `google.cloud.*` imports, no network). |
| [`cli/`](src/cxas_scrapi/cli) | The `cxas` command line. `cli/poly_cli.py` wires up `cxas poly build / validate / diff`. |
| [`evals/`](src/cxas_scrapi/evals) | Executing and analyzing agent evaluations — goldens, simulations, latency. |
| [`utils/`](src/cxas_scrapi/utils) | Pagination, proto/response flattening, linting, Sheets/GCS integrations. |
| [`migration/`](src/cxas_scrapi/migration) | Tools for migrating legacy Dialogflow CX agents into CXAS. |

The dependency arrow points one way: **`poly/` depends on nothing in the rest of
the SDK** (and pulls in no GCP libraries), so the compiler runs anywhere — CI, a
laptop, a sandbox — without credentials. The CLI and the rest of the SDK depend
on `poly/`, never the reverse.

```
cli/poly_cli.py ──► poly/engine.py ──► poly/models.py
                          │                  ▲
                          └──► poly/validators.py
                          (no google.cloud.*, no network)
```

---

## Inside the polymorphism engine

The `poly/` package is three small files. Reading them top to bottom is the
fastest way to understand the whole feature:

### `poly/models.py` — the schema

Pydantic models that define the **shape of an adapter card**. The top-level
[`AdapterCard`](src/cxas_scrapi/poly/models.py) holds:

- `metadata` ([`AdapterMetadata`](src/cxas_scrapi/poly/models.py)) — `channel`,
  `displayName`, `description`.
- `instruction_diffs` (`List[InstructionDiff]`) — edits to instruction text.
- `tools` (`List[ToolModification]`) — add/remove tools on an agent.
- `tool_definitions` (`List[ToolDefinition]`) — bring channel-only tools in.
- `model_overrides` (`List[ModelOverride]`) — per-agent model swap.
- `callbacks` (`List[CallbackDefinition]`) — channel-specific callbacks.
- `evaluations` (`List[EvalReference]`) — extra eval directories to merge.
- `deployment` (`Optional[DeploymentOverride]`) — channel/modality/widget config.

Every model uses `populate_by_name=True`, so cards can be written in friendly
**camelCase** (`displayName`, `sectionTag`, `pythonCode`) while the Python code
reads them as snake_case. The result of a compile is a
[`CompiledAgentConfig`](src/cxas_scrapi/poly/models.py): a pure-data snapshot of
everything the engine will write to disk, so callers can introspect or transform
it before anything touches the filesystem.

### `poly/validators.py` — the safety net

Pure, local checks (`AD001`–`AD007`) that run **before** compilation. Each
returns a list of issue dicts shaped exactly like the linter's results
(`{rule_id, severity, message, path}`), and the same checks back the `adapters`
category of `cxas lint`. See [Validation rules](#validation-rules).

### `poly/engine.py` — the compiler

[`PolymorphismEngine`](src/cxas_scrapi/poly/engine.py) does the work in three
phases:

1. **Load** — `load_base_project()` reads `app.json`, every agent (config +
   instruction + callback code), and every tool into memory as
   `BaseProject`. `load_adapter_cards()` globs `adapters/*.adapter.{yaml,yml,json}`.
2. **Compile** — `compile(card)` deep-copies the base and applies the card's
   deltas in a fixed order (see [pipeline](#the-compilation-pipeline)), returning
   a `CompiledAgentConfig`. `compile_all()` validates and compiles every card.
3. **Write** — `write_output(compiled, dir)` materializes one complete project
   directory: untouched base files are copied verbatim; agents, `app.json`, and
   `gecx-config.json` are reconstructed; channel-only tools/evals/deployment are
   added.

---

## Using polymorphism, step by step

The repository ships a complete, runnable example — the **Bella Notte**
restaurant agent — under [`examples/bella_notte/`](examples/bella_notte). All
commands below operate on it.

### 1. Start from an ordinary project

The base project is a normal SCRAPI project — nothing about it is
polymorphism-specific. The only addition is an `adapters/` directory:

```
examples/bella_notte/
├── app.json
├── gecx-config.json
├── agents/
│   ├── Bella_Notte_Host/        # root agent: routes reservation vs. takeout
│   ├── Reservation_Agent/       # slot-filling specialist
│   └── Takeout_Agent/
├── tools/                       # set_active_flow, book_reservation, …
├── evaluations/                 # shared, channel-neutral goldens
└── adapters/                    # ← the per-channel deltas live here
    ├── chat.adapter.yaml
    └── voice.adapter.yaml
```

Write the base instructions to be **channel-neutral**: describe *what* the agent
does, not *how* it should look on a screen or sound on a call.

### 2. Write a channel adapter card

An adapter card is a short declaration of deltas. Here is the voice adapter,
annotated:

```yaml
apiVersion: poly.cxas.dev/v1
kind: ChannelAdapter
metadata:
  channel: voice                       # the channel name (becomes output/voice/)
  displayName: Bella Notte — Voice

# Layer voice behavior on top of the base instructions.
instructionDiffs:
  - agent: Bella_Notte_Host
    mode: append                       # append | prepend | replace_section
    content: |
      <channel_voice>
      You are speaking on a phone call. There is no screen.
      - Keep every response to two or three short sentences.
      - Spell out numbers and times ("six thirty in the evening").
      </channel_voice>

# Inject pacing hints right before the model call.
callbacks:
  - agent: Bella_Notte_Host
    type: before_model
    pythonCode: adapters/voice_callbacks/voice_pacing.py
    description: Inject voice pacing and filler-phrase hints.

# Fold channel-specific evaluations into the compiled evaluations/.
evaluations:
  - sourceDir: adapters/voice_evals

# Emit a deployment.json for telephony, voice-only.
deployment:
  channelType: GOOGLE_TELEPHONY_PLATFORM
  modality: VOICE_ONLY
```

The chat adapter pulls the *same* base in the opposite direction — Markdown,
numbered lists, and an extra `send_rich_card` tool. See
[`chat.adapter.yaml`](examples/bella_notte/adapters/chat.adapter.yaml) for the
full version, which also demonstrates `tools` + `toolDefinitions`.

### 3. Validate before you build

```bash
cxas poly validate --app-dir examples/bella_notte
```

```
All 2 adapter card(s) valid.
```

Validation checks that every referenced agent/tool/section actually exists, that
no two cards claim the same channel, and more — see
[Validation rules](#validation-rules).

### 4. Preview the changes with `diff`

`diff` shows exactly what an adapter will change, **without writing anything**:

```bash
cxas poly diff chat --app-dir examples/bella_notte
```

```
Channel: chat   (adapter: adapters/chat.adapter.yaml)

agents/Bella_Notte_Host
  instruction: + N line(s) append
  tools (2 -> 3):
    + send_rich_card
  callbacks: + before_model (Inject rich card formatting hints…)

tools/
  + send_rich_card

evaluations/
  + 1 eval(s): Rich_Card_Confirmation

deployment.json
  + channelType: WEB_UI
  + modality: CHAT_ONLY
```

### 5. Build the channels

```bash
cxas poly build --app-dir examples/bella_notte --output-dir ./output
```

```
Compiled channel 'chat'  -> ./output/chat
Compiled channel 'voice' -> ./output/voice

Done. 2 channel(s) written to ./output
```

### 6. Lint, evaluate, and deploy — the output is "just a project"

The single most important property of the engine: **the compiled output is
indistinguishable from a hand-authored project.** Every existing command works on
it with zero changes:

```bash
cxas lint --app-dir ./output/chat     # ✓ passes
cxas lint --app-dir ./output/voice    # ✓ passes
# run evals, deploy, etc. on ./output/<channel> exactly as usual
```

There is no half-compiled state and no special runtime to install. That is the
payoff of *author once at the center*: you maintain a single agent, and the
channel-specific surfaces fall out of two short adapter files.

---

## Adapter card reference

An adapter card declares deltas in seven optional sections. Each is applied to
the deep-copied base during compilation.

| Section | Field | What it does |
|---|---|---|
| **Instruction diffs** | `instructionDiffs[]` | Edit an agent's instruction text. `mode: append` / `prepend` add text; `mode: replace_section` swaps the contents of an XML-style `<sectionTag>…</sectionTag>` block. |
| **Tool modifications** | `tools[]` | `add`/`remove` tool names on a named agent's `tools` list. |
| **Tool definitions** | `toolDefinitions[]` | Bring a channel-only tool into `tools/` from a `sourceDir` (its `<name>.json` + `python_code.py`). Required when a `tools.add` references a tool not in the base. |
| **Model overrides** | `modelOverrides[]` | Set `modelSettings.model` for an agent in this channel. |
| **Callbacks** | `callbacks[]` | Append a channel-specific callback (`before_model`, `after_model`, `before_tool`, `after_tool`, `before_agent`, `after_agent`). Auto-numbered after any existing ones. |
| **Evaluations** | `evaluations[]` | Merge a `sourceDir` of channel-specific evaluations into `evaluations/`. |
| **Deployment** | `deployment` | Emit a `deployment.json` (channel type, modality, web-widget config) and update `gecx-config.json`. |

Two conveniences worth knowing:

- **Agents may be referenced by display name or directory name** — the engine
  resolves either form.
- **`replace_section` is surgical.** It only replaces the matched `<tag>…</tag>`
  block, so the rest of the instruction stays byte-for-byte intact. If most of
  your sections need `replace_section`, that's a signal the channels may want to
  be [separate agents](#when-to-use-adapters-vs-separate-agents).

---

## The compilation pipeline

`PolymorphismEngine.compile()` applies an adapter in a fixed, deterministic
order. Understanding the order explains the output:

1. **Deep-copy the base.** Agent configs, instructions, and existing callback
   code are copied so the base is never mutated.
2. **Instruction diffs.** `append` / `prepend` / `replace_section` on each named
   agent.
3. **Tool add / remove.** Update each agent's `tools` list (adds are
   de-duplicated; removes are filtered out).
4. **Tool definitions.** Read each channel-only tool's directory; normalize its
   code path to the canonical `tools/<name>/python_function/python_code.py`.
5. **Model overrides.** Set `modelSettings.model` per agent.
6. **Callbacks.** Append channel callbacks, auto-numbering after existing ones
   (e.g. a second `before_model` callback becomes `before_model_callbacks_02`).
7. **Evaluations.** Merge each channel eval directory.
8. **Deployment + gecx config.** Build `deployment.json`; set `default_channel`,
   `app_dir`, and (for voice) `modality` in `gecx-config.json`.

Errors are **accumulated, not fail-fast**: a missing agent or section is recorded
as an issue and compilation continues, so a single run surfaces *every* problem
at once via a `CompilationError` carrying the full issue list.

---

## Driving the engine from Python

Everything the CLI does is available programmatically. The engine is GCP-free, so
this snippet runs anywhere:

```python
from cxas_scrapi.poly import PolymorphismEngine, CompilationError

engine = PolymorphismEngine("examples/bella_notte")
engine.load_base_project()
engine.load_adapter_cards()          # populates engine.adapters {channel: (card, path)}

try:
    # Compile and write every channel.
    compiled = engine.compile_all()  # {channel: CompiledAgentConfig}, validated first
    for channel, config in compiled.items():
        out_dir = engine.write_output(config, f"./output/{channel}")
        print(f"wrote {channel} -> {out_dir}")
except CompilationError as err:
    for issue in err.issues:
        print(issue["severity"], issue["rule_id"], issue["message"])
```

Because `compile()` returns a `CompiledAgentConfig` *before* anything is written,
you can inspect or post-process the compiled state — agents, instructions, merged
tools/evals, deployment — and only call `write_output()` when you're ready.

The public exports live in
[`cxas_scrapi.poly`](src/cxas_scrapi/poly/__init__.py): `PolymorphismEngine`,
`CompilationError`, `AdapterCard`, `CompiledAgentConfig`, and the individual
delta models.

---

## Validation rules

Run via `cxas poly validate` (or as the `adapters` category of `cxas lint`). The
`AD` prefix avoids collision with the `config` lint category, which owns
`A001`–`A006`.

| ID | Severity | Check |
|----|----------|-------|
| `AD001` | error | Adapter card has required fields (`apiVersion`, `kind`, `metadata.channel`) and valid types. |
| `AD002` | error | Every agent referenced in `instructionDiffs`, `tools`, `modelOverrides`, `callbacks` exists in `agents/`. |
| `AD003` | error | `replace_section` diffs set `sectionTag`, and that `<sectionTag>` exists in the target instruction. |
| `AD004` | warning | A tool `remove` references a tool not in the base agent's tool list. |
| `AD005` | error | A tool `add` references a tool defined neither in `tools/` nor in the adapter's `toolDefinitions`. |
| `AD006` | warning | The adapter declares no `evaluations` entries. |
| `AD007` | error | Two adapter cards target the same `metadata.channel`. |

`cxas poly build --channel all` runs this validation first and writes **nothing**
if any error-severity issue is found.

---

## When to use adapters vs. separate agents

Reach for **adapters** when:

- The channels share the same core flow, tools, and business logic.
- The differences are presentational or tuning — formatting, verbosity, pacing,
  a handful of channel-only tools.
- You want a single source of truth and one place to fix bugs.

Build **separate agents** when:

- The channels have genuinely different conversation graphs or tool sets with
  little overlap.
- The "delta" would be larger than the base — at that point an adapter hides more
  than it reveals.

A good rule of thumb: if you find yourself using `replace_section` on most
sections, the channels probably want to be separate agents.

---

## Where to go next

- **[Polymorphism guide](docs/guides/polymorphism.md)** — concepts and the
  compilation model in depth.
- **[Polymorphism pattern](docs/patterns/polymorphism.md)** — a full Bella Notte
  chat-vs-voice walkthrough.
- **[`cxas poly` CLI reference](docs/cli/poly.md)** — every flag for `build`,
  `validate`, and `diff`.
- **[Examples](examples/)** — the runnable Bella Notte project and its adapters.
- **[Official docs](https://googlecloudplatform.github.io/cxas-scrapi/stable/)**
  — install, authentication, and the full core SDK.

---

## Contributing

We welcome contributions and feature requests! Fork the project, create a feature
branch, commit your changes, and open a pull request. See
[CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

Distributed under the Apache 2.0 License. See [LICENSE.txt](LICENSE.txt).

## References

- [CX Agent Studio Documentation](https://docs.cloud.google.com/customer-engagement-ai/conversational-agents/ps)
- [CX Agent Studio Console](https://ces.cloud.google.com/)
</content>
</invoke>
