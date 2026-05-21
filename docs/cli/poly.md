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
| `--output-dir DIR` | No | `./output` | Directory to write compiled projects into. Each channel is written to `<output-dir>/<channel>/`. |

### Behavior

- With `--channel all`, all adapters are validated first; if any **error**-severity issue is found, nothing is written.
- With a specific `--channel`, only that adapter is validated and compiled.
- Each existing `<output-dir>/<channel>/` directory is replaced on every build.

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
cxas poly validate [--app-dir DIR]
```

### Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--app-dir DIR` | No | `.` (current directory) | Path to the base agent project root. |

### Rules

| ID | Severity | Check |
|----|----------|-------|
| `AD001` | error | Adapter card has required fields (`apiVersion`, `kind`, `metadata.channel`) and valid types. |
| `AD002` | error | Every agent referenced in `instructionDiffs`, `tools`, `modelOverrides`, `callbacks` exists in `agents/`. |
| `AD003` | error | `replace_section` diffs set `sectionTag`, and the `<sectionTag>` exists in the target instruction. |
| `AD004` | warning | A tool `remove` references a tool not in the base agent's tool list. |
| `AD005` | error | A tool `add` references a tool defined neither in `tools/` nor in the adapter's `toolDefinitions`. |
| `AD006` | warning | The adapter declares no `evaluations` entries. |
| `AD007` | error | Two adapter cards target the same `metadata.channel`. |

> **Note on rule IDs:** the `AD` prefix is used (not `A`) because the `config` lint category already owns `A001`–`A006`. The same rules run inside `cxas lint --only adapters`.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | No errors (warnings may be present), or no adapter cards found. |
| `1` | One or more **error**-severity issues, or a missing base project. |

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

deployment.json
  + channelType: GOOGLE_TELEPHONY_PLATFORM
  + modality: VOICE_ONLY
```

---

## See also

- **[Polymorphism guide](../guides/polymorphism.md)**
- **[Polymorphism pattern](../patterns/polymorphism.md)**
- **[`cxas lint`](lint.md)** — the `adapters` category runs `AD001`–`AD007` as part of a normal lint.
