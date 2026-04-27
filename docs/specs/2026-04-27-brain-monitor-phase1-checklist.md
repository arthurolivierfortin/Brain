# Checklist — Brain Monitor Phase 1 (skeleton + vitals)

**Linked spec:** [2026-04-27-brain-monitor-phase1-design.md](2026-04-27-brain-monitor-phase1-design.md)

**Budget:** 1 day. **Roadmap phase:** R:phase-2b.

**Commit emoji convention** (per CLAUDE.md): `🧠 Feature` for [SPEC-1] through [SPEC-8] (new code), `🧪 Test` for [TEST-1] (test-only commit).

**HTML/JS verification policy** (Phase 1): tests for inline JS are deferred to Phase 4 (Next.js + Playwright). [SPEC-1] and [SPEC-3] through [SPEC-8] are HTML/JSX-only and verified by manual eyeballing during the ≥7-day dogfood — `http://localhost:8621/monitor`, observe header bars react when a hook fires, confirm event log scrolls, toggle tweaks panel, hide tab and confirm polling pauses (Network tab in DevTools). The single pytest test [TEST-1] validates the route serves the file with the correct content-type and body markers; that is sufficient automated coverage for Phase 1. This rationale is part of the spec's accepted scope (out: "JS unit tests / browser tests").

## Code

- [x] [SPEC-1] Create directory `backend/src/brain/static/` and write skeleton `brain.html` containing only: `<!doctype html>`, `<html>`, `<head>` with `<meta charset="utf-8">` + `<title>brain · live monitor</title>` + the htop palette CSS (`:root` vars, body grid `auto 1fr 180px`, JetBrains Mono stack), React 18 + ReactDOM 18 + Babel CDN tags from unpkg, `<body>` with `<div id="root"></div>`, and an empty `<script type="text/babel">` block that mounts an empty `<App>` returning `<div className="brain-shell" />`. ~80 lines. — `backend/src/brain/static/brain.html`
- [x] [SPEC-2] Add `from pathlib import Path` import (top of file) and an `elif parsed.path == "/monitor":` branch in `BrainHTTPHandler.do_GET` (server.py, inserted between current line 239 `/health` and current line 240 catch-all `else`) that resolves `Path(__file__).parent / "static" / "brain.html"`, reads bytes, sends `200` with `Content-Type: text/html; charset=utf-8`, `Cache-Control: no-store`, `Access-Control-Allow-Origin: *`. On `FileNotFoundError`, respond `500` via `_json_response({"error": "monitor template missing"}, status=500)`. — `backend/src/brain/server.py`
- [ ] [SPEC-3] Implement `<Header>` component in `brain.html`: receives `stats` and `queue` props, renders top-8 entries of `stats.types` (sorted by count desc) as labeled bars with percentage of `stats.total`; a `mem` bar (`stats.total / 16384`); a `swap` bar (`queue.pending / 100`, red zone above 100); status dot (green when no `lastError`, red when set); since-uptime computed from a `useRef` page-load timestamp formatted `Hh:Mm`; total count; literal version badge `phase 2b`. — `backend/src/brain/static/brain.html`
- [ ] [SPEC-4] Implement `useStats(speed, paused)` hook in `brain.html`: `useEffect` + `setInterval` at `5000 / speed` ms, fetches `/stats` and `/queue/status` in parallel via `Promise.all`, returns `{ stats, queue, lastError }`. Skips the fetch when `paused` is true. Aborts pending fetch on unmount via `AbortController`. — `backend/src/brain/static/brain.html`
- [ ] [SPEC-5] Implement `useEvents(speed, paused)` hook in `brain.html`: `useEffect` + `setInterval` at `2000 / speed` ms, fetches `/events?limit=200`, reverses the array so newest is first, returns `{ events, lastError }`. Skips when `paused`; aborts on unmount. — `backend/src/brain/static/brain.html`
- [ ] [SPEC-6] Implement `<Footer>` component in `brain.html`: scrollable list of up to 200 events; each row has a type-colored badge (`hook_wake_up` green, `hook_post_turn` cyan, anything containing `reject` yellow, anything containing `error` or `failed` red, default grey), the agent, the details (truncated to 120 chars), and a relative timestamp via inline `formatRelative(iso)` helper (`Xs ago` / `Xm ago` / `Xh ago`). — `backend/src/brain/static/brain.html`
- [ ] [SPEC-7] Implement `<TweaksPanel>` component in `brain.html`: collapsed-by-default panel pinned bottom-right via `position: fixed`; expand toggle button; controls for pause (checkbox), speed multiplier (`<select>` with values 0.5 / 1 / 2), and accent color (`<input type="color">`); state held in a `useTweaks()` hook returning `{ tweaks, setTweaks }` (no localStorage); the accent value is applied via `document.documentElement.style.setProperty('--accent', tweaks.accent)`. — `backend/src/brain/static/brain.html`
- [ ] [SPEC-8] Wire document-visibility pause: add a single `useEffect` in the `<App>` component that listens to `visibilitychange` and tracks `documentHidden` in a state. Combine with `tweaks.running === false` into a single `paused` boolean passed to both `useStats` and `useEvents`. Verify in DevTools Network tab that polling stops when the tab is hidden. — `backend/src/brain/static/brain.html`

## Tests

- [x] [TEST-1] Pytest test for [SPEC-2]. Boots the HTTP handler on an ephemeral port via the `_start_server` pattern from `test_hook_http.py`, GETs `/monitor`, asserts: `response.status_code == 200`, `response.headers["content-type"].startswith("text/html")`, `b"<title>brain \xc2\xb7 live monitor</title>" in response.content` (UTF-8 byte sequence for `brain · live monitor`), AND `b'<div id="root"></div>' in response.content`. — `backend/tests/test_brain/test_monitor_route.py::test_monitor_route_serves_html`

[SPEC-1] and [SPEC-3] through [SPEC-8] have no [TEST-N] — they are HTML/JSX-only, verified manually during dogfood per the policy above.

## Storage / Migrations

- [ ] [DB-0] None.

## Verification gates

- [ ] [GATE-1] `cd backend && python -m ruff check .` passes (Python touched: `backend/src/brain/server.py`, `backend/tests/test_brain/test_monitor_route.py`).
- [ ] [GATE-2] `cd backend && python -m pytest -q` passes (new test file added; baseline 191 passing on main as of 2026-04-27).
- [ ] [GATE-3] frontend gates — (skipped — no frontend touched). The new `brain.html` is inert HTML+inline JSX served as a static file; there is no `frontend/` package, no `pnpm` workspace, and no JS test runner in this PR. Phase 4 introduces the Next.js + Playwright pipeline.

**Note:** mypy is NOT a hard gate for Brain (99+ pre-existing errors on main as of 2026-04-27, tracked as `docs/improvements/` P2 per CLAUDE.md). Builder may run `cd backend && python -m mypy .` for advisory signal; failures don't block the PR.
