# Brain Benchmark Results

Each published run lives in a dated `YYYY-MM-DD-<benchmark>-<adapter>.md`
file. `results.csv` is the append-only machine-readable log (one row per run).
To produce a run, see `benchmarks/README.md` at the repo root.

## Methodology — we measure deltas, not absolute scores

Brain is not chasing a leaderboard number. What matters is **how much Brain adds to a given reader**. So every release run produces three artifacts per benchmark, and the meaningful quantities are the **differences between them**:

| Adapter | What it represents |
|---------|--------------------|
| `none` | The reader with **no retrieved context** — its own parametric knowledge alone |
| `chromadb_raw` | Reader + **naïve vector search** — what raw embedding retrieval delivers |
| `brain` | Reader + **full Brain** — gate, graph, composite scoring, decay |

Two deltas are the numbers we care about:

- **`raw` − `none`** = what the embedding model adds
- **`brain` − `raw`** = what Brain's structure adds on top of the embedding

A high `brain` absolute score that matches a high `raw` score means the embedding is doing everything and Brain is cosmetic. A small `brain − raw` gap on a strong reader can hide a large gap on a weaker one — hence the reader choice below.

## Reader choice — Haiku, not Opus

We run the **reader on Haiku 4.5** (200k context, constrained reasoning) and never on Opus 4.7 (1M context, premium reasoning).

**Why:** Opus can ingest an entire LongMemEval dossier (50 sessions × 2k tokens ≈ 100k) directly into its 1M context window and reason its way to the answer **without any functional retrieval**. Any score gain Brain appears to deliver to Opus is contaminated by Opus compensating for missing or noisy memories. Running on Haiku forces Brain to actually contribute — gains there propagate upward (Sonnet and Opus benefit automatically), gains on Opus alone may be artifacts.

**Judge choice is independent.** The judge compares two strings to a ground truth — a narrow, non-generative task. Using a premium judge (Opus) there is defensible and minimizes false-positive CORRECTs.

## Configs

| Config | Reader | Judge | Use | Cost per 500Q × 3 adapters |
|--------|--------|-------|-----|----------------------------|
| `dev.yaml` | Ollama local | Ollama local | Iteration, debugging | $0 |
| `validation.yaml` | Haiku 4.5 | Sonnet 4.6 | Pre-merge / weekly regression | ~$12 |
| `rigorous.yaml` | Haiku 4.5 | Opus 4.7 | Premium judge, opt-in | ~$26 |

We do NOT maintain a config that runs Opus as reader. If future needs require it (external comparison, specific methodology), add an opt-in config with an explicit justification in the run issue.

## Interpreting an ablation report

Every release run publishes three paired reports (one per adapter). Read them as a group:

- If `brain − raw` is large and positive across categories: structure helps. Ship.
- If `brain ≈ raw`: embedding is doing the work. Either the structure is broken, or the benchmark doesn't stress structure (LongMemEval is known-light on temporal, multi-session). Investigate before claiming progress.
- If `brain < raw` on any category: regression. Open an issue. Don't ship.
- If `raw ≈ none`: the benchmark isn't stressing retrieval at all; the reader is answering from parametric knowledge. Switch benchmark or increase question difficulty.

## Reader/judge note — comparing to published numbers

Published-literature scores (mem0 49%, Zep 63.8%, MemPalace 96.6%) use GPT-4o as both reader and judge. Absolute numbers here are **not directly comparable** — different judges = different strictness = different distributions. If we ever need apples-to-apples, we re-run the comparator with our exact reader + judge config.

## Files

- `results.csv` — append-only, machine-readable (one row per adapter run)
- `YYYY-MM-DD-<benchmark>-<adapter>.md` — human-readable report per run
- Run triplets share a date + benchmark and differ only by adapter: `2026-05-01-longmemeval_s-none.md`, `...-chromadb_raw.md`, `...-brain.md`
