# Polymorphic Pizza — chat + voice from one agent

A complete, runnable demo for a fictional pizza shop, **Polymorphic Pizza**.

You author **one** agent project here. With a single command the polymorphism
engine compiles it into **two** ready-to-deploy projects:

- a **chat agent** for a web chat widget (Markdown, numbered lists, a visual
  order-confirmation card), and
- a **voice agent** for a phone line (short spoken turns, no symbols, prices
  read aloud).

Same business logic, same tools, one place to fix bugs — the channel
differences live in two short *adapter cards*.

> New here? Read the one-page idea in the
> [root README](../../README.md#the-core-idea) first. This page is the
> hands-on, copy-paste walkthrough.

---

## What's in the box

```
polymorphic_pizza/
├── app.json                 # the application (root agent = Pizza_Host)
├── gecx-config.json         # deployment config (fill in your GCP details to deploy)
├── cxaslint.yaml            # linter settings for this project
├── agents/
│   ├── Pizza_Host/          # greets the customer and routes the request
│   ├── Order_Agent/         # takes a pizza order start to finish
│   └── Tracking_Agent/      # looks up the status of an existing order
├── tools/                   # plain Python functions the agents call
│   ├── set_active_flow/     #   route to "order" or "track"
│   ├── get_menu/            #   list sizes, pizzas, toppings, prices
│   ├── quote_pizza/         #   price one pizza
│   ├── place_order/         #   place a confirmed order
│   └── get_order_status/    #   check an order by its number
├── evaluations/             # channel-neutral tests (shared by both channels)
└── adapters/                # ← the only channel-specific part
    ├── chat.adapter.yaml    #   what changes for web chat
    └── voice.adapter.yaml   #   what changes for the phone
```

**How the agents fit together:** the customer always meets `Pizza_Host`. When
they ask to order, the host calls the `set_active_flow` tool and is handed off
to `Order_Agent`; when they ask about an existing order, it hands off to
`Tracking_Agent`. (The hand-off is wired up by two small callbacks on the host
— you don't have to touch them to use the demo.)

---

## Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (the package manager this repo uses)

That's it. Everything below runs **locally** — no Google Cloud account or
credentials are needed to build and inspect the agents.

---

## Setup (once)

From the **repository root**:

```bash
uv sync --extra dev
```

This creates a virtual environment and installs the `cxas` command. Prefix the
commands below with `uv run` (as shown) and you don't need to activate anything.

---

## Run it, step by step

All commands are run from the repository root.

### 1. Validate the adapter cards

Checks that everything the adapters reference (agents, tools, evals) actually
exists.

```bash
uv run cxas poly validate --app-dir examples/polymorphic_pizza
```

```
All 2 adapter card(s) valid.
```

If you break an adapter while experimenting, use doctor for the actionable
version of the same validation:

```bash
uv run cxas poly doctor --app-dir examples/polymorphic_pizza
# or
uv run cxas poly validate --app-dir examples/polymorphic_pizza --explain
```

### 2. Preview what each channel changes

`diff` shows exactly what an adapter will do — **without writing any files**.
Use the default text form for review and `--json` when a script or CI job needs
stable fields.

```bash
uv run cxas poly diff chat  --app-dir examples/polymorphic_pizza
uv run cxas poly diff voice --app-dir examples/polymorphic_pizza
uv run cxas poly diff chat  --app-dir examples/polymorphic_pizza --json
```

For **chat** you'll see the `Order_Agent` gain a `send_order_card` tool, a chat
formatting block appended to two agents, and a `WEB_UI` deployment. For
**voice** you'll see spoken-pacing instructions and a `GOOGLE_TELEPHONY_PLATFORM`
deployment instead.

### 3. Build both channels

```bash
uv run cxas poly build --app-dir examples/polymorphic_pizza --output-dir ./output
```

```
Compiled channel 'chat' -> ./output/chat
Compiled channel 'voice' -> ./output/voice

Done. 2 channel(s) written to ./output
```

You now have two complete, independent projects under `./output/`.

### 4. Confirm the output is "just a project"

The compiled output is indistinguishable from a hand-written project, so every
normal command works on it:

```bash
uv run cxas lint --app-dir ./output/chat
uv run cxas lint --app-dir ./output/voice
```

```
Lint PASSED (no errors).
```

From here, `./output/chat` and `./output/voice` can be evaluated and deployed
exactly like any other CXAS project (that step needs a Google Cloud project —
see the [official docs](https://googlecloudplatform.github.io/cxas-scrapi/stable/)).

---

## See the difference

Open the same file in each compiled channel and compare:

```bash
# The order specialist's instructions, chat vs. voice:
cat ./output/chat/agents/Order_Agent/instruction.txt
cat ./output/voice/agents/Order_Agent/instruction.txt
```

| | Chat | Voice |
|---|---|---|
| **Instructions add** | Markdown, numbered lists, a confirmation card | 2–3 sentence turns, no symbols, spoken prices |
| **Extra tool** | `send_order_card` (visual card) | none |
| **Model/runtime config** | `gemini-3-pro`, text modality | `gemini-3-flash`, audio modality |
| **Deployment** | `WEB_UI` / `CHAT_ONLY` | `GOOGLE_TELEPHONY_PLATFORM` / `VOICE_ONLY` |
| **gecx-config modality** | `text` | `audio` |

Both were generated from the **same** `agents/`, `tools/`, and `evaluations/`.

---

## Try it yourself

Make a change once and watch it appear in both channels:

1. Add a new topping to `tools/get_menu/python_function/python_code.py`.
2. Re-run the build (step 3). Both `./output/chat` and `./output/voice` pick it
   up — no copy-paste, no drift.

Or tweak just one channel by editing `adapters/chat.adapter.yaml` (for example,
change `webWidgetTitle`) and rebuild — only the chat output changes.

To start a new channel from this same base app, scaffold the first pass:

```bash
uv run cxas poly init \
  --app-dir examples/polymorphic_pizza \
  --channel sms \
  --deployment-target TWILIO \
  --modality VOICE_ONLY \
  --with-callback before_model \
  --with-tool send_sms_card
```

That creates `adapters/sms.adapter.yaml`, a starter SMS eval, a starter callback,
and a channel-only tool folder. The callback stub starts with the correct
hook-specific function signature, and the adapter references it with a
project-relative `pythonCode` path. Replace the generated placeholder behavior
with real SMS-specific UX before building.

---

## How this maps to the engine

- The base project is an ordinary CXAS agent project.
- Each `adapters/<channel>.adapter.yaml` declares only the *deltas* for that
  channel: instruction edits, tools to add, callbacks, evaluations, and
  deployment settings.
- `cxas poly build` deep-copies the base, applies the deltas, and writes one
  finished project per channel.

For the full adapter-card reference and the compilation pipeline, see the
[root README](../../README.md) and the
[Polymorphism guide](../../docs/guides/polymorphism.md).
