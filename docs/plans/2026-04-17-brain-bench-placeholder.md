# Brain-Bench (phase 5b) — placeholder

> **Status**: not scheduled. Unblocks after phase 5a lands and produces a
> credible LongMemEval-s score. Detailed plan will be written then via
> `superpowers:writing-plans`.

## Pre-requisites before detailing

- [ ] Phase 5a published: at least one release run with Brain full + ChromaDB
      raw ablation in `docs/benchmarks/`
- [ ] Decision: which Money sessions to use (30-day window, specific branches)
- [ ] Decision: QA authoring workflow — who writes, how we prevent bias
      (user writes the QA AND runs Brain → review needed)

## What it will contain (sketch only)

- Dataset curation workflow: transcripts → JSONL with `{question, ground_truth, expected_sources, category}`
- `benchmarks/src/brain_bench/runners/brain_bench.py` — same shape as LongMemEval runner, different dataset loader and metrics
- 30-50 hand-authored QA in `benchmarks/datasets/brain_bench_v1.jsonl` (committed to the repo)
- A separate `config/brain_bench_dev.yaml` + `config/brain_bench_release.yaml`
- Published report in `docs/benchmarks/YYYY-MM-DD-brain_bench-<adapter>.md`

## Non-goals (carried forward)

- No Marcel data yet (phase 5c)
- No synthetic QA generation (phase 5c)
- No auto-extraction of QA from transcripts

## Reference

See `docs/specs/2026-04-17-benchmarks-design.md §6`.
