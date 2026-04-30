# Checklist — Gemini API key leak fix

**Linked spec:** [2026-04-29-gemini-key-leak-design.md](2026-04-29-gemini-key-leak-design.md)

## Code
- [x] [SPEC-1] Switch Gemini auth from query param to header in `GeminiFlashExtractor.extract`: remove `?key={self._api_key}` from the URL and pass `headers={"x-goog-api-key": self._api_key}` to `self._client.post`. — `backend/src/brain/hook.py`
- [x] [SPEC-2] Add module-top `logging.getLogger("httpx").setLevel(logging.WARNING)` (and the required `import logging`) in `hook.py` so httpx stops emitting full request URLs at INFO. — `backend/src/brain/hook.py`

## Tests
- [x] [TEST-1] Inject a fake `_client` capturing the `post` call; assert the outbound URL ends with `:generateContent` (no `?key=`, no `self._api_key` substring anywhere in the URL) AND `headers["x-goog-api-key"] == api_key`. — `backend/tests/test_brain/test_gemini_security.py::test_extract_uses_header_auth_not_query_param`
- [x] [TEST-2] After importing `brain.hook`, assert `logging.getLogger("httpx").level == logging.WARNING`. — `backend/tests/test_brain/test_gemini_security.py::test_httpx_logger_level_is_warning`

## Storage / Migrations
- [ ] [DB-0] None

## Verification gates
- [ ] [GATE-1] `cd backend && python -m ruff check .` passes
- [ ] [GATE-2] `cd backend && python -m pytest -q` passes (baseline 213 → 215, no regressions)
- [ ] [GATE-3] frontend skipped (no frontend touched)

**Note:** mypy is NOT a hard gate for Brain (per CLAUDE.md). Builder/judge MAY run it for advisory signal but failures don't block. Brain commit emoji: `🩹 Fix` for SPEC commits (security bug fix), `🧪 Test` for the test commit.
