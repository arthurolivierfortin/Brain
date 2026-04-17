# Brain

Drop-in AI memory system for LLM-powered apps and agents. Extracted from [Money](https://github.com/arthurolivierfortin/Money) to stand on its own — installable in any repo with one command.

**Status**: phase 1 extraction in progress (2026-04-16). Backend core copied from Money (`backend/src/brain/`, 9 modules, 143 tests green). Docker + installer + frontend pending. See [Roadmap](#roadmap).

---

## What this is

A local-first, Python-backed memory layer that any LLM app can consume via MCP. A Next.js frontend provides a memory browser, graph viz, and live stream. Designed to match or beat MemPalace's drop-in UX while delivering a power-user UI that MemPalace and mem0 lack.

## Install UX target (the bar to hit)

```bash
# One command — drops Brain into the current repo
npx brain
# → starts backend (Python) + frontend (Next.js) via Docker
# → auto-registers the MCP in .claude/settings.json
# → opens http://localhost:8700
```

Inspired by MemPalace's `pip install mempalace && mempalace init`, which is the current gold standard for memory-system drop-ins. We match the simplicity and add a frontend.

## Architecture (target)

```
brain/
├── backend/          # Python (FastAPI) — HTTP API + MCP server
├── frontend/         # Next.js 15 + Tailwind + shadcn — memory browser, graph viz
├── docker/
│   └── compose.yml   # backend:8611, frontend:8700
├── installer/        # Node script — npx brain
├── benchmarks/       # LongMemEval, LoCoMo harness + results
├── scripts/          # Client-side hooks (copy into consumer repos)
│   ├── brain_hook.py         # Claude Code Stop hook — POST session delta
│   ├── brain_statusline.py   # Claude Code statusLine — branch + ctx + brain state
│   └── brain_save_now.py     # Manual mid-session save trigger
└── docs/
    └── research/             # Competitive analysis
```

**Key decisions already made:**
- Backend: Python 3.12+ / FastMCP (existing Brain code is Python — mechanical extraction)
- Frontend: Next.js 15 + Tailwind + shadcn/ui (user's stack, Vercel-ready)
- Storage: **ChromaDB** (persistent, embedded) + `fastembed` for local embeddings. No external DB. Zep's Neo4j requirement is a drop-in killer.
- Fact extraction: currently rule-based (inherited from Money). LLM-based extraction is a phase-improvement item.
- MCP-first: 5 tools currently (`brain_store`, `brain_search`, `brain_related`, `brain_forget`, `brain_stats`). 29-tool expansion is phase-improvement.
- UI modes: **local** (per-repo drop-in, default) + **aggregator** (multi-brain, opt-in)

**Deferred to phase-improvement** (see [docs/improvements.md](docs/improvements.md)):
- Dynamic types — current `MemoryType` enum and gate `_NOISE_TYPES`/`_SIGNIFICANT_TYPES` frozensets are trading-biased hardcoded. Target: emerge from usage.
- Bi-temporal facts with validity windows (stolen from Graphiti)
- L0/L1/L2/L3 context layering (~170 token wake-up)
- mypy strict re-enabling (34 errors in inherited code)

See [docs/research/memory-systems.md](docs/research/memory-systems.md) for the full competitive analysis.

## Why this exists

Money accumulated a Brain service (SQLite + embeddings + MCP) that turned out to be broadly useful. Extracting it lets:

1. **Marcel** (Quebec grocery app, separate repo) and other future projects consume the same Brain
2. **Benchmark publicly** — LongMemEval / LoCoMo scores for credibility
3. **Ship a frontend** that neither MemPalace nor mem0 has locally
4. **Decouple the Brain lifecycle** from Money's trading concerns

Money keeps its current embedded Brain running until the new one is mature and dogfooded for 14+ days without regression.

## Research TL;DR (full version: [docs/research/memory-systems.md](docs/research/memory-systems.md))

| System | Install | UI | LongMemEval | Op burden |
|--------|---------|-----|-------------|-----------|
| **MemPalace** | `pip install` + Claude plugin | None (CLI + MCP) | 96.6% raw, 84.2% compressed | Low (ChromaDB) |
| **mem0** | `pip install mem0ai` + API key | Cloud dashboard only | 49% | Cloud-first |
| **Letta** | `npm i -g @letta-ai/letta-code` | ADE (cloud-locked) | N/A | Medium |
| **Zep/Graphiti** | pip + Neo4j/FalkorDB/Kuzu | Cloud dashboard | 63.8% | High (3 systems) |

**MemPalace caveats** (per lhl/agentic-memory analysis):
- 96.6% is measuring the embedding model, not their spatial structure
- AAAK compression regresses 12.4% (the "lossless" claim is false)
- Contradiction detection claimed in README but not implemented
- 7 commits, 11 days old — viral marketing outpaces maturity

**Our positioning:**
- Match MemPalace's install UX exactly
- Deliver a real frontend (gap in the market)
- Publish honest, ablated benchmarks (MemPalace's credibility gap)
- Ship bi-temporal facts (Graphiti's strength without Neo4j)

## Roadmap

### Phase 0 — Scaffolding (DONE)
- [x] Repo initialized with `.claude/` configs
- [x] Client-side scripts (hook, statusline, save-now) copied from Money
- [x] Research notes committed
- [x] Python dependency manager: **uv**
- [x] `backend/` layout (src-layout, `pyproject.toml`)

### Phase 1 — Backend extraction (IN PROGRESS)
- [x] Inventory of Money's Brain service (13 modules + 10 tests)
- [x] Copy 9 core modules (`store`, `gate`, `graph`, `memory`, `enrichment`, `events`, `pending_queue`, `decisions`, `server`) + 9 test files
- [x] Rename imports `money.brain` → `brain`, purge `money.core.*`, replace yaml-config with env vars
- [x] Install via uv, ruff clean, **143/143 pytest green**
- [ ] `docker compose up` — backend reachable on :8611, `/health` OK
- [ ] Dogfood: point Money's `BRAIN_URL` env var to the new container, run for a week

### Phase 2 — MCP server
- [ ] Port existing MCP tools (`brain_store`, `brain_search`, `brain_related`, `brain_stats`, `brain_forget`)
- [ ] Add the 29-tool surface MemPalace ships (wings/rooms/halls metaphor — or our equivalent)
- [ ] Claude plugin marketplace submission: `claude plugin install brain`

### Phase 3 — Installer
- [ ] `npx brain` Node script — detects Docker, drops compose.yml, starts containers, registers MCP
- [ ] Sub-commands: `brain stop`, `brain logs`, `brain benchmark`

### Phase 4 — Frontend
- [ ] Next.js 15 App Router scaffold in `frontend/`
- [ ] Memory browser (table + filters)
- [ ] Graph viz for `brain_related` (Cosmograph or Sigma.js)
- [ ] Live stream (SSE) of new memories
- [ ] Per-agent diary view

### Phase 5 — Benchmarks
**Strategy** (brainstormed 2026-04-17):
- LLM runner: Ollama (local, free) for dev loop; Claude/GPT-4o for published runs
- Ablations: minimal — **Brain full vs ChromaDB raw baseline** (avoids MemPalace trap: their 96.6% is the embedding, not the structure). Full ablations (no gate / no graph / no decay) deferred to v2.
- Two-phase: LongMemEval-s first (comparable, publishable), then Brain-Bench custom (concrete agent usage on Money/Marcel transcripts).

**Tasks**:
- [ ] Clone `xiaowu0162/LongMemEval`, write adapter wiring Brain HTTP API
- [ ] Ollama-backed dev loop (Llama 3.1 70B or Qwen 2.5): iterate adapter on 50-Q subset at $0 cost
- [ ] Run LongMemEval-s full 500 Q with Claude Opus reader + judge — publish score
- [ ] Re-run MemPalace + mem0 with the same Claude config for apples-to-apples comparison
- [ ] Ablation: Brain full vs ChromaDB raw — report the delta honestly
- [ ] Target: beat mem0's 49%, aim at Zep's 63.8%
- [ ] Phase 5b: Brain-Bench custom — ingest Money/Marcel transcripts, design QA covering dev-agent use cases
- [ ] Phase 5c: Add LoCoMo (snap-research/locomo)
- [ ] Benchmark viewer page on frontend, version-over-version diff

### Phase 6 — Aggregator mode
- [ ] Same Next.js codebase, different launch flag
- [ ] Reads `~/.brain/config.json` list of brain URLs
- [ ] Port 8700 fixed, brain selector in top bar
- [ ] Cross-brain search (opt-in)

### Phase 7 — Money migration + Brain-legacy removal
- [ ] Exit criteria: Brain standalone matches LongMemEval ≥ Money's current (measure first), 14 days dogfood without regression
- [ ] Switch Money to consume standalone Brain
- [ ] Delete Money's embedded Brain service

## Repo dependencies for a fresh agent

**Money** (`C:\Money`) — parent repo. Has:
- Working Brain service (Python, port 8611) — the code to extract
- `.claude/settings.json` — reference for this repo's config
- `scripts/brain_hook.py` / `scripts/brain_statusline.py` — already copied here

**Marcel** (`C:\Marcel`) — planned consumer. Next.js app. Will use `npx brain` once the installer lands.

## How a fresh Claude agent continues work

1. Read `CLAUDE.md` (this repo) for coding style and communication preferences
2. Read `docs/research/memory-systems.md` for the competitive landscape
3. Read this README's [Roadmap](#roadmap) for phase breakdown
4. Check `git log` for recent work
5. Pick the earliest unchecked box in the roadmap
6. Before coding: confirm the plan with the user (preference: no surprises)

## Communication & collaboration preferences

See `CLAUDE.md`. Non-negotiables:
- French-first communication with the user
- Blunt, critical, no glazing — this is an infrastructure project where ambiguity costs time
- No trailing summaries after work
- Never commit without being asked

## License

TBD. Target: MIT (like MemPalace) once the first release cut is tagged.
