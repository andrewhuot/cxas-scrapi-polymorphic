# Polymorphism Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make compiled polymorphism channels independently deployable (distinct app identity) and auditable (enriched build provenance), plus close an AD004 test gap and clean up the demo config.

**Architecture:** Additive changes to the unchanged build-time engine. A new optional `appIdentity` adapter block (with safe auto-derived defaults) resolves per-channel `displayName`/`name` during `compile()`; provenance is carried on `CompiledAgentConfig` and written into the existing `.poly_build.json` marker. A new AD011 validator + lint rule + diagnostics guide follow the established AD0xx pattern.

**Tech Stack:** Python 3.10+, Pydantic v2, pytest, `uv`. All commands run from repo root.

---

## File structure

- `src/cxas_scrapi/poly/models.py` — add `AppIdentity` model + `app_identity` field on `AdapterCard`; add `provenance` field on `CompiledAgentConfig`.
- `src/cxas_scrapi/poly/engine.py` — resolve app identity in `compile()`; compute provenance in `compile()`; write provenance into the marker in `write_output()`.
- `src/cxas_scrapi/poly/validators.py` — AD011 checks in `validate_adapter_card`.
- `src/cxas_scrapi/poly/diagnostics.py` — AD011 `RuleGuide`.
- `src/cxas_scrapi/utils/lint_rules/adapters.py` — `AdapterAppIdentityValid` (AD011) rule class.
- `examples/polymorphic_pizza/gecx-config.json` — fix `default_channel`/`app_dir` artifacts.
- `.agents/skills/cxas-polymorphic-adapters/SKILL.md` + `references/debug-adapter.md` — document AD011.
- Tests: `test_models.py`, `test_engine.py`, `test_validators.py`, `test_adapter_lint_rules.py`, `test_hardening.py`.

---

## Task 1: AppIdentity model

**Files:**
- Modify: `src/cxas_scrapi/poly/models.py` (after `AdapterMetadata`, ~line 84; field on `AdapterCard` ~line 209)
- Test: `tests/cxas_scrapi/poly/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cxas_scrapi/poly/test_models.py`:

```python
def test_app_identity_parses_camelcase():
    from cxas_scrapi.poly.models import AdapterCard

    card = AdapterCard.model_validate(
        {
            "apiVersion": "poly.cxas.dev/v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "displayName": "X — Chat"},
            "appIdentity": {
                "displayName": "X — Chat",
                "name": "f6e9c2a1-0000-5000-8000-000000000000",
            },
        }
    )
    assert card.app_identity is not None
    assert card.app_identity.display_name == "X — Chat"
    assert card.app_identity.name == "f6e9c2a1-0000-5000-8000-000000000000"


def test_app_identity_rejects_unknown_field():
    import pytest
    from pydantic import ValidationError

    from cxas_scrapi.poly.models import AdapterCard

    with pytest.raises(ValidationError):
        AdapterCard.model_validate(
            {
                "apiVersion": "poly.cxas.dev/v1",
                "kind": "ChannelAdapter",
                "metadata": {"channel": "chat", "displayName": "X"},
                "appIdentity": {"bogus": 1},
            }
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cxas_scrapi/poly/test_models.py::test_app_identity_parses_camelcase -v`
Expected: FAIL (`card.app_identity` does not exist / extra field forbidden on AdapterCard).

- [ ] **Step 3: Add the model**

In `src/cxas_scrapi/poly/models.py`, add after the `AdapterMetadata` class:

```python
class AppIdentity(BaseModel):
    """Per-channel overrides for the compiled app's identity.

    Both fields are optional.  When absent, the engine auto-derives a
    distinct display name and a deterministic per-channel ``name`` so two
    channels never collide as the same deployed app.
    """

    model_config = _MODEL_CONFIG

    display_name: Optional[str] = Field(default=None, alias="displayName")
    name: Optional[str] = None
```

Then add this field to `AdapterCard` (next to `deployment`):

```python
    app_identity: Optional[AppIdentity] = Field(
        default=None, alias="appIdentity"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cxas_scrapi/poly/test_models.py -v`
Expected: PASS (both new tests + existing).

- [ ] **Step 5: Commit**

```bash
git add src/cxas_scrapi/poly/models.py tests/cxas_scrapi/poly/test_models.py
git commit -m "feat(poly): add optional appIdentity block to AdapterCard"
```

---

## Task 2: Resolve per-channel app identity in compile()

**Files:**
- Modify: `src/cxas_scrapi/poly/engine.py` (add `import uuid`; new helper; call in `compile()` before the `CompiledAgentConfig(...)` return ~line 507)
- Test: `tests/cxas_scrapi/poly/test_engine.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cxas_scrapi/poly/test_engine.py`:

```python
def test_app_identity_distinct_per_channel(polymorphic_pizza_dir):
    from cxas_scrapi.poly import PolymorphismEngine

    engine = PolymorphismEngine(str(polymorphic_pizza_dir))
    engine.load_base_project()
    compiled = engine.compile_all()

    chat_app = compiled["chat"].app_config
    voice_app = compiled["voice"].app_config

    # Display names differ and come from each adapter's metadata.
    assert chat_app["displayName"] != voice_app["displayName"]
    assert "Chat" in chat_app["displayName"]
    assert "Voice" in voice_app["displayName"]
    # name UUIDs differ across channels.
    assert chat_app["name"] != voice_app["name"]


def test_app_identity_name_is_deterministic(polymorphic_pizza_dir):
    from cxas_scrapi.poly import PolymorphismEngine

    def name_for(channel):
        engine = PolymorphismEngine(str(polymorphic_pizza_dir))
        engine.load_base_project()
        return engine.compile_all()[channel].app_config["name"]

    assert name_for("chat") == name_for("chat")


def test_app_identity_explicit_override_wins(copied_pizza_with_identity):
    # Fixture writes appIdentity into chat.adapter.yaml; see conftest note.
    from cxas_scrapi.poly import PolymorphismEngine

    engine = PolymorphismEngine(str(copied_pizza_with_identity))
    engine.load_base_project()
    compiled = engine.compile_all()
    assert compiled["chat"].app_config["displayName"] == "Override Chat Name"
```

For the override test, add this fixture to `tests/cxas_scrapi/poly/conftest.py`:

```python
@pytest.fixture
def copied_pizza_with_identity(tmp_path, polymorphic_pizza_dir):
    import shutil

    dst = tmp_path / "pizza"
    shutil.copytree(polymorphic_pizza_dir, dst)
    card = dst / "adapters" / "chat.adapter.yaml"
    text = card.read_text()
    text += (
        "\nappIdentity:\n"
        "  displayName: Override Chat Name\n"
    )
    card.write_text(text)
    return dst
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cxas_scrapi/poly/test_engine.py -k app_identity -v`
Expected: FAIL with `KeyError: 'displayName'` differences not present (both channels share the base `displayName`) / override ignored.

- [ ] **Step 3: Implement the helper + call it**

In `src/cxas_scrapi/poly/engine.py`, add `import uuid` to the imports (alongside `import copy`).

Add this method to `PolymorphismEngine` (near the other helpers, e.g. after `_build_deployment`):

```python
    @staticmethod
    def _resolve_app_identity(
        app_config: Dict[str, Any],
        adapter: AdapterCard,
        channel: str,
    ) -> None:
        """Give the compiled app a per-channel identity, in place.

        displayName comes from an explicit ``appIdentity.displayName`` or, by
        default, the adapter's ``metadata.displayName`` so two channels are
        never indistinguishable as the same deployed app.  name comes from an
        explicit ``appIdentity.name`` or a deterministic uuid5 of the base
        name plus channel (matching the per-channel id pattern used by
        ``poly init`` scaffolding).
        """
        identity = adapter.app_identity
        base_name = str(
            app_config.get("displayName") or adapter.metadata.display_name
        )

        display = None
        if identity is not None and identity.display_name:
            display = identity.display_name
        elif adapter.metadata.display_name:
            display = adapter.metadata.display_name
        if display:
            app_config["displayName"] = display

        if identity is not None and identity.name:
            app_config["name"] = identity.name
        else:
            app_config["name"] = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{base_name}:{channel}")
            )
```

Then in `compile()`, just before constructing the returned `CompiledAgentConfig`, resolve identity on the copied app config. Replace the existing `app_config=copy.deepcopy(self.base.app_json),` argument with a pre-built local:

Change the return block from:

```python
        return CompiledAgentConfig(
            channel=channel,
            app_config=copy.deepcopy(self.base.app_json),
```

to:

```python
        app_config = copy.deepcopy(self.base.app_json)
        self._resolve_app_identity(app_config, adapter, channel)

        return CompiledAgentConfig(
            channel=channel,
            app_config=app_config,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cxas_scrapi/poly/test_engine.py -k app_identity -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/cxas_scrapi/poly/engine.py tests/cxas_scrapi/poly/test_engine.py tests/cxas_scrapi/poly/conftest.py
git commit -m "feat(poly): give each compiled channel a distinct app identity"
```

---

## Task 3: AD011 validator

**Files:**
- Modify: `src/cxas_scrapi/poly/validators.py` (add AD011 block inside `validate_adapter_card`, before the final AD006 block ~line 398; update module docstring ~line 38)
- Test: `tests/cxas_scrapi/poly/test_validators.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cxas_scrapi/poly/test_validators.py`:

```python
def test_ad011_bad_uuid_name(copied_base):
    from cxas_scrapi.poly.models import AdapterCard
    from cxas_scrapi.poly.validators import validate_adapter_card

    card = AdapterCard.model_validate(
        {
            "apiVersion": "poly.cxas.dev/v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "displayName": "X"},
            "appIdentity": {"name": "not-a-uuid"},
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    issues = validate_adapter_card(card, str(copied_base))
    assert any(i["rule_id"] == "AD011" for i in issues)


def test_ad011_empty_display_name(copied_base):
    from cxas_scrapi.poly.models import AdapterCard
    from cxas_scrapi.poly.validators import validate_adapter_card

    card = AdapterCard.model_validate(
        {
            "apiVersion": "poly.cxas.dev/v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "displayName": "X"},
            "appIdentity": {"displayName": "   "},
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    issues = validate_adapter_card(card, str(copied_base))
    assert any(i["rule_id"] == "AD011" for i in issues)


def test_ad011_valid_identity_clean(copied_base):
    from cxas_scrapi.poly.models import AdapterCard
    from cxas_scrapi.poly.validators import validate_adapter_card

    card = AdapterCard.model_validate(
        {
            "apiVersion": "poly.cxas.dev/v1",
            "kind": "ChannelAdapter",
            "metadata": {"channel": "chat", "displayName": "X"},
            "appIdentity": {
                "displayName": "X — Chat",
                "name": "f6e9c2a1-0000-5000-8000-000000000000",
            },
            "evaluations": [{"sourceDir": "adapters/chat_evals"}],
        }
    )
    issues = validate_adapter_card(card, str(copied_base))
    assert not any(i["rule_id"] == "AD011" for i in issues)
```

> Note: the `copied_base` fixture's project must have `adapters/chat_evals`; if it does not, drop the `evaluations` key and ignore the unrelated AD006 warning in the assertions (they already filter on AD011 only).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cxas_scrapi/poly/test_validators.py -k ad011 -v`
Expected: FAIL (no AD011 issue emitted).

- [ ] **Step 3: Implement AD011**

In `src/cxas_scrapi/poly/validators.py`, add `import uuid` at the top. Inside `validate_adapter_card`, add before the `# AD006` block near the end:

```python
    # AD011 — appIdentity is well-formed when present.
    ident = adapter.app_identity
    if ident is not None:
        if ident.display_name is not None and not ident.display_name.strip():
            add(
                "AD011",
                ERROR,
                "appIdentity.displayName must be non-empty when set.",
            )
        if ident.name is not None:
            try:
                uuid.UUID(str(ident.name))
            except (ValueError, AttributeError, TypeError):
                add(
                    "AD011",
                    ERROR,
                    f"appIdentity.name '{ident.name}' is not a valid UUID.",
                )
```

Update the module docstring rule list (after the `AD010` line ~line 38) to add:

```
    AD011  appIdentity is well-formed (name is a valid UUID; displayName non-empty)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cxas_scrapi/poly/test_validators.py -k ad011 -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/cxas_scrapi/poly/validators.py tests/cxas_scrapi/poly/test_validators.py
git commit -m "feat(poly): add AD011 validation for appIdentity"
```

---

## Task 4: AD011 lint rule + diagnostics guide + AD004 test

**Files:**
- Modify: `src/cxas_scrapi/utils/lint_rules/adapters.py` (add `AdapterAppIdentityValid` after `AdapterToolType` ~line 241)
- Modify: `src/cxas_scrapi/poly/diagnostics.py` (add AD011 to `RULE_GUIDES` after AD010 ~line 211)
- Test: `tests/cxas_scrapi/poly/test_adapter_lint_rules.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/cxas_scrapi/poly/test_adapter_lint_rules.py`. First update the import block to include the two new/used classes:

```python
from cxas_scrapi.utils.lint_rules.adapters import (
    AdapterAddUndefinedTool,
    AdapterAgentRefsExist,
    AdapterAppIdentityValid,
    AdapterDeploymentValues,
    AdapterDuplicateChannel,
    AdapterHasEvaluations,
    AdapterPathInScope,
    AdapterRemoveUnknownTool,
    AdapterReplaceSectionExists,
    AdapterSchemaValid,
    AdapterToolType,
)
```

Then add the tests:

```python
def test_ad004_remove_unknown_tool_warns(ctx, copied_base):
    f = _adapter(copied_base, "rm.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: rm, displayName: RM}\n"
        "tools:\n"
        "  - {agent: Test_Agent, remove: [ghost_tool]}\n"
    )
    results = AdapterRemoveUnknownTool().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD004" for r in results)


def test_ad011_bad_uuid_reported(ctx, copied_base):
    f = _adapter(copied_base, "id.adapter.yaml")
    f.write_text(
        "apiVersion: v1\n"
        "kind: ChannelAdapter\n"
        "metadata: {channel: id, displayName: ID}\n"
        "appIdentity: {name: not-a-uuid}\n"
    )
    results = AdapterAppIdentityValid().check(f, f.read_text(), ctx)
    assert any(r.rule_id == "AD011" for r in results)
```

Also extend the registry test set in `test_rules_autoregister_in_registry` to include `"AD011"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cxas_scrapi/poly/test_adapter_lint_rules.py -k "ad004 or ad011 or autoregister" -v`
Expected: FAIL — `AdapterAppIdentityValid` import error (AD004 test should pass already since the class exists; if `Test_Agent` lacks `ghost_tool` it asserts the warning).

- [ ] **Step 3: Implement the lint rule + diagnostics guide**

In `src/cxas_scrapi/utils/lint_rules/adapters.py`, add after `AdapterToolType`:

```python
@rule("adapters")
class AdapterAppIdentityValid(_AdapterRule):
    id = "AD011"
    name = "adapter-app-identity-valid"
    description = (
        "appIdentity.name is a valid UUID and displayName is non-empty when set"
    )
    default_severity = Severity.ERROR
```

In `src/cxas_scrapi/poly/diagnostics.py`, add to `RULE_GUIDES` after the `AD010` entry:

```python
    "AD011": RuleGuide(
        what="The adapter's appIdentity block is malformed.",
        why=(
            "Each channel compiles to a distinct deployable app; an explicit "
            "appIdentity.name must be a real UUID and displayName must be "
            "non-empty so the override is usable."
        ),
        fix=(
            "Provide a valid UUID for appIdentity.name (or omit it to let the "
            "engine derive one), and give appIdentity.displayName a non-empty "
            "value or remove it."
        ),
    ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/cxas_scrapi/poly/test_adapter_lint_rules.py -v`
Expected: PASS (all, including new AD004/AD011/registry).

- [ ] **Step 5: Commit**

```bash
git add src/cxas_scrapi/utils/lint_rules/adapters.py src/cxas_scrapi/poly/diagnostics.py tests/cxas_scrapi/poly/test_adapter_lint_rules.py
git commit -m "feat(poly): AD011 lint rule + doctor guide; add AD004 lint test"
```

---

## Task 5: Enrich .poly_build.json provenance

**Files:**
- Modify: `src/cxas_scrapi/poly/models.py` (add `provenance` field to `CompiledAgentConfig` ~line 246)
- Modify: `src/cxas_scrapi/poly/engine.py` (compute provenance in `compile()`; write it in `write_output` marker ~line 673)
- Test: `tests/cxas_scrapi/poly/test_hardening.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/cxas_scrapi/poly/test_hardening.py`:

```python
def test_provenance_marker_is_enriched(tmp_path, polymorphic_pizza_dir):
    import json

    from cxas_scrapi.poly import PolymorphismEngine

    engine = PolymorphismEngine(str(polymorphic_pizza_dir))
    engine.load_base_project()
    compiled = engine.compile_all()
    out = engine.write_output(compiled["chat"], str(tmp_path / "chat"))

    marker = json.loads((out / ".poly_build.json").read_text())
    assert marker["channel"] == "chat"
    assert marker["adapter_card"].endswith("chat.adapter.yaml")
    assert len(marker["adapter_sha256"]) == 64
    assert "Order_Agent" in marker["base_agents"]
    assert marker["base_agents"] == sorted(marker["base_agents"])
    assert marker["applied_deltas"]["tools_added"] == 1
    assert marker["applied_deltas"]["deployment"] is True
    assert isinstance(marker["engine_version"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cxas_scrapi/poly/test_hardening.py::test_provenance_marker_is_enriched -v`
Expected: FAIL with `KeyError: 'adapter_card'`.

- [ ] **Step 3: Add the `provenance` field to the model**

In `src/cxas_scrapi/poly/models.py`, add to `CompiledAgentConfig`:

```python
    # Build-provenance metadata written into the .poly_build.json marker.
    provenance: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Compute provenance in compile()**

In `src/cxas_scrapi/poly/engine.py`, add these imports at the top:

```python
import hashlib
from importlib import metadata as importlib_metadata
```

Add a helper method to `PolymorphismEngine`:

```python
    def _build_provenance(
        self, adapter: AdapterCard, card_path: Optional[Path]
    ) -> Dict[str, Any]:
        assert self.base is not None
        try:
            version = importlib_metadata.version("cxas-scrapi")
        except Exception:  # pragma: no cover - environment dependent
            version = "unknown"

        adapter_rel = ""
        adapter_sha = ""
        if card_path is not None:
            try:
                adapter_rel = str(Path(card_path).relative_to(self.app_dir))
            except ValueError:
                adapter_rel = Path(card_path).name
            try:
                adapter_sha = hashlib.sha256(
                    Path(card_path).read_bytes()
                ).hexdigest()
            except OSError:
                adapter_sha = ""

        return {
            "engine_version": version,
            "adapter_card": adapter_rel,
            "adapter_sha256": adapter_sha,
            "base_agents": sorted(self.base.agents.keys()),
            "applied_deltas": {
                "instruction_diffs": len(adapter.instruction_diffs),
                "tools_added": sum(len(m.add) for m in adapter.tools),
                "tools_removed": sum(len(m.remove) for m in adapter.tools),
                "tool_definitions": len(adapter.tool_definitions),
                "model_overrides": len(adapter.model_overrides),
                "callbacks": len(adapter.callbacks),
                "evaluations": len(adapter.evaluations),
                "deployment": adapter.deployment is not None,
            },
        }
```

Then in `compile()`, populate it on the returned config. Add to the `CompiledAgentConfig(...)` constructor call:

```python
            provenance=self._build_provenance(adapter, card_path),
```

- [ ] **Step 5: Write provenance into the marker**

In `write_output`, change the marker write (currently `{channel, source, generated_at}`) to merge in provenance:

```python
        marker = {
            "channel": compiled.channel,
            "source": str(self.app_dir),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        marker.update(compiled.provenance)
        self._write_json(out / _POLY_MARKER, marker)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/cxas_scrapi/poly/test_hardening.py -v`
Expected: PASS (new test + existing hardening tests).

- [ ] **Step 7: Commit**

```bash
git add src/cxas_scrapi/poly/models.py src/cxas_scrapi/poly/engine.py tests/cxas_scrapi/poly/test_hardening.py
git commit -m "feat(poly): record build provenance in .poly_build.json"
```

---

## Task 6: Demo config cleanup + AD011 docs

**Files:**
- Modify: `examples/polymorphic_pizza/gecx-config.json`
- Modify: `.agents/skills/cxas-polymorphic-adapters/SKILL.md` (AD011 in the validation-rules list)
- Modify: `.agents/skills/cxas-polymorphic-adapters/references/debug-adapter.md` (AD011 cause/fix)

- [ ] **Step 1: Fix the demo gecx-config artifacts**

In `examples/polymorphic_pizza/gecx-config.json`, change `"app_dir": "cxas_app/Polymorphic_Pizza/"` to `"app_dir": "."` and change `"default_channel": "text"` to `"default_channel": "chat"` (an actual channel; compile overwrites it per channel, but the base value should name a real channel rather than a modality).

- [ ] **Step 2: Verify the demo still builds + lints clean**

Run:
```bash
uv run cxas poly build --app-dir examples/polymorphic_pizza --output-dir /tmp/poly_demo_check --force
uv run cxas lint --app-dir /tmp/poly_demo_check/chat
uv run cxas lint --app-dir /tmp/poly_demo_check/voice
```
Expected: build compiles 2 channels; both lints `PASSED`.

- [ ] **Step 3: Document AD011 in the skill**

In `.agents/skills/cxas-polymorphic-adapters/SKILL.md`, add to the Validation Rules list after the AD010 line:

```
- `AD011`: `appIdentity` malformed (name not a valid UUID, or empty displayName)
```

In `.agents/skills/cxas-polymorphic-adapters/references/debug-adapter.md`, add an AD011 entry mirroring the existing rule entries: cause = "appIdentity.name is not a valid UUID or appIdentity.displayName is empty"; fix = "provide a valid UUID (or omit name to auto-derive) and a non-empty displayName (or omit it)".

- [ ] **Step 4: Commit**

```bash
git add examples/polymorphic_pizza/gecx-config.json .agents/skills/cxas-polymorphic-adapters/SKILL.md .agents/skills/cxas-polymorphic-adapters/references/debug-adapter.md
git commit -m "docs(poly): document AD011; fix pizza demo gecx-config artifacts"
```

---

## Task 7: Full verification

- [ ] **Step 1: Run the full poly suite**

Run: `uv run pytest tests/cxas_scrapi/poly/ -q`
Expected: all pass (≥ 85 prior + ~11 new).

- [ ] **Step 2: Rebuild the demo and inspect identity + provenance**

Run:
```bash
uv run cxas poly build --app-dir examples/polymorphic_pizza --output-dir /tmp/poly_final --force
python -c "import json; c=json.load(open('/tmp/poly_final/chat/app.json')); v=json.load(open('/tmp/poly_final/voice/app.json')); print('chat', c['displayName'], c['name']); print('voice', v['displayName'], v['name']); assert c['displayName']!=v['displayName'] and c['name']!=v['name']; print('OK distinct identity')"
python -c "import json; m=json.load(open('/tmp/poly_final/chat/.poly_build.json')); print(json.dumps(m, indent=2)); assert m['adapter_sha256'] and m['base_agents'] and m['applied_deltas']['tools_added']==1; print('OK provenance')"
uv run cxas lint --app-dir /tmp/poly_final/chat
uv run cxas lint --app-dir /tmp/poly_final/voice
```
Expected: distinct identities printed, provenance present, both lints PASS.

- [ ] **Step 3: Confirm no regressions in the broader linter test**

Run: `uv run pytest tests/cxas_scrapi/poly/test_adapter_lint_rules.py tests/cxas_scrapi/utils -q`
Expected: pass (AD011 auto-registers; no other lint category disturbed).

---

## Self-review notes

- **Spec coverage:** Section 1 → Tasks 1–4; Section 2 → Task 5; Section 3 (AD004) → Task 4; Section 4 (demo) → Task 6. All covered.
- **Type consistency:** `AppIdentity.display_name`/`.name`, `AdapterCard.app_identity`, `CompiledAgentConfig.provenance`, `_resolve_app_identity`, `_build_provenance`, `AdapterAppIdentityValid` (AD011) used consistently across tasks.
- **No placeholders:** every code step shows full code; commands show expected output.
