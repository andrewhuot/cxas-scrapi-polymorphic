# Polymorphism Hardening — Design

**Date:** 2026-05-22
**Baseline:** `origin/main` @ `805cbe4` ("feat(poly): add first-wave developer experience")
**Status:** Approved (Sections 1 & 2)

## Context

The CXAS SCRAPI polymorphism feature compiles one channel-neutral base agent
project plus declarative channel adapter cards into N complete, channel-specific
output projects (build-time only; no polymorphic runtime). It is the V1
validation vehicle for the Polymorphic Agent Architecture product proposal.

A review of the work against the proposal found the implementation solid — the
Polymorphic Pizza demo works end to end, 85 poly tests pass — with a small set
of gaps between current behavior and the proposal's claims. Main's `805cbe4`
commit independently closed the largest one (CLI was untested) by shipping
`cxas poly init` / `doctor` / `diff --json` plus `test_poly_cli.py`. The engine,
validators, instruction helpers, and `AdapterCard` model are otherwise unchanged.

This spec covers the remaining work, scoped to "correctness + light vision":
make the proposal's "two ready-to-deploy projects" and "auditable derivation"
claims literally true, plus two small test/cleanup items.

## Goals

1. Compiled channels must have distinct app identities so both can deploy
   without colliding (the proposal's "ready-to-deploy" claim).
2. The compiled output must carry enough provenance to audit how it was derived
   (the proposal's "derivation rather than duplication" claim).
3. Close the AD004 lint-rule test parity gap.
4. Remove misleading config artifacts from the flagship demo.

## Non-goals

- No new v2 schema fields the proposal defers to design-partner feedback
  (guardrail overrides, channel variables, per-channel sub-agent routing,
  LLM-assisted instruction diffing). The proposal intentionally ships a minimal
  schema first.
- No changes to the engine's compile pipeline ordering, validation contract, or
  the "output is just a project" property.
- No `AgentCard` object. The "Canonical Agent Card" remains the base project
  itself; this is a deliberate MVP framing, not a gap to close here.

---

## Section 1 — Per-channel app identity

### Problem

`engine.compile()` copies `app.json` verbatim into every channel
(`engine.py:506`, `app_config=copy.deepcopy(self.base.app_json)`). Both `name`
(a resource UUID) and `displayName` are identical across channels. On deploy,
`cxas app push` (`cli/app.py` `_app_push`) keys app identity on `displayName` —
the `name` UUID is reassigned by the platform on import. So two channels both
named "Polymorphic Pizza" create two indistinguishable apps in the console, or
import over each other. There is no adapter field to override app identity.

### Design

**Model** (`src/cxas_scrapi/poly/models.py`): new optional block on
`AdapterCard`.

```python
class AppIdentity(BaseModel):
    model_config = _MODEL_CONFIG  # extra="forbid", camelCase aliases
    display_name: Optional[str] = Field(default=None, alias="displayName")
    name: Optional[str] = None

class AdapterCard(BaseModel):
    ...
    app_identity: Optional[AppIdentity] = Field(
        default=None, alias="appIdentity"
    )
```

Adapter card usage (optional — the demo will not need it):

```yaml
appIdentity:
  displayName: "Polymorphic Pizza — Chat"   # optional explicit override
  name: "f6e9..."                            # optional explicit UUID
```

**Compile** (`engine.compile()`, immediately after the `app_config` deep-copy
in the `CompiledAgentConfig` construction path): resolve identity into the
copied `app_config` dict before returning.

- `displayName`:
  - if `app_identity.display_name` set → use it;
  - else → auto-derive from `adapter.metadata.display_name` (already authored in
    every card, e.g. "Polymorphic Pizza — Chat").
- `name`:
  - if `app_identity.name` set → use it;
  - else → `str(uuid.uuid5(uuid.NAMESPACE_URL, f"{base_name}:{channel}"))`,
    where `base_name` is the base `app.json["displayName"]` (falling back to the
    app dir name). This mirrors the house pattern already established for
    per-channel tool IDs at `scaffold.py:463`. Deterministic: same base+channel
    always yields the same id, so rebuilds never churn it and redeploys stay
    idempotent.

Implement as a small private helper `_resolve_app_identity(app_config, adapter,
channel)` that mutates the copied dict, keeping `compile()` readable.

**Validation** — new rule **AD011** (`validators.py`):

- If `app_identity.name` is set, it must parse as a valid UUID
  (`uuid.UUID(value)` does not raise). Otherwise emit AD011 ERROR.
- `app_identity.display_name`, if set, must be non-empty after strip; empty →
  AD011 ERROR.
- Wire into `validate_adapter_card` (single-card pass).
- Add to the lint-rule registry under `utils/lint_rules/adapters.py` as a new
  `Adapter*` rule class for parity with AD001–AD010.
- Add an `AD011` `RuleGuide(what, why, fix)` entry to `RULE_GUIDES` in
  `diagnostics.py` so `cxas poly doctor` produces a "likely fix" hint,
  consistent with main's new diagnostics pattern.
- Add `AD011` to the rule list documented in
  `.agents/skills/cxas-polymorphic-adapters/SKILL.md` and its
  `references/debug-adapter.md`.

### Why this shape

Optional field + safe auto-default means the common case is correct out of the
box (the demo auto-derives distinct names with zero card edits) while authors
retain explicit control. Auto-deriving `displayName` from the card's existing
`metadata.displayName` reuses data authors already write. Deterministic uuid5
preserves the "recompile to propagate, idempotent redeploy" workflow the
proposal centers on, and matches existing code so the package stays coherent.

---

## Section 2 — Provenance in the build marker

### Problem

The proposal frames compiled output as an *auditable derivation* of the
canonical source ("consistency guarantees that come from derivation rather than
duplication"). Today the only build record is `.poly_build.json`
(`engine.py:673`), holding just `{channel, source, generated_at}` — not enough
to answer "which adapter, at what revision, produced this, with what deltas?"

### Design

Enrich the marker written in `write_output`. It stays a dotfile (not copied into
a subsequent build's source, never linted, never deployed), so this adds zero
new surface and does not mutate the deploy artifact.

New marker shape:

```json
{
  "channel": "chat",
  "source": "/abs/path/to/base",
  "generated_at": "2026-05-22T...Z",
  "engine_version": "1.2.0",
  "adapter_card": "adapters/chat.adapter.yaml",
  "adapter_sha256": "…",
  "base_agents": ["Order_Agent", "Pizza_Host", "Tracking_Agent"],
  "applied_deltas": {
    "instruction_diffs": 2,
    "tools_added": 1,
    "tools_removed": 0,
    "tool_definitions": 1,
    "model_overrides": 1,
    "callbacks": 1,
    "evaluations": 1,
    "deployment": true
  }
}
```

**Implementation details:**

- `engine_version`: read the installed package version
  (`importlib.metadata.version("cxas-scrapi")`), guarded with a fallback to
  `"unknown"` so it never raises in odd environments.
- `adapter_card`: project-relative path of the source card. `compile()` already
  receives `card_path`; thread it (or the channel→path map) into `write_output`.
  Since `write_output` takes only the `CompiledAgentConfig` today, carry the
  needed provenance fields **on `CompiledAgentConfig`** (a `provenance: Dict`
  populated in `compile()`), keeping `write_output`'s signature stable and the
  config self-describing — consistent with the existing "hold compiled state as
  a model" design.
- `adapter_sha256`: SHA-256 of the raw adapter card file bytes.
- `base_agents`: sorted base agent dir names.
- `applied_deltas`: counts derived from the adapter card's lists (and
  `bool(adapter.deployment)`), computed in `compile()`.

### Why this shape

Enriching the existing marker (vs. a new committed `provenance.json` or stamping
`app.json`) keeps the deploy artifact byte-clean and avoids any risk that the
platform rejects unknown keys — while making the derivation fully auditable from
a single file already present in every channel output.

---

## Section 3 — AD004 lint-rule test parity

Every adapter rule AD001–AD010 has a dedicated lint-rule `.check()` test in
`tests/cxas_scrapi/poly/test_adapter_lint_rules.py` **except** AD004
(remove-unknown-tool), which appears there only in the registry-membership
assertion (line 170). Add a dedicated `AdapterRemoveUnknownTool().check()` test
that constructs an adapter removing a tool the base agent does not have and
asserts a single AD004 warning. (Plus an AD011 `.check()` test from Section 1.)

---

## Section 4 — Demo config cleanup

`examples/polymorphic_pizza/gecx-config.json` has two misleading
copy-paste artifacts (both overwritten by compile, so harmless at runtime but
confusing in the flagship example):

- `"default_channel": "text"` — `text` is a modality, not a channel. Compile
  overwrites it to the channel name. Set the base to a neutral, accurate value.
- `"app_dir": "cxas_app/Polymorphic_Pizza/"` — a nested-layout path that does
  not match the actual flat demo layout. Compile rewrites `app_dir` to `"."`.
  Correct it to `"."` so the base file is self-consistent.

This is a documentation-quality fix on the example most users copy from; no
engine behavior changes.

---

## Testing strategy

New/updated tests (all under `tests/cxas_scrapi/poly/`):

- **App identity** (`test_engine.py`): auto-derived `displayName` and `name`
  differ across two channels; uuid5 is deterministic across two compiles of the
  same channel; explicit `appIdentity` overrides win.
- **AD011** (`test_validators.py` + `test_adapter_lint_rules.py`): bad UUID →
  AD011 error; empty displayName → AD011 error; valid override → clean.
- **Provenance** (`test_hardening.py`): after `write_output`, the marker
  contains `engine_version`, `adapter_card`, `adapter_sha256`, sorted
  `base_agents`, and correct `applied_deltas` counts.
- **AD004** (`test_adapter_lint_rules.py`): dedicated `.check()` test.
- **Demo E2E** (manual + existing round-trip tests): rebuild
  `examples/polymorphic_pizza`, lint both channels, confirm chat/voice now carry
  distinct `displayName` and `name` in their compiled `app.json` and enriched
  markers.

Success criteria: full poly suite green (≥ existing 85 + new), demo's two
channels are independently deployable (distinct identity), each channel marker
is self-describing.

## Risks / edge cases

- **Base app.json missing `displayName`**: fall back to the app dir name for the
  uuid5 seed and for the derived display name suffix. Covered by a test.
- **Adapter `metadata.displayName` already channel-specific** (it is, in the
  demo): used directly — no double-suffixing. The auto-derive uses
  `metadata.displayName` as-is, it does not append the channel again.
- **uuid5 namespace choice**: `NAMESPACE_URL` to match `scaffold.py`; documented
  in the marker via `name` so it is inspectable.
