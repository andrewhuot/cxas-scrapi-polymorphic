---
title: Polymorphism in 5 Minutes
description: Add a new channel to an existing SCRAPI app with cxas poly init, validate --explain, diff --json, and build.
---

# Polymorphism in 5 Minutes

This is the fastest way to understand the new polymorphism developer workflow.
In five minutes, you will:

1. start from an existing direct SCRAPI app
2. scaffold a new adapter with `cxas poly init`
3. validate it with guided diagnostics available if something is off
4. inspect the machine-readable delta with `cxas poly diff --json`
5. build a compiled channel project and lint it like any other app

This walkthrough uses the repo's **Polymorphic Pizza** example and adds a new
`sms` channel.

## Prerequisites

From the repo root:

```bash
uv sync --extra dev
```

You need Python 3.10+ and `uv`.

---

## 1. Copy the example to a scratch directory

Keep the committed example clean and work in a temp copy:

```bash
rm -rf /tmp/polymorphic-pizza-sms
cp -R examples/polymorphic_pizza /tmp/polymorphic-pizza-sms
```

Confirm that the app is a **direct** SCRAPI project root:

```bash
test -f /tmp/polymorphic-pizza-sms/app.json
test -d /tmp/polymorphic-pizza-sms/agents
test -d /tmp/polymorphic-pizza-sms/adapters
```

If those checks pass, you're ready.

---

## 2. Scaffold a new channel with `cxas poly init`

Create a starter `sms` adapter with a channel-only tool and callback:

```bash
uv run cxas poly init \
  --app-dir /tmp/polymorphic-pizza-sms \
  --channel sms \
  --deployment-target TWILIO \
  --modality VOICE_ONLY \
  --with-tool send_sms_card \
  --with-callback before_model
```

This creates a minimal but valid starter workflow around the adapter:

```text
/tmp/polymorphic-pizza-sms/
├── adapters/sms.adapter.yaml
├── adapters/sms_evals/Sms_Smoke/Sms_Smoke.yaml
├── adapters/sms_tools/send_sms_card/send_sms_card.json
├── adapters/sms_tools/send_sms_card/python_code.py
└── adapters/sms_callbacks/before_model.py
```

The generated content is intentionally conservative. It gives you a valid place
for channel-specific instructions, evals, callback logic, and channel-only tool
code without inventing unsupported adapter-card fields. Callback stubs use the
right entry function and typed signature for their hook, and all generated
`sourceDir`/`pythonCode` references are project-relative so the adapter stays
portable.

If you only want to preview what would be written, add `--dry-run`.

---

## 3. Validate the scaffold

Run the normal validator first:

```bash
uv run cxas poly validate --app-dir /tmp/polymorphic-pizza-sms
```

If you want more guidance, use the explain/doctor flow:

```bash
uv run cxas poly validate --app-dir /tmp/polymorphic-pizza-sms --explain
# or
uv run cxas poly doctor --app-dir /tmp/polymorphic-pizza-sms
```

These commands use the same AD rule IDs as standard validation, but add:

- what failed
- why it matters
- which adapter field or referenced path to inspect
- a likely fix shape

That means you can start with the normal validator in CI and switch to
`--explain` or `doctor` when you want a faster debugging loop.

---

## 4. Inspect the delta before you build

The new JSON diff is useful for both humans and tooling. For the new `sms`
adapter:

```bash
uv run cxas poly diff sms --app-dir /tmp/polymorphic-pizza-sms --json
```

You will get a `poly-diff/v1` report describing the adapter delta in a stable,
machine-readable shape. The report includes:

- the channel id and adapter path
- summary counts
- per-agent instruction/tool/callback changes
- channel-only tool definitions
- eval merges
- deployment and runtime-config overlays
- a flattened `deltas[]` list for simple CI assertions

Want the reviewer-friendly text form instead?

```bash
uv run cxas poly diff sms --app-dir /tmp/polymorphic-pizza-sms
```

Use text for code review and `--json` for automation.

---

## 5. Build and lint the compiled output

Compile the app into channel-specific projects:

```bash
rm -rf /tmp/polymorphic-pizza-output
uv run cxas poly build \
  --app-dir /tmp/polymorphic-pizza-sms \
  --output-dir /tmp/polymorphic-pizza-output
```

Now lint the compiled project exactly like any other SCRAPI app:

```bash
uv run cxas lint --app-dir /tmp/polymorphic-pizza-output/chat
uv run cxas lint --app-dir /tmp/polymorphic-pizza-output/voice
uv run cxas lint --app-dir /tmp/polymorphic-pizza-output/sms
```

That is the core payoff of polymorphism: the output is **just a project**.
There is no special runtime to install and no half-compiled state to reason
about.

---

## What to edit next

After the scaffold succeeds, replace the starter content with real channel
behavior:

- tighten the `sms.adapter.yaml` instruction diffs for your actual UX
- replace the stub eval with real assertions about the new channel
- implement the callback logic instead of leaving the starter body in place
- flesh out the channel-only tool if the adapter needs one

A useful loop is:

```bash
uv run cxas poly validate --app-dir /tmp/polymorphic-pizza-sms --explain
uv run cxas poly diff sms --app-dir /tmp/polymorphic-pizza-sms
uv run cxas poly build --app-dir /tmp/polymorphic-pizza-sms --output-dir /tmp/polymorphic-pizza-output
uv run cxas lint --app-dir /tmp/polymorphic-pizza-output/sms
```

---

## Where to go next

- **[Polymorphism guide](polymorphism.md)** — concepts, trade-offs, and the compilation model
- **[Polymorphism pattern](../patterns/polymorphism.md)** — a deeper Bella Notte walkthrough
- **[`cxas poly` CLI reference](../cli/poly.md)** — all command options, including `init`, `doctor`, `validate --explain`, and `diff --json`
