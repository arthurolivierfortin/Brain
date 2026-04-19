---
id: 0001
title: Project meta-conventions — docs, traceability, agent cadence
status: accepted
date: 2026-04-19
---

## Context

Brain is a research-adjacent infrastructure project (memory system, benchmarks, publishable scores) carried primarily by one user + Claude pairs. After phase 1 extraction and phase 5a benchmarks harness landed, the user raised three meta-concerns:

1. **Documentation access** — "I want anyone entering the project to understand it easily and in depth, like Money's docs". Should Brain have a dedicated docs project?
2. **Structure discipline** — the user is strict about file/folder separation. `docs/` had become inconsistent (loose `improvements.md` at root next to folders).
3. **Workflow / traceability** — should Brain adopt a multi-agent pipeline (analyzer → researcher → builder → reviewer, with the controller as manager) and issue-driven development, or keep the current direct controller-dispatch mode without GitHub issues?

The driving goal is "research-project traceability": decisions, hypotheses, results, reversals must all be discoverable 6 months later.

## Decision

**Documentation**
- Keep docs in-repo under `docs/`; no separate docs project for now.
- Defer mkdocs/Docusaurus until `docs/` > ~30 files OR an external consumer (Marcel) ships.
- Structure `docs/` into 8 subfolders, each with its own `README.md`:
  `architecture/`, `research/`, `specs/`, `plans/`, `runbooks/`, `benchmarks/`, `improvements/`, `decisions/`.
- Root of `docs/` holds only `README.md` (master index).
- Specs and plans are **append-only** history.
- Doc-freshness rule: every PR that changes observable behavior MUST touch the relevant doc(s); reviewer blocks otherwise.

**Traceability**
- **Issue-first**: every non-trivial change gets a GitHub issue opened *before* code.
- Bug found during a run → one issue per bug, linked to the run artifact (JSONL + commit SHA).
- Benchmark runs → issue with config, dataset, scores, cost, duration; commit JSONL + markdown report.
- Every PR references its issue (`Closes #N` / `Refs #N`).
- Labels: `bug`, `feature`, `bench`, `docs`, `chore`, `research` + `area/*`.

**Agent cadence**
- No rigid analyzer → researcher → builder → reviewer pipeline. Cost > benefit at current scale (1 user, interactive sessions).
- Keep existing typed agents: `builder`, `code-quality`, `reviewer`, `research-planner`, `think`.
- Add one new agent when it produces concrete leverage: `bench-analyzer` (reads a run JSONL, produces an analysis report, opens issues for regressions) — written **after** phase 5a is merged, not before.
- Controller (Claude in session) stays the orchestrator. Automation over discipline arrives only when Brain needs to run autonomously (nightly benches, scheduled release runs) — not yet.

## Alternatives considered

**A. Separate docs project (Docusaurus/mkdocs) now**
- Pros: matches Money's setup, deployable site, external-facing.
- Cons: heavy overhead (build pipeline, deployment, cross-repo sync) for zero current benefit — no external users. Premature.
- Rejected: not yet.

**B. Multi-agent pipeline for every task (analyzer + researcher + builder + reviewer + manager)**
- Pros: maximum traceability, mirrors Money's autonomous loop.
- Cons: overhead without a night-cycle justification. Each task becomes 4-5 subagent dispatches. Slows iteration without adding clarity when the user is already in-session.
- Rejected: defer until Brain runs unattended.

**C. Keep the current ad-hoc mode with no issues**
- Pros: fastest iteration.
- Cons: zero traceability. Session logs disappear. Decisions vanish. Unacceptable for a project meant to publish benchmarks and justify design choices.
- Rejected: fails the research-traceability goal.

## Consequences

**Gains**
- Anyone (future Claude session, future contributor, user in 6 months) can navigate `docs/` and understand what's been decided and why.
- GitHub issues become the immutable URL for every bug, every run, every decision.
- Bench results and the bugs they surface are linkable from issues → PRs → ADRs → spec files.
- When the doc volume justifies a site, the tree is already shaped correctly for mkdocs/Docusaurus nav.

**Costs**
- Every non-trivial task now has an issue-opening step. ~1 min overhead per task. Acceptable.
- Specs being append-only means design evolution requires a new spec + ADR, not in-place edits. This is the point: history stays legible.
- Doc-freshness enforcement relies on reviewer discipline. If reviews get skipped, the rule rots.

**Reversal cost**
- If this fails, undoing is cheap: collapse `docs/` subfolders back, stop requiring issues. No code is coupled to this convention.

## Follow-up actions

- [ ] Retroactively open issues for the 2 Brain bugs surfaced during the 2026-04-19 smoke run (metadata not preserved through `/search`, `top_k` ignored).
- [ ] Retroactively open an issue for the smoke run itself, with the JSONL path + qwen2.5:0.5b judge caveat documented.
- [ ] Write `bench-analyzer` agent after phase 5a branch merges to main.
