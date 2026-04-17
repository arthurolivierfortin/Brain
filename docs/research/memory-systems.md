# Brain Extraction — Memory Systems Research

Date: 2026-04-16
Purpose: inventory the landscape before extracting Brain into its own repo, so we can steal the best UX patterns and avoid the worst architecture traps.
Scope: install UX, frontend/UI, architecture, benchmark methodology, licensing, maturity.

---

## TL;DR — What to steal, what to avoid

**Steal:**
- **MemPalace's install command** (`pip install X && X init`) and its **Claude Code plugin marketplace** integration. One line to drop in.
- **Letta's ADE (Agent Development Environment)** concept for the frontend — visual memory inspector, real-time tool calls, context state. Gold standard for UI power.
- **LongMemEval** (ICLR 2025) as the primary benchmark target. It's the de facto standard in 2026.
- **Mining** existing artifacts (convos, projects) retroactively — MemPalace does this, mem0/Letta/Zep don't.
- **MCP-first** exposure (29 tools in MemPalace, we already do this).
- **L0/L1/L2/L3 context layering** — load 170 tokens always, expand on demand.

**Avoid:**
- **Zep's operational footprint** — requires Neo4j + Graphiti + compatible graph DB = 3 systems minimum. Kills drop-in.
- **MemPalace's inflated benchmark claims** — their headline 96.6% is raw ChromaDB (embedding model), not their spatial structure. AAAK compression regresses 12.4%. The lhl/agentic-memory analysis rips this apart.
- **mem0's cloud-first model** — drop-in only if you have an API key.
- **No UI** (MemPalace's current state) — leaves a huge gap.

---

## 1. MemPalace (user's reference — "easy to drop in")

### Install UX (the bar we must match or beat)

```bash
pip install mempalace
mempalace init ~/projects/myapp
mempalace mine ~/projects/myapp                    # ingest projects
mempalace mine ~/chats/ --mode convos              # ingest conversations
mempalace search "why did we switch to GraphQL"
```

**Claude Code integration** — the killer move:
```bash
claude plugin marketplace add MemPalace/mempalace
claude plugin install --scope user mempalace
```
That's it. Tools appear, no manual MCP config editing. This is the UX pattern we need to copy.

**Dependencies:** Python 3.9+, chromadb ≥ 0.4.0, pyyaml ≥ 6.0. **No API keys, no internet needed post-install.** Fully local.

### Architecture — method of loci metaphor

- **Wings** — top-level categories (people, projects)
- **Rooms** — topics within wings (e.g., `auth-migration`, `ci-pipeline`)
- **Halls** (identical per wing) — memory types:
  - `hall_facts` — decisions locked in
  - `hall_events` — sessions and milestones
  - `hall_discoveries` — breakthroughs
  - `hall_preferences` — habits and opinions
  - `hall_advice` — recommendations
- **Closets** — summaries pointing to original content
- **Drawers** — verbatim original files, never summarized
- **Tunnels** — cross-wing connections linking related rooms

### Context loading stack (what to copy)

| Layer | Content | Size | Loading |
|-------|---------|------|---------|
| L0 | Identity / system prompt | ~50 tokens | Always |
| L1 | Team, projects, preferences | ~120 tokens (AAAK) | Always |
| L2 | Room-level recent sessions | on demand | topic-triggered |
| L3 | Deep semantic search | on demand | explicit query |

Total wake-up: 600–900 tokens. **This is the pattern** — don't load the whole brain on every turn.

### MCP tools (29 total)

- **Palace read** (6): `mempalace_status`, `mempalace_search`, `mempalace_list_wings`, etc.
- **Palace write** (2): `mempalace_add_drawer`, `mempalace_delete_drawer`
- **Knowledge graph** (4): `mempalace_kg_query`, `mempalace_kg_add`, `mempalace_kg_timeline`
- **Navigation** (6): `mempalace_traverse`, `mempalace_find_tunnels`
- **Drawer management** (3)
- **Agent diary** (2) — per-agent wing + diary
- **System** (2)

### No UI

**MemPalace has no web frontend.** Purely CLI + MCP. This is a gap we can exploit — a powerful frontend becomes our differentiator.

### Benchmark claims (with critical caveats)

| Benchmark | MemPalace | Caveat |
|-----------|-----------|--------|
| LongMemEval R@5 (raw verbatim) | 96.6% | Measures ChromaDB embedding, not palace structure |
| LongMemEval R@5 (AAAK compressed) | 84.2% | -12.4% regression — "lossless" claim is false |
| LoCoMo R@10 | 60.3% | Described as "mediocre" (competitors 83–89%) |
| Wake-up cost | ~170 tokens | Genuinely best-in-class |

### Critical weaknesses (from lhl/agentic-memory analysis)

- Headline benchmark is the embedding model, not the architecture
- "Zero information loss" claim is false
- Contradiction detection claimed in README but **not implemented in code**
- Knowledge graph is simple triple lookup, no multi-hop traversal
- Single ChromaDB collection (no isolation)
- O(n) performance for palace graph ops — doesn't scale
- No decay/forgetting mechanism
- Naive slug-based entity IDs, no entity resolution
- **Only 7 commits, created 2026-04-05** — extremely early-stage despite viral marketing (22K stars in 48h per Medium)

### License

MIT — we can learn from the code freely.

---

## 2. mem0 — the popular commercial player

### Install UX

```bash
pip install mem0ai
```
```python
from mem0 import MemoryClient
client = MemoryClient(api_key="your-api-key")
```

**Cloud-first** — requires an API key by default. OSS self-host exists but is secondary.

### Architecture

- Extracts facts (not full transcripts) via LLM
- Default LLM: `gpt-5-mini`
- Works with OpenAI / Anthropic / Ollama / custom
- Claims ~90% token reduction vs full-context approaches
- Graph backend optional (FalkorDB drop-in plugin via runtime patching)

### Benchmark

- LongMemEval (GPT-4o): **49.0%** — far below MemPalace raw and Zep

### UI

Web dashboard exists but cloud-hosted only. No local UI.

### What to steal

- The **fact-extraction** approach (vs storing whole transcripts) — reduces noise and cost
- The **graph backend is pluggable** pattern (good abstraction)

### What to avoid

- Cloud-first model breaks drop-in ethos
- 49% LongMemEval — we should not ship below this

---

## 3. Letta (formerly MemGPT) — the ADE reference

### Install UX

**Desktop agent:**
```bash
npm install -g @letta-ai/letta-code
```

**Server:** Docker image, or managed cloud ($20–200/mo).

### Architecture — "LLM as OS"

- Core memory (context = RAM)
- Archival memory (vector store = disk)
- Recall memory (chat history = swap)
- Agent manages its own memory via function calls

Stateful agents that evolve over time. Similar conceptual model to MemPalace's L0/L1/L2/L3.

### ADE — Agent Development Environment (the UI gold standard)

- Visual interface for debugging agent behavior
- Memory state inspection across all three tiers
- Real-time tool call monitoring
- Included in managed cloud

**This is what our frontend should aim at.** A Next.js version of the ADE scoped to Brain's model.

### What to steal

- ADE feature set — memory state inspector, live tool calls, context window viz
- Stateful agent paradigm (matches Claude Code's session model)

### What to avoid

- Cloud dependency for the UI (ADE is tied to Letta's managed platform)
- Heavy framework commitment — Letta is a full agent framework, we want a memory layer

---

## 4. Zep / Graphiti — the temporal graph specialist

### Install UX (the cautionary tale)

- Zep Community Edition **deprecated April 2025**
- Self-host path: Graphiti + **Neo4j / FalkorDB / Kuzu** graph DB
- Minimum 3 systems to provision and operate

### Architecture

- Temporal knowledge graph
- Facts stored as nodes with start/end validity windows
- Entity resolution across conversations + structured records
- Bi-temporal model (event time + ingestion time)

### Benchmark

- LongMemEval (GPT-4o): **63.8%** — strong temporal reasoning category
- +15 points over mem0 on temporal tasks

### What to steal

- **Bi-temporal facts with validity windows** — crucial for "this was true until X changed"
- Entity resolution approach

### What to avoid

- Operational burden kills drop-in. "Run Graphiti + manage Neo4j" is NOT the same as "docker run brain".
- Our drop-in MUST be embedded DB (SQLite) + embeddings, no external DB.

---

## 5. Benchmark landscape

### LongMemEval (ICLR 2025) — primary target

- 500 meticulously curated questions
- 5 abilities tested: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention
- Settings: 115K tokens (LongMemEvalₛ) up to 1.5M tokens (LongMemEvalₘ)
- Evaluation: GPT-4o as judge (>97% agreement with humans) + Recall@k + NDCG@k
- 3 stages evaluated: indexing, retrieval, reading
- **30% accuracy drop** observed in commercial assistants on sustained interactions
- Repo: `xiaowu0162/LongMemEval`
- **Current leaderboard reference points:** MemPalace raw 96.6%, Zep 63.8%, mem0 49%

### LoCoMo (Snap Research, ACL 2024) — secondary

- Multi-session dialogues
- Up to 32 sessions, ~600 turns (~16K tokens) per dialogue, 6–12 months simulated span
- Images included (multi-modal)
- Event graphs with up to 25 events
- Human F1 ~88 vs best LLM baselines 37–42 — humans still dominate
- Temporal questions especially hard (models 20–30 F1 vs humans 92.6)
- Repo: `snap-research/locomo`

### LoCoMo-Plus (2026) — newest

- Cognitive memory under cue-trigger semantic disconnect
- Latent constraints retention across long conversations
- Useful as a stretch goal, not initial target

### Setup cost estimate for running LongMemEval

- Clone repo, download dataset (~gigabytes)
- Provision LLM (GPT-4o for judge — costs ~$X per full run)
- Write adapter that plugs memory system into their harness
- One full run: ~500 questions × (indexing + retrieval + reading) = likely $20–100 in API costs depending on context size used
- Multiple runs needed for versioning / ablations

---

## 6. Key insights for Brain extraction

### Install UX target

Match MemPalace exactly:
```bash
pip install brain-mcp
brain init
# or
claude plugin install brain
```
Plus bonus: `docker run` one-liner for the full backend + UI stack.

### Frontend positioning — our differentiator

MemPalace has **no UI**. Letta's ADE is cloud-locked. This is an open lane.

Brain's frontend should deliver:
1. **Memory browser** — search, filter, pagination (table CRUD for power users)
2. **Graph visualization** — Cosmograph/Sigma.js for `brain_related` results
3. **Live stream** — SSE of new memories as hooks fire
4. **Benchmark viewer** — LongMemEval/LoCoMo results with version-over-version diff
5. **Per-agent diaries** — inspired by MemPalace's agent wings

### Architecture decisions informed by research

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite + ChromaDB (or similar local vector DB) | Drop-in like MemPalace; no external DB like Zep |
| Fact extraction | LLM-based (opt-in) | Better than rule-based (MemPalace weakness); pluggable LLM |
| Temporal model | Bi-temporal with validity windows | Steal from Graphiti; crucial for "what was true when" |
| Context layering | L0/L1/L2/L3 pattern | Proven wake-up cost minimization |
| MCP tools | Match MemPalace's 29-tool surface | Already proven to work in Claude Code |
| Backend | Python (FastAPI) | Existing Brain is Python; extraction is mechanical |
| Frontend | Next.js 15 + Tailwind + shadcn | User's stack; Vercel-ready for public benchmark viewer |
| Install | `pip install` + Claude plugin marketplace | Only viable drop-in pattern in 2026 |

### Benchmark strategy

**Phase 1 (MVP):** LongMemEval-s (115K tokens setting) only. Publish score. Target ≥ mem0's 49% (easy bar), aim at Zep's 63.8% (stretch).

**Phase 2:** Full LongMemEval-m + LoCoMo. Publish comparative dashboard in the frontend.

**Phase 3:** Run ablations — with/without graph, with/without fact extraction, with/without temporal — to prove architecture contributions (MemPalace's fatal gap: can't isolate structure's contribution from embedding's).

### Critical lessons from MemPalace's failure modes

1. **Publish honest benchmarks.** State the isolation clearly: "this score is the embedding model, not our structure." Ablate.
2. **Don't claim features you haven't coded.** Contradiction detection, multi-hop graph traversal — only ship when implemented.
3. **Start with single-collection simplicity**, plan for isolation strategy before scale matters.
4. **Write a decay/forgetting mechanism from day one.** Indefinite accumulation rots the store.
5. **Entity resolution is not slug matching.** Plan for real resolution (embeddings-based) even if v1 is naive.

---

## Sources

- [MemPalace README](https://github.com/milla-jovovich/mempalace/blob/main/README.md)
- [MemPalace critical analysis (lhl/agentic-memory)](https://github.com/lhl/agentic-memory/blob/main/ANALYSIS-mempalace.md)
- [MemPalace: Viral AI Memory System (Medium)](https://medium.com/@creativeaininja/mempalace-the-viral-ai-memory-system-that-got-22k-stars-in-48-hours-an-honest-look-and-setup-26c234b0a27b)
- [mem0 GitHub](https://github.com/mem0ai/mem0)
- [mem0 docs](https://docs.mem0.ai/)
- [Letta GitHub](https://github.com/letta-ai/letta)
- [Letta docs](https://docs.letta.com/concepts/memgpt/)
- [Graphiti (Zep) GitHub](https://github.com/getzep/graphiti)
- [Zep benchmarks vs mem0 (Atlan)](https://atlan.com/know/zep-vs-mem0/)
- [Supermemory vs Zep (April 2026)](https://blog.supermemory.ai/supermemory-vs-zep/)
- [LongMemEval GitHub (xiaowu0162)](https://github.com/xiaowu0162/LongMemEval)
- [LongMemEval paper (arXiv)](https://arxiv.org/abs/2410.10813)
- [LoCoMo benchmark page](https://snap-research.github.io/locomo/)
- [LoCoMo paper (arXiv)](https://arxiv.org/pdf/2402.17753)
- [LoCoMo-Plus (2026 extension)](https://arxiv.org/abs/2602.10715v1)
- [Mem0 vs Zep vs LangMem vs MemoClaw comparison (DEV)](https://dev.to/anajuliabit/mem0-vs-zep-vs-langmem-vs-memoclaw-ai-agent-memory-comparison-2026-1l1k)
- [Best AI agent memory frameworks 2026 (Atlan)](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)
