---
name: cycle-start
description: Start a new feature — brainstorm with you in main thread, write a spec + checklist via spec-writer subagent, then create a GitHub issue. Use when you have an idea you want to ship through /cycle.
user-invocable: true
---

# Cycle Start

You are starting a new feature for Brain. The goal of this command is to get from "I have an idea" to "GitHub issue with checklist exists, ready for /cycle to pick up". Brainstorming stays in the main thread (with the user); spec writing is delegated to a subagent.

**Pattern reference:** Apply `superpowers:brainstorming` discipline — one question at a time, propose 2-3 approaches, present design, get approval. The terminal state is dispatching `spec-writer`, not `writing-plans`.

## Phase 1 — Brainstorm (main thread, with user)

Do NOT dispatch a subagent for brainstorming. Brainstorming is a conversation between you and the user. Subagents work in isolation and cannot brainstorm with humans.

### 1a. Explore project context

```bash
cat docs/STATUS.md
cat README.md  # Brain has the roadmap inside README.md, not a separate ROADMAP.md
gh issue list --repo arthurolivierfortin/Brain --label "ad-hoc" --state open --limit 5
git log --oneline -10
```

Read 2-3 source files relevant to what the user described. For Brain, those usually live under `backend/src/brain/` (Python core) or `scripts/` (Claude Code hooks).

### 1b. Ask clarifying questions

One at a time. Multiple choice when possible. Focus on:
- Purpose / problem being solved
- Constraints (perf, compat, scope)
- Success criteria
- What's explicitly OUT of scope

### 1c. Propose 2-3 approaches

Each with tradeoffs. Lead with your recommendation.

### 1d. Present the design (in sections, get approval per section)

Cover:
- Architecture (where it fits in `backend/`, `frontend/`, `scripts/`, etc.)
- Components / data flow
- Error handling
- Test strategy
- Consumer impact (HTTP API surface? MCP tools? installer?)

Scale each section to its complexity. A few sentences if simple, 200-300 words if nuanced.

### 1e. HARD GATE — User approval

Do NOT proceed to Phase 2 until the user explicitly approves the design. "Sounds good", "yes", "ok let's do this", "ouais", "vas-y" all count. Anything ambiguous → ask one more question.

## Phase 2 — Write the brainstorm summary

Write `data/brainstorm.md` with everything that was decided:

```markdown
# Brainstorm — <topic>
**Date:** YYYY-MM-DD
**Roadmap phase:** R:phase-<N>

## Problem
<1 paragraph — why we're doing this>

## Decisions
- <bullets — what was chosen and why>

## Scope (in)
- <bullets>

## Scope (out — explicit YAGNI)
- <bullets>

## Architecture
<2-3 paragraphs as approved>

## Open questions
- <bullets — flag for spec-writer>
```

## Phase 3 — Dispatch spec-writer

```
Agent(
  subagent_type="spec-writer",
  prompt="Convert the brainstorm at data/brainstorm.md into a spec + checklist.
Roadmap phase: R:phase-<N>.
Issue context: <if there's an existing issue, give number and title>.
Write outputs per your agent instructions and emit data/spec_verdict.json."
)
```

Read `data/spec_verdict.json`:
- `ready` → proceed to Phase 4
- `needs_decomposition` → present the proposed split to the user. They pick one to start with, the others become future issues. Re-dispatch spec-writer for the chosen sub-feature.

## Phase 4 — User reviews the spec

```
Spec written and committed to <spec_path>.
Checklist at <checklist_path>.

Please review both files and let me know if you want changes before I create the GitHub issue.
```

Wait for the user's response. If they request changes, edit the spec/checklist and loop back. Only proceed once the user approves.

## Phase 5 — Create GitHub issue

```bash
PHASE=$(grep -oP 'R:phase-\K[0-9a-z]+' docs/STATUS.md | head -1)

gh issue create \
  --repo arthurolivierfortin/Brain \
  --title "<feature title>" \
  --body "$(cat <<'EOF'
## Goal
<one sentence from spec>

## Linked spec
docs/specs/YYYY-MM-DD-<topic>-design.md

## Checklist
docs/specs/YYYY-MM-DD-<topic>-checklist.md

## Phase
R:phase-<N>
EOF
)" \
  --label "R:phase-<N>,feature,todo,P:normal"
```

Note: For ad-hoc work outside the roadmap, use `--label "ad-hoc,todo,P:<priority>"` instead.

## Phase 6 — Hand off

```
Issue #<NUMBER> created.

Run /cycle to pick it up — researcher → builder → judge.
Or, if you want to ship multiple issues today, run /plan to enqueue more first.
```

## Rules

- Brainstorming NEVER happens in a subagent
- Do NOT skip Phase 1d (design presentation) — even for "simple" features
- Do NOT skip Phase 4 (user reviews spec) — written spec is what binds /cycle
- Spec lives in `docs/specs/` (per CLAUDE.md docs structure — NOT `docs/superpowers/specs/`)
- One feature per `/cycle-start` invocation. If the brainstorm reveals 3 features, create 3 issues, one at a time.
- Specs and plans are append-only history (per CLAUDE.md). Don't edit a merged spec — write a new dated spec if the design evolves.
