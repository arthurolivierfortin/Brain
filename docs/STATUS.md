# Brain — STATUS

**Updated:** 2026-04-30
**Current phase:** R:phase-2c (Storage layering — raw buffer + consolidation)

> Source-of-truth roadmap lives in [README.md](../README.md#roadmap). This file is the machine-parseable handle that `/cycle`, `/cycle-start`, `/plan`, and `/status` read.

## Current phase

`R:phase-2c` — Storage layering (cerveau-style: raw buffer → extracted → consolidated)

Promoted from "improvements" 2026-04-30 after dogfood revealed Gemini-filter-at-ingest drops too many facts. User confirmed initial mental model was always "L1 stocks everything raw, higher layers filter". Closes the discordance documented in [data/brainstorm-storage-layering.md](../data/brainstorm-storage-layering.md).

Phasing:
- [ ] 2c.1 — Raw buffer (L1) + multi-hook capture (UserPromptSubmit + PostToolUse + dual-write at Stop) — issue #40, spec [docs/specs/2026-04-30-storage-layering-2c1-design.md](specs/2026-04-30-storage-layering-2c1-design.md)
- [ ] 2c.2 — Hourly consolidation cron (L1 raw → L2 extracted via batched Gemini with cumulative context)
- [ ] 2c.3 — L3 consolidated layer (reinforcement OR survival promotion)
- [ ] 2c.4 — Monitor visualization (color=type, opacity=maturity, ring=retrieval-tag)

## Phase 2b — completed

`R:phase-2b` — Hook architecture + Brain monitor (closed 2026-04-30)

Brain monitor (3 PRs, 3 phases) shipped 2026-04-27:
- [x] Phase 1 — skeleton + vitals (#16, PR #20)
- [x] Phase 2 — graph viz + thought stream (#17, PR #21)
- [x] Phase 3 — left panel + tabs + polish (#18, PR #22)

L2/L3 layering shipped 2026-04-28:
- [x] L2-A backend (#25, PR #27) — WakeUpHandler refactor + topic-triggered retrieval + cross-agent + reranking + degraded_wake_up observability + ADR 0003
- [x] L2-B adapter (#26, PR #28) — `scripts/brain_wake_up.py` collects git + CLAUDE.md, sends in payload
- [x] L3 = `brain_search` MCP tool (already existed; clarified in README + ADR 0003)

Brain monitor fidelity pass shipped 2026-04-28:
- [x] Monitor fidelity (#30, PR #31) — htop tabs in header, agent dropdown, L2 badge, layer rings on graph nodes, animation system, memory_type co-occurrence matrix, hash router (#/memory/, #/hook/, #/agent/), drawer inspectors with j/k navigation

Phase 2b dogfood folded into 2c.1 build (the storage layering work IS the dogfood signal — 2c.1 ships, we observe how L1 fills up, calibrates 2c.2's consolidation cadence).

Phase 2b monitor regressions fixed 2026-04-30 (PR #39): graph drift, tweaks panel removal, drawer overlay, mockup-fidelity bars + force-directed sim ported from tmp/BrainV2/brain-graph.jsx.

All other phase 2b deliverables checked off in README.md.

## Known follow-ups (post-2b)

- MatrixView cell-overlay positioning bug at brain.html ~L1153 (Phase 3 cosmetic, ~80px offset). Possibly fixed by the monitor fidelity refactor — verify in dogfood.
- L2 threshold (`BRAIN_L2_THRESHOLD`, default 0.45) needs dogfood-period calibration — adjust if too few/too many memories surface.
- queue_log.jsonl persistence deferred (HEALTH sparkline currently in-memory only) — open ad-hoc issue if dogfood reveals a need.
- Phase 4 Next.js rewrite (frontend/) lands the typed version of brain.html with Playwright tests — current static + Babel-in-browser is the dogfood artifact.

## Phase pipeline (next)

After 2c completes:
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
