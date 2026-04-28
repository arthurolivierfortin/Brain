# Checklist — L2-A backend (topic-triggered retrieval + L0/L1 cross-agent + L3 doc)

**Linked spec:** [2026-04-28-l2-a-backend-design.md](2026-04-28-l2-a-backend-design.md)

## Code

- [x] [SPEC-1] Extend `HookRequest` dataclass with three optional fields (`git_recent_commits: str = ""`, `git_branch: str = ""`, `claude_md_excerpt: str = ""`) defaulted to empty strings — `backend/src/brain/hook.py`
- [x] [SPEC-2] Refactor `BrainStore.search_by_tag(tag, agent, top_k)` so `agent` becomes `agent: str | None = None`; when `None`, drop the `where={"agent": ...}` clause and read all agents — `backend/src/brain/store.py`
- [x] [SPEC-3] Add `_build_topic_query(req: HookRequest) -> str` to `WakeUpHandler` returning the labeled-concat format from spec; returns `""` if all three optional fields are empty — `backend/src/brain/hook.py`
- [x] [SPEC-4] Add `_apply_threshold(candidates: list[dict], threshold: float) -> list[dict]` filtering on `cosine_similarity = 1 - distance/2 > threshold`; preserves input order — `backend/src/brain/hook.py`
- [x] [SPEC-5] Add `_rerank_candidates(candidates: list[dict]) -> list[dict]` implementing `score = cosine × (1 + log(access+1) × 0.05) × exp(-age_days × 0.01)`, with `_age_days(iso_ts, now)` helper that returns 0 on parse failure; sort descending by score — `backend/src/brain/hook.py`
- [x] [SPEC-6] Add `_fit_to_budget(memories: list[dict], cap: int) -> list[dict]` greedy include in order while running `len(content) // 4` total ≤ cap — `backend/src/brain/hook.py`
- [x] [SPEC-7] Add `_log_degraded(events, req, reason: str, layer_affected: str, fallback_used: str = "") -> None` writing `degraded_wake_up` event with metadata `{reason, layer_affected, fallback_used, agent, session_id}` — `backend/src/brain/hook.py`
- [x] [SPEC-8] Refactor `WakeUpHandler.__init__` to accept `events: EventLog` and read env vars `BRAIN_L2_THRESHOLD` (default `0.45`) + `BRAIN_L2_TOPK_RAW` (default `20`) once; refactor `WakeUpHandler.handle` to: drop `agent=req.agent` from L0/L1 search_by_tag calls (cross-agent), apply per-layer caps via `_fit_to_budget` (L0=100, L1=300, L2=500), build topic_query and run L2 pipeline (search → threshold → rerank → fit_to_budget) wrapped in try/except calling `_log_degraded` on failure, and update `_format` to render a `## Topic` section when L2 non-empty — `backend/src/brain/hook.py`
- [x] [SPEC-9] Server-side `/hook/wake_up` POST handler: read `git_recent_commits`, `git_branch`, `claude_md_excerpt` from JSON body (default `""`), pass them into `HookRequest`, instantiate `WakeUpHandler(store, events)`, then enrich the existing `events.log("hook_wake_up", ...)` call with `memory_ids` (nested dict per layer), `cosine_scores` (list, L2 entries only), `threshold_applied`, `tokens_per_layer` — `backend/src/brain/server.py`
- [ ] [SPEC-10] Replace the obsolete `test_scopes_to_agent` in `backend/tests/test_brain/test_hook_wake_up.py` (asserts agent isolation, now broken by the refacto) — delete it; new cross-agent assertions live in TEST-9 (`test_wake_up_cross_agent.py`) — `backend/tests/test_brain/test_hook_wake_up.py`
- [ ] [SPEC-11] README Phase 2b roadmap: tick `[x]` for "L2 topic-triggered retrieval"; clarify in the same section that "L3 explicit deep semantic search API" IS the existing `brain_search` MCP tool (mark `[x]` and add a sentence pointing to ADR 0003) — `README.md`
- [ ] [SPEC-12] New ADR `docs/decisions/0003-l2-l3-design.md` per ADR template (id 0003, title "L2 topic-triggered retrieval at wake_up + L3 = brain_search MCP", status accepted, date 2026-04-28); cover: cross-agent decision, threshold/rerank choice, env vars, degraded_wake_up event_type, why no pre_turn yet — `docs/decisions/0003-l2-l3-design.md`
- [ ] [SPEC-13] Append to `docs/specs/2026-04-19-hook-architecture-design.md` an "Update 2026-04-28" footer noting that "L2 topic-triggered retrieval + L3 deep semantic search" moved from Out-of-scope to In-scope via 2026-04-28-l2-a-backend-design.md (append-only, do NOT edit existing prose) — `docs/specs/2026-04-19-hook-architecture-design.md`

## Tests

- [x] [TEST-1] Reranking math correctness: synthetic candidates with controlled cosine/access/age, assert sort order matches the manually computed scores — `backend/tests/test_brain/test_l2_rerank.py::test_rerank_orders_by_composite_score`
- [x] [TEST-2] Threshold filter: candidates spanning above/at/below 0.45, assert below-threshold excluded and at-threshold excluded (strict `>`); `BRAIN_L2_THRESHOLD` env var override respected — `backend/tests/test_brain/test_l2_threshold.py::test_apply_threshold_strict_and_env_override`
- [x] [TEST-3] `_fit_to_budget` respects cap, preserves input order, drops items that would overflow — `backend/tests/test_brain/test_l2_threshold.py::test_fit_to_budget_caps_and_preserves_order`
- [x] [TEST-4] Cascade — embedding raises: monkeypatch `store.search` to raise, assert L2=[], `degraded_wake_up` event logged with `reason="embedding_failed"` — `backend/tests/test_brain/test_l2_cascade.py::test_embedding_failure_logs_degraded`
- [x] [TEST-5] Cascade — ChromaDB timeout: monkeypatch `store.search` to sleep > timeout, assert L2=[], `degraded_wake_up` event logged with `reason="db_timeout"` — `backend/tests/test_brain/test_l2_cascade.py::test_db_timeout_logs_degraded`
- [x] [TEST-6] Silent path — empty topic_query (no new fields sent): assert L2=[] AND no `degraded_wake_up` event written — `backend/tests/test_brain/test_l2_cascade.py::test_empty_topic_is_silent`
- [x] [TEST-7] Silent path — all candidates below threshold: seed two memories, request with topic that scores < 0.45 against both; assert L2=[] AND no `degraded_wake_up` event — `backend/tests/test_brain/test_l2_cascade.py::test_all_below_threshold_is_silent`
- [ ] [TEST-8] Integration — full L2 pipeline against real ChromaDB seeded with 10 fixture memories; assert top-N ordering and that `cosine_scores` event metadata is populated and matches the rendered context order — `backend/tests/test_brain/test_l2_integration.py::test_full_l2_pipeline_against_real_chromadb`
- [ ] [TEST-9] Cross-agent — seed memories tagged `identity` and `preference` under `agent="A"` AND `agent="B"`; call `WakeUpHandler.handle(HookRequest(agent="A", ...))`; assert both agents' memories appear in L0 and L1 (and in L2 once topic_query non-empty) — `backend/tests/test_brain/test_wake_up_cross_agent.py::test_l0_l1_l2_are_cross_agent`
- [ ] [TEST-10] HTTP integration — POST `/hook/wake_up` with the three new fields populated; assert 200 + response shape unchanged + the persisted `events.jsonl` `hook_wake_up` event contains the enriched metadata keys (`memory_ids`, `cosine_scores`, `threshold_applied`, `tokens_per_layer`) — `backend/tests/test_brain/test_hook_http.py::test_wake_up_accepts_topic_fields_and_enriches_event_metadata`

## Storage / Migrations

- [ ] [DB-0] None — no SQLite migration, no ChromaDB re-index. The new event_type `degraded_wake_up` is a free-form string, no schema change needed in `events.py`.

## Verification gates

- [ ] [GATE-1] `cd backend && python -m ruff check .` passes
- [ ] [GATE-2] `cd backend && python -m pytest -q` passes (baseline 193, expect ~205 after this PR: +10 new tests, -1 deleted test, ~+3 from existing-test updates)
- [ ] [GATE-3] Frontend skipped — no `frontend/` changes in this PR

**Note:** mypy is NOT a hard gate for Brain. Builder/judge MAY run it for advisory signal but failures don't block.

## Commit prefixes (Brain convention)

- `🧠 Feature` — SPEC-1, 3, 4, 5, 6, 7, 8, 9 (new code paths, new behavior)
- `🧬 Refactor` — SPEC-2 (cross-agent refacto on `search_by_tag`)
- `🧪 Test` — TEST-1..10, SPEC-10 (test deletion is a test commit)
- `📓 Docs` — SPEC-11, 12, 13
