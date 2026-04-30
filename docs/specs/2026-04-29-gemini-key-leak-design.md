# Gemini API key leak in docker logs — Design

**Goal:** Stop leaking `GOOGLE_API_KEY` in plaintext in backend logs by switching Gemini auth from query param to header and silencing httpx URL logs.
**Roadmap phase:** R:phase-2 (security hygiene; ad-hoc P:high)
**Scope (in):**
- Replace `?key=...` query param with `x-goog-api-key` header in `GeminiFlashExtractor.extract`.
- Set `logging.getLogger("httpx").setLevel(logging.WARNING)` at module top of `backend/src/brain/hook.py`.
- Two unit tests: outbound URL/header shape; httpx logger level after import.

**Scope (out):**
- OAuth migration for Gemini (V2+).
- App-wide httpx logging policy or a centralized HTTP client wrapper.
- Sanitizing/rotating already-leaked logs (impossible — already in container stderr).
- Rotating the exposed key (user action — flagged separately).
- Touching `benchmarks/src/brain_bench/adapters/brain.py` or `scripts/brain_*.py` httpx clients (different processes, no Gemini key flows through them).

**Constraints:**
- Single PR, ~30 min implementation.
- Must keep `extract` returning `list[ExtractedMemory]`, no signature change.
- Test baseline: 213 → 215 (two new tests, no regressions).
- Brain commit emoji: `🩹 Fix` for SPEC commits (security bug fix, not a new feature), `🧪 Test` for test commits.

## Architecture

`GeminiFlashExtractor.extract` currently builds `url = f"{self._API_URL}/{self._model}:generateContent?key={self._api_key}"` and calls `self._client.post(url, json=...)`. httpx's default INFO log emits the full URL including the query string, so every extraction writes the API key to stderr (visible via `docker logs brain`).

The fix has two layers:

1. **Auth via header.** Drop `?key=` from the URL; pass `headers={"x-goog-api-key": self._api_key}` to `self._client.post`. Google REST API documents both forms as supported (https://ai.google.dev/api/rest#authentication); header is the recommended pattern.
2. **Belt-and-suspenders log silencing.** Add at module top of `backend/src/brain/hook.py`:
   ```python
   import logging
   logging.getLogger("httpx").setLevel(logging.WARNING)
   ```
   This raises httpx's default `INFO` URL-emission to `WARNING`, so even a future regression that re-introduces query-param secrets in any httpx call originating from the backend process will not log them. The line lives in `hook.py` (not a global config module) because that's where the Gemini extractor lives and where the leak originated; a global app-wide config is YAGNI for one extractor.

Process scoping note: the other `httpx.Client` in this repo (`benchmarks/src/brain_bench/adapters/brain.py`) runs in a separate benchmark CLI process and is unaffected by the backend's logger config. The Claude Code hook scripts (`scripts/brain_*.py`) also run as separate processes. No cross-process side effects.

## Affected systems
- HTTP API: none (extractor is internal).
- MCP tools: none.
- Storage: no migrations, no re-index.
- Frontend: none.
- Installer (`npx brain`): none.
- Scripts (Claude Code hooks): none.
- Benchmarks: none — `benchmarks/src/brain_bench/adapters/brain.py` runs in a separate process and does not touch Gemini.
- Tests: 2 new unit tests in `backend/tests/test_brain/test_gemini_security.py`. Both use a fake `_client` injected via the existing `_client` constructor kwarg — no real network. Deterministic.

## Risks

1. **Header vs query-param API behavior.** Both are documented as supported; header is Google's recommendation. Resolution: post-merge manual smoke test — trigger one Claude Code Stop hook, observe Gemini returns 200 and structured memories appear via `/monitor`. If it fails, revert is one-line.
2. **Global httpx logger level affects other in-process httpx callers.** Verified by grep — no other `httpx.Client` is constructed inside the backend process (`benchmarks/` and `scripts/` httpx use lives in separate processes). FastAPI itself does not depend on httpx. Setting the level at module top of `hook.py` is safe and the smallest blast radius that still covers the backend. If a future PR adds another in-process httpx client, the WARNING level would suppress its INFO request logs too — that is intentional belt-and-suspenders behavior.

## Consumer impact

None. Money's legacy Brain runs separately on port 8611 with its own auth; this change is internal to Brain's standalone backend (port 8621). Marcel does not exist yet.
