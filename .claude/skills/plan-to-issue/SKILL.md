---
name: plan-to-issue
description: Convert an existing spec/plan (or the latest one) into a GitHub issue with linked checklist, ready for /cycle. Use when you've already brainstormed inline and want to formalize it.
user-invocable: true
---

# Plan to Issue

Bridge between inline brainstorming/planning and our /cycle workflow. Use this when you have a spec already written (e.g. you ran `superpowers:brainstorming` directly) and want to ship it through /cycle.

If you DON'T have a spec yet, run `/cycle-start` instead — it does brainstorm + spec + issue in one flow.

## Step 1 — Identify the spec

If the user passed an argument, use that path. Otherwise find the most recent spec:

```bash
ls -t docs/specs/*-design.md | head -1
```

Show the user what you found and ask "Use this one? (y/n or path)".

## Step 2 — Verify a checklist exists

Each spec needs a matching checklist:

```bash
SPEC=docs/specs/<date>-<topic>-design.md
CHECKLIST=docs/specs/<date>-<topic>-checklist.md

[ -f "$CHECKLIST" ] || echo "NO CHECKLIST"
```

If no checklist:
- Dispatch `spec-writer` to generate one from the spec:

```
Agent(
  subagent_type="spec-writer",
  prompt="A spec already exists at <SPEC_PATH> but no checklist. Read the spec
(do NOT rewrite it). Produce only the checklist at <CHECKLIST_PATH> following
your strict format, and emit data/spec_verdict.json.
The brainstorm doesn't exist as a separate file — the spec IS the source."
)
```

Read `data/spec_verdict.json`. If `needs_decomposition` → present split, ask user.

## Step 3 — Validate the checklist

Read the checklist file. Verify it has:
- At least one `[SPEC-N]` item
- At least one `[TEST-N]` item
- The 4 `[GATE-N]` items
- No vague items ("add validation", "handle edge cases" — see spec-writer rules)

If invalid → tell the user what's missing, ask if they want spec-writer to fix it.

## Step 4 — Determine label

```bash
PHASE=$(grep -oP 'R:phase-\K[0-9a-z]+' docs/STATUS.md | head -1)
```

Ask the user: "Roadmap phase R:phase-<N> or ad-hoc?" Default to roadmap if the spec mentions a phase.

## Step 5 — Create the issue

```bash
TITLE="<title from spec — first H1 line stripped>"

gh issue create \
  --repo arthurolivierfortin/Brain \
  --title "$TITLE" \
  --body "$(cat <<'EOF'
## Goal
<one sentence from spec>

## Linked spec
<spec path>

## Checklist
<checklist path>

## Phase
R:phase-<N>  (or "ad-hoc")
EOF
)" \
  --label "R:phase-<N>,feature,todo,P:normal"
```

For ad-hoc: `--label "ad-hoc,todo,P:<priority>"`.

## Step 6 — Hand off

```
Issue #<NUMBER> created from <spec_path>.

Run /cycle to pick it up.
```

## Rules

- Do NOT create an issue without a checklist (the judge depends on it)
- Do NOT modify the spec content — only create the checklist if missing (specs are append-only per CLAUDE.md)
- One issue per spec — if the spec is too big, spec-writer will say `needs_decomposition` and the user splits before re-running this command
- The original brainstorm doesn't need to live anywhere structured — the spec is the source of truth
