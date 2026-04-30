# Checklist — Storage layering 2c.1

**Linked spec:** [2026-04-30-storage-layering-2c1-design.md](2026-04-30-storage-layering-2c1-design.md)
**Budget:** 1.5 days. **Roadmap phase:** R:phase-2c.

**Commit emoji per CLAUDE.md:** `🧠 Feature` for [SPEC-N], `🧪 Test` for grouped test commits.

## Code

- [ ] [SPEC-1] Create `backend/src/brain/raw_buffer.py` with `RawEvent` Pydantic model (fields per spec §Backend), and a `RawBuffer` class with `__init__(root: Path)`, `append(event: RawEvent)`, `list_since(ts: datetime, limit: int = 1000)`, `rotate_if_needed()`, `purge_older_than(days: int)`. Use single-thread `queue.SimpleQueue` + dedicated daemon thread for serialized writes (no fcntl). File path: `<root>/brain_raw_buffer.YYYY-MM-DD.jsonl`. Atomic write = `f.write(json.dumps(...) + "\n")` with `f.flush()` per line.

- [ ] [SPEC-2] Add `POST /raw_event` endpoint in `backend/src/brain/server.py`. Body: `RawEvent` minus `event_id` and `timestamp` (server-assigns `uuid4()` and `datetime.now(UTC)`). Returns 200 with `{event_id, timestamp}`. On `RawBuffer` exception → log warning, return 200 with `{stored: false, reason}` (never 500 — this endpoint must not block client hooks).

- [ ] [SPEC-3] Modify `POST /hook/post_turn` in `server.py` to **also** write a `RawEvent(kind=assistant_message, content=turn.assistant, tool_use=...)` to the raw buffer BEFORE the existing Gemini extract logic. Wrap in `try/except: log.warning(...)` so failure to write raw never breaks the legacy path.

- [ ] [SPEC-4] Add `RawBuffer` instance to `server.py`'s app state on startup (`app.state.raw_buffer = RawBuffer(Path("/data/raw_buffer"))`). Wire it into the existing `drain_thread` loop: every iteration, call `raw_buffer.rotate_if_needed()` and `raw_buffer.purge_older_than(7)`.

- [ ] [SPEC-5] On server boot, run idempotent migration in `Store.__init__` (or wherever the ChromaDB collection is opened): for each entry in the `memories` collection where `metadata.storage_layer` is missing, set it to `"extracted"`. Use ChromaDB's `update` with the existing `id`. Log count `migrated=N` once.

- [ ] [SPEC-6] Create `scripts/brain_user_prompt.py` mirroring `scripts/brain_post_turn.py` structure (same imports, same `BRAIN_URL` env, same `derive_agent` helper). On stdin JSON `{prompt, session_id, cwd}`: builds `RawEvent(kind=user_message, content=prompt, agent=derive_agent(cwd), session_id, project=cwd)`, POSTs to `{BRAIN_URL}/raw_event` with `timeout=0.5`. Catches every exception, returns `{}` to stdout (UserPromptSubmit hook contract). Always exit 0.

- [ ] [SPEC-7] Create `scripts/brain_post_tool.py`: stdin JSON `{tool_name, tool_input, tool_response, session_id, cwd}`. Builds `RawEvent(kind=tool_use, content=json.dumps(tool_input)[:2000], tool_name, tool_input, tool_output_excerpt=str(tool_response)[:2000], agent, session_id, project=cwd)`. Same fire-and-forget pattern. Returns `{}` exit 0.

- [ ] [SPEC-8] Update `.claude/settings.json` to register `UserPromptSubmit` → `python scripts/brain_user_prompt.py` and `PostToolUse` → `python scripts/brain_post_tool.py`. Preserve existing SessionStart + Stop entries.

- [ ] [SPEC-9] Add basic redaction in `RawBuffer.append`: regex-strip `[A-Za-z0-9_-]{20,}` sequences that follow `key=`, `apikey=`, `Bearer `, `password=`, `token=`, replacing with `<redacted>`. Apply to `content` and `tool_output_excerpt` only.

## Tests

- [ ] [TEST-1] `backend/tests/test_brain/test_raw_buffer.py::test_append_writes_jsonl_line` — create `RawBuffer(tmp_path)`, append one event, assert file `tmp_path/brain_raw_buffer.YYYY-MM-DD.jsonl` exists with exactly one valid JSON line containing the event fields.

- [ ] [TEST-2] `test_raw_buffer.py::test_list_since_filters_by_timestamp` — append 5 events spaced 1 minute apart (use `freezegun` or pass timestamps explicitly), call `list_since(ts=event3.timestamp)`, assert returns events 3, 4, 5 only.

- [ ] [TEST-3] `test_raw_buffer.py::test_rotate_if_needed_creates_new_file_at_midnight` — patch `datetime.now` to one date, append, then patch to next day, call `rotate_if_needed()`, append again, assert two distinct files exist.

- [ ] [TEST-4] `test_raw_buffer.py::test_purge_older_than_drops_old_files` — create three day-files manually (`brain_raw_buffer.2026-04-20.jsonl` through `.04-30.jsonl`), call `purge_older_than(7)` with `now=2026-04-30`, assert files older than 7 days are deleted, returns count=2 (assuming `2026-04-20` and `2026-04-21` are both >7d old).

- [ ] [TEST-5] `test_raw_buffer.py::test_redaction_strips_secrets` — append event with `content="api_key=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123"`, read back, assert content contains `<redacted>` not the secret.

- [ ] [TEST-6] `backend/tests/test_brain/test_raw_event_endpoint.py::test_post_raw_event_returns_200_and_writes` — TestClient, POST valid body, assert 200 + body contains `event_id`, then read raw buffer and assert event present.

- [ ] [TEST-7] `test_raw_event_endpoint.py::test_post_raw_event_swallows_storage_failure` — monkeypatch `RawBuffer.append` to raise, POST event, assert 200 with `{stored: false}`, no exception bubbled.

- [ ] [TEST-8] `backend/tests/test_brain/test_post_turn_dual_write.py::test_post_turn_writes_to_raw_and_extracted` — mock GeminiFlashExtractor to return one fact, POST `/hook/post_turn` with a turn, assert: (a) one new entry in ChromaDB `memories`, (b) one new line in raw buffer with `kind=assistant_message`.

- [ ] [TEST-9] `backend/tests/test_brain/test_migration_storage_layer.py::test_migration_tags_unflagged_entries` — seed ChromaDB with 2 entries (no `storage_layer` metadata), call migration, assert both entries now have `storage_layer="extracted"`. Run again, assert no-op (count=0 logged).

- [ ] [TEST-10] `scripts/tests/test_brain_user_prompt.py::test_subprocess_posts_user_message` — captor HTTP server pattern from existing `test_brain_wake_up_l2.py`, run subprocess with stdin `{"prompt": "hello brain", "session_id": "s1", "cwd": "/x"}`, assert captor received POST to `/raw_event` with `kind=user_message`, `content="hello brain"`, then assert subprocess stdout is `{}`.

- [ ] [TEST-11] `scripts/tests/test_brain_user_prompt.py::test_subprocess_silent_on_brain_down` — set `BRAIN_URL=http://127.0.0.1:1` (unreachable), run subprocess, assert exit 0 and stdout `{}` (NEVER blocks user input).

- [ ] [TEST-12] `scripts/tests/test_brain_post_tool.py::test_subprocess_posts_tool_use_with_excerpt` — captor pattern, stdin `{"tool_name":"Bash","tool_input":{"command":"ls"},"tool_response":"a\nb\nc","session_id":"s1","cwd":"/x"}`, assert captor received `kind=tool_use`, `tool_name=Bash`, `tool_output_excerpt` contains "a\nb\nc".

## Storage / Migrations

- [ ] [DB-1] Idempotent ChromaDB migration on boot — covered by [SPEC-5]/[TEST-9].

## Verification gates

- [ ] [GATE-1] `cd backend && python -m ruff check .` — green
- [ ] [GATE-2a] `cd backend && python -m pytest -q` — 215 (baseline) + 9 new = 224 passing
- [ ] [GATE-2b] `python -m ruff check scripts/`
- [ ] [GATE-2c] `python -m pytest scripts/tests/ -q` — 19 (baseline) + 3 new = 22
- [ ] [GATE-3] Manual: rebuild Docker, restart Claude Code, run a 3-turn session with a tool call. Verify `docker exec brain ls /data/raw_buffer/` shows today's file with ≥9 events (3 user + 3 assistant + ≥3 tool).
- [ ] [GATE-4] `curl -s http://localhost:8621/storage_stats` — deferred to 2c.2; not part of 2c.1 gates.
