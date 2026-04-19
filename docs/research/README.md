# Research

External studies that justify design decisions: competitive analysis, literature reviews, third-party benchmark ablations we relied on.

## What goes here

- **Competitive analysis** — what MemPalace, mem0, Zep, Letta do, where they win/lose
- **Literature summaries** — LongMemEval, LoCoMo, HELMET, Graphiti bi-temporal paper
- **Independent ablation write-ups** — when we reproduce a third-party claim (e.g., `lhl/agentic-memory` on MemPalace)

## What does NOT go here

- **Our own benchmark results** → [`../benchmarks/`](../benchmarks/)
- **Our own design specs** → [`../specs/`](../specs/)
- **Decision rationale** (distilled from research) → [`../decisions/`](../decisions/)

## Naming

`<topic>.md` — lowercase, hyphenated, no dates. Research is cumulative: append to the existing file, don't fork a new one per session.

## Index

- [`memory-systems.md`](memory-systems.md) — competitive landscape of LLM memory systems (MemPalace, mem0, Zep, Letta, Graphiti)
