# Brain Monitor Phase 1 (skeleton + vitals) — Implementation Plan

**Linked spec:** [2026-04-27-brain-monitor-phase1-design.md](../specs/2026-04-27-brain-monitor-phase1-design.md)
**Linked checklist:** [2026-04-27-brain-monitor-phase1-checklist.md](../specs/2026-04-27-brain-monitor-phase1-checklist.md)
**Goal:** Serve a self-contained live-monitor HTML at `GET /monitor` so the dogfood operator can observe Brain hooks, gate decisions, and queue depth in real time.
**Branch:** `feat/16-brain-monitor-phase1`

---

### Task 1 — [SPEC-2] + [TEST-1]: Backend `/monitor` route + pytest smoke test

This is the only task with automated test coverage. Do it first — the test validates SPEC-2; SPEC-1 must exist before the test can pass.

**Files:**
- Create: `backend/src/brain/static/` (new directory — create by writing brain.html into it)
- Create: `backend/src/brain/static/brain.html` (skeleton HTML, ~80 lines — see Task 2)
- Modify: `backend/src/brain/server.py` (add `from pathlib import Path` import + `/monitor` branch)
- Create: `backend/tests/test_brain/test_monitor_route.py`

---

- [ ] **Step 1.1: Write the failing test**

```python
# backend/tests/test_brain/test_monitor_route.py
from __future__ import annotations

from pathlib import Path
from threading import Thread
from http.server import HTTPServer

import httpx
import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain import server  # noqa: E402


def _start_server(tmp_path: Path, api_key: str = "fake") -> tuple[HTTPServer, str]:
    import os
    os.environ["BRAIN_PERSIST_DIR"] = str(tmp_path / "chromadb")
    os.environ["GOOGLE_API_KEY"] = api_key
    server._store = None
    server._events = None
    server._queue = None
    if hasattr(server, "_extractor"):
        server._extractor = None
    http_cls, handler_cls = server.create_http_app()
    srv = http_cls(("127.0.0.1", 0), handler_cls)
    port = srv.server_address[1]
    thr = Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    return srv, f"http://127.0.0.1:{port}"


def test_monitor_route_serves_html(tmp_path: Path) -> None:
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.get(f"{url}/monitor")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert b"<title>brain \xc2\xb7 live monitor</title>" in resp.content
        assert b'<div id="root"></div>' in resp.content
    finally:
        srv.shutdown()
```

- [ ] **Step 1.2: Run test, watch it fail**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_monitor_route.py -q
```

Expected: FAIL with `AssertionError` on `status_code == 200` (route does not exist yet) OR `FileNotFoundError` if route is inserted before `brain.html` exists. Either failure mode is correct.

- [ ] **Step 1.3: Create the `static/` directory and skeleton `brain.html`**

(See Task 2 for the full content of `brain.html`. The skeleton needed for the test to pass is ~80 lines. Write that file first so Step 1.4 can succeed.)

- [ ] **Step 1.4: Add the `/monitor` route to `backend/src/brain/server.py`**

Two changes, in order:

**Change A — Add import at top of file (after the existing imports block, around line 16):**

```python
from pathlib import Path
```

The existing imports in server.py are `json`, `logging`, `typing.Any`, `mcp`, `brain.events`, `brain.pending_queue`, `brain.store`. Add `from pathlib import Path` as a new line after the stdlib imports (`json`, `logging`) and before the third-party imports, or at the end of the stdlib block — either is acceptable to ruff.

**Change B — Insert `elif` branch in `BrainHTTPHandler.do_GET` between the `/health` branch (line 238-239) and the catch-all `else` (line 240):**

```python
elif parsed.path == "/monitor":
    _html_path = Path(__file__).parent / "static" / "brain.html"
    try:
        _html_bytes = _html_path.read_bytes()
    except FileNotFoundError:
        self._json_response({"error": "monitor template missing"}, status=500)
        return
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Cache-Control", "no-store")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.end_headers()
    self.wfile.write(_html_bytes)
```

Note: this branch does NOT use `_json_response` for the happy path (which always sends `Content-Type: application/json`). It calls the lower-level `send_response` / `send_header` / `end_headers` / `wfile.write` directly — same pattern the stdlib `BaseHTTPRequestHandler` uses.

- [ ] **Step 1.5: Run test, watch it pass**

```bash
cd /c/Brain/backend && python -m pytest tests/test_brain/test_monitor_route.py -q
```

Expected: `1 passed`

- [ ] **Step 1.6: Tick [SPEC-2] and [TEST-1] in checklist, commit**

```bash
git add backend/src/brain/server.py backend/tests/test_brain/test_monitor_route.py docs/specs/2026-04-27-brain-monitor-phase1-checklist.md
git commit -m "🧪 Test: [TEST-1] monitor route smoke test + [SPEC-2] /monitor route (#16)"
```

---

### Task 2 — [SPEC-1]: Skeleton `brain.html` (~80 lines)

**Files:**
- Create: `backend/src/brain/static/brain.html`

No automated test — HTML/JSX verified manually per checklist policy.

- [ ] **Step 2.1: Write `backend/src/brain/static/brain.html` (skeleton only)**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>brain · live monitor</title>
  <style>
    :root {
      --bg: #0b0b0f;
      --fg: #c5c8d3;
      --accent: #6fd6c9;
      --mem: #b48ead;
      --swap: #ebcb8b;
      --ok: #a3be8c;
      --err: #bf616a;
      --font: "JetBrains Mono", ui-monospace, "Cascadia Code", monospace;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; background: var(--bg); color: var(--fg); font-family: var(--font); font-size: 13px; }
    #root {
      display: grid;
      grid-template-rows: auto 1fr 180px;
      height: 100vh;
    }
    .brain-shell { display: contents; }
  </style>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <script crossorigin src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    const { useState, useEffect, useRef } = React;

    function App() {
      return <div className="brain-shell" />;
    }

    ReactDOM.createRoot(document.getElementById("root")).render(<App />);
  </script>
</body>
</html>
```

- [ ] **Step 2.2: Verify skeleton renders without JS errors**

Open `http://localhost:8621/monitor` in a browser. Console should show no errors; page body is blank (no components yet). This verifies the CDN tags, Babel transpilation, and React mount work.

- [ ] **Step 2.3: Tick [SPEC-1] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase1-checklist.md
git commit -m "🧠 Feature: [SPEC-1] brain.html skeleton + static/ directory (#16)"
```

---

### Task 3 — [SPEC-3]: `<Header>` component

**Files:**
- Modify: `backend/src/brain/static/brain.html`

No automated test — HTML/JSX verified manually per checklist policy.

- [ ] **Step 3.1: Replace `App` and add `Header` in `brain.html`**

Replace the `<script type="text/babel">` block with:

```jsx
const { useState, useEffect, useRef } = React;

// ── helpers ──────────────────────────────────────────────────────────────────
function formatRelative(iso) {
  const diffSec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  return `${Math.floor(diffSec / 3600)}h ago`;
}

function formatUptime(startMs) {
  const totalSec = Math.floor((Date.now() - startMs) / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  return `${h}h:${String(m).padStart(2, "0")}m`;
}

// ── Bar component ─────────────────────────────────────────────────────────────
function Bar({ label, value, max, color, redZone }) {
  const pct = Math.min(1, value / Math.max(max, 1));
  const isRed = redZone && value > redZone;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "2px" }}>
      <span style={{ width: "90px", textAlign: "right", color: "var(--fg)", opacity: 0.7 }}>{label}</span>
      <div style={{ flex: 1, height: "10px", background: "rgba(255,255,255,0.07)", borderRadius: "2px" }}>
        <div style={{
          width: `${(pct * 100).toFixed(1)}%`,
          height: "100%",
          background: isRed ? "var(--err)" : color,
          borderRadius: "2px",
          transition: "width 0.4s",
        }} />
      </div>
      <span style={{ width: "40px", fontSize: "11px", opacity: 0.8 }}>
        {(pct * 100).toFixed(0)}%
      </span>
    </div>
  );
}

// ── Header ────────────────────────────────────────────────────────────────────
function Header({ stats, queue, lastError, startMs }) {
  const types = Object.entries(stats?.types ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8);
  const extra = Object.keys(stats?.types ?? {}).length - 8;
  const total = stats?.total ?? 0;

  return (
    <header style={{
      padding: "10px 16px",
      borderBottom: "1px solid rgba(255,255,255,0.08)",
      background: "rgba(255,255,255,0.02)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", alignItems: "center" }}>
        <span style={{ color: "var(--accent)", fontWeight: "bold", letterSpacing: "0.05em" }}>
          brain · live monitor
        </span>
        <div style={{ display: "flex", gap: "16px", fontSize: "11px", alignItems: "center" }}>
          <span>total: <b>{total.toLocaleString()}</b></span>
          <span>uptime: <b>{formatUptime(startMs)}</b></span>
          <span style={{ padding: "1px 6px", borderRadius: "3px", background: "rgba(255,255,255,0.1)" }}>
            phase 2b
          </span>
          <span style={{
            width: "8px", height: "8px", borderRadius: "50%",
            background: lastError ? "var(--err)" : "var(--ok)",
            display: "inline-block",
          }} title={lastError ?? "ok"} />
        </div>
      </div>

      {/* cluster cores */}
      <div style={{ marginBottom: "6px" }}>
        {types.map(([type, count]) => (
          <Bar
            key={type}
            label={type}
            value={count}
            max={total || 1}
            color="var(--accent)"
          />
        ))}
        {extra > 0 && (
          <div style={{ fontSize: "11px", opacity: 0.5, paddingLeft: "96px" }}>+{extra} more types</div>
        )}
      </div>

      <Bar label="mem" value={total} max={16384} color="var(--mem)" />
      <Bar label="swap" value={queue?.pending ?? 0} max={100} color="var(--swap)" redZone={100} />
    </header>
  );
}

// ── Footer ─────────────────────────────────────────────────────────────────────
function Footer({ events }) {
  return (
    <footer style={{
      borderTop: "1px solid rgba(255,255,255,0.08)",
      overflowY: "auto",
      padding: "6px 12px",
    }}>
      {(events ?? []).map((ev, i) => {
        const type = ev.event_type ?? "";
        let badgeColor = "#555";
        if (type === "hook_wake_up") badgeColor = "var(--ok)";
        else if (type === "hook_post_turn") badgeColor = "var(--accent)";
        else if (type.includes("reject")) badgeColor = "var(--swap)";
        else if (type.includes("error") || type.includes("failed")) badgeColor = "var(--err)";

        const details = (ev.details ?? "").slice(0, 120);
        return (
          <div key={i} style={{ display: "flex", gap: "8px", padding: "2px 0", fontSize: "12px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
            <span style={{ padding: "0 4px", borderRadius: "2px", background: badgeColor, color: "#000", flexShrink: 0, fontSize: "10px" }}>
              {type}
            </span>
            <span style={{ opacity: 0.7, flexShrink: 0 }}>{ev.agent ?? ""}</span>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {details}
            </span>
            <span style={{ opacity: 0.5, flexShrink: 0, fontSize: "11px" }}>
              {formatRelative(ev.timestamp)}
            </span>
          </div>
        );
      })}
    </footer>
  );
}

// ── TweaksPanel ────────────────────────────────────────────────────────────────
function useTweaks() {
  const [tweaks, setTweaks] = useState({ accent: "#6fd6c9", speed: 1, running: true });
  useEffect(() => {
    document.documentElement.style.setProperty("--accent", tweaks.accent);
  }, [tweaks.accent]);
  return { tweaks, setTweaks };
}

function TweaksPanel({ tweaks, setTweaks }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "fixed", bottom: "190px", right: "12px", zIndex: 100 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ background: "var(--accent)", color: "#000", border: "none", borderRadius: "4px", padding: "4px 10px", cursor: "pointer", fontFamily: "var(--font)", fontSize: "12px" }}
      >
        {open ? "close" : "tweaks"}
      </button>
      {open && (
        <div style={{ marginTop: "6px", background: "#1a1a22", border: "1px solid rgba(255,255,255,0.12)", borderRadius: "6px", padding: "10px 14px", display: "flex", flexDirection: "column", gap: "8px", minWidth: "180px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <input
              type="checkbox"
              checked={tweaks.running}
              onChange={e => setTweaks(t => ({ ...t, running: e.target.checked }))}
            />
            polling on
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            speed
            <select
              value={tweaks.speed}
              onChange={e => setTweaks(t => ({ ...t, speed: Number(e.target.value) }))}
              style={{ background: "#222", color: "var(--fg)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "3px" }}
            >
              <option value={0.5}>0.5×</option>
              <option value={1}>1×</option>
              <option value={2}>2×</option>
            </select>
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            accent
            <input
              type="color"
              value={tweaks.accent}
              onChange={e => setTweaks(t => ({ ...t, accent: e.target.value }))}
            />
          </label>
        </div>
      )}
    </div>
  );
}

// ── Hooks ──────────────────────────────────────────────────────────────────────
function useStats(speed, paused) {
  const [state, setState] = useState({ stats: null, queue: null, lastError: null });
  useEffect(() => {
    if (paused) return;
    const ctrl = new AbortController();
    const intervalMs = Math.round(5000 / speed);

    async function fetchData() {
      try {
        const [sr, qr] = await Promise.all([
          fetch("/stats", { signal: ctrl.signal }),
          fetch("/queue/status", { signal: ctrl.signal }),
        ]);
        const [statsData, queueData] = await Promise.all([sr.json(), qr.json()]);
        setState({ stats: statsData, queue: queueData, lastError: null });
      } catch (err) {
        if (err.name !== "AbortError") {
          setState(s => ({ ...s, lastError: err.message }));
        }
      }
    }

    fetchData();
    const id = setInterval(fetchData, intervalMs);
    return () => { clearInterval(id); ctrl.abort(); };
  }, [speed, paused]);
  return state;
}

function useEvents(speed, paused) {
  const [state, setState] = useState({ events: [], lastError: null });
  useEffect(() => {
    if (paused) return;
    const ctrl = new AbortController();
    const intervalMs = Math.round(2000 / speed);

    async function fetchData() {
      try {
        const r = await fetch("/events?limit=200", { signal: ctrl.signal });
        const data = await r.json();
        setState({ events: [...(data.events ?? [])].reverse(), lastError: null });
      } catch (err) {
        if (err.name !== "AbortError") {
          setState(s => ({ ...s, lastError: err.message }));
        }
      }
    }

    fetchData();
    const id = setInterval(fetchData, intervalMs);
    return () => { clearInterval(id); ctrl.abort(); };
  }, [speed, paused]);
  return state;
}

// ── App ────────────────────────────────────────────────────────────────────────
function App() {
  const startMs = useRef(Date.now()).current;
  const [docHidden, setDocHidden] = useState(document.hidden);
  const { tweaks, setTweaks } = useTweaks();

  useEffect(() => {
    const onVisibility = () => setDocHidden(document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const paused = docHidden || !tweaks.running;
  const { stats, queue, lastError: statsError } = useStats(tweaks.speed, paused);
  const { events, lastError: eventsError } = useEvents(tweaks.speed, paused);
  const lastError = statsError || eventsError;

  return (
    <div className="brain-shell" style={{ display: "contents" }}>
      <Header stats={stats} queue={queue} lastError={lastError} startMs={startMs} />
      <main style={{ overflow: "hidden" }} />
      <Footer events={events} />
      <TweaksPanel tweaks={tweaks} setTweaks={setTweaks} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
```

- [ ] **Step 3.2: Tick [SPEC-3] through [SPEC-8] in checklist, commit**

All JSX components (`Header`, `Footer`, `TweaksPanel`, `useStats`, `useEvents`, visibility handler) are in this one replacement — they are bundled into a single commit per SPEC because they are all in the same file and interdependent.

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase1-checklist.md
git commit -m "🧠 Feature: [SPEC-3..8] header/footer/tweaks/hooks/visibility in brain.html (#16)"
```

---

### Final Task — Verification gates

- [ ] **Step F.1: ruff**

```bash
cd /c/Brain/backend && python -m ruff check .
```

Expected: no errors. If ruff flags anything in `server.py` (unused import, line length), fix in place.

- [ ] **Step F.2: pytest**

```bash
cd /c/Brain/backend && python -m pytest -q
```

Expected: 192 passed (191 baseline + 1 new test `test_monitor_route_serves_html`).

- [ ] **Step F.3:** Frontend gates skipped — no `frontend/` package touched.

- [ ] **Step F.4: Tick [GATE-1] and [GATE-2] in checklist, push, open PR**

```bash
git add docs/specs/2026-04-27-brain-monitor-phase1-checklist.md
git commit -m "🧹 Chore: tick GATE-1/2 in monitor phase1 checklist (#16)"
git push -u origin feat/16-brain-monitor-phase1
gh pr create --title "Brain monitor — Phase 1: skeleton + vitals (#16)" --body "$(cat <<'EOF'
## Summary
- Serves `GET /monitor` from `backend/src/brain/static/brain.html` (new additive route in `BrainHTTPHandler.do_GET`)
- Self-contained HTML + Babel-in-browser + React 18: header vitals (cluster cores, mem/swap bars, status dot, uptime), footer event log, tweaks panel
- One pytest smoke test (`test_monitor_route_serves_html`) validates 200, content-type, title marker, root div

Closes #16

## Test plan
- [x] `python -m ruff check .` — green
- [x] `python -m pytest -q` — 192 passed
- [ ] Manual: open http://localhost:8621/monitor, observe header bars update after a hook fires, event log scrolls, tweaks panel toggles, Network tab confirms polling pauses when tab hidden

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Implementation notes for builder

**Order constraint:** Task 1 (route + test) and Task 2 (skeleton HTML) are co-dependent — the test fails until `brain.html` exists. Write the skeleton HTML first, then add the route, then run the test. The plan above reflects this: Task 1 references Task 2 at Step 1.3.

**`_json_response` is NOT used for the `/monitor` happy path.** It hardcodes `Content-Type: application/json`. The `/monitor` branch sends `text/html; charset=utf-8` using the lower-level `send_response` / `send_header` / `end_headers` / `wfile.write` directly.

**`from pathlib import Path` placement:** server.py currently imports only `json`, `logging`, `typing.Any`, `mcp`, and three `brain.*` modules. Add `from pathlib import Path` after `import logging` (line 14) to keep the stdlib block together. ruff will enforce import order.

**The `static/` directory does not exist yet.** The builder creates it by writing `brain.html` into `backend/src/brain/static/brain.html`. No `mkdir` command needed if the editor creates intermediate directories; otherwise `mkdir -p backend/src/brain/static` first.

**SPEC-3 through SPEC-8 share one file.** The checklist records them as separate spec items but they all land in `brain.html`. The builder ticks each individually but can commit them together since the file is not testable at the unit level.
