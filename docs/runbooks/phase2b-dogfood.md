# Phase 2b Dogfood Runbook

Measurement and acceptance procedure for the hook architecture MVP. Run this over ≥ 7 days of real Brain sessions before declaring Phase 2b merge-ready.

## Prerequisites

- Docker brain container up and healthy: `curl http://localhost:8621/health`
- `$GOOGLE_API_KEY` set in the environment that launched Docker
- Seeds landed (Task G1 ran successfully)
- `.claude/settings.json` references `brain_wake_up.py` + `brain_post_turn.py`
- Legacy `brain_hook.py` deleted

## Hard criteria (gate the Phase 2b merge)

| # | Metric | Target | How to measure |
|---|--------|--------|----------------|
| 1 | `/hook/wake_up` p95 latency | < 500 ms | Query events: `curl "http://localhost:8621/events?limit=500" \| jq '[.events[] \| select(.event_type=="hook_wake_up") \| .metadata.duration_ms] \| sort \| .[(length*0.95 \| floor)]'` |
| 2 | `/hook/post_turn` p95 latency | < 2000 ms | Same as above with `hook_post_turn` and `extraction_ms` |
| 3 | Session blocks from hook timeout | 0 | Scan Claude Code session logs for any aborted starts |
| 4 | Backend tests green | 100% | `cd backend && .venv/Scripts/python -m pytest -q` |
| 5 | Adapter tests green | 100% | `backend/.venv/Scripts/python -m pytest scripts/tests/ -q` |
| 6 | Dogfood sessions | ≥ 50 | Event log count: `curl .../events?limit=10000 \| jq '[.events[] \| select(.event_type=="hook_wake_up")] \| length'` |
| 7 | Coherent events | No silent drops | Compare count of `hook_wake_up` events vs. actual CC sessions started (qualitative) |

## Soft criteria (guide iteration)

- Subjective: "Brain knows who I am at session start, I don't re-explain preferences"
- Extracted memories per session: 5–20. < 5 = under-extraction, > 50 = over-extraction → tune Extractor prompt
- No massive duplicates, no 2k-token blobs — inspect via `curl .../search?query=X&agent=brain`

## Observability commands

```bash
# Activity over time
curl -s http://localhost:8621/events/timeline | python -m json.tool

# Recent hook events
curl -s "http://localhost:8621/events?limit=50" | python -c \
  "import json,sys; [print(e['event_type'], e.get('metadata',{})) \
   for e in json.load(sys.stdin).get('events',[]) \
   if e['event_type'].startswith('hook_')]"

# Current brain totals
curl -s http://localhost:8621/stats | python -m json.tool

# Inspect extracted memories
curl -s "http://localhost:8621/search?query=IDENTITY&agent=brain&top_k=10" | python -m json.tool
```

## Iteration loop during dogfood

1. Session happens → events logged
2. Review `curl .../stats` and new memories in `.../search`
3. If quality is off: adjust `GeminiFlashExtractor.SYSTEM_PROMPT`, rebuild Docker, next session uses new prompt
4. If latency is off: profile which step is slow (extraction vs. gate vs. store), optimize

## Known pre-dogfood TODOs (from code review)

These were surfaced during the Phase 2b implementation and should be addressed before or during the first dogfood week:

- **`PostTurnHandler` test coverage** — no unit test exercises the `rejected_by_gate > 0` path (content too short bypassed by fixture-lengthening). Add before declaring hard criterion #5 met.
- **`_fallback_content` drops `tool_calls`** — when extraction fails AND the turn is mostly tool-call-driven, the raw fallback loses 100% of signal. Fix before week 1.
- **Non-idempotent `seed_brain.py`** — gate dedupes only `event_type="error"`, so re-running seeds duplicates everything. Before re-seeding (after a schema change or wipe), `POST /reset {"agent":"brain"}` first. Content-hash dedup for context memories is a separate follow-up improvement.

## Exit criteria

Phase 2b MVP merges when:
- [ ] All 7 hard criteria above are green
- [ ] Legacy `brain_hook.py` deleted (Task G3) — **DONE**
- [ ] ADR 0002 written (Task G5)
- [ ] Phase 2b README checkboxes all checked

Deferred post-MVP items stay in the roadmap un-checked. Each becomes its own sub-project.
