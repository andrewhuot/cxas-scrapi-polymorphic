# cxas poly

`cxas poly` is the **Polymorphism Engine**: it compiles a single base agent project plus per-channel **adapter cards** into channel-optimized agent project directories. The compiled output is a complete, ordinary SCRAPI project — lintable, evaluable, and deployable with no special handling.

See the **[Polymorphism guide](../guides/polymorphism.md)** for concepts and the **[Polymorphism pattern](../patterns/polymorphism.md)** for a full walkthrough.

The command has three subcommands:

| Subcommand | Purpose |
|---|---|
| [`cxas poly build`](#cxas-poly-build) | Compile channel-optimized projects. |
| [`cxas poly validate`](#cxas-poly-validate) | Validate adapter cards against the base project. |
| [`cxas poly diff`](#cxas-poly-diff) | Show what an adapter changes for a channel. |

Adapter cards live in `<app-dir>/adapters/` and are named `*.adapter.yaml`, `*.adapter.yml`, or `*.adapter.json`.

---

## cxas poly build

Compile one or all channels into output project directories.

### Usage

```
cxas poly build [--app-dir DIR]
                [--channel NAME|all]
                [--output-dir DIR]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--app-dir DIR` | No | `.` (current directory) | Path to the base agent project root (the directory containing `app.json`, `agents/`, `tools/`, `adapters/`). |
| `--channel NAME` | No | `all` | A specific channel to compile (matched against an adapter's `metadata.channel`), or `all` to compile every adapter. |
| `--output-dir DIR` | No | `./output` | Directory to write compiled projects into. Each channel is written to `<output-dir>/<channel>/`. Must not overlap the base project. |
| `--force` | No | off | Overwrite a `<output-dir>/<channel>/` that is non-empty and was **not** created by `cxas poly build`. Without it, such a directory is left untouched. |
| `--strict` | No | off | Treat warnings as errors and abort the build. |

### Behavior

- With `--channel all`, all adapters are validated first; if any **error**-severity issue is found (including a malformed card), nothing is written.
- With a specific `--channel`, only that adapter is validated and compiled.
- A `<output-dir>/<channel>/` directory is replaced only when it is empty or was previously produced by `cxas poly build` (it carries a `.poly_build.json` marker); otherwise the build refuses unless `--force` is given. The output directory may never overlap the base project.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All requested channels compiled and written successfully. |
| `1` | No adapters found, unknown `--channel`, validation errors, or a missing base project. |

### Example

```bash
cxas poly build --app-dir examples/bella_notte --output-dir ./output
```

```
Compiled channel 'chat'  -> ./output/chat
Compiled channel 'voice' -> ./output/voice

Done. 2 channel(s) written to ./output
```

---

## cxas poly validate

Validate every adapter card against the base project structure. Prints results in the same severity/rule-ID format as `cxas lint`.

### Usage

```
cxas poly validate [--app-dir DIR] [--format text|json] [--strict]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--app-dir DIR` | No | `.` (current directory) | Path to the base agent project root. |
| `--format` | No | `text` | Output format. `json` emits a machine-readable report (`errors`, `warnings`, `issues[]`) for CI. |
| `--strict` | No | off | Exit non-zero if any warnings are present (not just errors). |

### Rules

| ID | Severity | Check |
|----|----------|-------|
| `AD001` | error | Adapter card has required fields (`apiVersion`, `kind`, `metadata.channel`) and valid types (malformed cards are reported here, not as a traceback). |
| `AD002` | error | Every agent referenced in `instructionDiffs`, `tools`, `modelOverrides`, `callbacks` exists in `agents/`. |
| `AD003` | error | `replace_section` diffs set `sectionTag`, and a matching `<sectionTag …>…</sectionTag>` block (attributes allowed) exists in the target instruction. |
| `AD004` | warning | A tool `remove` references a tool not in the base agent's tool list. |
| `AD005` | error | A tool `add` references a tool defined neither in `tools/`, the adapter's `toolDefinitions`, nor a platform tool; or a referenced `pythonCode`/`sourceDir` is missing. |
| `AD006` | warning | The adapter declares no `evaluations` entries. |
| `AD007` | error | Two adapter cards target the same `metadata.channel`. |
| `AD008` | error | A referenced `sourceDir`/`pythonCode` path escapes the project root. |
| `AD009` | error | `deployment` `channelType`/`modality`/`theme` use known, supported values. |
| `AD010` | error | `toolDefinitions` declare a supported `toolType` (`python`, `openapi`). |

> **Note on rule IDs:** the `AD` prefix is used (not `A`) because the `config` lint category already owns `A001`–`A006`. The same rules run inside `cxas lint --only adapters`.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | No errors (warnings may be present, unless `--strict`), or no adapter cards found. |
| `1` | One or more **error**-severity issues (or any warnings with `--strict`), or a missing base project. |

### Example

```bash
cxas poly validate --app-dir examples/bella_notte
```

```
All 2 adapter card(s) valid.
```

---

## cxas poly diff

Show a human-readable, per-agent summary of what a channel's adapter changes — without writing any files.

### Usage

```
cxas poly diff CHANNEL [--app-dir DIR]
```

### Arguments & options

| Argument / Option | Required | Default | Description |
|-------------------|----------|---------|-------------|
| `CHANNEL` | Yes | — | The channel to diff (matched against an adapter's `metadata.channel`). |
| `--app-dir DIR` | No | `.` (current directory) | Path to the base agent project root. |

### Output

For each touched agent, the diff shows instruction additions/replacements, tool changes (`+`/`-`), model overrides (`old -> new`), and added callbacks, followed by new tools, merged evaluations, and the deployment overrides.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Diff rendered successfully. |
| `1` | Unknown channel, compilation error, or a missing base project. |

### Example

```bash
cxas poly diff voice --app-dir examples/bella_notte
```

```
Channel: voice   (adapter: adapters/voice.adapter.yaml)

agents/Bella_Notte_Host
  instruction: + N line(s) append
  callbacks: + before_model (Inject voice pacing and filler-phrase hints.)

gecx-config.json (deployment)
  + channel_type: GOOGLE_TELEPHONY_PLATFORM
  + modality: VOICE_ONLY
```

---

## See also

- **[Polymorphism guide](../guides/polymorphism.md)**
- **[Polymorphism pattern](../patterns/polymorphism.md)**
- **[`cxas lint`](lint.md)** — the `adapters` category runs `AD001`–`AD010` as part of a normal lint.
