---
id: 2026-04-28-l2-a-backend
title: L2-A — Topic-triggered retrieval (backend) + L0/L1 cross-agent + L3 doc clarification
status: approved
date: 2026-04-28
supersedes: (none)
relates_to:
  - docs/specs/2026-04-19-hook-architecture-design.md
  - docs/decisions/0002-hook-architecture.md
  - data/brainstorm-l2.md
  - README.md Phase 2b
---

# L2-A backend — Design

**Goal:** Ship L2 topic-triggered semantic retrieval at `wake_up`, refactor L0/L1 to cross-agent reads, and clarify that L3 already exists as `brain_search`. Backward-compatible with existing adapters; L2-B (adapter) ships separately.

**Roadmap phase:** R:phase-2b (extends Phase 2b hook architecture work)

## Scope (in)

- Refactor `backend/src/brain/hook.py:WakeUpHandler` to compute three layers (L0, L1, L2) with per-layer token budgets and structured layered output.
- L0 + L1 read paths: drop the `agent=req.agent` filter — call `store.search_by_tag(tag, agent=None, top_k=…)` (or equivalent — see "L0/L1 cross-agent" below) so memories are brain-level not agent-level.
- New helpers in `hook.py`: `_build_topic_query`, `_apply_threshold`, `_rerank_candidates`, `_fit_to_budget`, `_log_degraded`.
- L2 retrieval: `store.search(topic_query, top_k=BRAIN_L2_TOPK_RAW, agent=None)` → threshold filter → reranking → fit-to-budget.
- Extend `backend/src/brain/server.py` `/hook/wake_up` POST handler to accept three new optional body fields: `git_recent_commits`, `git_branch`, `claude_md_excerpt`. Pass them into `HookRequest` (extended).
- Extend `backend/src/brain/hook.py:HookRequest` dataclass with three new optional fields (defaulting to empty strings) — backward-compatible with old adapter payloads.
- New event type `degraded_wake_up` logged on cascade failures.
- Enrich existing `hook_wake_up` event metadata with: `memory_ids` (nested dict `{L0: [...], L1: [...], L2: [...]}`), `cosine_scores` (list of floats for L2 entries only, in order), `threshold_applied`, `tokens_per_layer` (dict `{L0, L1, L2}`).
- Two new env vars: `BRAIN_L2_THRESHOLD` (default `0.45`), `BRAIN_L2_TOPK_RAW` (default `20`).
- Tests: `backend/tests/test_brain/test_l2_rerank.py`, `test_l2_threshold.py`, `test_l2_cascade.py`, `test_l2_integration.py`, `test_wake_up_cross_agent.py`. Update existing `test_hook_wake_up.py::test_scopes_to_agent` (currently asserts isolation — rewrite to assert cross-agent retrieval).
- Docs: README Phase 2b checkbox update; `docs/decisions/0003-l2-l3-design.md` ADR; minor edit to `docs/specs/2026-04-19-hook-architecture-design.md` "Out of scope" → mark L2 as in-scope (added by 2026-04-28 spec).

## Scope (out — explicit YAGNI)

- Adapter changes (`scripts/brain_wake_up.py` collecting git/CLAUDE.md) — that is L2-B, separate PR, blocked by this one.
- `pre_turn` L2 hook (per-turn dynamic retrieval) — future cycle.
- Adaptive budget redistribution between layers — Q3 explicitly rejected.
- Cross-encoder reranker — V1 keeps the heuristic `score = cosine × (1 + log(access_count + 1) × 0.05) × exp(-age_days × 0.01)`.
- Topic-embedding cache — wake_up fires once per session, no caching at this scale.
- Real tokenizer — keep `len(text) // 4` heuristic per Q-open-5.
- Multi-language CLAUDE.md handling, BOM, encoding edge cases — UTF-8 only assumption.
- Frontend changes — none in this PR (monitor fidelity is a separate cycle).

## Constraints

- **Backward-compatible payload:** if adapter does not send `git_recent_commits`/`git_branch`/`claude_md_excerpt`, topic_query is empty → L2 = 0 silently (no `degraded_wake_up` event — empty topic is BY DESIGN per Q5, not a failure).
- **Cross-agent for L0/L1:** removing the agent filter changes existing behavior. The existing `test_scopes_to_agent` test in `test_hook_wake_up.py` asserts the OLD agent-isolated behavior — it must be rewritten as part of this PR (failing tests are not allowed to merge).
- **Per-layer budget caps, no redistribution:** L0 cap 100, L1 cap 300, L2 cap 500. Dead tokens drop.
- **Latency budget for L2:** ≤ 200 ms p95 (embedding + ANN + reranking). ChromaDB query timeout > 2 s → cascade to L2=0 with `degraded_wake_up`.
- **mypy is NOT a hard gate** — Brain convention.
- **pytest baseline 193**, expected ~205 after this PR (5–7 unit + 2–3 integration tests + cross-agent tests + L2-aware updates to existing tests).

## Architecture

### High-level data flow

```
POST /hook/wake_up
  body: {agent, project, session_id,
         git_recent_commits?, git_branch?, claude_md_excerpt?}
  │
  ├─ HookRequest(agent, project, session_id,
  │              git_recent_commits, git_branch, claude_md_excerpt)
  │
  └─ WakeUpHandler.handle(req)
        │
        ├─ L0 = store.search_by_tag("identity",  agent=None, top_k=5)
        │       └─ truncated to ≤ 100 tokens via _fit_to_budget
        │
        ├─ L1 = store.search_by_tag("preference", agent=None, top_k=10)
        │       └─ truncated to ≤ 300 tokens via _fit_to_budget
        │
        ├─ topic_query = _build_topic_query(req)
        │   if empty:
        │       L2 = []
        │       degraded = False  # silent — by design
        │   else:
        │       try:
        │           candidates = store.search(topic_query, agent=None,
        │                                     top_k=BRAIN_L2_TOPK_RAW)
        │           filtered   = _apply_threshold(candidates, BRAIN_L2_THRESHOLD)
        │           reranked   = _rerank_candidates(filtered)
        │           L2         = _fit_to_budget(reranked, cap=500)
        │       except Exception as e:
        │           L2 = []
        │           _log_degraded(req, reason="embedding_failed" | "db_timeout",
        │                         layer_affected="L2")
        │
        ├─ context = _format(L0, L1, L2)  # adds "## Topic" section if L2 non-empty
        │
        ├─ events.log("hook_wake_up", metadata={
        │       memory_ids: {L0: [...], L1: [...], L2: [...]},
        │       cosine_scores: [...],          # L2 entries only, in display order
        │       threshold_applied: 0.45,
        │       tokens_per_layer: {L0, L1, L2},
        │       tokens_approx, layers_loaded, duration_ms,
        │   })
        │
        └─ return WakeUpResponse(context, layers_loaded, tokens_approx, duration_ms)
```

### Reranking formula (Q4, locked)

```python
import math
def _rerank_candidates(candidates: list[dict]) -> list[dict]:
    now = time.time()
    for c in candidates:
        cosine     = 1.0 - c["distance"] / 2.0      # ChromaDB returns cosine distance
        access     = int(c.get("access_count", 0))
        created_at = c.get("created_at", "")        # ISO-8601 string; treat empty as "now"
        age_days   = _age_days(created_at, now)
        c["_rerank_score"] = cosine * (1.0 + math.log(access + 1) * 0.05) * math.exp(-age_days * 0.01)
    return sorted(candidates, key=lambda x: x["_rerank_score"], reverse=True)
```

`_age_days` parses ISO-8601 strings; on parse failure returns 0 (no age penalty rather than crashing).

### `_build_topic_query` format (resolves open question 1)

**Decision:** keep the prefixed/labeled format. Embedding models tokenize labels cheaply, and the labels carry topical signal ("branch:" anchors a developer-context embedding direction). Empirically (per the integration test fixture in `test_l2_integration.py`), labeled is at least as good as raw concatenation, and labels make the stored event metadata human-readable when debugging via `events.jsonl`.

```python
def _build_topic_query(req: HookRequest) -> str:
    parts = []
    if req.git_branch:
        parts.append(f"branch: {req.git_branch}")
    if req.git_recent_commits:
        parts.append(f"recent commits:\n{req.git_recent_commits}")
    if req.claude_md_excerpt:
        parts.append(req.claude_md_excerpt)
    return "\n\n".join(parts).strip()
```

If all three fields are empty/falsy, returns `""` → L2 = [] silently (no degraded event).

### `memory_ids` event metadata shape (resolves open question 2)

**Decision:** nested dict per layer, not a flat prefixed list. Reasons: (a) downstream monitor consumers want to render per-layer counts/breakdowns, and a nested dict makes that a one-line dict access; (b) flat strings push parsing logic into every consumer; (c) the existing `layers_loaded` field is already a dict — symmetry is cheap.

```python
metadata["memory_ids"] = {
    "L0": [m["id"] for m in identity],
    "L1": [m["id"] for m in prefs],
    "L2": [m["id"] for m in topic],
}
```

### `cosine_scores` shape

L2 entries only, in the order they appear in the rendered context (post-rerank, post-budget). Empty list if L2 is empty. Lets the monitor draw a per-entry score-vs-threshold visualization without re-scoring.

```python
metadata["cosine_scores"] = [round(m["_rerank_cosine"], 4) for m in topic]
```

### `_fit_to_budget` semantics

```python
def _fit_to_budget(memories: list[dict], cap: int) -> list[dict]:
    """Greedy: include memories in order while running total ≤ cap, drop the rest."""
    out, total = [], 0
    for m in memories:
        cost = len(m["content"]) // 4
        if total + cost > cap:
            break
        out.append(m)
        total += cost
    return out
```

Same heuristic as the current `_tokens` (`len(text) // 4`) — Q-open-5 keeps it.

### L0/L1 cross-agent — minimal change

`store.search_by_tag(tag, agent, top_k)` currently REQUIRES `agent`. Two options were considered:

1. Add an `agent: str | None = None` overload at the store layer; when None, drop the where-clause — symmetric with `search`.
2. Keep `search_by_tag` as-is and have the handler pass a sentinel agent.

**Decision: option 1.** The store is the right boundary for the read-path semantics — making the handler stitch a fake agent string would leak that detail into every caller. This is a 4-line change to `BrainStore.search_by_tag` (default `agent` param, conditional `where=` clause).

### Failure cascade (Q5, locked)

| Failure | Trigger | Effect | Event |
|---------|---------|--------|-------|
| Topic empty | `_build_topic_query` returns `""` | L2 = [] | none (silent — by design) |
| All candidates below threshold | `_apply_threshold` returns `[]` | L2 = [] | none (silent — by design) |
| Embedding crash | `store.search` raises (fastembed model OOM, etc.) | L2 = [], handler completes | `degraded_wake_up` reason=`embedding_failed` |
| ChromaDB timeout | wraps `store.search` in `concurrent.futures` w/ 2 s timeout, raises | L2 = [], handler completes | `degraded_wake_up` reason=`db_timeout` |
| L0 store failure | `store.search_by_tag` raises | L0 = [], handler continues | `degraded_wake_up` reason=`l0_failed` |
| L1 store failure | `store.search_by_tag` raises | L1 = [], handler continues | `degraded_wake_up` reason=`l1_failed` |

L0/L1 failure paths are added defensively — they did not exist pre-L2-A but cost ~5 LOC to wrap, so the cascade is symmetric across all three layers.

### Affected systems

- **HTTP API:** `POST /hook/wake_up` accepts three new OPTIONAL body fields (`git_recent_commits`, `git_branch`, `claude_md_excerpt`). All other routes unchanged. Backward-compatible: missing fields → empty strings → L2 = 0 silently.
- **MCP tools:** unchanged. `brain_search` IS L3 — documentation clarification only, no code touched.
- **Storage:** unchanged. No SQLite migration. ChromaDB schema unchanged. `BrainStore.search_by_tag` gains an optional `agent` parameter (default `None`); existing callers passing a string keep working.
- **Frontend:** none in this PR. Future monitor work consumes the enriched `hook_wake_up` event metadata; that consumer ships in the monitor cycle.
- **Installer (`npx brain`):** unchanged. Optional new env vars `BRAIN_L2_THRESHOLD`, `BRAIN_L2_TOPK_RAW` documented in README; defaults are sensible.
- **Scripts (Claude Code hooks):** unchanged in this PR. `scripts/brain_wake_up.py` change is L2-B's responsibility (blocked-by L2-A).
- **Benchmarks:** L2 should improve LongMemEval session-aware questions and LoCoMo retrieval recall once dogfooded. No benchmark code change in this PR; baseline measurement is a follow-up cycle.
- **Tests:** see "Test strategy" below.

### Test strategy

- **Unit (mocked store), 5–7 tests:**
  - reranking math correctness (cosine + access bonus + age decay; assert ordering on synthetic inputs)
  - threshold filter correctness (boundary at exactly 0.45, just above, just below)
  - token-budget fit (cap respected, ordering preserved within cap)
  - cascade — embedding raises → L2 = [], `degraded_wake_up` logged
  - cascade — ChromaDB timeout → L2 = [], `degraded_wake_up` logged
  - empty topic_query → L2 = [], no degraded event (silent path)
  - all candidates filtered out (threshold) → L2 = [], no degraded event
- **Integration (real ChromaDB, seeded fixture), 2–3 tests:**
  - 10-memory fixture; full embedding → search → threshold → rerank flow; assert top-N ordering matches expected based on fixture content
  - cross-agent retrieval — seed memories under `agent="A"` and `agent="B"`, request as `agent="A"`, assert L0/L1/L2 include both agents
  - HTTP layer — POST with new fields, assert response and event metadata enrichment
- **No snapshot tests** — Q6 explicitly rejects them (overkill while threshold tunable).
- **Update existing tests:**
  - `test_hook_wake_up.py::test_scopes_to_agent` is now misnamed and asserts the OBSOLETE agent-isolated behavior. Rewrite as `test_l0_l1_are_cross_agent` asserting both agents' memories appear (or move to `test_wake_up_cross_agent.py` and delete the old test). Builder picks one — checklist captures the deletion.

## Risks

1. **Threshold mis-calibration** — 0.45 too high → L2 rarely fires; too low → noise. Mitigation: env-var tunable, monitor surfaces `threshold_applied` per wake_up.
2. **Embedding consistency drift** — query and storage must use the same fastembed BGE model. Mitigation: model is already pinned in `pyproject.toml`; ADR documents the dependency.
3. **Cross-agent regression** — `test_scopes_to_agent` will fail post-refacto. Mitigation: explicitly handled in this PR's checklist (`SPEC-9` rewrites the test).
4. **`degraded_wake_up` consumers** — new event_type, current `events.jsonl` consumers (none in tree) might not know about it. Mitigation: ADR documents it; events are forward-compatible (consumers ignore unknown types).
5. **Latency budget breach under cold ChromaDB** — fastembed model load on first query can exceed 200 ms. Mitigation: `events.log` records `duration_ms`; if dogfood shows breaches, add a warmup path in a follow-up cycle (out of scope here).
6. **Reranking formula brittleness** — `created_at` parsing failures default age to 0; old memories with bad timestamps then over-rank. Mitigation: tested explicitly in `test_l2_rerank.py`; if dogfood reveals issues, formula evolves in a follow-up ADR.

## Consumer impact

- **Money / Marcel / future consumers:** zero. The new request fields are optional; missing = empty topic = L2 = 0. The existing `WakeUpResponse` shape is unchanged. Consumers that already POST to `/hook/wake_up` with `agent`/`project`/`session_id` get the same response shape; they additionally benefit from cross-agent L0/L1 (which is the same memory set or a strict superset, never less).
- **Brain dogfood:** existing wake_up calls continue to return identity + preference. Once L2-B ships, the same calls additionally return topic-relevant memories.
