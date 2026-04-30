# Gemini API Key Leak Fix — Implementation Plan

**Linked spec:** [2026-04-29-gemini-key-leak-design.md](../specs/2026-04-29-gemini-key-leak-design.md)
**Linked checklist:** [2026-04-29-gemini-key-leak-checklist.md](../specs/2026-04-29-gemini-key-leak-checklist.md)
**Goal:** Stop GOOGLE_API_KEY from appearing in docker logs by replacing Gemini query-param auth with a header and silencing httpx URL logging.
**Branch:** `feat/34-gemini-key-leak`

---

### Task 1 — [SPEC-1] + [TEST-1]: Switch GeminiFlashExtractor auth from `?key=` query param to `x-goog-api-key` header

**Files:**
- Modify: `backend/src/brain/hook.py:175-185` (the `extract` method URL construction and `post` call)
- Create: `backend/tests/test_brain/test_gemini_security.py`

- [ ] **Step 1.1: Write the failing test**

```python
# backend/tests/test_brain/test_gemini_security.py
"""Security regression tests for GeminiFlashExtractor."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from brain.hook import GeminiFlashExtractor, Turn


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({"memories": []})}]}}]
    }
    resp.raise_for_status = MagicMock()
    return resp


def test_extract_uses_header_auth_not_query_param() -> None:
    """SPEC-1: outbound URL must not contain the API key; header must carry it."""
    api_key = "test-key-abc123"
    fake_client = MagicMock()
    fake_client.post.return_value = _ok_response()

    ext = GeminiFlashExtractor(api_key=api_key, _client=fake_client)
    ext.extract(Turn(user="u", assistant="a"))

    assert fake_client.post.called
    call_args = fake_client.post.call_args
    url: str = call_args.args[0] if call_args.args else call_args.kwargs["url"]
    headers: dict = call_args.kwargs.get("headers", {})

    # URL must end with :generateContent — no query string
    assert url.endswith(":generateContent"), f"URL has unexpected suffix: {url}"
    assert "?" not in url, f"URL must not contain query string, got: {url}"
    assert api_key not in url, f"API key must not appear in URL, got: {url}"

    # Key must be in the header instead
    assert headers.get("x-goog-api-key") == api_key, (
        f"Expected header x-goog-api-key={api_key!r}, got headers={headers}"
    )
```

- [ ] **Step 1.2: Run the test, watch it fail**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_gemini_security.py::test_extract_uses_header_auth_not_query_param -q
```

Expected: FAIL — `AssertionError: URL has unexpected suffix` (current URL has `?key=...`) or `AssertionError: API key must not appear in URL`.

- [ ] **Step 1.3: Implement the fix in `hook.py`**

In `backend/src/brain/hook.py`, inside `GeminiFlashExtractor.extract`, replace lines 175-185 with:

```python
    def extract(self, turn: Turn) -> list[ExtractedMemory]:
        prompt = self._build_prompt(turn)
        url = f"{self._API_URL}/{self._model}:generateContent"
        try:
            resp = self._client.post(url, json={
                "systemInstruction": {"parts": [{"text": self.SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 2048,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
            }, headers={"x-goog-api-key": self._api_key})
            resp.raise_for_status()
```

The only changes are:
1. `url` no longer appends `?key={self._api_key}`
2. `self._client.post(...)` gains `headers={"x-goog-api-key": self._api_key}`

- [ ] **Step 1.4: Run the test, watch it pass**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_gemini_security.py::test_extract_uses_header_auth_not_query_param -q
```

Expected: PASS

- [ ] **Step 1.5: Verify no regression in existing extractor tests**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_hook_extractor.py -q
```

Expected: 6 tests, all PASS. The existing tests assert on `call_kwargs["json"]` body only and do not assert on the URL, so they survive the URL change unmodified.

- [ ] **Step 1.6: Tick [SPEC-1] and [TEST-1] in checklist, commit**

```bash
git add backend/src/brain/hook.py backend/tests/test_brain/test_gemini_security.py docs/specs/2026-04-29-gemini-key-leak-checklist.md
git commit -m "$(cat <<'EOF'
🩹 Fix: SPEC-1 switch Gemini auth from query param to header (#34)

Removes ?key=... from the outbound URL; passes x-goog-api-key header
instead. Prevents GOOGLE_API_KEY from appearing in httpx log lines.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 — [SPEC-2] + [TEST-2]: Silence httpx URL logging at module top of `hook.py`

**Files:**
- Modify: `backend/src/brain/hook.py:1-18` (imports block)
- Modify: `backend/tests/test_brain/test_gemini_security.py` (add TEST-2)

- [ ] **Step 2.1: Write the failing test (append to the existing test file)**

```python
# Append to backend/tests/test_brain/test_gemini_security.py

import logging


def test_httpx_logger_level_is_warning() -> None:
    """SPEC-2: importing brain.hook must suppress httpx INFO URL logs."""
    import brain.hook  # noqa: F401 — side-effect import triggers module-top setLevel
    assert logging.getLogger("httpx").level == logging.WARNING, (
        f"Expected httpx logger level WARNING ({logging.WARNING}), "
        f"got {logging.getLogger('httpx').level}"
    )
```

- [ ] **Step 2.2: Run the test, watch it fail**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_gemini_security.py::test_httpx_logger_level_is_warning -q
```

Expected: FAIL — `AssertionError: Expected httpx logger level WARNING (30), got 0` (default NOTSET=0).

- [ ] **Step 2.3: Implement the fix in `hook.py`**

In `backend/src/brain/hook.py`, add `import logging` to the existing imports block and add the one-liner immediately after all imports, before any class or function definition. The file currently imports at lines 1-17; the module-level call goes right after:

```python
# top of backend/src/brain/hook.py — after existing imports
import logging  # add to the imports block (alphabetical order between `import json` and `import math`)

# ... rest of imports unchanged ...

logging.getLogger("httpx").setLevel(logging.WARNING)
```

Concrete placement: after the last `import` statement (currently `import httpx` at line 17), before the first `@dataclass` / class / function definition. One blank line above and below the call, matching existing file style.

- [ ] **Step 2.4: Run the test, watch it pass**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_gemini_security.py::test_httpx_logger_level_is_warning -q
```

Expected: PASS

- [ ] **Step 2.5: Tick [SPEC-2] and [TEST-2] in checklist, commit**

```bash
git add backend/src/brain/hook.py docs/specs/2026-04-29-gemini-key-leak-checklist.md
git commit -m "$(cat <<'EOF'
🩹 Fix: SPEC-2 silence httpx URL logging at module top of hook.py (#34)

Adds logging.getLogger("httpx").setLevel(logging.WARNING) so httpx
stops emitting full request URLs at INFO, belt-and-suspenders guard
against any future query-param secret regression in this process.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Final task — Verification gates

- [ ] **Step F.1: ruff**

```bash
cd /c/Brain/backend && python -m ruff check .
```

Expected: no errors. `logging.getLogger(...)` at module top is a valid Python statement; ruff does not flag it.

- [ ] **Step F.2: full pytest suite (baseline 213 → 215)**

```bash
cd /c/Brain/backend && python -m pytest -q
```

Expected: 215 tests collected, 0 failed, 0 errors.

- [ ] **Step F.3: Tick [GATE-1] and [GATE-2] in checklist, push, open PR**

```bash
git push -u origin feat/34-gemini-key-leak
gh pr create --title "Fix: GOOGLE_API_KEY leak in docker logs via httpx URL (#34)" --body "$(cat <<'EOF'
## Summary
- Switches Gemini auth from `?key=` query param to `x-goog-api-key` header (SPEC-1)
- Silences httpx INFO URL logging at module top of `hook.py` (SPEC-2)
- Adds 2 security regression tests in `test_gemini_security.py` (TEST-1, TEST-2)

## Test plan
- [ ] `cd backend && python -m ruff check .` — passes (GATE-1)
- [ ] `cd backend && python -m pytest -q` — 215 tests, 0 failures (GATE-2)
- [ ] Manual smoke: docker rebuild + restart, trigger a post_turn hook, `docker logs brain --tail 20` — zero `?key=` substring visible
- [ ] User action: rotate exposed key at https://aistudio.google.com/app/apikey

Closes #34

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Implementation notes

**TEST-1 call_args extraction:** `fake_client.post` is called positionally (`self._client.post(url, json=..., headers=...)`). The test extracts `url` via `call_args.args[0]` and `headers` via `call_args.kwargs["headers"]`. This matches the current calling convention in `extract`; if the builder passes `url` as a keyword arg instead, the test's `call_args.args[0] if call_args.args else call_args.kwargs["url"]` guard handles both forms.

**TEST-2 import isolation:** pytest runs all tests in the same process by default. `brain.hook` will already be imported by the time `test_httpx_logger_level_is_warning` runs (other test files import it). The `import brain.hook` inside the test body is a no-op re-import — the module-level `setLevel` already executed at first import. The assertion will read the level that was set at import time. This is correct behavior and is what we want to verify.

**Existing `test_hook_extractor.py` compatibility:** none of the 6 existing tests assert on the URL passed to `fake_client.post` — they only inspect `call_args.kwargs["json"]` (the request body). The header change and URL change in SPEC-1 do not break any existing assertions.
