# Brain — STATUS

**Updated:** 2026-04-27
**Current phase:** R:phase-2b (Hook architecture — MVP, dogfood-ready)

> Source-of-truth roadmap lives in [README.md](../README.md#roadmap). This file is the machine-parseable handle that `/cycle`, `/cycle-start`, `/plan`, and `/status` read.

## Current phase

`R:phase-2b` — Hook architecture + Brain monitor

Brain monitor (3 PRs, 3 phases) shipped 2026-04-27:
- [x] Phase 1 — skeleton + vitals (#16, PR #20)
- [x] Phase 2 — graph viz + thought stream (#17, PR #21)
- [x] Phase 3 — left panel + tabs + polish (#18, PR #22)

Remaining deliverables for phase 2b:
- [ ] Dogfood hook architecture + monitor on Brain sessions for ≥7 days, verify cerveau-parfait effect (open `http://localhost:8621/monitor` while Brain runs)

All other phase 2b deliverables checked off in README.md.

## Known follow-ups (post-2b)

- MatrixView cell-overlay positioning bug at `backend/src/brain/static/brain.html` ~L1153 (double-counts `LABEL_GUTTER`; cosmetic, ~80px offset). Open as ad-hoc P:low if confirmed during dogfood.

## Phase pipeline (next)

After 2b dogfood completes:
- `R:phase-3` — Installer (`npx brain`)
- `R:phase-2-extended` — 29-tool MCP surface (parallel-able with 3)
- `R:phase-4` — Frontend (Next.js, memory browser, graph viz, live stream)
- `R:phase-5` — Benchmarks (LongMemEval / LoCoMo)
- `R:phase-6` — Aggregator mode
- `R:phase-7` — Money migration + legacy Brain removal

## Ad-hoc / cross-phase

Anything outside the roadmap goes through GitHub issues with the `ad-hoc` label and a `P:high` / `P:normal` / `P:low` priority label.

## How this file is updated

- Builder PRs that ship a roadmap deliverable update README.md (tick the box)
- `/cycle` updates this STATUS.md when a phase advances or a new ad-hoc batch is opened
- Manual edits welcome — keep `**Updated:**` honest
