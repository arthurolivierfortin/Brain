# Decisions (ADRs)

Architecture Decision Records. Each file captures a single decision, its context, the options considered, and what was chosen. ADRs are how we remember *why* — not what we did, but what we chose not to do and why that choice still holds.

## What goes here

- **One decision per file** — focused, short (1-3 screens)
- **Durable rationale** — "why ChromaDB over SQLite+pgvector", "why Python over Go", "why French-first communication"
- **Reversals** — when a past ADR is replaced, write a new ADR with `Supersedes: NNNN` in the header

## What does NOT go here

- **Feature specs** (broader, with implementation scope) → [`../specs/`](../specs/)
- **Research** that feeds the decision → [`../research/`](../research/)
- **Running debates** — open an issue instead. An ADR is a decision that's been made.

## Naming

`NNNN-<slug>.md` where `NNNN` is a 4-digit zero-padded counter (`0001`, `0002`, …). ADRs are **never renumbered**. If you supersede `0003`, write `0007` with `Supersedes: 0003` — don't reuse `0003`.

## Template

```markdown
---
id: NNNN
title: <short decision title>
status: accepted | superseded-by:NNNN | deprecated
date: YYYY-MM-DD
supersedes:            # optional
superseded_by:         # optional, filled in later
---

## Context
<why did this come up, what forces are in play>

## Decision
<what we chose, one or two sentences>

## Alternatives considered
- A: <pros / cons>
- B: <pros / cons>

## Consequences
<what does this enable, what does it cost, what breaks if we reverse later>
```

## Index

- [`0001-project-meta-conventions.md`](0001-project-meta-conventions.md) — doc structure, issue-first workflow, agent cadence (2026-04-19)
- [`0002-hook-architecture.md`](0002-hook-architecture.md) — hook contract + MVP shape for wake_up/post_turn, L0/L1 via tags (2026-04-19)
