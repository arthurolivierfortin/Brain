# Brain Monitor — Phase 1 (skeleton + vitals) — Design

**Goal:** Serve a self-contained live-monitor HTML at `GET /monitor` so the dogfood operator can observe Brain hooks, gate decisions, and queue depth in real time during the ≥7-day phase-2b dogfood.
**Roadmap phase:** R:phase-2b
**Cycle invocation:** Phase 1 of 3 (header vitals + footer event log + tweaks). Phases 2 (graph + thought stream) and 3 (left panel + matrix/console + search/shortcuts) are separate future cycle-starts.

## Scope (in)

- New directory + new file `backend/src/brain/static/brain.html` (single self-contained HTML, ~300 lines, JSX inline). Directory does not yet exist; the spec creates it.
- New route `GET /monitor` in `BrainHTTPHandler.do_GET` (`backend/src/brain/server.py`) returning the file as `text/html; charset=utf-8` with `Cache-Control: no-store`, `Access-Control-Allow-Origin: *`. Inserted as a new `elif` branch between the existing `/health` branch (line 238–239) and the catch-all 404 `else` at line 240.
- Header zone (htop-style):
  - "Cluster cores" rendered dynamically from `/stats.types` — top 8 memory_type entries by count, percentage of `stats.total`, one bar each. Resolves open question #1: NOT a hardcoded `lang/reason/percept/...` list.
  - `mem` bar: `stats.total / 16384` (16K is a visual cap, not a backend constraint). Resolves the "max value" question — visual only.
  - `swap` bar: `queue.pending / 100`, red zone above 100. Resolves open question #4.
  - Status dot: green when last poll succeeded, red when `lastError` set on either polling hook.
  - Uptime: not exposed by `/stats` (no backend field today). Phase 1 displays `since: <localStorage-less in-memory page-load timestamp>` formatted as `Hh:Mm` — refers to "monitor session uptime", not Brain process uptime. Phase 2 will add `process_started_at` to `/health` if needed.
  - Total memories: `stats.total`.
  - Version: hardcoded literal `"phase 2b"` in the JS — resolves open question #3 (simpler than parsing `pyproject.toml` from JS, fits the 1-day budget; the version label is dogfood-cosmetic).
- Footer zone: scrollable event log, last 200 events from `/events?limit=200`. Plain CSS-flex list (no virtualization at 200 items). Newest at top. Color badge per `event_type`:
  - `hook_wake_up` → green
  - `hook_post_turn` → cyan
  - `gate_reject` (or any `*reject*` substring) → yellow
  - `error` (or any `error`/`failed`) → red
  - default → grey
  - Relative timestamps via inline `formatRelative(iso)` helper (`Xs ago`, `Xm ago`, `Xh ago`).
- Tweaks panel (toggle bottom-right): pause polling toggle, polling-speed multiplier (0.5x / 1x / 2x), accent color picker. NO localStorage in Phase 1 (in-memory only — page reload resets to defaults).
- Polling hooks (inline JS):
  - `useStats(intervalMs, paused)` — fetches `/stats` and `/queue/status` in parallel via `Promise.all`. Default 5000 ms.
  - `useEvents(intervalMs, paused)` — fetches `/events?limit=200`. Default 2000 ms.
  - Both pause when `document.hidden` (via `visibilitychange` listener) OR when the tweaks-panel pause toggle is set. Speed multiplier divides the interval.
- One pytest test in `backend/tests/test_brain/test_monitor_route.py` validating the route returns 200, correct content-type, and the expected title marker.

## Scope (out — explicit YAGNI)

- Graph viz, right thought stream, activity timeline mini-chart — Phase 2 cycle-start.
- Left panel cluster meters, top-accessed memory list, matrix/console tabs, search/filter on event log, keyboard shortcuts, localStorage persistence of tweaks — Phase 3 cycle-start.
- SSE / WebSocket transport — polling is sufficient for one-operator dogfood. Phase 4 (Next.js rewrite) revisits.
- Authentication — localhost-only single-user.
- JS unit / browser tests — Phase 4 introduces Playwright. Phase 1 HTML behavior is verified by manual eyeballing during dogfood (documented in checklist as "manual verification").
- Bundling, minification, build step — Babel-in-browser keeps iteration friction zero.
- Mobile / responsive layout — desktop dashboard.
- Modifying any other Brain HTTP endpoint, MCP tool, or storage schema.
- Installer (`npx brain`) post-install message referencing `/monitor` — deferred to Phase 3 installer cycle.

## Constraints

- Single self-contained HTML file (~300 lines including the JSX). Babel-in-browser + React 18 from unpkg CDN, identical pattern to `tmp/brain.html`.
- Must run with no build step (drop file on disk, hit the URL).
- Must NOT add any new HTTP route besides `/monitor` (Phase 1 strictly consumes existing `/stats`, `/events`, `/queue/status`).
- Must NOT change any existing endpoint's response shape.
- Polling defaults (5 s stats, 2 s events) MUST pause when `document.hidden` to avoid burning CPU on background tabs during long dogfood runs.

## Architecture

**File layout (after this PR):**

```
backend/src/brain/
├── server.py                  # /monitor route added in BrainHTTPHandler.do_GET
└── static/                    # NEW directory
    └── brain.html             # NEW self-contained HTML+JSX (~300 lines)
```

**Backend route flow** (`BrainHTTPHandler.do_GET`, server.py lines 206–241):

1. New `elif parsed.path == "/monitor":` branch inserted immediately before the catch-all `else` at current line 240.
2. Resolve path via `Path(__file__).parent / "static" / "brain.html"` (uses `pathlib.Path`; `from pathlib import Path` already not imported in server.py, so the spec adds the import at the top of the file).
3. Read the file as bytes (`Path.read_bytes()`).
4. Send `200`, `Content-Type: text/html; charset=utf-8`, `Cache-Control: no-store`, `Access-Control-Allow-Origin: *`.
5. If the file is missing (deployment error), respond `500` with JSON `{"error": "monitor template missing"}` reusing `_json_response`.

**Hatch packaging:** the file lives under `src/brain/static/`. The current `[tool.hatch.build.targets.wheel] packages = ["src/brain"]` already ships everything under `src/brain/` into the wheel as long as the file is on disk. No `pyproject.toml` change needed for Phase 1 (the file is read directly from the source tree at runtime via `Path(__file__).parent`, which works for both editable installs and the Docker image where the package is copied to `site-packages`). If a future install mode strips non-`.py` files, we'll add a `[tool.hatch.build.targets.wheel.force-include]` entry — out of scope for Phase 1.

**Resolution of open question #2 — `/stats` schema (read from `store.py::stats()`, lines 810–844):**

```json
{
  "total": int,
  "agents": { "<agent>": int, ... },
  "types":  { "<memory_type>": int, ... },
  "top_accessed": [
    { "access_count": int, "agent": str, "id": str }, ...
  ]
}
```

Confirmed: `types` is a flat dict `{memory_type: count}`. The header "cluster cores" iterate `Object.entries(stats.types)`, sort by count desc, slice top 8.

**`/queue/status` schema (server.py lines 232–237):**

```json
{ "pending": int, "queue_path": str }
```

The `swap` bar uses `queue.pending` / 100 as soft max.

**`/events?limit=200` schema (server.py lines 225–228, EventLog.recent):**

```json
{ "events": [
  { "event_type": str, "timestamp": iso8601, "agent": str, "node_id": str, "details": str, "metadata": {...?} }, ...
] }
```

Newest is last in the JSONL file → the frontend reverses the array so newest renders at top.

**Frontend structure (~300 lines, all inline in brain.html):**

- `<style>` block: htop palette (`--bg #0b0b0f`, `--fg #c5c8d3`, `--accent #6fd6c9`, `--mem #b48ead`, `--swap #ebcb8b`, `--ok #a3be8c`, `--err #bf616a`), JetBrains Mono / `ui-monospace` stack, CSS Grid `grid-template-rows: auto 1fr 180px` with the middle row as an empty placeholder div for Phase 2.
- `<script type="text/babel">` block:
  - `useStats(speed, paused)` and `useEvents(speed, paused)` hooks — `useEffect` + `setInterval`, listen to `visibilitychange`, divide interval by speed multiplier, abort fetch on unmount.
  - `useTweaks()` — `useState({ accent: "#6fd6c9", speed: 1, running: true })`, no localStorage.
  - `<App>` root: 3-row grid; renders `<Header>`, an empty `<main className="phase2-placeholder">` (visible during Phase 2 dev), and `<Footer>`.
  - `<Header>` component: cluster cores (top-8 from `stats.types`), `mem` bar, `swap` bar, status dot, since-uptime, total count, `phase 2b` version badge.
  - `<Footer>` component: events list with type-colored badges, relative timestamps via `formatRelative(iso)`.
  - `<TweaksPanel>` component: collapsed by default; expand button bottom-right; controls write into the tweaks state, which is read by header/footer to apply accent and propagate `paused` / `speed` to hooks.
- Document title: literal `<title>brain · live monitor</title>` — used by the pytest body assertion.
- Anchor: `<div id="root"></div>` — used by the pytest body assertion as a secondary marker.

**Error handling:**

- Polling fetches: `try/catch`. On error, hook returns `{ data: <last good>, error: <message> }`. Header turns the status dot red. UI keeps polling.
- Missing fields in `/stats`: defensive defaults (`stats?.types ?? {}`, `stats?.total ?? 0`).
- File-missing on backend: 500 JSON, no template fallback.

## Affected systems

- **HTTP API:** ONE new route — `GET /monitor` (additive, returns `text/html`). All other endpoints unchanged. CORS unchanged (existing `*`).
- **MCP tools:** unchanged. No new tool, no schema change. The monitor consumes HTTP only.
- **Storage:** unchanged. No SQLite migration. No ChromaDB re-index. No new metadata fields written.
- **Frontend:** the existing `tmp/brain.html` and `tmp/brain-*.jsx` mockups stay in `tmp/` as inspiration for Phase 4 Next.js rewrite. The new file is `backend/src/brain/static/brain.html`. No `frontend/` package created. No build tooling.
- **Installer (`npx brain`):** unchanged in this PR. Phase 3 installer will mention `http://localhost:8621/monitor` in its post-install message.
- **Scripts (Claude Code hooks — wake_up / post_turn / statusline):** unchanged.
- **Benchmarks:** unchanged. Monitor is a passive read-only consumer of existing endpoints; cannot affect LongMemEval or LoCoMo runs.
- **Tests:** ONE new pytest test file `backend/tests/test_brain/test_monitor_route.py`, one test `test_monitor_route_serves_html` that boots the HTTP handler (same `_start_server` pattern as `test_hook_http.py`), GETs `/monitor`, asserts status 200, `Content-Type` starts with `text/html`, body contains the literal byte sequence `<title>brain · live monitor</title>` AND `<div id="root"></div>`.

## Risks

- **Hatch wheel does not include the static file in some install modes.** Mitigation: the runtime resolves via `Path(__file__).parent / "static" / "brain.html"`, which works for source / editable / Docker-copy installs. If a wheel-only install strips the HTML, the route returns 500 and the dogfood operator notices immediately. Tracked as a known risk; force-include rule will be added if it bites.
- **Babel-in-browser is slow on first load.** Acceptable for 1-operator dogfood; Phase 4 replaces.
- **Polling at 2 s for events on a long-running tab.** Mitigated by `visibilitychange` pause and the tweaks-panel pause/speed controls.
- **`/events` payload size at limit=200.** Each event is small (~200 bytes); ~40 KB per poll. Acceptable.
- **`stats.types` could contain >8 distinct keys** if Brain accrues many memory types during dogfood. Mitigation: hard-slice top 8; the rest aggregate visually as "+N more" badge (rendered when `Object.keys(stats.types).length > 8`).
- **`Path(__file__).parent` resolves differently in PEP 660 editable installs vs site-packages.** Both resolve to the directory containing `server.py`, so `static/brain.html` lookup is consistent. No risk.

## Consumer impact

- **Money** (legacy embedded Brain on `:8611`): no impact. Money does not call `/monitor` and the standalone Brain on `:8621` is what gets the new route.
- **Marcel / future consumers:** no impact (new additive endpoint).
- **Open question #5 — verification gates resolved:** only Python is touched (HTML is inert template data — no JS gate possible without Playwright, which is deferred to Phase 4). `[GATE-1]` ruff, `[GATE-2]` mypy, `[GATE-3]` pytest. `[GATE-4]` skipped as "no frontend touched".
