# Brain — STATUS

**Updated:** 2026-04-27
**Current phase:** R:phase-2b (Hook architecture — MVP)

> Source-of-truth roadmap lives in [README.md](../README.md#roadmap). This file is the machine-parseable handle that `/cycle`, `/cycle-start`, `/plan`, and `/status` read.

## Current phase

`R:phase-2b` — Hook architecture (the real product)

Remaining deliverables for phase 2b:
- [ ] Dogfood hook architecture on Brain sessions for ≥7 days, verify cerveau-parfait effect

All other phase 2b deliverables checked off in README.md.

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
