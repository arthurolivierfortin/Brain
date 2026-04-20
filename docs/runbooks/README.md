# Runbooks

Operational how-tos. If a fresh agent or a new contributor asks "how do I X?", the answer should be a runbook, not a Slack thread or a session transcript.

## What goes here

- **Startup procedures** — "how to start Brain locally", "how to bring up the Docker stack"
- **Benchmark execution** — "how to run a smoke test", "how to run a release bench", "how to interpret output"
- **Recovery procedures** — "Brain container won't start", "ChromaDB corruption recovery"
- **Integration how-tos** — "how to wire Brain into a Claude Code project"

## What does NOT go here

- **Why something works the way it does** → [`../decisions/`](../decisions/) or [`../architecture/`](../architecture/)
- **Published bench results** → [`../benchmarks/`](../benchmarks/)

## Naming

`<action>.md` — imperative verb, lowercase, hyphenated. Examples: `start-brain-locally.md`, `run-release-bench.md`, `recover-chromadb.md`.

## Index

_(empty — fill as operational procedures stabilize)_
