---
status: approved
date: 2026-04-17
topic: benchmarks
owner: arthu
---

# Brain Benchmarks — Design Spec

## 1. Context

Brain standalone is extracted and functional (143 tests green, Docker healthy).
Phase 5 of the roadmap is benchmarks: measure Brain's memory performance
against published systems (MemPalace, mem0, Zep) and against itself
(ablations), and validate its usefulness on real agent workloads.

Two audiences, two benchmarks:
1. **Public comparison** (external credibility) — run the standard academic
   benchmark so numbers compare to the literature.
2. **Concrete usage** (our own confidence) — run on real agent transcripts
   to see if Brain actually helps on dev-agent work.

## 2. Decisions (brainstormed 2026-04-17)

| # | Decision | Value |
|---|----------|-------|
| 1 | Primary benchmark | **LongMemEval-s** (ICLR 2025, 500 Q, 115K token setting) |
| 2 | Secondary benchmark | **Brain-Bench custom** (phase 5b, Money transcripts) |
| 3 | Deferred | LongMemEval-m (1.5M tokens), LoCoMo, LoCoMo-Plus |
| 4 | Dev LLM | **Ollama** local (Llama 3.1 70B or Qwen 2.5) — $0 iteration |
| 5 | Release LLM | **Claude Opus 4.7** reader + judge (or GPT-4o for broader comparability) |
| 6 | Ablations (MVP) | **Brain full vs ChromaDB raw** — only. Avoids MemPalace trap (their 96.6% is the embedding, not the structure). Full ablations (no gate / no graph / no decay) deferred to v2. |
| 7 | Code location | `benchmarks/` at repo root. Separate `pyproject.toml`, not shipped with `brain` package. |
| 8 | Results location | `docs/benchmarks/` — dated `.md` per run + append-only `results.csv` + README summary table |
| 9 | Metrics | Recall@5, global accuracy, per-category accuracy (5), cost $, mean latency/Q, config (reader, judge, adapter, commit, date) |
| 10 | Brain-Bench source | Money Claude Code transcripts (~30 days in `~/.claude/projects/C--Money/*.jsonl`), 30-50 manually curated QA |

## 3. Architecture

```
C:\Brain\
├── backend/                        # unchanged, lean
├── benchmarks/                     # NEW — bench tooling, isolated
│   ├── pyproject.toml              # deps: datasets, pandas, ollama, anthropic, httpx
│   ├── config/
│   │   ├── dev.yaml                # ollama + subset 50 Q
│   │   └── release.yaml            # claude-opus + full 500 Q
│   ├── adapters/
│   │   ├── base.py                 # Adapter protocol: ingest(session), retrieve(query, k)
│   │   ├── brain.py                # Brain HTTP API (localhost:8621)
│   │   └── chromadb_raw.py         # Baseline: ChromaDB direct, no Brain
│   ├── runners/
│   │   ├── longmemeval.py          # pipeline: load → ingest → retrieve → read → judge → aggregate → report
│   │   └── brain_bench.py          # phase 5b — Money transcripts custom
│   ├── llm/
│   │   ├── base.py                 # LLMClient protocol: complete(messages) -> str
│   │   ├── ollama.py               # reader + judge via local Ollama
│   │   └── anthropic.py            # reader + judge via Claude API
│   ├── external/
│   │   └── LongMemEval/            # cloned via scripts/setup.sh (gitignored)
│   ├── scripts/
│   │   ├── setup.sh                # clone LongMemEval, pull Ollama models
│   │   └── run.sh                  # wrapper: docker up → run → publish report
│   └── tests/                      # adapter tests (NOT the bench itself)
└── docs/
    └── benchmarks/
        ├── README.md                            # index + how-to-read
        ├── results.csv                          # machine-readable, append-only
        └── 2026-XX-XX-longmemeval-s.md          # one file per published run
```

**Key components:**

- **`adapters/base.py`** — `Adapter` protocol:
  ```python
  class Adapter(Protocol):
      def ingest(self, session: Session) -> None: ...
      def retrieve(self, query: str, k: int) -> list[Memory]: ...
  ```
  Two concrete impls: `brain.py` (HTTP calls) and `chromadb_raw.py` (direct ChromaDB). The ablation is `adapter=brain` vs `adapter=chromadb_raw` — everything else identical.

- **`runners/longmemeval.py`** — orchestrator. Loads the LongMemEval-s dataset (500 Q + simulated multi-session conversations), loops over Q, calls adapter.retrieve, calls `llm.reader.complete` with retrieved context, calls `llm.judge.complete` comparing against ground truth, appends each Q result to a JSONL log (resume-safe), aggregates, writes report.

- **`llm/base.py`** — `LLMClient` protocol. Two impls: ollama + anthropic. Reader and judge can be swapped independently via config.

## 4. Pipeline (LongMemEval-s)

```
┌─────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
│ Load dataset    │ → │ Ingest       │ → │ Retrieve     │ → │ Read          │
│ (500 Q + convos)│   │ via adapter  │   │ top-k=5 per Q│   │ via LLM reader│
└─────────────────┘   └──────────────┘   └──────────────┘   └───────────────┘
                                                                    ↓
┌─────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────────┐
│ Write report    │ ← │ Aggregate    │ ← │ Judge        │ ← │ Answer string │
│ md + csv + log  │   │ R@5, acc/cat │   │ via LLM judge│   │ per Q         │
└─────────────────┘   └──────────────┘   └──────────────┘   └───────────────┘
```

**Config example** (`benchmarks/config/dev.yaml`):
```yaml
dataset: longmemeval_s
subset: 50                  # 10 Q per category × 5 categories — stratified sample
adapter: brain              # or "chromadb_raw"
reader: { provider: ollama, model: "llama3.1:70b" }
judge:  { provider: ollama, model: "llama3.1:70b" }
brain_url: http://localhost:8621
output_dir: benchmarks/runs/      # NOT docs/benchmarks/ — dev runs are not published
dry_run: false
```

**Release** (`benchmarks/config/release.yaml`):
```yaml
dataset: longmemeval_s
subset: null                      # full 500 Q
adapter: brain                    # run 1: brain; run 2: chromadb_raw (ablation)
reader: { provider: anthropic, model: "claude-opus-4-7" }
judge:  { provider: anthropic, model: "claude-opus-4-7" }
brain_url: http://localhost:8621
output_dir: docs/benchmarks/       # release runs ARE published
```

**Resilience**:
- Each Q result is appended to `runs/<timestamp>.jsonl` immediately. If the run crashes at Q 347/500, we resume from 348 (no re-pay of 347 Q's).
- Brain healthcheck (`GET /health`) before ingestion. If down, hard stop.
- LLM judge batched (10 Q per call) with exponential retry on rate limits.

**Dev loop** (~5 min, cost $0):
```bash
cd benchmarks
python -m runners.longmemeval --config config/dev.yaml
# output → benchmarks/runs/YYYY-MM-DD_HH-MM_dev.md (NOT committed)
```

**Release** (~1-3 h, cost ~$20-50 in Claude API):
```bash
python -m runners.longmemeval --config config/release.yaml --adapter brain
python -m runners.longmemeval --config config/release.yaml --adapter chromadb_raw
# output → docs/benchmarks/2026-XX-XX-longmemeval-s-{brain,chromadb_raw}.md
#        + append to docs/benchmarks/results.csv
```

## 5. Output formats

### 5.1 Per-run markdown (`docs/benchmarks/YYYY-MM-DD-<bench>-<adapter>.md`)

> Template below. **All numeric values (0.742, $43.20, etc.) are illustrative placeholders, not real scores.** Actual scores are produced by the release run.

```markdown
# LongMemEval-s — Brain full — 2026-XX-XX

**Config**: reader=claude-opus-4-7, judge=claude-opus-4-7, adapter=brain, N=500
**Commit**: <sha>
**Duration**: 2h 14min — **Cost**: $43.20 — **Mean latency/Q**: 16.1s

| Metric              | Score   |
|---------------------|---------|
| Recall@5            | 0.742   |
| Accuracy (global)   | 0.681   |

| Category               | Accuracy | N  |
|------------------------|----------|-----|
| Info extraction        | 0.85     | 100 |
| Multi-session reasoning| 0.62     | 100 |
| Temporal reasoning     | 0.54     | 100 |
| Knowledge updates      | 0.71     | 100 |
| Abstention             | 0.68     | 100 |

## Comparison (Claude-judged, same config)
| System        | Accuracy | R@5   |
|---------------|----------|-------|
| Brain full    | 0.681    | 0.742 |
| ChromaDB raw  | 0.612    | 0.710 |
| mem0 (re-run) | 0.XXX    | ...   |
| MemPalace (re-run) | ...  | ...   |

## Notes
- [honest caveats, known failure modes, config rationale]
```

### 5.2 CSV (`docs/benchmarks/results.csv`) — append-only

```csv
date,commit,benchmark,adapter,reader,judge,n,accuracy,recall_at_5,acc_info_ext,acc_multi_session,acc_temporal,acc_knowledge_upd,acc_abstention,cost_usd,duration_s,mean_latency_q_s
2026-04-20,abc123,longmemeval_s,brain,claude-opus-4-7,claude-opus-4-7,500,0.681,0.742,0.85,0.62,0.54,0.71,0.68,43.20,8040,16.1
2026-04-20,abc123,longmemeval_s,chromadb_raw,claude-opus-4-7,claude-opus-4-7,500,0.612,0.710,...
```

### 5.3 README summary table

A condensed table at top of `docs/benchmarks/README.md` showing latest run per (benchmark × adapter), sorted by date. No duplication in the main repo README — link from there.

## 6. Brain-Bench phase 5b (custom, agent workload)

**Goal**: measure whether Brain actually helps on real dev-agent tasks — not simulated QA.

**Source**: Money Claude Code transcripts, `~/.claude/projects/C--Money/*.jsonl`. ~30 days of real dev sessions.

**QA generation**: manual. 30-50 questions authored by the user, each tied to a real decision that happened in a real session. Each QA has:
- `question`: natural-language, agent-like ("pourquoi on a retiré Discord de Brain ?")
- `ground_truth`: extract from the transcript (short paragraph)
- `expected_sources`: list of session IDs where the answer lives
- `category`: decision / bug / architecture / tool-usage / preference

**Pipeline**: same as LongMemEval but with the Money dataset and custom metrics:
- Retrieval@k — did we surface the right session?
- Answer accuracy (LLM judge against ground_truth)
- Latency & cost

**Separation**: `runners/brain_bench.py`. Shares adapters, llm wrappers, report writer. Only dataset loader + metric aggregation differ.

**Not in MVP**: Marcel transcripts, synthetic QA generation, auto-extraction of QA from transcripts. Phase 5c.

## 7. Non-goals (explicit)

- **No CI** for benchmarks. Runs are manual decisions (each release run = human commit message with rationale).
- **No frontend viewer** yet. Phase 4 frontend will consume `results.csv`.
- **No Docker** for the harness itself. Only Brain runs in Docker; the harness is a local Python process.
- **No continuous integration with Money**. Brain-Bench uses Money transcripts as a *dataset*, not a live coupling.
- **No automated QA generation** in phase 5b. Hand-curated QAs only.

## 8. Success criteria

**Phase 5a (LongMemEval-s MVP)**:
1. `benchmarks/` directory exists, `pyproject.toml` installable
2. `scripts/setup.sh` clones LongMemEval dataset, downloads Ollama model
3. Dev run on subset 50 Q completes end-to-end with Ollama reader+judge, cost $0, <10 min wall time
4. Release run on full 500 Q with Claude Opus completes, publishes two reports (brain + chromadb_raw)
5. `docs/benchmarks/results.csv` contains both rows
6. README summary table committed
7. **Target scores** (release, Claude-judged): accuracy > 0.49 (mem0 baseline on GPT-4o-judged LongMemEval-s). Stretch: > 0.63 (Zep baseline). Note: these targets are from published GPT-4o-judge runs; absolute numbers may shift under Claude-judge but the *ordering* vs re-run mem0/MemPalace is what validates Brain.

**Phase 5b (Brain-Bench custom)**:
1. 30-50 manually-curated QA from Money transcripts in `benchmarks/datasets/brain_bench_v1.jsonl`
2. `runners/brain_bench.py` runs end-to-end on the custom dataset
3. Published report shows Brain delta vs ChromaDB raw on real agent-like queries

## 9. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| LongMemEval dataset is heavy (GB-scale) | Clone into `benchmarks/external/` (gitignored). Scripts handle download. |
| Ollama model not locally available | `scripts/setup.sh` runs `ollama pull llama3.1:70b`. Fallback to smaller model documented. |
| Claude API costs overshoot | Release runs are opt-in, never auto. Dev loop is Ollama-only by default. `--dry-run` flag. |
| LongMemEval judge is GPT-4o by convention — Claude judge gives different absolute scores | We re-run MemPalace and mem0 with the same Claude-judge config → apples-to-apples comparison is valid, even if absolute numbers differ from published. |
| ChromaDB baseline might beat Brain on certain categories | That's the point of ablation. Publish honestly. Use the signal to improve Brain, not hide it. |
| Brain-Bench is biased by the user (who writes both the QA and the ground truth) | Acknowledge in the report. Future phase 5c: have a second pair of eyes annotate. |

## 10. Implementation phases

1. **Scaffold** `benchmarks/` — pyproject, directory structure, empty modules with protocols
2. **Adapter + LLM wrappers** — `brain.py`, `chromadb_raw.py`, `ollama.py`, `anthropic.py`
3. **Runner: LongMemEval** — dataset loader, retrieval loop, judge, aggregator, report writer
4. **Dev run validation** — subset 50 Q on Ollama, verify end-to-end, cost $0
5. **Release run** — full 500 Q on Claude, publish first real report
6. **Re-run comparators** — mem0, MemPalace with same Claude config
7. **Phase 5b: Brain-Bench** — dataset curation (manual), runner, report

Phases 1-4 are coding. 5 is a decision (run when confident). 6 is research + wiring. 7 is its own cycle.
