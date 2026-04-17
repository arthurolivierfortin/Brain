# Brain Benchmark Results

Each published run lives in a dated `YYYY-MM-DD-<benchmark>-<adapter>.md`
file. `results.csv` is the append-only machine-readable log (one row per
run). To produce a run, see `benchmarks/README.md`.

## Latest scores

_(populated automatically by release runs — see CSV for the authoritative history)_

## Interpreting the ablation

Every release publishes **two runs**: `brain` (full) and `chromadb_raw`
(bare ChromaDB baseline). The delta between them is what Brain's structure
adds on top of the embedding model.

- If `brain` ≫ `chromadb_raw`: the gate, graph, and composite scoring help.
- If `brain` ≈ `chromadb_raw`: the embedding is doing all the work. Signal
  to revisit the design — **not** to hide the score.

## Reader/judge note

Scores are produced with Claude Opus 4.7 as both reader and judge.
Published-literature scores for mem0 (49%), Zep (63.8%) and MemPalace (96.6%)
use GPT-4o. Absolute numbers are NOT directly comparable across judges. When
we want to compare, we re-run the comparator with our Claude config.

## Files

- `results.csv` — append-only, machine-readable
- `YYYY-MM-DD-<benchmark>-<adapter>.md` — human-readable report per run
