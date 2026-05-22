---
name: cxas-polymorphic-adapters
description: Use when authoring, reviewing, validating, building, diffing, or debugging CXAS SCRAPI polymorphic channel adapters, adapter cards, channel-specific variants, or chat/voice/API/web/telephony adaptation work.
---

# CXAS Polymorphic Adapters

Use this skill to help users keep one channel-neutral SCRAPI agent project at
the center and compile channel-specific projects at the edges with `cxas poly`.

## Contract

- Polymorphism in this repo is build-time only. There is no polymorphic runtime.
- The output of `cxas poly build` is an ordinary SCRAPI project that should
  lint, eval, and deploy like a hand-authored project.
- The adapter card schema is whatever `src/cxas_scrapi/poly/models.py`
  supports today. Do not invent fields, channels, tool types, or deployment
  values.
- Adapter validation is the source of truth for buildability:
  `src/cxas_scrapi/poly/validators.py` backs `cxas poly validate`, `cxas lint`,
  and `PolymorphismEngine.compile()`.

## When To Use This Skill

Use this skill when the user mentions:

- Polymorphism, polymorphic agents, channel adapters, or adapter cards
- `cxas poly`, `cxas poly build`, `cxas poly validate`, or `cxas poly diff`
- Making one base agent work across chat, voice, API, or telephony channels
- Writing or editing `adapters/*.adapter.yaml` files
- `AD001`-`AD011` validation errors
- Comparing or inspecting compiled channel output

Do not use this skill for:

- Building a new agent from scratch from a PRD — use `cxas-agent-foundry`
- Running or debugging the broader eval lifecycle after compilation — use
  `cxas-agent-foundry` on the compiled project
- Converting eval formats — use `cxas-sim-eval`

## Load First

For any real adapter task, skim these before editing:

- `README.md`
- `docs/guides/polymorphism.md`
- `examples/polymorphic_pizza/README.md`
- The target project's `app.json`, `agents/`, `tools/`, `evaluations/`,
  `gecx-config.json`, and `adapters/`
- Existing adapter examples under `examples/*/adapters/*.adapter.yaml`

For schema or behavior questions, read the code instead of guessing:

- `src/cxas_scrapi/poly/models.py`
- `src/cxas_scrapi/poly/validators.py`
- `src/cxas_scrapi/poly/engine.py`
- `src/cxas_scrapi/cli/poly_cli.py`

## Task Router

- **Decide adapter vs separate agents**: use the decision framework below.
- **Write or revise an adapter card**: read
  `references/adapter-authoring.md`.
- **Validate, diff, or build channels**: read
  `references/build-and-validate.md`.
- **Debug a validation or compilation problem**: read
  `references/debug-adapter.md`.
- **Need general agent build/eval/debug lifecycle after compilation**: also use
  `.agents/skills/cxas-agent-foundry/SKILL.md` on the compiled project.

## Adapters vs Separate Agents

Use adapters when most of the work is shared:

- Same root business flow, same source of truth, and mostly the same tools
- Differences are channel presentation or tuning: response format, pacing,
  rich cards, callbacks, model selection, extra evals, or deployment settings
- The base can stay channel-neutral without hiding important channel behavior

Prefer separate agents when the channels are really different products:

- Conversation graphs, tools, state machines, or compliance requirements differ
  more than they overlap
- The adapter would replace most sections or remove or rebuild most tools
- A future maintainer would need to read the compiled output to understand the
  actual product

Rule of thumb: if the adapter delta is larger than the base, or
`replace_section` becomes the main authoring tool, stop and recommend separate
agents or a smaller shared base.

## The Three Primitives

| Primitive | What it is | Where it lives |
|---|---|---|
| Base project | An ordinary SCRAPI project: `app.json`, `agents/`, `tools/`, `evaluations/`. Channel-neutral. | Project root |
| Adapter card | A YAML or JSON file declaring per-channel deltas: instruction edits, tool add/remove, model overrides, callbacks, evals, deployment. | `adapters/<channel>.adapter.yaml` |
| Poly engine | The compiler. Deep-copies the base, applies adapter deltas, writes one complete project per channel. | `cxas poly` CLI / `cxas_scrapi.poly` Python API |

## Adapter Card Quick Reference

Required header:

```yaml
apiVersion: poly.cxas.dev/v1
kind: ChannelAdapter
metadata:
  channel: <string>
  displayName: <string>
  description: <optional string>
```

Optional delta sections, applied in this fixed order during compilation:

| Section | Field | What it does |
|---|---|---|
| Instruction diffs | `instructionDiffs[]` | `mode: append` / `prepend` / `replace_section` on a named agent's instruction text |
| Tool modifications | `tools[]` | `add` / `remove` tool names on a named agent's `tools` list |
| Tool definitions | `toolDefinitions[]` | Bring a channel-only tool into `tools/` from a `sourceDir` |
| Model overrides | `modelOverrides[]` | Set `modelSettings.model` for an agent |
| Callbacks | `callbacks[]` | Append channel callbacks like `before_model` or `after_tool` |
| Evaluations | `evaluations[]` | Merge channel eval directories into compiled `evaluations/` |
| Expectations / datasets | `evaluationExpectations[]`, `evaluationDatasets[]` | Merge channel expectation and dataset dirs |
| Deployment | `deployment` | Fold channel/modality/widget config into compiled `gecx-config.json` |
| App identity | `appIdentity` | Override the compiled app's `displayName`/`name`. Optional — defaults to the adapter's `metadata.displayName` and a deterministic per-channel UUID so channels never collide as one deployed app |

Supported values to keep handy:

- `toolType`: `python`, `openapi`
- instruction diff `mode`: `append`, `prepend`, `replace_section`
- callback `type`: `before_model`, `after_model`, `before_tool`,
  `after_tool`, `before_agent`, `after_agent`
- `deployment.channelType`: `WEB_UI`, `API`, `TWILIO`,
  `GOOGLE_TELEPHONY_PLATFORM`, `CONTACT_CENTER_AS_A_SERVICE`, `FIVE9`,
  `CONTACT_CENTER_INTEGRATION`
- `deployment.modality` and `webWidgetConfig.modality`: `CHAT_AND_VOICE`,
  `VOICE_ONLY`, `CHAT_ONLY`, `CHAT_VOICE_AND_VIDEO`
- `webWidgetConfig.theme`: `LIGHT`, `DARK`

Key conventions:

- Agents can be referenced by display name or directory name.
- `replace_section` requires `sectionTag` and a matching XML block in the base
  instruction.
- `tools.add` must resolve to a base tool, a same-card `toolDefinitions`
  entry, or a supported platform tool.
- All `sourceDir` and `pythonCode` paths are relative to the app root. Absolute
  paths and `..` escapes are rejected so adapter cards stay portable.

## Validation Rules

These are the same rule IDs surfaced by `cxas poly validate`, `cxas lint`, and
`compile()`:

- `AD001`: malformed card or missing required schema fields
- `AD002`: referenced agent does not exist
- `AD003`: invalid `replace_section` usage
- `AD004`: removing a tool the base agent does not have
- `AD005`: missing tool definition, callback file, or source directory
- `AD006`: adapter has no `evaluations` entries
- `AD007`: duplicate `metadata.channel`
- `AD008`: path is absolute or escapes the app root
- `AD009`: unsupported deployment enum value
- `AD010`: unsupported `toolType`
- `AD011`: malformed `appIdentity` (name not a valid UUID, or empty displayName)

Load `references/debug-adapter.md` for cause and fix guidance.

## Working Loop

1. Identify the direct app root. It must contain `app.json`; nested foundry
   workspaces are not the input shape for `cxas poly`.
2. Inventory the base: root agent, child agents, tools, callbacks, evals,
   `gecx-config.json`, and any existing adapters.
3. Make a channel concern map before writing: instructions, tools, tool
   definitions, callbacks, evals, model overrides, deployment settings, and
   non-goals.
4. Keep the base channel-neutral. Put channel-specific language, rich UI,
   telephony pacing, or API-specific behavior in adapters.
5. Add or update `adapters/<channel>.adapter.yaml`. For a new channel, start
   with `cxas poly init` so referenced eval/tool/callback paths are created
   with the card.
6. Validate first. Use `cxas poly doctor` or `validate --explain` when raw AD
   rule output is not actionable enough.
7. Diff before writing. Use `cxas poly diff <channel> --json` when CI or tools
   need stable machine-readable deltas.
8. Build, then lint the compiled output.
9. Debug adapter rule IDs at the source adapter/base files, not by editing the
   compiled output.

## Required Commands

Use `uv run` from the repo root unless the environment has an activated venv.

```bash
uv run cxas poly init --app-dir <app_dir> --channel <channel>
uv run cxas poly validate --app-dir <app_dir>
uv run cxas poly doctor --app-dir <app_dir>
uv run cxas poly diff <channel> --app-dir <app_dir>
uv run cxas poly diff <channel> --app-dir <app_dir> --json
uv run cxas poly build --app-dir <app_dir> --output-dir <output_dir>
uv run cxas lint --app-dir <output_dir>/<channel>
```

When warnings must block, use `--strict` on `validate`, `doctor`, and `build`.
`init` writes only fields supported by the current `AdapterCard` schema and
creates referenced starter eval/tool/callback files when requested.

## Python API Quick Reference

```python
from cxas_scrapi.poly import PolymorphismEngine, CompilationError

engine = PolymorphismEngine("<app_dir>")
engine.load_base_project()
engine.load_adapter_cards()

try:
    compiled = engine.compile_all()
    for channel, config in compiled.items():
        engine.write_output(config, f"./output/{channel}")
except CompilationError as err:
    for issue in err.issues:
        print(issue["severity"], issue["rule_id"], issue["message"])
```

## Working Examples

The repo ships two complete examples:

- `examples/polymorphic_pizza/` — beginner chat + voice example
- `examples/bella_notte/` — larger reservation example with richer channel
  deltas

Use those as templates when authoring new adapters.

## Non-Negotiables

- Do not fetch, push, or deploy unless the user explicitly asks.
- Do not describe compiled output as the maintained source; the maintained
  source is the base project plus adapter cards.
- Do not document unsupported adapter fields. If a requested delta is not in
  `AdapterCard`, call that out and suggest a supported alternative or source
  change.
- Do not use absolute paths or paths outside the app root in adapter cards;
  validators reject non-portable path references.
- Every behavior-changing adapter should have at least one channel-specific
  eval entry unless the user intentionally accepts the `AD006` warning.
- Never hand-edit compiled output directories; rebuild from the base plus
  adapters instead.
