---
name: cxas-polymorphic-adapters
description: Use when authoring, reviewing, validating, building, diffing, or debugging CXAS SCRAPI polymorphic channel adapters, adapter cards, channel-specific variants, or chat/voice/API/web/telephony adaptation work.
---

# CXAS Polymorphic Adapters

This is the Claude discovery wrapper for the repo's canonical polymorphic
adapter skill.

## Canonical Source

Read this file first:

```text
.agents/skills/cxas-polymorphic-adapters/SKILL.md
```

Then load the matching reference:

```text
.agents/skills/cxas-polymorphic-adapters/references/adapter-authoring.md
.agents/skills/cxas-polymorphic-adapters/references/build-and-validate.md
.agents/skills/cxas-polymorphic-adapters/references/debug-adapter.md
```

## Quick Routing

| User intent | Load |
|---|---|
| Should I use adapters or separate agents? | canonical `SKILL.md` decision framework |
| Write or revise an adapter card | `references/adapter-authoring.md` |
| Validate, diff, or build adapters | `references/build-and-validate.md` |
| Fix AD00x or compilation issues | `references/debug-adapter.md` |

## Key Commands

```bash
uv run cxas poly validate --app-dir <app_dir>
uv run cxas poly diff <channel> --app-dir <app_dir>
uv run cxas poly build --app-dir <app_dir> --output-dir <output_dir>
uv run cxas lint --app-dir <output_dir>/<channel>
```

## Claude-Specific Rule

Do not maintain a separate Claude-only version of the workflow. If this wrapper
and the canonical `.agents` skill ever disagree, the canonical skill wins.
