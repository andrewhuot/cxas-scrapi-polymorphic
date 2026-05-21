---
title: Polymorphism Pattern
description: A step-by-step walkthrough of compiling the Bella Notte agent into channel-optimized chat and voice variants with channel adapter cards.
---

# Polymorphism Pattern

This page walks through the **Polymorphism Pattern** end to end using the Bella Notte restaurant agent: one base project, two channel adapter cards (chat and voice), and the `cxas poly` compiler that turns them into two complete, deployable projects.

If you haven't read the concept overview yet, start with the **[Polymorphism guide](../guides/polymorphism.md)**.

---

## 1. The base agent

The base project is an ordinary SCRAPI project — nothing about it is polymorphism-specific:

```
examples/bella_notte/
├── app.json
├── gecx-config.json
├── agents/
│   ├── Bella_Notte_Host/        # root agent: routes reservation vs. takeout
│   ├── Reservation_Agent/       # slot-filling specialist
│   └── Takeout_Agent/
├── tools/                       # set_active_flow, set_reservation_basics, …
├── evaluations/                 # shared, channel-neutral goldens
└── evaluationExpectations/
```

The base instructions are written to be **channel-neutral**: they describe *what* the host does (greet, route, answer hours/location) without committing to *how* it should look on a screen or sound on a call.

---

## 2. The chat adapter

`examples/bella_notte/adapters/chat.adapter.yaml` specializes the agent for a web chat widget:

```yaml
apiVersion: poly.cxas.dev/v1
kind: ChannelAdapter
metadata:
  channel: chat
  displayName: Bella Notte — Chat
  description: Web chat optimization: markdown, selectable lists, rich cards.

instructionDiffs:
  - agent: Bella_Notte_Host
    mode: append
    content: |
      <channel_chat>
      You are responding in a web chat widget that renders Markdown.
      - Use **bold** for emphasis and short numbered lists for options.
      - When confirming, call the send_rich_card tool to render a card.
      </channel_chat>
  - agent: Reservation_Agent
    mode: append
    content: |
      <channel_chat>
      Present available time slots as a numbered, selectable list.
      </channel_chat>

tools:
  - agent: Bella_Notte_Host
    add: [send_rich_card]

toolDefinitions:
  - displayName: send_rich_card
    toolType: python
    sourceDir: adapters/chat_tools/send_rich_card

callbacks:
  - agent: Bella_Notte_Host
    type: before_model
    pythonCode: adapters/chat_callbacks/inject_rich_content.py
    description: Inject rich card formatting hints for chat confirmations.

evaluations:
  - sourceDir: adapters/chat_evals

deployment:
  channelType: WEB_UI
  modality: CHAT_ONLY
  webWidgetConfig:
    theme: LIGHT
    webWidgetTitle: Bella Notte Reservations
```

Section by section:

- **`instructionDiffs`** — append a `<channel_chat>` block to the host and the reservation agent. `append` keeps all the base behavior and layers chat presentation on top.
- **`tools` + `toolDefinitions`** — make `send_rich_card` available to the host *and* bring its definition (`send_rich_card.json` + `python_code.py`) into `tools/`. The engine normalizes the tool's code path to the canonical `tools/send_rich_card/python_function/python_code.py`.
- **`callbacks`** — append a `before_model` callback. The base host already has `before_model_callbacks_01`, so this becomes `before_model_callbacks_02` automatically.
- **`evaluations`** — fold the `adapters/chat_evals/` directory into the compiled `evaluations/`.
- **`deployment`** — emit a `deployment.json` for a `WEB_UI` / `CHAT_ONLY` deployment.

---

## 3. The voice adapter

`examples/bella_notte/adapters/voice.adapter.yaml` tunes the same agent for telephony:

```yaml
apiVersion: poly.cxas.dev/v1
kind: ChannelAdapter
metadata:
  channel: voice
  displayName: Bella Notte — Voice

instructionDiffs:
  - agent: Bella_Notte_Host
    mode: append
    content: |
      <channel_voice>
      You are speaking on a phone call. There is no screen.
      - Keep every response to two or three short sentences.
      - Never use Markdown, bullet points, or symbols.
      - Spell out numbers and times ("six thirty in the evening").
      - Say a brief filler before tool calls so the line is not silent.
      </channel_voice>
  - agent: Reservation_Agent
    mode: append
    content: |
      <channel_voice>
      Offer at most three available times at once, spoken aloud.
      Read confirmations back field by field with a short pause between each.
      </channel_voice>

callbacks:
  - agent: Bella_Notte_Host
    type: before_model
    pythonCode: adapters/voice_callbacks/voice_pacing.py
    description: Inject voice pacing and filler-phrase hints.

evaluations:
  - sourceDir: adapters/voice_evals

deployment:
  channelType: GOOGLE_TELEPHONY_PLATFORM
  modality: VOICE_ONLY
  disableBargeInControl: false
  disableDtmf: false
```

The voice adapter is almost entirely additive: it never touches the base tool list, because the base host has no chat-only tools to remove. (If a rich-card tool *were* present in the base, you'd add a `tools: [{agent: …, remove: [send_rich_card]}]` here.)

Notice the symmetry: both adapters `append` a channel block and add a `before_model` callback, but they pull behavior in opposite directions — verbose-and-visual vs. terse-and-spoken — from the same base.

---

## 4. Build the channels

```bash
cxas poly build --app-dir examples/bella_notte --output-dir ./output
```

```
Compiled channel 'chat'  -> ./output/chat
Compiled channel 'voice' -> ./output/voice

Done. 2 channel(s) written to ./output
```

Each output directory is a complete project. The chat host now lists `send_rich_card`; the voice host does not. The chat instruction carries the `<channel_chat>` block; the voice instruction carries `<channel_voice>`.

Preview exactly what an adapter changes — without writing anything — with `diff`:

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

---

## 5. Lint, evaluate, and deploy the output

Because each compiled directory *is* a normal project, every existing command works on it unchanged:

```bash
# Lint each channel — both pass cleanly.
cxas lint --app-dir ./output/chat
cxas lint --app-dir ./output/voice

# Run the merged eval suite (base + channel goldens) on a channel.
cxas run --app-dir ./output/chat --eval-dir ./output/chat/evaluations

# Deploy — the compiled deployment.json carries channel/modality settings.
```

This is the payoff of the **[author once at the center](../guides/polymorphism.md#the-compilation-model)** model: you maintain a single Bella Notte agent, and the channel-specific surfaces fall out of two short adapter files.

---

## See also

- **[Polymorphism guide](../guides/polymorphism.md)** — concepts and when to use adapters.
- **[`cxas poly` CLI reference](../../cli/poly.md)** — full command and flag reference.
