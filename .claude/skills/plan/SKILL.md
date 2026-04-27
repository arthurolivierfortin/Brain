---
name: plan
description: Create GitHub Issues for the current roadmap phase. Reads README.md roadmap and docs/STATUS.md, generates issues.
user-invocable: true
---

# Plan Phase

Generate GitHub Issues for the current (or specified) roadmap phase.

## Instructions

### Step 1: Read current state

```bash
cat docs/STATUS.md
cat README.md  # Brain's roadmap is inside README.md (## Roadmap section)
```

Identify the current phase from STATUS.md.

### Step 2: Check if issues already exist

```bash
gh issue list --repo arthurolivierfortin/Brain --label "R:phase-<N>" --state all --json number,title
```

If issues already exist for this phase, show them and ask if the user wants to add more or regenerate.

### Step 3: Generate issues from the README roadmap

For each unchecked deliverable in the phase, create a GitHub Issue:

```bash
gh issue create \
  --repo arthurolivierfortin/Brain \
  --title "<deliverable title>" \
  --body "## Context
From README.md Roadmap Phase <N>: <phase title>

## Task
<description of what to build>

## Acceptance Criteria
- [ ] <criterion 1>
- [ ] <criterion 2>
- [ ] Tests pass (ruff/mypy/pytest for Python; pnpm lint/typecheck/test for frontend)

## Phase
R:phase-<N>" \
  --label "R:phase-<N>,feature,todo,P:normal"
```

### Step 4: Confirm

List all created issues and show the phase plan.

### Rules
- One issue per deliverable — don't combine multiple features
- Keep issues small and focused (1-2 day scope max)
- Split large deliverables into sub-issues
- Always include acceptance criteria
- This skill creates "shell" issues (acceptance criteria only). For an issue ready for `/cycle`, use `/cycle-start` instead — it produces a full spec + machine-readable checklist.
