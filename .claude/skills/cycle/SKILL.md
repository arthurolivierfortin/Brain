---
name: cycle
description: Main dev loop — picks the next issue, runs spec-aware research → TDD build → 2-stage judge review, merges if approved.
user-invocable: true
---

# Development Cycle

You are the development orchestrator for Brain. You do NOT build or review yourself. You spawn subagents for each phase.

**Companion command:** `/cycle-start` to brainstorm + spec-write a NEW feature into a GitHub issue. `/cycle` (this) picks up issues and ships them.

## Step 0 — Pull latest

```bash
git checkout main
git pull origin main
```

## Step 1 — Pick the next issue

### 1a. Ad-hoc priority work
```bash
gh issue list --repo arthurolivierfortin/Brain --label "ad-hoc" --label "P:high" --state open --limit 1 --json number,title
```
If any → use that issue.

### 1b. Otherwise, current roadmap phase
Read `docs/STATUS.md` to find current phase (e.g. `R:phase-2b`).
```bash
gh issue list --repo arthurolivierfortin/Brain --label "R:phase-<N>" --label "todo" --state open --limit 1 --json number,title --jq '.[0]'
```

If no `todo` issues for current phase:
- All closed → say "Phase <N> complete! Review and approve to advance." STOP.
- Some still open (in-progress/in-review) → say "Phase <N> has issues in progress. Wait." STOP.

If no issues exist for the phase → say "No issues for Phase <N>. Run /plan or /cycle-start." STOP.

## Step 2 — Verify the issue has a checklist

The issue body MUST link to `docs/specs/<...>-checklist.md`. If it doesn't:

- Old issues without checklists are legacy — offer to run `/cycle-start` (brainstorm + spec) for the issue's topic to bring it into the new format. Otherwise STOP.

## Step 3 — Research — dispatch researcher

```
Agent(
  subagent_type="researcher",
  prompt="Research and plan implementation for issue #<NUMBER>: <TITLE>.
Spec: <spec path from issue body>
Checklist: <checklist path from issue body>
Follow your agent instructions exactly. Write result to data/plan_verdict.json."
)
```

Read `data/plan_verdict.json`:
- `approved` → Step 4
- `blocked` → label issue `blocked`, post the reason as comment, STOP
- `needs_input` → say what's needed, STOP

## Step 4 — Build — dispatch builder

```
Agent(
  subagent_type="builder",
  prompt="Implement issue #<NUMBER>: <TITLE>.
Plan: data/plan_verdict.json
Spec: <spec path>
Checklist: <checklist path>
Follow your agent instructions exactly (TDD per task, tick checklist, run gates).
Write result to data/build_verdict.json. Do NOT merge."
)
```

Read `data/build_verdict.json`:
- `pr_created` with `items_skipped: []` → Step 5
- `pr_created` with `items_skipped` non-empty → reject — builder cannot ship a PR with skipped checklist items. Comment on PR, set issue back to `todo`. STOP.
- `failed` → comment reason on issue, STOP.

## Step 5 — Judge — dispatch judge (2-stage review)

```bash
gh pr list --base main --state open --json "number,title" --limit 10
```

```
Agent(
  subagent_type="judge",
  prompt="Review PR #<PR_NUMBER> for issue #<ISSUE_NUMBER>.
Linked checklist: <checklist path>
Plan: data/plan_verdict.json
Run Stage 1 (spec compliance) THEN Stage 2 (sandbox + quality).
Follow your agent instructions exactly (strict verdict schema, sandbox output mandatory).
Write result to data/review_verdict_pr<PR_NUMBER>.json."
)
```

Read `data/review_verdict_pr<N>.json`:
- Validate the schema. If `sandbox` block is missing or empty → REJECT verdict, re-dispatch judge.
- `verdict: approved` → Step 6
- `verdict: request_changes` → Step 7
- `verdict: rejected` → close PR, re-open issue as `todo` with rejection reason

## Step 6 — Merge

```bash
PR_TITLE=$(gh pr view <PR_NUMBER> --json title --jq .title)
gh pr merge <PR_NUMBER> --rebase --delete-branch --subject "$PR_TITLE"
gh issue close <ISSUE_NUMBER>
```

Update `docs/STATUS.md` — mark deliverable done.

## Step 7 — Re-build on changes_requested (max 2 retries)

```
Agent(
  subagent_type="builder",
  prompt="Address judge feedback on PR #<PR_NUMBER>.
Verdict: data/review_verdict_pr<N>.json
For each blocking_item and important issue, fix it.
Re-run all gates. Push to the same branch. Do NOT merge.
Write updated data/build_verdict.json."
)
```

Then loop back to Step 5 (re-dispatch judge).

After 2 retries with `request_changes`:
- Reject the PR — close it, re-open issue as `todo` with the latest verdict pasted as comment, STOP.

## Step 8 — Return to main

```bash
git checkout main
git pull origin main
```

## Summary

```
/cycle
  ├─ ad-hoc P:high? → use that issue
  ├─ else → next R:phase-<N>/todo issue
  ├─ verify issue has linked checklist (else /cycle-start)
  ├─ Agent(researcher) → plan_verdict.json
  ├─ Agent(builder)    → TDD per [SPEC-N], tick checklist, gates, PR
  ├─ Agent(judge)      → Stage 1 spec compliance → Stage 2 sandbox + quality
  │     ├─ approved          → rebase merge, close issue, update STATUS.md
  │     ├─ request_changes   → builder fix + re-judge (max 2x)
  │     └─ rejected          → close PR, re-open issue
  └─ git checkout main
```

## Rules
- NEVER do the work yourself — spawn `Agent()` for every phase
- One issue per cycle invocation
- Max 2 builder→judge retries before rejecting
- Phase transitions require human approval
- Judge verdict MUST include sandbox output — reject the verdict if missing
- ALL changes go through PR — never push to `main` directly
- NEVER `subagent_type="general-purpose"` (per CLAUDE.md — crashes silently in Docker)
