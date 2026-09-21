# Brain — Agent Guide

You are working in the **Brain** repo, a drop-in memory system for LLM apps. If you have never seen this project, read [README.md](README.md) first, then come back here.

This file sets communication style, coding rules, and the "how to continue" protocol for fresh agents.

---

## Coding rules

1. **No comments unless the WHY is non-obvious.** Well-named identifiers carry the WHAT.
2. **No backwards-compat shims** without user approval. Delete, don't deprecate.
3. **No features outside the task.** A bug fix is not a refactor pass.
4. **No premature abstractions.** Three similar lines > one generic util.
5. **No `type: ignore` / `noqa` without a comment explaining why.**
6. **Decimal for money-like values.** Never float for anything precision-sensitive.
7. **No mocks at service boundaries in integration tests.** Hit the real thing (local Docker is fine).

## Project context (the short version)

Brain was extracted from [Money](https://github.com/arthurolivierfortin/Money), a trading bot where a SQLite + embeddings memory service grew useful enough to stand alone. Goal: a drop-in you can install in any repo with `npx brain` — like MemPalace, but with a real frontend.

**Key decisions already locked** (see README for rationale):
- Python backend (FastAPI), Next.js 15 frontend
- SQLite + local vector DB — no Neo4j, no cloud dependencies
- Bi-temporal facts (stolen from Graphiti)
- L0/L1/L2/L3 context layering (stolen from MemPalace)
- MCP-first exposure
- Local mode default, aggregator mode opt-in

## Labels et docs

- Labels propres à Brain, en plus de `T:*` / `S:*` du socle : `bench`, `research`, et les aires `area/backend`, `area/benchmarks`, `area/docker`, `area/docs`, `area/frontend`, `area/mcp`.
- **Bug found during a run?** → one issue per bug, immediately. Link the bug to the run artifact (JSONL path + commit SHA).
- **Benchmark run?** → issue with config used, dataset, scores, cost, duration. Commit the JSONL + markdown report, reference them in the issue.
- **Design docs** live in `docs/specs/` and `docs/plans/`. The issue links to them, not the other way around — git is the source of truth, issues are the discussion log.
- Specs et plans sont append-only et les ADR numérotés : voir « Documentation structure » ci-dessous.

Rationale: Brain is a research project as much as an engineering one. Scores, ablations, and reversed decisions need to be discoverable 6 months later without spelunking session logs.

## Documentation structure (MANDATORY)

All docs live under `docs/`. No doc file at the root of `docs/` except `README.md` (the master index).

```
docs/
├── README.md                  # master index — what each folder contains
├── architecture/              # durable design decisions (system shape, modules, data flow)
├── research/                  # competitive analysis, external benchmark studies
├── specs/                     # YYYY-MM-DD-<topic>-design.md (brainstorming outputs)
├── plans/                     # YYYY-MM-DD-<topic>-implementation.md (plan skill outputs)
├── runbooks/                  # "how to start Brain locally", "how to run a bench", troubleshooting
├── benchmarks/                # published run reports (markdown) + results.csv
├── improvements/              # tracked technical debt, one file per item when it grows
└── decisions/                 # ADR-style records: NNNN-<slug>.md, why we chose X over Y
```

**Rules:**
- Each subfolder has a `README.md` = index + naming convention + what-goes-here.
- Every PR that changes observable behavior MUST touch the relevant doc(s). Reviewer blocks the merge otherwise. Doc-freshness > doc-volume.
- Specs and plans are **append-only** history. Don't edit a merged spec — write a new dated spec if the design evolves. Issues/ADRs cross-link the delta.
- ADRs are numbered (`0001`, `0002`, …) and never renumbered. Supersede by writing a new ADR that references the old one as `Supersedes: 0003`.
- No doc lives in `benchmarks/` (code) or `backend/` except READMEs for that code unit's consumers. Long-form docs go in `docs/`.

**Deferred:** A separate docs site (mkdocs/Docusaurus) lands when `docs/` exceeds ~30 files OR when an external consumer (Marcel) starts depending on Brain.

## External systems this repo talks to

- **Brain standalone HTTP API** — `http://localhost:8621` (this repo's Docker service, host-port 8621→container 8611). MCP SSE on `http://localhost:8620`.
- **Money legacy Brain** — `http://localhost:8611` (Money's embedded Brain, still running until the dogfood cutover). Do NOT confuse with this repo's service.
- **Gemini Flash** — extracts structured memories from Claude Code turn deltas inside Brain backend (`GeminiFlashExtractor`, `GOOGLE_API_KEY` env var passed into the Docker container)
- **Claude Code statusLine + SessionStart + Stop hooks** — `.claude/settings.json` wires them to `scripts/brain_statusline.py`, `scripts/brain_wake_up.py`, `scripts/brain_post_turn.py`

## Docker safety — non-negotiable invariants

Context: on 2026-04-17 an agent ran `docker compose --project-name docker --remove-orphans down` from `C:/Brain/docker/` and wiped 10 Money containers (volumes survived, images cached). The project name `docker` was derived from the parent directory and collided with Money's `C:/Money/docker/` compose. **Never repeat this.**

1. **Every compose.yml MUST start with `name: <explicit>` at top level.** Never let the project name be inferred from the directory (directories named `docker/` collide across repos).
2. **`--remove-orphans` is destructive cross-project.** Forbidden unless:
   - `docker compose ls` has been inspected
   - `docker compose config` confirms the target project name
   - The user has explicitly approved after seeing the orphan list
3. **Any "Found orphan containers [...]" warning = STOP.** Read the list. If any container outside the current repo appears, the project namespace is contaminated — fix `name:` and retry. Never force through.
4. **`--project-name` flag: never pass a name that is not unique to this repo.** If you need to operate on another project's containers, `cd` into that repo and use its compose file.
5. **Transparency over silent recovery.** If a destructive action leaks across projects, tell the user immediately, list the exact impact (containers lost, volumes touched, data state), and wait for instructions. Never "fix it quietly".

## Where to find missing context

If something's unclear:
- **Design decisions** → README.md
- **Competitive landscape / why we chose X** → docs/research/memory-systems.md
- **Existing Brain code to extract** → `C:\Money` (grep for `brain_` in src/)
- **Money's `.claude/` for reference** → `C:\Money\.claude\`
- **User's memory / past conversations** → `C:\Users\arthu\.claude\projects\C--Brain\*.jsonl` (once sessions exist)
