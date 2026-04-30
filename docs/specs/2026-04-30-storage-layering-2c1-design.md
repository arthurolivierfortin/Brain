# SPEC — Storage layering 2c.1: Raw buffer + multi-hook capture

**Date:** 2026-04-30
**Issue:** TBD (opened on PR creation)
**Roadmap phase:** R:phase-2c
**Author decision basis:** [data/brainstorm-storage-layering.md](../../data/brainstorm-storage-layering.md), user direction "comme un cerveau, populer selon le texte de l'utilisateur chaque message de l'agent plus le context de l'agent".

## Goal in one sentence

Stand up a hippocampus-style raw episodic buffer (`L1`) that records every user message, every assistant message, and every tool-use context, separate from the existing Gemini-filtered store, so no signal is dropped at ingest time.

## Locked decisions

| Q | Decision | Rationale |
|---|----------|-----------|
| Q1 storage format | **JSONL append-only file** at `data/brain_raw_buffer.jsonl`, daily rotation `data/brain_raw_buffer.YYYY-MM-DD.jsonl`. | Simple, debuggable, no extra infra. Migrate to ChromaDB only if dogfood proves we need vector search over raw. |
| Q2 consolidation timing | **Deferred to 2c.2** (hourly cron). Phase 2c.1 only stands up the buffer, no consolidation. | One change per phase. |
| Q3 promotion logic | **Deferred to 2c.2.** Existing `Stop`-hook Gemini extract continues unchanged in 2c.1 — dual-write to raw + extracted. | Backwards-compatible during transition. |
| Q4 raw → consolidated | **Deferred to 2c.3.** Just dual-write for now. | |
| Q5 TTL | **7 days hard drop.** Daily rotation file ≥ 7 days old purged by background drain thread. | Privacy + size cap. |
| Q6 viz | **Deferred to 2c.4.** Adds storage_layer field to events for forward-compat. | |
| Q7 migration | Existing 10 ChromaDB memories tagged `storage_layer=extracted` on first server boot post-deploy via idempotent migration. | Zero disruption. |
| Q8 naming | Use `L1-raw / L2-extracted / L3-consolidated` for **storage**, leave existing L0-L3 docs alone for **retrieval** (rename in a separate doc-only PR — not in 2c.1). | Avoids merge conflict noise. |

## What "comme un cerveau" means concretely (the must-have)

The user said: "ça vienne populer selon le texte de l'utilisateur chaque message de l'agent plus le context de l'agent". Three capture surfaces:

1. **User text** — every user prompt → L1 raw entry. New `UserPromptSubmit` hook script.
2. **Agent text** — every assistant turn → L1 raw entry (already captured at Stop hook today, just write to L1 too).
3. **Agent context** — tool calls + tool results → L1 raw entry. New `PostToolUse` hook script.

That's the minimum to make L1 actually feel like a hippocampus. Without #1 and #3, the buffer is a 1-event-per-turn aggregate, which is what we already have.

## Scope (2c.1, in)

### Backend
- New module `backend/src/brain/raw_buffer.py`:
  - `append(event: RawEvent) -> None` — atomic line write to current day's file
  - `list_since(ts: datetime, limit: int = 1000) -> list[RawEvent]` — read all events with `timestamp >= ts`
  - `rotate_if_needed() -> Path | None` — opens new file at midnight UTC
  - `purge_older_than(days: int) -> int` — deletes day-files older than N days, returns count
- `RawEvent` schema (Pydantic):
  ```python
  class RawEvent(BaseModel):
      event_id: str  # uuid4
      timestamp: datetime  # ISO 8601 UTC
      kind: Literal["user_message", "assistant_message", "tool_use"]
      agent: str
      session_id: str
      project: str  # cwd
      content: str  # full text, no truncation
      tool_name: str | None = None
      tool_input: dict | None = None
      tool_output_excerpt: str | None = None  # first 2000 chars
      metadata: dict = {}
  ```
- New endpoint `POST /raw_event` accepting `RawEvent` (minus `event_id` + `timestamp`, server-assigns).
- Extend `POST /hook/post_turn` to **also** write a `kind=assistant_message` event to raw buffer (dual-write). Existing Gemini extract pipeline unchanged.
- Background `drain_thread` (already running every 60s in `server.py`) calls `raw_buffer.rotate_if_needed()` and `raw_buffer.purge_older_than(7)`.
- Migration on boot: scan `memories` collection, set metadata `storage_layer="extracted"` on entries that lack it. Idempotent.

### Hooks
- New `scripts/brain_user_prompt.py`:
  - Reads JSON from stdin: `{prompt, session_id, cwd, ...}` (Claude Code UserPromptSubmit hook contract)
  - POSTs `RawEvent(kind=user_message, content=prompt)` to `/raw_event`
  - Returns `{}` on success (UserPromptSubmit hook expects no output to skip injection)
  - Catches all exceptions silently (do NOT block user input on Brain failure)
- New `scripts/brain_post_tool.py`:
  - Reads JSON from stdin: `{tool_name, tool_input, tool_response, session_id, cwd, ...}` (Claude Code PostToolUse contract)
  - POSTs `RawEvent(kind=tool_use, content=str(tool_input)[:2000], tool_name, tool_input, tool_output_excerpt)`
  - Returns `{}` on success
  - Same exception swallowing
- `.claude/settings.json` registers the two new hooks alongside existing SessionStart + Stop.

### Tests
- `backend/tests/test_brain/test_raw_buffer.py` — unit: append, list_since, rotate (freezegun for date), purge, concurrent-write smoke
- `backend/tests/test_brain/test_raw_event_endpoint.py` — http: POST /raw_event with valid + invalid payloads
- `backend/tests/test_brain/test_post_turn_dual_write.py` — http: POST /hook/post_turn writes to both ChromaDB AND raw buffer
- `backend/tests/test_brain/test_migration_storage_layer.py` — migrates an unflagged entry, verifies metadata.storage_layer="extracted", idempotent on second run
- `scripts/tests/test_brain_user_prompt.py` — subprocess test with captor server, verify payload + silent failure
- `scripts/tests/test_brain_post_tool.py` — same pattern for PostToolUse

## Scope (2c.1, out — explicit YAGNI)

- Consolidation cron (Phase 2c.2)
- Gemini batched re-distillation (Phase 2c.2)
- L3 consolidated layer (Phase 2c.3)
- Monitor visualization changes (Phase 2c.4)
- L0-L3 retrieval rename (separate doc-only PR)
- Cross-agent consolidation patterns
- Memory deletion / forget
- Compression / archive of expired raw files
- Embedding raw events for vector search

## Architecture diagram

```
                    ┌──────────────────────┐
                    │  Claude Code session │
                    └──┬───────┬────────┬──┘
                       │       │        │
            UserPrompt │   PostTool     │ Stop
            Submit     │   Use          │
                       │       │        │
                       ▼       ▼        ▼
              brain_user_   brain_post_  brain_post_
              prompt.py     tool.py      turn.py
                       │       │        │
                       └───────┼────────┘
                               │
                          POST /raw_event           POST /hook/post_turn
                               │                          │
                               ▼                          ▼
                       ┌──────────────────┐      ┌──────────────────┐
                       │  raw_buffer.py   │      │ Gemini extract   │
                       │  L1 — JSONL      │      │ existing logic   │
                       │  daily rotation  │      └────────┬─────────┘
                       │  7-day TTL       │               │
                       └──────────────────┘               ▼
                                              ┌──────────────────┐
                                              │ ChromaDB         │
                                              │ L2 — extracted   │ ← also dual-written
                                              └──────────────────┘  from /hook/post_turn
```

## Risks

1. **Hook latency on UserPromptSubmit blocks user input** — must be fire-and-forget OR ≤200ms. Mitigation: hook script uses `httpx.post(timeout=0.5)` and silently swallows. If Brain is down, hook returns `{}` instantly.
2. **Disk fill** — 50 turns/day × 5KB/turn × 7d = 1.75 MB. Trivial. But add a `max_bytes_per_day=50MB` safety in `append()` that drops the entry rather than letting one runaway session fill disk.
3. **Concurrent writes** — Brain backend is single-process FastAPI but post_turn + raw_event can race. Use file lock (fcntl on Linux, msvcrt on Windows) or restrict raw writes to a single-thread queue. Choice: single-thread queue via existing `drain_thread`-style worker, simpler than locks.
4. **Re-extraction of facts already in L2** — none yet, deferred to 2c.2.
5. **`tool_output` may contain secrets** — never log secrets. Truncate to 2000 chars and run a simple regex redaction pass on `tool_output_excerpt` for `KEY=`, `Bearer `, `password=`. Out-of-scope-but-flagged for 2c.2 hardening.

## Verification gates

- [ ] `cd backend && ruff check .` passes
- [ ] `cd backend && python -m pytest -q` — 215 baseline + 6 new passes (target 221)
- [ ] `python -m ruff check scripts/` passes
- [ ] `python -m pytest scripts/tests/ -q` — all green incl. 2 new
- [ ] Manual smoke: rebuild Docker, run a Claude Code session, verify `data/brain_raw_buffer.YYYY-MM-DD.jsonl` shows ≥3 entries (user+assistant+tool) per turn

## Cycle phase

R:phase-2c (new). After 2c.1 ships, `STATUS.md` updates to track 2c.2/3/4 as remaining boxes.
