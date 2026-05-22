# PLAN.md

## Goal
Implement the first wave of polymorphic-agent developer experience improvements:
`cxas poly init` scaffolding, guided validation diagnostics via `doctor` and
`validate --explain`, and stable `cxas poly diff --json` output with clearer
human review output.

## Context
- Current branch/worktree: `feat/poly-first-wave-codex` in
  `/Users/andrew/Desktop/cxas-scrapi-polymorphic-codex-first-wave`.
- Base behavior is build-time polymorphism only: base project plus
  `adapters/*.adapter.yaml` compiles to ordinary SCRAPI projects.
- Core implementation:
  - `src/cxas_scrapi/cli/poly_cli.py`
  - `src/cxas_scrapi/poly/models.py`
  - `src/cxas_scrapi/poly/engine.py`
  - `src/cxas_scrapi/poly/validators.py`
  - `src/cxas_scrapi/utils/lint_rules/adapters.py`
- Existing docs and examples:
  - `README.md`
  - `docs/cli/poly.md`
  - `docs/guides/polymorphism.md`
  - `docs/patterns/polymorphism.md`
  - `examples/polymorphic_pizza/**`
  - `examples/bella_notte/**`
- Existing tests:
  - `tests/cxas_scrapi/poly/test_models.py`
  - `tests/cxas_scrapi/poly/test_validators.py`
  - `tests/cxas_scrapi/poly/test_engine.py`
  - `tests/cxas_scrapi/poly/test_hardening.py`
  - `tests/cxas_scrapi/poly/test_adapter_lint_rules.py`

## Constraints
- Do not fetch, pull, or push.
- Preserve existing `cxas poly build`, `validate`, `diff`, and adapter-rule
  behavior unless extending it intentionally.
- Do not invent runtime polymorphism or unsupported adapter-card fields.
- Keep emitted scaffolded paths valid under current validators and compiler.
- Prefer shared helpers and explicit data shapes over CLI-only string handling.
- Avoid unrelated churn and generated output in the repo.

## Milestones

### Milestone 1 - Understand And Plan
Read the requested docs/examples/source, refresh prior polymorphism memory, and
replace this plan with the first-wave implementation checklist.

### Milestone 2 - Shared DX Helpers
Add reusable helper modules for scaffold planning/writing, validation
explanations, and diff report generation. Keep business validation in
`validators.py` and compilation in `engine.py`.

### Milestone 3 - CLI Surface
Wire helpers into:
- `cxas poly init` with non-interactive flags and prompt fallback.
- `cxas poly doctor` and `cxas poly validate --explain`.
- `cxas poly diff --json` plus improved text rendering.

### Milestone 4 - Tests, Docs, Examples
Add targeted tests for scaffold output, doctor/explain output, and diff JSON.
Update CLI docs, guide/pattern docs, README, and example walkthroughs where the
new commands materially improve the workflow.

### Milestone 5 - Verification And Cleanup
Run targeted tests and real example commands, check formatting/diff cleanliness,
and optionally commit the intended changes with a conventional commit.

## Verification Commands
Run from the repo root.

```bash
git diff --check
uv run --with-editable . --with alive-progress pytest tests/cxas_scrapi/poly -q
uv run --with-editable . --with alive-progress cxas poly init --app-dir /tmp/poly-init-smoke --channel chat --deployment-target WEB_UI --modality CHAT_ONLY --with-tool send_channel_card --with-callback before_model --force
uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte
uv run --with-editable . --with alive-progress cxas poly doctor --app-dir examples/bella_notte
uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte --json
uv run --with-editable . --with alive-progress cxas poly build --app-dir examples/bella_notte --output-dir /tmp/poly_first_wave_build
uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_first_wave_build/chat
uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_first_wave_build/voice
```

For the `init` smoke, first create `/tmp/poly-init-smoke` from the committed
test fixture or another direct app project before running the command.

## Acceptance Criteria
- A developer can scaffold one or more adapter cards plus referenced starter
  eval/tool/callback files from an existing direct SCRAPI app.
- Scaffolded adapter cards use only fields supported by current
  `AdapterCard` models and validate under current rules.
- Validation diagnostics explain what failed, why, where to look, and a likely
  fix shape without forking validator business logic.
- `cxas poly diff --json` emits a stable, machine-readable v1 report for CI and
  tools, while text diff remains readable for humans.
- Docs and examples describe the new first-wave workflow accurately.
- The full `tests/cxas_scrapi/poly` suite and real example validation/build/lint
  checks pass.

## Progress
- [x] Milestone 1 complete
- [x] Milestone 2 complete
- [x] Milestone 3 complete
- [x] Milestone 4 complete
- [x] Milestone 5 complete

## Decision Log
- 2026-05-22 00:23 - Keep polymorphism strictly build-time and expose new DX
  through local CLI/helper modules only; no runtime behavior or deploy behavior
  changes are in scope.
- 2026-05-22 00:23 - Add `doctor` as the clearer guided-debug command while
  also supporting `validate --explain` for users who naturally start from
  validation.
- 2026-05-22 00:23 - Put stable diff data behind a shared report builder, then
  render both text and JSON from that report so CI and humans see the same
  underlying deltas.
- 2026-05-22 01:05 - Keep `cxas poly init` scaffold defaults conservative:
  known chat/web/voice/telephony/api channels get deployment defaults, unknown
  channel ids stay valid but do not invent deployment fields.
- 2026-05-22 01:05 - Reverted unrelated `uv.lock` churn from `uv run`; the
  first-wave implementation does not need dependency changes.

## Notes / Blockers
- Verification completed:
  - `git diff --check`
  - `uv run --with-editable . --with alive-progress ruff check src/cxas_scrapi/poly src/cxas_scrapi/cli/poly_cli.py tests/cxas_scrapi/poly`
  - `uv run --with-editable . --with alive-progress pytest tests/cxas_scrapi/poly -q` (85 passed, 1 existing pytest config warning)
  - `uv run --with-editable . --with alive-progress cxas poly init --app-dir /tmp/cxas_poly_init_smoke_codex --channel sms --deployment-target TWILIO --modality VOICE_ONLY --with-tool send_sms_card --with-callback before_model`
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir /tmp/cxas_poly_init_smoke_codex` (0 errors, 1 pre-existing fixture warning from the original voice adapter)
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte`
  - `uv run --with-editable . --with alive-progress cxas poly doctor --app-dir examples/bella_notte`
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte --explain`
  - `uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte`
  - `uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte --json`
  - `uv run --with-editable . --with alive-progress cxas poly build --app-dir examples/bella_notte --output-dir /tmp/poly_first_wave_build`
  - `uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_first_wave_build/chat`
  - `uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_first_wave_build/voice`
- No blockers.
