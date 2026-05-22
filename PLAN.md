# PLAN.md

## Goal
Review the polymorphism implementation holistically, polish code and
documentation, and leave the feature ready to share.

## Context
- Current workspace: `/Users/andrew/.codex/worktrees/1030/cxas-scrapi-polymorphic`
- Current git state: detached `HEAD` worktree; do not fetch, pull, push, or
  deploy.
- Polymorphism is build-time only. The maintained source is a direct SCRAPI app
  plus `adapters/*.adapter.yaml`; compiled channel outputs are generated
  artifacts.
- Core implementation:
  - `src/cxas_scrapi/poly/models.py`
  - `src/cxas_scrapi/poly/validators.py`
  - `src/cxas_scrapi/poly/engine.py`
  - `src/cxas_scrapi/poly/instructions.py`
  - `src/cxas_scrapi/poly/scaffold.py`
  - `src/cxas_scrapi/poly/diagnostics.py`
  - `src/cxas_scrapi/poly/diffing.py`
  - `src/cxas_scrapi/cli/poly_cli.py`
  - `src/cxas_scrapi/utils/lint_rules/adapters.py`
- Docs and examples to audit:
  - `README.md`
  - `docs/guides/polymorphism.md`
  - `docs/guides/polymorphism-5-minute-tutorial.md`
  - `docs/patterns/polymorphism.md`
  - `docs/cli/poly.md`
  - `examples/polymorphic_pizza/**`
  - `examples/bella_notte/**`
  - `.agents/skills/cxas-polymorphic-adapters/SKILL.md`
- Existing polymorphism tests:
  - `tests/cxas_scrapi/poly/test_models.py`
  - `tests/cxas_scrapi/poly/test_validators.py`
  - `tests/cxas_scrapi/poly/test_engine.py`
  - `tests/cxas_scrapi/poly/test_hardening.py`
  - `tests/cxas_scrapi/poly/test_adapter_lint_rules.py`
  - `tests/cxas_scrapi/poly/test_scaffold.py`
  - `tests/cxas_scrapi/poly/test_diagnostics.py`
  - `tests/cxas_scrapi/poly/test_diffing.py`
  - `tests/cxas_scrapi/poly/test_poly_cli.py`

## Constraints
- Preserve current public behavior unless a review finding justifies a change.
- Do not invent adapter fields, runtime polymorphism, channels, tool types, or
  deployment enum values unsupported by the current schema.
- Behavior changes require tests that fail first, then minimal implementation.
- Documentation-only polish may be edited directly, but must stay aligned with
  current code and examples.
- Keep changes small, local, and reviewable. Avoid unrelated refactors or
  generated-output churn.
- Do not hand-edit compiled output directories; rebuild from source adapters.

## Milestones

### Milestone 1 — Understand And De-Risk
Read the polymorphism code, CLI, linter bridge, docs, examples, and tests.
Identify correctness, security, maintainability, documentation, and shareability
gaps before editing implementation files.

### Milestone 2 — Baseline Verification
Run targeted tests and real example commands to distinguish existing failures
from review findings:
- `git diff --check`
- `uv run --with-editable . --with alive-progress pytest tests/cxas_scrapi/poly -q`
- `uv run --with-editable . --with alive-progress ruff check src/cxas_scrapi/poly src/cxas_scrapi/cli/poly_cli.py tests/cxas_scrapi/poly`
- `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/polymorphic_pizza`
- `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte`
- `uv run --with-editable . --with alive-progress cxas poly doctor --app-dir examples/bella_notte`
- `uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte --json`
- `uv run --with-editable . --with alive-progress cxas poly build --app-dir examples/bella_notte --output-dir /tmp/poly_readiness_build`
- `uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_readiness_build/chat`
- `uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_readiness_build/voice`

### Milestone 3 — Polish Implementation
For each confirmed implementation issue, write a focused failing test first,
verify the failure, implement the minimal fix, and rerun the relevant tests.
Likely focus areas are path safety, validation consistency, CLI error handling,
diff stability, scaffold output, and linter parity.

### Milestone 4 — Polish Documentation And Examples
Tighten docs/examples/skill guidance so a new developer can understand the
build-time model, author an adapter, validate/debug it, inspect diffs, build
outputs, and lint compiled projects without relying on hidden context.

### Milestone 5 — Final Verification And Readiness Summary
Run the verification commands, inspect the final diff, update this plan with
completed work and any remaining risks, and summarize whether the feature is
ready to share.

## Verification Commands
Run from the repo root.

```bash
git diff --check
uv run --with-editable . --with alive-progress ruff check src/cxas_scrapi/poly src/cxas_scrapi/cli/poly_cli.py tests/cxas_scrapi/poly
uv run --with-editable . --with alive-progress pytest tests/cxas_scrapi/poly -q
uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/polymorphic_pizza
uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte
uv run --with-editable . --with alive-progress cxas poly doctor --app-dir examples/bella_notte
uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte --explain
uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte
uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte --json
rm -rf /tmp/poly_readiness_build
uv run --with-editable . --with alive-progress cxas poly build --app-dir examples/bella_notte --output-dir /tmp/poly_readiness_build
uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_readiness_build/chat
uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_readiness_build/voice
```

## Acceptance Criteria
- Review findings are either fixed, explicitly documented as accepted residual
  risk, or proven not to be issues.
- Adapter validation remains the shared source of truth for `cxas poly
  validate`, `cxas poly build`, and the `adapters` lint category.
- `cxas poly init`, `doctor`, `validate --explain`, `diff --json`, and `build`
  behave predictably on the shipped examples.
- Docs and examples match the implemented schema and command behavior.
- Targeted polymorphism tests, lint checks, real example validation, diff,
  build, and compiled-output lint commands pass.

## Progress
- [x] Milestone 1 plan refreshed
- [x] Milestone 1 review complete
- [x] Milestone 2 baseline verification complete
- [x] Milestone 3 implementation polish complete
- [x] Milestone 4 docs/examples polish complete
- [x] Milestone 5 final verification complete

## Decision Log
- 2026-05-22 03:15 — Treat this pass as a readiness review, not a feature
  expansion. The bar is correctness, consistency, docs clarity, and example
  health.
- 2026-05-22 03:15 — Keep adapter validation as the source of truth. Any CLI or
  linter polish should reuse validator behavior rather than forking rules.
- 2026-05-22 03:35 — Reject absolute adapter `sourceDir`/`pythonCode` paths even
  when they point inside the current app root. Adapter cards should be portable
  project-relative source, not machine-local manifests.
- 2026-05-22 03:35 — Make `cxas poly init --with-callback` generate hook-specific
  typed callback stubs for all supported callback hooks, matching the callback
  linter contract from the first scaffolded file.

## Notes / Blockers
- Review findings fixed:
  - `cxas poly init --with-callback` now generates the correct entry function,
    argument list, and return annotation for each supported callback hook.
  - Adapter validation now reports `AD008` for absolute paths as well as `..`
    escapes, keeping adapter cards project-relative and portable.
  - Docs, examples, and the repo-local polymorphism skill now describe those
    contracts consistently.
- Verification completed:
  - `git diff --check`
  - `uv run --with-editable . --with alive-progress ruff check src/cxas_scrapi/poly src/cxas_scrapi/cli/poly_cli.py tests/cxas_scrapi/poly`
  - `uv run --with-editable . --with alive-progress pytest tests/cxas_scrapi/poly -q` (87 passed, 1 existing pytest config warning)
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/polymorphic_pizza`
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte`
  - `uv run --with-editable . --with alive-progress cxas poly doctor --app-dir examples/bella_notte`
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir examples/bella_notte --explain`
  - `uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte`
  - `uv run --with-editable . --with alive-progress cxas poly diff chat --app-dir examples/bella_notte --json`
  - `uv run --with-editable . --with alive-progress cxas poly build --app-dir examples/bella_notte --output-dir /tmp/poly_readiness_build`
  - `uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_readiness_build/chat`
  - `uv run --with-editable . --with alive-progress cxas lint --app-dir /tmp/poly_readiness_build/voice`
  - `uv run --with-editable . --with alive-progress cxas poly init --app-dir /tmp/poly_init_callbacks_smoke --channel sms --deployment-target TWILIO --modality VOICE_ONLY --with-callback before_model --with-callback after_model --with-callback before_agent --with-callback after_agent --with-callback before_tool --with-callback after_tool`
  - `uv run --with-editable . --with alive-progress cxas poly validate --app-dir /tmp/poly_init_callbacks_smoke` (0 errors, 1 pre-existing fixture warning from the original voice adapter)
- No blockers.
