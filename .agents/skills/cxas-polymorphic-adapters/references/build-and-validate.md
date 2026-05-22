# Build, Validate, And Diff

Use this reference after an adapter card exists, or when the user wants to
review deltas, compile channels, or inspect compiled output.

## Preflight

From the repo root, confirm the app root is a direct SCRAPI project:

```bash
test -f <app_dir>/app.json
test -d <app_dir>/agents
test -d <app_dir>/adapters
```

If `app.json` is missing, polymorphism will fail with "No app.json found".
Locate the direct project root before continuing.

## Validation Loop

Run validation before every build:

```bash
uv run cxas poly validate --app-dir <app_dir>
```

Useful options:

- `--format json` for structured output
- `--explain` for guided what/why/path/fix output
- `--strict` when warnings should block

Use doctor when debugging:

```bash
uv run cxas poly doctor --app-dir <app_dir>
uv run cxas poly doctor --app-dir <app_dir> --format json
```

`cxas lint` also discovers `adapters/*.adapter.{yaml,yml,json}` and delegates
to the same rule IDs. In zero-warning workspaces, treat adapter warnings as
blockers.

## Preview The Delta

Preview what a channel changes before writing output:

```bash
uv run cxas poly diff chat --app-dir <app_dir>
uv run cxas poly diff voice --app-dir <app_dir>
uv run cxas poly diff chat --app-dir <app_dir> --json
```

Use the diff to verify:

- Touched agents are expected
- Instruction diffs are small and scoped
- Added and removed tools are intentional
- New callbacks, evals, and deployment settings appear where expected

## Build

Build into a directory outside the source app:

```bash
uv run cxas poly build --app-dir <app_dir> --output-dir <output_dir>
```

Build one channel when iterating:

```bash
uv run cxas poly build --app-dir <app_dir> --channel chat --output-dir <output_dir>
```

What build does:

1. Validates adapter cards
2. Deep-copies the base project per channel
3. Applies deltas in fixed order: instruction diffs → tool modifications →
   tool definitions → model overrides → callbacks → evals → deployment
4. Writes one complete project directory per channel
5. Places a `.poly_build.json` marker in each output directory

The writer refuses to overwrite a non-empty directory unless it was produced by
`cxas poly build` and contains `.poly_build.json`, or unless `--force` is
used. Do not use an output directory inside the app root; the engine rejects
overlap.

## Lint And Inspect Compiled Output

Compiled channels are ordinary projects:

```bash
uv run cxas lint --app-dir <output_dir>/chat
uv run cxas lint --app-dir <output_dir>/voice
```

Then inspect the specific deltas you expected:

```bash
cat <output_dir>/<channel>/gecx-config.json
cat <output_dir>/<channel>/agents/<Agent>/instruction.txt
cat <output_dir>/<channel>/agents/<Agent>/<Agent>.json
find <output_dir>/<channel>/tools -maxdepth 2 -type f | sort
find <output_dir>/<channel>/evaluations -maxdepth 2 -type f | sort
```

If the compiled output looks wrong, fix the base project or adapter card and
rebuild. Do not make the compiled directory the maintained source.

## Python API

For programmatic inspection or debugging without writing output:

```python
from cxas_scrapi.poly import PolymorphismEngine, CompilationError

engine = PolymorphismEngine("<app_dir>")
engine.load_base_project()
engine.load_adapter_cards()

card, path = engine.adapters["chat"]
compiled = engine.compile(card, path)

print(compiled.agent_instructions.keys())
print(compiled.agents["Order_Agent"]["tools"])
print(compiled.deployment)
```

To compile all channels programmatically:

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
        print(issue["rule_id"], issue["message"])
```

## Relevant Verification

For real engine, validator, CLI, and lint-rule coverage:

```bash
uv run pytest tests/cxas_scrapi/poly
```

For a fast example smoke:

```bash
uv run cxas poly validate --app-dir examples/polymorphic_pizza
uv run cxas poly doctor --app-dir examples/polymorphic_pizza
uv run cxas poly diff chat --app-dir examples/polymorphic_pizza
uv run cxas poly diff chat --app-dir examples/polymorphic_pizza --json
uv run cxas poly build --app-dir examples/polymorphic_pizza --output-dir .tmp-poly-output
uv run cxas lint --app-dir .tmp-poly-output/chat
uv run cxas lint --app-dir .tmp-poly-output/voice
```

Clean temporary output after inspection if it is not part of the task.

## Typical Workflow

1. `uv run cxas poly init --app-dir <app_dir> --channel <channel>` for a new
   channel
2. `uv run cxas poly validate --app-dir <app_dir>`
3. `uv run cxas poly doctor --app-dir <app_dir>` if validation is not clear
4. `uv run cxas poly diff <channel> --app-dir <app_dir>`
5. `uv run cxas poly diff <channel> --app-dir <app_dir> --json` when CI/tooling
   needs stable deltas
6. `uv run cxas poly build --app-dir <app_dir> --output-dir <output_dir>`
7. `uv run cxas lint --app-dir <output_dir>/<channel>`
8. Inspect compiled instructions, tools, evals, and deployment config
9. Hand the compiled project to `cxas-agent-foundry` if the user now wants
   eval, push, or broader lifecycle work
