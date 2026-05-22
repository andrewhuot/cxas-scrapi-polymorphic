# Adapter Authoring

Use this reference when writing or revising `adapters/<channel>.adapter.yaml`
for the current SCRAPI polymorphism engine.

## Source Files To Read

Before authoring an adapter, read the real project files:

- `app.json`: app display name, root agent, app-level tool inventory
- `agents/<agent>/<agent>.json`: agent display names, `tools`, callbacks,
  `modelSettings`, child agents, and instruction path
- `agents/<agent>/instruction.txt`: channel-neutral base behavior and any XML
  sections available for `replace_section`
- `tools/<tool>/<tool>.json` and tool code: which tools already exist
- `evaluations/`, `evaluationExpectations/`, `evaluationDatasets/`: shared
  baseline eval coverage
- Existing `adapters/*.adapter.yaml`: current channel strategy and naming

Use `examples/polymorphic_pizza/adapters/` for a smaller example and
`examples/bella_notte/adapters/` for a larger slot-filling example.

## Step-By-Step Workflow

### 1. Identify the target channel and requirements

Get clear on:

- What channel is being added: `chat`, `voice`, or another channel id
- Which changes are actually channel-specific: formatting, pacing, callbacks,
  deployment target, widget settings, model tuning, or channel-only tools
- Whether the channel delta is small enough for an adapter, instead of a fully
  separate agent

### 2. Start from the required card skeleton

```yaml
apiVersion: poly.cxas.dev/v1
kind: ChannelAdapter
metadata:
  channel: chat
  displayName: Example App - Chat
  description: Web chat optimization for Example App.

instructionDiffs: []
tools: []
toolDefinitions: []
modelOverrides: []
callbacks: []
evaluations: []
evaluationExpectations: []
evaluationDatasets: []
deployment: {}
```

Only include blocks that are needed. Adapter files are discovered only when
named `*.adapter.yaml`, `*.adapter.yml`, or `*.adapter.json` under `adapters/`.
`metadata.channel` becomes the output directory name and generated deployment
id.

### 3. Write instruction diffs

Prefer `append` for channel behavior because it keeps the base readable and the
delta small:

```yaml
instructionDiffs:
  - agent: Order_Agent
    mode: append
    content: |
      <channel_voice>
      Keep each spoken turn to two or three short sentences.
      Never use Markdown or symbols.
      </channel_voice>
```

Use `replace_section` only when the base already has a stable XML section:

```yaml
instructionDiffs:
  - agent: Reservation_Agent
    mode: replace_section
    sectionTag: channel_behavior
    content: |
      Offer at most three available times at once, spoken aloud.
```

Channel-specific guidance:

- **chat**: Markdown, numbered lists, visual confirmations, richer UI helper
  tools, short paragraphs
- **voice**: short spoken turns, no Markdown or symbols, read numbers aloud,
  pacing hints, tool-call filler phrases, tighter confirmations

If most sections want `replace_section`, recommend separate agents.

### 4. Add tool modifications and channel-only tools

`tools.add` may reference:

- A tool already present under `tools/`
- A channel-only tool declared in the same card's `toolDefinitions`
- Supported platform tools currently allowed by validators: `end_session`,
  `customize_response`

Example:

```yaml
tools:
  - agent: Order_Agent
    add:
      - send_order_card

toolDefinitions:
  - displayName: send_order_card
    toolType: python
    sourceDir: adapters/chat_tools/send_order_card
```

For Python channel-only tools, the source directory must include the tool JSON
and the referenced code. The compiler normalizes the code to
`tools/<displayName>/python_function/python_code.py` in the compiled output.

For OpenAPI tools, use `toolType: openapi`; the engine copies the source
folder verbatim.

### 5. Add callbacks when the channel needs runtime hints

Supported callback types:

- `before_model`
- `after_model`
- `before_tool`
- `after_tool`
- `before_agent`
- `after_agent`

Example:

```yaml
callbacks:
  - agent: Bella_Notte_Host
    type: before_model
    pythonCode: adapters/voice_callbacks/voice_pacing.py
    description: Inject voice pacing hints.
```

Callback paths are relative to the app root. The compiler appends the callback
after existing callbacks of that type and writes it into the agent's standard
callback directory in compiled output.

### 6. Add channel evals

Every behavior-changing adapter should usually add channel eval coverage:

```yaml
evaluations:
  - sourceDir: adapters/voice_evals
```

The same source-dir structure also applies to `evaluationExpectations` and
`evaluationDatasets`. If `evaluations` is missing, validation reports `AD006`
warning.

### 7. Set deployment values

Chat example:

```yaml
deployment:
  channelType: WEB_UI
  modality: CHAT_ONLY
  webWidgetConfig:
    theme: LIGHT
    webWidgetTitle: Polymorphic Pizza
```

Voice example:

```yaml
deployment:
  channelType: GOOGLE_TELEPHONY_PLATFORM
  modality: VOICE_ONLY
  disableBargeInControl: false
  disableDtmf: false
```

Supported values to keep handy:

- `deployment.channelType`: `WEB_UI`, `API`, `TWILIO`,
  `GOOGLE_TELEPHONY_PLATFORM`, `CONTACT_CENTER_AS_A_SERVICE`, `FIVE9`,
  `CONTACT_CENTER_INTEGRATION`
- `deployment.modality` and `webWidgetConfig.modality`: `CHAT_AND_VOICE`,
  `VOICE_ONLY`, `CHAT_ONLY`, `CHAT_VOICE_AND_VIDEO`
- `webWidgetConfig.theme`: `LIGHT`, `DARK`

The compiler stores the resolved deployment block in compiled
`gecx-config.json`; it does not write a separate deployment file.

## Authoring Checklist

- Base instructions describe the shared job, not a specific screen or phone
  channel
- Adapter deltas are small and organized by channel intent
- Every referenced agent and tool matches an actual display name or directory
- Channel-only tool source dirs and callback files exist under the app root
- Each adapter has channel evals or an explicit reason to accept `AD006`
- Deployment values come from the supported enum lists
- Output directories for builds live outside the source app directory

## Verify Before Hand-Off

```bash
uv run cxas poly validate --app-dir <app_dir>
uv run cxas poly diff <channel> --app-dir <app_dir>
uv run cxas poly build --app-dir <app_dir> --output-dir <output_dir>
uv run cxas lint --app-dir <output_dir>/<channel>
```

Starter templates worth copying from:

- `examples/polymorphic_pizza/adapters/chat.adapter.yaml`
- `examples/polymorphic_pizza/adapters/voice.adapter.yaml`
- `examples/bella_notte/adapters/chat.adapter.yaml`
- `examples/bella_notte/adapters/voice.adapter.yaml`
