# Debug Adapter Validation And Compilation Errors

Use this reference when `cxas poly validate`, `cxas poly build`, or the
compiled output behaves unexpectedly.

## Rule Reference

### AD001 — Schema or required fields

Cause:

- Malformed YAML or JSON
- Missing `apiVersion`, `kind`, or required `metadata` fields
- Wrong types in required fields

Required minimum header:

```yaml
apiVersion: poly.cxas.dev/v1
kind: ChannelAdapter
metadata:
  channel: chat
  displayName: Example App - Chat
```

Fixes:

- Check YAML indentation and list syntax
- Ensure `kind` is exactly `ChannelAdapter`
- Ensure the file name is `*.adapter.yaml`, `*.adapter.yml`, or
  `*.adapter.json`

### AD002 — Referenced agent does not exist

Cause:

- An agent named in `instructionDiffs`, `tools`, `modelOverrides`, or
  `callbacks` does not match a real agent

Fixes:

- Check directory names under `agents/`
- Check agent `displayName` values in `agents/<agent>/<agent>.json`
- Use either directory name or display name consistently

### AD003 — Invalid `replace_section`

Cause:

- `mode: replace_section` is missing `sectionTag`, or
- The base instruction does not contain the target XML section

Fixes:

- Add `sectionTag`
- Verify the tag exists in `agents/<Agent>/instruction.txt`
- If no stable base section exists, switch to `append`

### AD004 — Remove targets a tool the base agent does not have

Cause:

- `tools[].remove` names a tool not present in the base agent's tool list

Fixes:

- Remove the no-op `remove`
- Correct the tool name or target agent

### AD005 — Missing definition or source path

Cause:

- `tools[].add` references a tool that is not in base tools, same-card
  `toolDefinitions`, or supported platform tools
- `toolDefinitions[].sourceDir` does not exist or lacks a valid tool file
- `callbacks[].pythonCode` does not exist
- An eval, expectation, or dataset source dir does not exist

Fixes:

- Add or correct the tool definition
- Create the referenced callback or source directory under the app root
- Re-check relative paths from the direct app root

### AD006 — No evaluations entries

Cause:

- The adapter has no `evaluations` block

Fix:

- Add channel eval coverage, or explicitly accept the warning if the user
  truly wants none

### AD007 — Duplicate channel id

Cause:

- Two cards share the same `metadata.channel`

Fix:

- Rename one channel id so each adapter is unique

### AD008 — Path escapes the app root

Cause:

- `sourceDir` or `pythonCode` resolves outside the app via `..` or absolute
  paths

Fix:

- Keep all paths relative to the direct app root and inside it

### AD009 — Invalid deployment enum value

Cause:

- Unsupported `channelType`, `modality`, or `theme`

Fix:

- Use only the enum values supported in `src/cxas_scrapi/poly/models.py`

### AD010 — Unsupported tool type

Cause:

- `toolDefinitions[].toolType` is not `python` or `openapi`

Fix:

- Use `python` or `openapi`, or change source code before documenting a new
  type

### AD011 — Malformed appIdentity

Cause:

- `appIdentity.name` is set but is not a valid UUID
- `appIdentity.displayName` is set but blank

Fix:

- Provide a real UUID for `appIdentity.name`, or omit it to let the engine
  derive a deterministic per-channel id
- Give `appIdentity.displayName` a non-empty value, or omit it to fall back to
  the adapter's `metadata.displayName`

## Common Failure Patterns

### "No app.json found"

The engine expects a direct project root. Nested foundry layouts are not valid
base inputs for `cxas poly`.

### "Refusing to write output — it overlaps the base project"

The output directory cannot be inside or equal to the source app directory.
Pick a sibling temp or output directory instead.

### "Refusing to overwrite — not created by cxas poly build"

The target directory exists and does not contain `.poly_build.json`. Use a new
output directory or `--force` if overwriting is intentional.

### Build succeeds but compiled output lints poorly

Usually means:

- A channel-only tool definition is incomplete
- A callback has syntax or path problems
- An instruction diff produced invalid or lint-hostile text

Fix the source adapter or base project, then rebuild.

### Voice output still uses Markdown

Inspect the compiled voice instruction and strengthen the voice
`instructionDiff`.

### Chat output lacks rich UI tools

Check `tools.add`, `toolDefinitions`, and callback paths. Missing definitions
are often `AD005`.

### Shared behavior drifted across channels

The base project is not channel-neutral enough. Move shared business logic back
into the base and keep adapters focused on channel deltas.

## Debugging Workflow

1. Run guided validation:

```bash
uv run cxas poly doctor --app-dir <app_dir>
```

2. Run structured validation when a script/tool needs JSON:

```bash
uv run cxas poly validate --app-dir <app_dir> --format json
uv run cxas poly validate --app-dir <app_dir> --explain --format json
```

3. Fix issues by rule ID at the source adapter/base files.
4. Re-run validation until clean.
5. Preview the delta:

```bash
uv run cxas poly diff <channel> --app-dir <app_dir>
uv run cxas poly diff <channel> --app-dir <app_dir> --json
```

6. Build and lint compiled output.
7. Compare compiled files to the intended behavior.

## Compiled Output Inspection

```bash
cat <output_dir>/<channel>/gecx-config.json
cat <output_dir>/<channel>/agents/<Agent>/instruction.txt
cat <output_dir>/<channel>/agents/<Agent>/<Agent>.json
find <output_dir>/<channel>/tools -maxdepth 2 -type f | sort
find <output_dir>/<channel>/evaluations -maxdepth 2 -type f | sort
```

## Python Introspection

```python
from cxas_scrapi.poly.engine import PolymorphismEngine

engine = PolymorphismEngine("<app_dir>")
engine.load_base_project()
engine.load_adapter_cards()
card, path = engine.adapters["chat"]
compiled = engine.compile(card, path)

print(compiled.agent_instructions.keys())
print(compiled.agents["Order_Agent"]["tools"])
print(compiled.deployment)
```

This mirrors the CLI path and keeps debugging grounded in the same engine.

## If The Requested Workflow Is Unsupported

Point to the exact missing `AdapterCard` field, enum, or engine behavior in
`src/cxas_scrapi/poly/models.py`, `src/cxas_scrapi/poly/validators.py`, or
`src/cxas_scrapi/poly/engine.py`, then recommend either:

- a supported adapter shape, or
- a source-code change with tests
