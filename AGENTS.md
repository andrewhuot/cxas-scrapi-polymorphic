# cxas-scrapi

This repository is a workspace and SDK for building and managing GECX (Google Customer Engagement Suite) conversational agents.

## Repository Structure

```
cxas-scrapi/                    # SDK source code
.agents/skills/                 # Collection of reusable agent skills
├── cxas-agent-foundry/         # Composite skill for end-to-end agent lifecycle
├── cxas-sim-eval/              # Skill for converting evals
└── ...
<project_name>/                 # (Optional) App-specific agent workspaces managed by skills (e.g., cymbal/)
.venv/                          # Shared virtual environment
AGENTS.md                       # Workspace overview (this file)
.active-project                 # (Optional) Points to the currently active project folder
```

## Setup

Run the setup script to create a virtual environment and install the `cxas-scrapi` SDK from the local source:

```bash
.agents/skills/cxas-agent-foundry/scripts/setup.sh          # Full setup (install + configure)
.agents/skills/cxas-agent-foundry/scripts/setup.sh --configure  # Reconfigure only
source .venv/bin/activate
```

Requires Python 3.10+ and [astral-uv](https://docs.astral.sh/uv/getting-started/installation/).

## GitHub / PR Targeting

This workspace has both:

- `origin` -> `https://github.com/andrewhuot/cxas-scrapi-polymorphic.git`
- `upstream` -> `https://github.com/GoogleCloudPlatform/cxas-scrapi.git`

Unless the user explicitly asks otherwise, draft and open PRs against
`andrewhuot/cxas-scrapi-polymorphic`, not `GoogleCloudPlatform/cxas-scrapi`.
Before creating a PR, verify the target repository with:

```bash
gh repo view --json nameWithOwner,defaultBranchRef
```

The expected default target for this workspace is:

```text
andrewhuot/cxas-scrapi-polymorphic
```

## Available Skills

This workspace provides several specialized AI skills to assist with development. 

- **`cxas-agent-foundry`**: The primary skill for the end-to-end GECX agent lifecycle. Use this for building agents from PRDs, generating and running evals, debugging failures, and syncing code.
- **`cxas-polymorphic-adapters`**: A repo-native skill for deciding, authoring, validating, building, diffing, and debugging polymorphic channel adapter cards with `cxas poly`.
- **`cxas-sim-eval`**: A utility skill for converting CXAS golden evaluations to SCRAPI SimulationEvals test cases.

*Note: For detailed development workflows, linter policies, and GECX-specific conventions, refer to the documentation within the respective skills (e.g., `.agents/skills/cxas-agent-foundry/SKILL.md`).*
