# PLAN.md

## Goal
Review and improve the polymorphic agent architecture so the Canonical Agent Card/root app, Channel Adapter Cards, Polymorphism Engine, and channel-specific runtime configs match the product proposal and the Polymorphic Pizza demo proves the end-to-end workflow.

## Context
- Product proposal: `/Users/andrew/Downloads/Polymorphic_Agent_Architecture_Product_Proposal.md`
- Recent polymorphism commits inspected with local timestamps from May 21, 2026:
  - `dad1236` / `a6e7d15` — initial Polymorphism Engine and Bella Notte adapters
  - `bcd017d` — Polymorphic Pizza chat + voice demo
  - `0264160` / `1d8252a` — production hardening pass
- Core implementation:
  - `src/cxas_scrapi/poly/models.py`
  - `src/cxas_scrapi/poly/engine.py`
  - `src/cxas_scrapi/poly/instructions.py`
  - `src/cxas_scrapi/poly/validators.py`
  - `src/cxas_scrapi/cli/poly_cli.py`
  - `src/cxas_scrapi/utils/lint_rules/adapters.py`
- Demo project:
  - `examples/polymorphic_pizza/app.json`
  - `examples/polymorphic_pizza/gecx-config.json`
  - `examples/polymorphic_pizza/adapters/chat.adapter.yaml`
  - `examples/polymorphic_pizza/adapters/voice.adapter.yaml`
  - `examples/polymorphic_pizza/agents/**`
  - `examples/polymorphic_pizza/tools/**`
  - `examples/polymorphic_pizza/evaluations/**`
- Existing tests:
  - `tests/cxas_scrapi/poly/test_engine.py`
  - `tests/cxas_scrapi/poly/test_models.py`
  - `tests/cxas_scrapi/poly/test_validators.py`
  - `tests/cxas_scrapi/poly/test_hardening.py`
  - `tests/cxas_scrapi/poly/test_adapter_lint_rules.py`

## Constraints
- Preserve existing `cxas poly` CLI behavior unless a change is required to fulfill the product architecture.
- Prefer small, additive, testable refactors.
- Do not edit unrelated files.
- Treat compiled channel output as a generated artifact, not a source of truth.
- Channel adapters must express deltas from the canonical app, not duplicate full agent definitions.
- Runtime configs must remain compatible with existing SCRAPI lint/build/deploy workflows.

## Milestones

### Milestone 1 — Understand and de-risk
Review the proposal, recent commits, current poly module, linter rules, docs, and Polymorphic Pizza assets. Identify gaps between the product vision and implementation. Verify current behavior with targeted tests and `cxas poly` commands.

### Milestone 2 — Implement architecture fixes
Make focused changes where the implementation currently falls short. Expected areas include deterministic runtime config merge behavior, adapter validation, root agent/app-card treatment, compiled output cleanliness, and demo adapters that visibly demonstrate channel-specific depth.

### Milestone 3 — Harden and verify
Add or update tests for every behavior change. Build and lint the Polymorphic Pizza chat and voice outputs. Update docs or demo instructions only when needed to match the verified workflow.

## Verification Commands
Run these from the repo root unless noted otherwise.

```bash
uv run pytest tests/cxas_scrapi/poly -q
uv run cxas poly validate --app-dir examples/polymorphic_pizza
uv run cxas poly diff chat --app-dir examples/polymorphic_pizza
uv run cxas poly diff voice --app-dir examples/polymorphic_pizza
uv run cxas poly build --app-dir examples/polymorphic_pizza --output-dir /tmp/polymorphic_pizza_build
uv run cxas lint --app-dir /tmp/polymorphic_pizza_build/chat
uv run cxas lint --app-dir /tmp/polymorphic_pizza_build/voice
```

## Acceptance Criteria
- The code review identifies concrete architecture/product-fit risks with file and line references.
- The final implementation keeps the canonical project as the source of truth and applies channel adapters as auditable deltas.
- Chat output contains chat-specific runtime config, tools, callbacks, instructions, and evals.
- Voice output contains voice-specific runtime config, callbacks, instructions, and evals without chat-only tools or formatting.
- The Polymorphic Pizza demo validates, builds, and produces lint-clean channel outputs.
- Targeted polymorphism tests pass.

## Progress
- [x] Milestone 1 started: proposal, recent commits, and demo README inspected.
- [x] Milestone 1 complete: identified duplicate-channel validation loss, unknown-field drift risk, and missing channel runtime config overlay.
- [x] Milestone 2 complete: implemented strict adapter models, preserved all adapter cards for cross-card validation, added `gecxConfig` deep merge, and updated the Pizza demo adapters.
- [x] Milestone 3 complete: added regression tests, updated docs, built the Pizza chat/voice outputs, and linted both compiled projects.

## Decision Log
- 2026-05-22 00:00 — Treat May 21 local commit timestamps as the polymorphism work "committed today" because the repo log shows all relevant polymorphism commits in that local evening window while the session date is May 22, 2026.
- 2026-05-22 00:00 — Use the Polymorphic Pizza example as the primary product validation target because the proposal says the example should be the main mechanism for communicating and validating the architecture.
- 2026-05-22 00:00 — Reject unknown adapter fields with Pydantic `extra="forbid"` so adapter deltas stay auditable and typo-safe.
- 2026-05-22 00:00 — Preserve the full ordered adapter-card list separately from the channel lookup map so duplicate channel adapters are validated instead of overwritten.
- 2026-05-22 00:00 — Add `gecxConfig` as a deep-merged adapter delta for channel-specific runtime defaults while keeping compiler-owned `default_channel`, `app_dir`, and deployment-derived modality deterministic.

## Notes / Blockers
- Verification used `/tmp/polymorphic_pizza_build_codex` as the generated output directory.
- No blockers.
