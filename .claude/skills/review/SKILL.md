---
name: review
description: Review open PRs targeting main. Spawns judge agent (2-stage spec compliance + sandbox).
user-invocable: true
---

# Review

Review all open PRs targeting `main`. Each PR is judged independently against its linked checklist.

## Instructions

### Step 1: List open PRs

```bash
gh pr list --base main --state open --json "number,title" --limit 20
```

If no open PRs → say "No open PRs to review." STOP.

### Step 2: Verify each PR has a linked checklist

For each PR, read the body. It must reference `docs/specs/<...>-checklist.md`.
- If a PR is missing a checklist link → flag it: "PR #N has no checklist — judge cannot review. Run /cycle-start retroactively for this PR's topic, or skip."

### Step 3: Spawn judge per PR (do not batch)

For each PR with a checklist:

```
Agent(
  subagent_type="judge",
  prompt="Review PR #<N> targeting main.
Linked checklist: <path from PR body>
Run Stage 1 (spec compliance) THEN Stage 2 (sandbox + quality).
Follow your agent instructions exactly (strict verdict schema, sandbox output mandatory).
Write result to data/review_verdict_pr<N>.json."
)
```

Judges run sequentially — they each `gh pr checkout`, which would conflict if parallel.

### Step 4: Show results

Read each `data/review_verdict_pr<N>.json` and display:

| PR | Stage 1 | Stage 2 | Verdict | Sandbox |
|----|---------|---------|---------|---------|
| #N | approved/blocked | approved/blocked | approved/request_changes/rejected | ruff:✓ mypy:✓ pytest:✓ (frontend gates if applicable) |

For each `approved` PR, ask: "Merge PR #N? (rebase + delete branch)"

For each `request_changes`, list the blocking_items and important issues.

## Rules

- Do NOT merge without explicit user approval per PR
- NEVER `subagent_type="general-purpose"` for the judge (per CLAUDE.md)
- Judge verdict MUST contain sandbox output — re-dispatch if missing
