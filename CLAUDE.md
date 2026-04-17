# Brain — Agent Guide

You are working in the **Brain** repo, a drop-in memory system for LLM apps. If you have never seen this project, read [README.md](README.md) first, then come back here.

This file sets communication style, coding rules, and the "how to continue" protocol for fresh agents.

---

## Communication style (MANDATORY)

**French-first.** The user writes in French. Respond in French by default. Technical terms stay English when that's clearer.

**Blunt. No glazing.** This is infrastructure — ambiguity costs time and money.
- Never praise adequate work. "Ça marche" ≠ "c'est bon à merger".
- Name problems directly: "c'est cassé", "ça va échouer sous charge", "ce design est fragile" are acceptable.
- Quantify when possible: "coût ~1500 appels API/jour" > "c'est cher".
- Challenge assumptions: ask "qu'est-ce qui pète si X échoue?" before agreeing with the user.
- Admit ignorance: "je ne sais pas" > guess confident.
- No trailing summaries — the user reads diffs.
- No diplomatic hedging — remove "peut-être", "on pourrait considérer", "il serait bon de".

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

## How to start a task (every time)

1. **Read STATUS**: `git log --oneline -10` to see recent work.
2. **Re-read the relevant README section** — it's the source of truth for decisions.
3. **Write a short plan**:
   - What am I trying to accomplish? (one sentence)
   - Steps (numbered)
   - Files touched
   - What could go wrong
   - How to verify it worked
4. **Confirm the plan with the user** before editing multiple files or making architecture moves. The user prefers explicit approval for anything beyond a focused fix.
5. **Work one sub-task at a time.** Commit and move on, don't batch.

## Verification protocol

Run before reporting any task complete:

```bash
# When Python code exists:
ruff check .
mypy .
pytest

# When frontend exists:
pnpm lint
pnpm typecheck
pnpm test
```

Paste the output in the conversation. "Should work" is not verification.

## Commit convention

When the user asks for a commit, use brain/neuro emoji prefixes:

- `🧠 Feature: ...` — new capability
- `🩹 Fix: ...` — bug fix
- `📓 Docs: ...` — documentation only
- `🧹 Chore: ...` — maintenance, deps, scaffolding
- `🧪 Test: ...` — tests added/fixed
- `🧬 Refactor: ...` — no behavior change

Always add the `Co-Authored-By` line. Never use `--no-verify` without explicit user approval.

## PR workflow

No agent has been built for Brain yet. For now: feature branch → push → `gh pr create` → human reviews. The Money dev-cycle / release-train infrastructure does NOT apply here yet.

## External systems this repo talks to

- **Brain standalone HTTP API** — `http://localhost:8621` (this repo's Docker service, host-port 8621→container 8611). MCP SSE on `http://localhost:8620`.
- **Money legacy Brain** — `http://localhost:8611` (Money's embedded Brain, still running until the dogfood cutover). Do NOT confuse with this repo's service.
- **Gemini Flash** — summarizes Claude Code session deltas in `scripts/brain_hook.py` (`GOOGLE_API_KEY` env var)
- **Claude Code statusLine + Stop hook** — `.claude/settings.json` wires them up

## Subagent rules

- **Never** `subagent_type="general-purpose"` — it crashes silently in Docker and has caused lost work in Money.
- Use typed agents defined in `.claude/agents/` when available.

**Current agents** (adapted from Money, stripped of trading context):

| Agent | Model | When to use |
|-------|-------|-------------|
| `builder` | opus | Implement one feature from a GitHub Issue end-to-end (branch → code → tests → PR, does not merge) |
| `code-quality` | haiku | After any code change — runs ruff/mypy/pytest + frontend lint/types/tests. Reports only, does not fix |
| `reviewer` | opus | Review open PRs independently — no context from builder, strict quality checklist |
| `research-planner` | sonnet | Before complex implementation — produces `data/plan_verdict.json` with files to create/modify, risks, deps |
| `think` | opus | Propose next feature from roadmap — creates ONE GitHub Issue per cycle |

**Not ported from Money** (trading-specific or cycle-specific): `market-analyst`, `risk-auditor`, `strategy-tester`, `self-improver`, all four `release-train-*`. Add Brain-equivalents only when a real need appears.

## Anti-hallucination

1. Never claim "the benchmark passes" without showing the score output.
2. Never claim "tests pass" without pasting the runner output.
3. Never claim "Brain is running" without showing a successful healthcheck (`curl localhost:8621/health` for this repo's standalone Brain).

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

## What a fresh agent should do first

1. Read this file (done if you're reading).
2. Read `README.md`.
3. Read `docs/research/memory-systems.md` — it's the reason every decision in README exists.
4. `git log --oneline -10` to see what's landed.
5. Open `README.md` [Roadmap](README.md#roadmap), find the earliest unchecked box in the current phase.
6. Propose a plan for that box to the user before editing.

## Where to find missing context

If something's unclear:
- **Design decisions** → README.md
- **Competitive landscape / why we chose X** → docs/research/memory-systems.md
- **Existing Brain code to extract** → `C:\Money` (grep for `brain_` in src/)
- **Money's `.claude/` for reference** → `C:\Money\.claude\`
- **User's memory / past conversations** → `C:\Users\arthu\.claude\projects\C--Brain\*.jsonl` (once sessions exist)
