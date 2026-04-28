---
id: 0003
title: L2 topic-triggered retrieval at wake_up + L3 = brain_search MCP
status: accepted
date: 2026-04-28
supersedes:
superseded_by:
relates_to:
  - docs/decisions/0002-hook-architecture.md
  - docs/specs/2026-04-28-l2-a-backend-design.md
---

## Context

Phase 2b shipped L0 (identity tag filter) and L1 (preference tag filter) in `WakeUpHandler`. Sessions received static token injections — same memories every time, independent of the current task. Brain needed semantic adaptivity to fulfill the cerveau-parfait vision. L3 (explicit deep semantic search) was already implemented as `brain_search` MCP tool but not documented as part of the L0–L3 taxonomy.

## Decision

**L2: topic-triggered semantic retrieval at `wake_up`**

- Fires once per session at `wake_up` (not `pre_turn` — deferred, see YAGNI below).
- Topic query built from three optional fields in the wake_up request payload: `git_recent_commits`, `git_branch`, `claude_md_excerpt`. If all empty → L2 = 0 silently (by design, not a failure).
- Retrieval: `store.search(topic_query, agent=None, top_k=BRAIN_L2_TOPK_RAW)` → threshold filter → reranking → budget cap.
- Reranking formula: `score = cosine × (1 + log(access_count + 1) × 0.05) × exp(-age_days × 0.01)` — favors recent, frequently-accessed, semantically relevant memories.
- Token budgets per layer: L0 cap 100, L1 cap 300, L2 cap 500. No redistribution between layers.
- Env vars: `BRAIN_L2_THRESHOLD` (default 0.45), `BRAIN_L2_TOPK_RAW` (default 20). `BRAIN_L2_TIMEOUT_S` is a module-level constant in `hook.py` (default 2.0 s) that tests monkeypatch.

**Cross-agent retrieval for L0, L1, and L2**

All three layers drop the `agent=` filter. Brain's access-control unit is the Brain instance (database), not the query. An identity memory stored by `claude-code` should benefit any other agent operating on the same Brain. Agent-level read/write ACL is deferred to Phase 6 (multi-tenant aggregator).

This required a 4-line change to `BrainStore.search_by_tag`: `agent` param now defaults to `None`; when `None`, no `where=` clause is applied.

**L3: `brain_search` MCP tool (already exists)**

L3 is the explicit, model-invoked deep search tier — agents call `brain_search` when they need to retrieve memories beyond what L2 auto-injects. This tool existed before this ADR; this ADR clarifies its role in the L0–L3 taxonomy. No code change for L3 in this cycle.

**Failure cascade**

| Failure | Trigger | Effect | Event |
|---------|---------|--------|-------|
| Empty topic | `_build_topic_query` returns `""` | L2 = [] | none (silent by design) |
| Below threshold | `_apply_threshold` returns `[]` | L2 = [] | none (silent by design) |
| Embedding crash | `store.search` raises | L2 = [] | `degraded_wake_up` reason=`embedding_failed` |
| ChromaDB timeout (> 2 s) | `concurrent.futures` timeout | L2 = [] | `degraded_wake_up` reason=`db_timeout` |
| L0 store failure | `search_by_tag` raises | L0 = [] | `degraded_wake_up` reason=`l0_failed` |
| L1 store failure | `search_by_tag` raises | L1 = [] | `degraded_wake_up` reason=`l1_failed` |

**Observability**

`hook_wake_up` event enriched with: `memory_ids` (nested dict per layer), `cosine_scores` (L2 entries, post-rerank order), `threshold_applied`, `tokens_per_layer`. New event type `degraded_wake_up` for cascade failures.

## Alternatives considered

- **Pre-turn L2 (per-turn dynamic retrieval):** Rejected for V1 — one code path to harden; pre-turn adds latency on every turn. Deferred to future cycle post-dogfood.
- **Adaptive budget redistribution:** Rejected — adds complexity, hurts predictability. Dead tokens drop.
- **Cross-encoder reranker:** Rejected for V1 — heuristic formula sufficient until dogfood reveals gaps.
- **Topic embedding cache:** Rejected — wake_up fires once per session at this scale.
- **Agent-level query isolation (keep old behavior):** Rejected — Brain is shared-brain-first; per-agent isolation is a future feature, not the default.

## YAGNI notes

- `pre_turn` L2 hook — future cycle
- Real tokenizer (keep `len // 4` heuristic)
- Topic embedding cache
- Multi-language CLAUDE.md handling
- Cross-platform git compatibility (adapter-side concern, L2-B)
