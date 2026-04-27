# Brain Monitor Phase 2 Implementation Plan

**Linked spec:** [2026-04-27-brain-monitor-phase2-design.md](../specs/2026-04-27-brain-monitor-phase2-design.md)
**Linked checklist:** [2026-04-27-brain-monitor-phase2-checklist.md](../specs/2026-04-27-brain-monitor-phase2-checklist.md)
**Goal:** Add force-directed graph, right-panel thought stream, and header activity sparkline to the Phase 1 brain monitor — all in `brain.html`, consuming existing endpoints only.
**Branch:** `feat/17-monitor-phase2`

---

## Pre-conditions

- Phase 1 PR #20 merged. `backend/src/brain/static/brain.html` contains Phase 1 skeleton (header htop, footer event log, tweaks panel).
- `backend/tests/test_brain/test_monitor_route.py::test_monitor_route_serves_html` passes (Phase 1 gate).
- `/graph`, `/events`, `/events/timeline` endpoints are live in `backend/src/brain/server.py` (lines 222–231).

---

## Task 0 — [TEST-1]: Schema smoke test for GET /graph

This is the one automated test for Phase 2. Write it **first**, before any HTML changes, so the gate exists.

**Files:**
- Create: `backend/tests/test_brain/test_graph_route.py`

### Step 0.1: Write the failing test

```python
# backend/tests/test_brain/test_graph_route.py
"""Schema smoke test for GET /graph — validates fields the JS monitor depends on."""
from __future__ import annotations

from http.server import HTTPServer
from pathlib import Path
from threading import Thread

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


def test_graph_route_returns_expected_schema(tmp_path: Path) -> None:
    srv, url = _start_server(tmp_path)
    try:
        # Seed two entries; use skip_gate=True so they bypass noise filter
        r1 = httpx.post(f"{url}/store", json={
            "content": "alpha memory for graph test",
            "agent": "test",
            "memory_type": "fact",
            "skip_gate": True,
        })
        assert r1.status_code == 200
        entry_id_1 = r1.json().get("id", "")

        r2 = httpx.post(f"{url}/store", json={
            "content": "beta memory for graph test",
            "agent": "test",
            "memory_type": "context",
            "links": entry_id_1,
            "skip_gate": True,
        })
        assert r2.status_code == 200

        resp = httpx.get(f"{url}/graph")
        assert resp.status_code == 200

        body = resp.json()
        assert "entries" in body
        entries = body["entries"]
        assert isinstance(entries, list)
        assert len(entries) >= 2

        for entry in entries:
            assert "id" in entry, f"missing 'id' in {entry}"
            assert "memory_type" in entry, f"missing 'memory_type' in {entry}"
            assert "links" in entry, f"missing 'links' in {entry}"
            assert "access_count" in entry, f"missing 'access_count' in {entry}"
            assert isinstance(entry["links"], str), (
                f"'links' must be str (CSV), got {type(entry['links'])}"
            )
            assert isinstance(entry["access_count"], int), (
                f"'access_count' must be int, got {type(entry['access_count'])}"
            )
    finally:
        srv.shutdown()
```

### Step 0.2: Run test, watch it pass (route already exists)

```bash
cd backend && python -m pytest tests/test_brain/test_graph_route.py::test_graph_route_returns_expected_schema -v
```

Expected: PASS (the route exists; this test validates schema only).

### Step 0.3: Tick [TEST-1] in checklist, commit

```bash
git add backend/tests/test_brain/test_graph_route.py docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧪 Test: graph route schema smoke test [TEST-1] (#17)"
```

---

## Task 1 — [SPEC-1]: Grid layout migration + focus state lift

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Phase 1's `<App>` renders a single-column middle row. Phase 2 migrates to 3 columns.

### Step 1.1: Edit `brain.html` — CSS and `<App>` layout

In the `<style>` block, replace:

```css
#root {
  display: grid;
  grid-template-rows: auto 1fr 180px;
  height: 100vh;
}
```

with:

```css
#root {
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  grid-template-rows: auto 1fr 180px;
  height: 100vh;
}
.header-row { grid-column: 1 / -1; }
.footer-row { grid-column: 1 / -1; }
.left-placeholder {
  background: rgba(255,255,255,0.01);
  border-right: 1px solid rgba(255,255,255,0.05);
}
.thought-stream {
  border-left: 1px solid rgba(255,255,255,0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
```

In `<App>`, add `const [focus, setFocus] = useState(null);` and replace the `<main>` placeholder with three siblings:

```jsx
// Inside <App> return, replacing:
//   <main style={{ overflow: "hidden" }} />
// with:
<div className="left-placeholder" />
<BrainGraph
  nodes={graph.nodes}
  edges={graph.edges}
  lastError={graph.lastError}
  isLoading={graph.isLoading}
  lastFetchedAt={graph.lastFetchedAt}
  onRefresh={graph.refresh}
  focus={focus}
  setFocus={setFocus}
  activatedAtRef={activatedAtRef}
  paused={paused}
/>
<ThoughtStream
  events={thoughts.events}
  focus={focus}
  setFocus={setFocus}
/>
```

The `<Header>` and `<Footer>` elements each need `className="header-row"` / `className="footer-row"` so they span all 3 columns. In the `<Header>` JSX, add `className="header-row"` to the wrapping `<header>` element. In `<Footer>`, add `className="footer-row"` to the wrapping `<footer>` element.

Declare the refs and hooks that Tasks 2–13 will implement (stubs return empty state so React renders without crashing while the feature is being wired):

```jsx
// In <App>, after the existing hooks:
const [focus, setFocus] = useState(null);
const activatedAtRef = useRef({});
// graph, thoughts, timeline are declared in Tasks 2, 11, 13 respectively
```

### Step 1.2: Manual verification anchor

Open `http://localhost:8621/monitor`. Three columns visible in the middle row. Header and footer still span full width. Phase 1 bars/footer-log/tweaks still work.

### Step 1.3: Tick [SPEC-1] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-1 grid layout migration + focus lift (#17)"
```

---

## Task 2 — [SPEC-2]: `useGraph()` hook + `paletteFor()` helper

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Add after the existing `useEvents` hook and before `<App>`:

```jsx
// ── paletteFor ───────────────────────────────────────────────────────────────
function paletteFor(memoryType) {
  const P = {
    fact:         '#6fd6c9',
    preference:   '#b48ead',
    context:      '#ebcb8b',
    decision:     '#a3be8c',
    event:        '#88c0d0',
    strategy:     '#d08770',
    relationship: '#bf616a',
  };
  return P[memoryType] ?? '#5d6478';
}

// ── useGraph ─────────────────────────────────────────────────────────────────
function useGraph() {
  const [state, setState] = React.useState({
    nodes: [], edges: [], lastError: null, lastFetchedAt: null, isLoading: false,
  });
  const fetchRef = React.useRef(null);

  function doFetch() {
    if (fetchRef.current) fetchRef.current.abort();
    const ctrl = new AbortController();
    fetchRef.current = ctrl;
    setState(s => ({ ...s, isLoading: true }));

    fetch('/graph', { signal: ctrl.signal })
      .then(r => r.json())
      .then(data => {
        const rawEntries = data.entries ?? [];
        if (rawEntries.length > 500) {
          setState({ nodes: [], edges: [], lastError: 'graph too large', lastFetchedAt: Date.now(), isLoading: false });
          return;
        }
        const nodeSet = new Set(rawEntries.map(e => e.id));
        const nodes = rawEntries.map(e => ({
          id: e.id,
          memory_type: e.memory_type,
          color: paletteFor(e.memory_type),
          size: 4 + Math.log((e.access_count ?? 0) + 1) * 2,
          access_count: e.access_count ?? 0,
          x: (Math.random() - 0.5) * 200,
          y: (Math.random() - 0.5) * 200,
          vx: 0, vy: 0,
          fx: null, fy: null,
        }));
        const seen = new Set();
        const edges = [];
        rawEntries.forEach(e => {
          const linkIds = e.links ? e.links.split(',').map(s => s.trim()).filter(Boolean) : [];
          linkIds.forEach(lid => {
            if (!nodeSet.has(lid)) return;
            const key = e.id < lid ? `${e.id}|${lid}` : `${lid}|${e.id}`;
            if (seen.has(key)) return;
            seen.add(key);
            edges.push([e.id < lid ? e.id : lid, e.id < lid ? lid : e.id]);
          });
        });
        setState({ nodes, edges, lastError: null, lastFetchedAt: Date.now(), isLoading: false });
      })
      .catch(err => {
        if (err.name === 'AbortError') return;
        setState(s => ({ ...s, lastError: err.message, isLoading: false }));
      });
  }

  React.useEffect(() => {
    doFetch();
    return () => { if (fetchRef.current) fetchRef.current.abort(); };
  }, []);

  return { ...state, refresh: doFetch };
}
```

In `<App>`, call `const graph = useGraph();`.

### Step 2.1: Manual verification anchor

Network tab shows exactly one `/graph` fetch on first paint. No further `/graph` polling.

### Step 2.2: Tick [SPEC-2] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-2 useGraph hook + paletteFor helper (#17)"
```

---

## Task 3 — [SPEC-3]: `<BrainGraph>` shell (canvas + ResizeObserver + error placeholders)

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Add the `<BrainGraph>` component after `useGraph`. At this stage it mounts the canvas and handles errors, but does not yet draw anything (simulation is Task 4).

```jsx
// ── BrainGraph ────────────────────────────────────────────────────────────────
function BrainGraph({ nodes, edges, lastError, isLoading, lastFetchedAt, onRefresh, focus, setFocus, activatedAtRef, paused }) {
  const wrapRef = React.useRef(null);
  const canvasRef = React.useRef(null);
  const [size, setSize] = React.useState({ w: 600, h: 400 });
  const viewRef = React.useRef({ x: 0, y: 0, k: 1 });
  const dragNodeRef = React.useRef(null);

  // ResizeObserver
  React.useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth || 600;
      const h = el.clientHeight || 400;
      setSize({ w, h });
      if (canvasRef.current) {
        canvasRef.current.width = w;
        canvasRef.current.height = h;
      }
    });
    ro.observe(el);
    const w = el.clientWidth || 600;
    const h = el.clientHeight || 400;
    setSize({ w, h });
    if (canvasRef.current) { canvasRef.current.width = w; canvasRef.current.height = h; }
    return () => ro.disconnect();
  }, []);

  if (lastError === 'graph too large') {
    return (
      <div ref={wrapRef} style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg)', opacity: 0.5, fontSize: '12px' }}>
        graph too large to render — use search instead
      </div>
    );
  }
  if (lastError) {
    return (
      <div ref={wrapRef} style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--err)', fontSize: '12px' }}>
        ouch — failed to load graph: {lastError}
      </div>
    );
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      <canvas ref={canvasRef} width={size.w} height={size.h} style={{ display: 'block' }} />
    </div>
  );
}
```

### Step 3.1: Manual verification anchor

Open `/monitor`. Center column shows an empty (black/transparent) canvas that resizes with the window. Force a network error (DevTools offline) — error placeholder text appears.

### Step 3.2: Tick [SPEC-3] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-3 BrainGraph shell + ResizeObserver + error placeholders (#17)"
```

---

## Task 4 — [SPEC-4]: Simulation tick + render loop

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Add the two standalone functions `simulate` and `render` before `<BrainGraph>`, then wire the rAF loop inside `<BrainGraph>`.

### Step 4.1: Add `simulate()` function

```jsx
// ── simulate ──────────────────────────────────────────────────────────────────
function simulate(nodes, edges, size, dragNode, nodeById) {
  const cx = size.w / 2, cy = size.h / 2;
  const REPULSE_SAME = 220;
  const REPULSE_CROSS = 380;
  const SPRING_K = 0.02;
  const CENTER_K = 0.0005;
  const CLUSTER_K = 0.001;
  const DAMP = 0.85;
  const DT = 0.5;
  const MARGIN = 30;

  // 1. Repulsion — O(n²) Coulomb.
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      let dx = a.x - b.x, dy = a.y - b.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 0.01) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 1; }
      const sameType = a.memory_type === b.memory_type;
      const k = sameType ? REPULSE_SAME : REPULSE_CROSS;
      const f = k / d2;
      const d = Math.sqrt(d2);
      a.vx += (dx / d) * f; a.vy += (dy / d) * f;
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
    }
  }

  // 2. Spring attraction along edges.
  for (const [aId, bId] of edges) {
    const a = nodeById.get(aId), b = nodeById.get(bId);
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const target = 80 + (a.size + b.size) / 2;
    const f = (d - target) * SPRING_K;
    a.vx += (dx / d) * f; a.vy += (dy / d) * f;
    b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
  }

  // 3. Center gravity (weak).
  for (const n of nodes) {
    n.vx += (cx - n.x) * CENTER_K;
    n.vy += (cy - n.y) * CENTER_K;
  }

  // 4. Cluster gravity — pull each node toward centroid of its memory_type group.
  const sums = {};
  for (const n of nodes) {
    const s = sums[n.memory_type] ??= { x: 0, y: 0, n: 0 };
    s.x += n.x; s.y += n.y; s.n += 1;
  }
  for (const t of Object.keys(sums)) {
    sums[t].x /= sums[t].n; sums[t].y /= sums[t].n;
  }
  for (const n of nodes) {
    const s = sums[n.memory_type];
    n.vx += (s.x - n.x) * CLUSTER_K;
    n.vy += (s.y - n.y) * CLUSTER_K;
  }

  // 5. Damping + integration + soft bounds.
  for (const n of nodes) {
    if (n === dragNode || n.fx != null) {
      n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; continue;
    }
    n.vx *= DAMP; n.vy *= DAMP;
    n.x += n.vx * DT; n.y += n.vy * DT;
    if (n.x < MARGIN) n.vx += (MARGIN - n.x) * 0.05;
    if (n.x > size.w - MARGIN) n.vx += (size.w - MARGIN - n.x) * 0.05;
    if (n.y < MARGIN) n.vy += (MARGIN - n.y) * 0.05;
    if (n.y > size.h - MARGIN) n.vy += (size.h - MARGIN - n.y) * 0.05;
  }
}
```

### Step 4.2: Add `render()` function

```jsx
// ── render ────────────────────────────────────────────────────────────────────
function render(ctx, nodes, edges, view, activatedAt, focus, nodeById) {
  const now = Date.now();
  ctx.save();
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.translate(view.x, view.y);
  ctx.scale(view.k, view.k);

  // Build edgeFocusSet for O(1) per-edge lookup when focused.
  let edgeFocusSet = null;
  if (focus) {
    edgeFocusSet = new Set([focus]);
    for (const [aId, bId] of edges) {
      if (aId === focus) edgeFocusSet.add(bId);
      if (bId === focus) edgeFocusSet.add(aId);
    }
  }

  // Edges (drawn under nodes).
  ctx.lineWidth = 1;
  for (const [aId, bId] of edges) {
    const a = nodeById.get(aId), b = nodeById.get(bId);
    if (!a || !b) continue;
    const inFocus = focus && (focus === aId || focus === bId);
    const eitherActive = (now - (activatedAt[aId] ?? 0) < 5000) || (now - (activatedAt[bId] ?? 0) < 5000);
    ctx.globalAlpha = focus ? (inFocus ? 0.9 : 0.05) : (eitherActive ? 0.5 : 0.15);
    ctx.strokeStyle = a.memory_type === b.memory_type ? a.color : '#3a3f4d';
    ctx.beginPath();
    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }

  // Halos (drawn between edges and nodes so they appear behind node fills).
  for (const n of nodes) {
    const t = activatedAt[n.id];
    if (!t) continue;
    const age = now - t;
    if (age >= 5000) continue;
    ctx.globalAlpha = 1 - age / 5000;
    ctx.fillStyle = n.color;
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.size + 6, 0, Math.PI * 2);
    ctx.fill();
  }

  // Nodes.
  const edgeSetTouchingFocus = edgeFocusSet;
  for (const n of nodes) {
    const dim = focus && focus !== n.id && !(edgeSetTouchingFocus && edgeSetTouchingFocus.has(n.id));
    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.fillStyle = n.color;
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
    ctx.fill();
    if (focus === n.id) {
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  ctx.restore();
}
```

### Step 4.3: Wire rAF loop in `<BrainGraph>`

Inside `<BrainGraph>`, after the ResizeObserver `useEffect`, add:

```jsx
// nodeById map — rebuild only when nodes array reference changes
const nodeById = React.useMemo(
  () => new Map(nodes.map(n => [n.id, n])),
  [nodes]
);

// rAF loop
React.useEffect(() => {
  const canvas = canvasRef.current;
  if (!canvas || nodes.length === 0) return;
  const ctx = canvas.getContext('2d');
  let rafId;

  const tick = () => {
    if (!paused) {
      simulate(nodes, edges, size, dragNodeRef.current, nodeById);
      render(ctx, nodes, edges, viewRef.current, activatedAtRef.current, focus, nodeById);
    }
    rafId = requestAnimationFrame(tick);
  };
  rafId = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(rafId);
}, [nodes, edges, size, paused, focus, nodeById]);
```

### Step 4.4: Manual verification anchor

Seed a few entries. Open `/monitor`. Nodes spread and cluster by color. Tab away — CPU drops. Tweaks panel "pause" → CPU drops.

### Step 4.5: Tick [SPEC-4] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-4 simulation tick + render loop (#17)"
```

---

## Task 5 — [SPEC-5]: Click-to-focus

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Inside `<BrainGraph>`, add mouse-event handlers on the `<canvas>` element. These share state with Task 6 (drag), so both [SPEC-5] and [SPEC-6] are wired in the same event handler block. Write [SPEC-5] first, then extend in Task 6.

```jsx
// Hit test helper — call inside BrainGraph
function hitTest(clientX, clientY, rect, view, nodes) {
  const wx = (clientX - rect.left - view.x) / view.k;
  const wy = (clientY - rect.top - view.y) / view.k;
  let closest = null, minD2 = Infinity;
  for (const n of nodes) {
    const dx = n.x - wx, dy = n.y - wy;
    const d2 = dx * dx + dy * dy;
    const threshold = n.size + 4;
    if (d2 < threshold * threshold && d2 < minD2) { minD2 = d2; closest = n; }
  }
  return { node: closest, wx, wy };
}
```

Inside `<BrainGraph>` body, declare interaction refs:

```jsx
const mouseDownRef = React.useRef(null); // { x, y, wx, wy, node|null, isPan }
const panStartRef = React.useRef(null);  // { x, y, vx, vy }
```

Canvas event handlers:

```jsx
function handleMouseDown(e) {
  if (e.button !== 0) return;
  const rect = canvasRef.current.getBoundingClientRect();
  const { node, wx, wy } = hitTest(e.clientX, e.clientY, rect, viewRef.current, nodes);
  mouseDownRef.current = { x: e.clientX, y: e.clientY, wx, wy, node };
  if (node) {
    node.fx = wx; node.fy = wy;
    dragNodeRef.current = node;
  } else {
    panStartRef.current = { x: e.clientX, y: e.clientY, vx: viewRef.current.x, vy: viewRef.current.y };
  }
}

function handleMouseMove(e) {
  if (!mouseDownRef.current) return;
  const { node } = mouseDownRef.current;
  if (node) {
    const rect = canvasRef.current.getBoundingClientRect();
    const wx = (e.clientX - rect.left - viewRef.current.x) / viewRef.current.k;
    const wy = (e.clientY - rect.top - viewRef.current.y) / viewRef.current.k;
    node.fx = wx; node.fy = wy;
  } else if (panStartRef.current) {
    viewRef.current.x = panStartRef.current.vx + (e.clientX - panStartRef.current.x);
    viewRef.current.y = panStartRef.current.vy + (e.clientY - panStartRef.current.y);
  }
}

function handleMouseUp(e) {
  if (!mouseDownRef.current) return;
  const { x, y, node } = mouseDownRef.current;
  const moved = Math.hypot(e.clientX - x, e.clientY - y);
  if (node) {
    node.fx = null; node.fy = null;
    dragNodeRef.current = null;
    if (moved < 3) {
      // click: toggle focus
      setFocus(prev => prev === node.id ? null : node.id);
    }
  } else {
    if (moved < 3) setFocus(null); // click on background clears focus
    panStartRef.current = null;
  }
  mouseDownRef.current = null;
}

function handleMouseLeave() {
  if (mouseDownRef.current?.node) {
    const n = mouseDownRef.current.node;
    n.fx = null; n.fy = null;
    dragNodeRef.current = null;
  }
  panStartRef.current = null;
  mouseDownRef.current = null;
}
```

Wire handlers on the `<canvas>`:

```jsx
<canvas
  ref={canvasRef}
  width={size.w}
  height={size.h}
  style={{ display: 'block', cursor: panStartRef.current ? 'grabbing' : 'grab' }}
  onMouseDown={handleMouseDown}
  onMouseMove={handleMouseMove}
  onMouseUp={handleMouseUp}
  onMouseLeave={handleMouseLeave}
/>
```

### Step 5.1: Manual verification anchor

Click a node → node gets a white ring; thought stream (once wired in Task 12) filters. Click empty space → focus clears.

### Step 5.2: Tick [SPEC-5] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-5 click-to-focus (#17)"
```

---

## Task 6 — [SPEC-6]: Drag-to-pin

**Files:**
- Modify: `backend/src/brain/static/brain.html`

The drag-to-pin behavior is already partially implemented by the `handleMouseDown`/`handleMouseMove`/`handleMouseUp` handlers written in Task 5 — `node.fx = wx; node.fy = wy` is set on mousedown-on-node, updated on mousemove, and cleared on mouseup. The `simulate()` function already honors `fx/fy` (step 5 of algorithm: `if (n.fx != null) { n.x = n.fx; n.y = n.fy; ... }`).

No new code is required. Task 6 is: verify the drag path is correct and the pin clears on mouseup.

### Step 6.1: Verify drag behavior in manual test

Click and hold a node, drag across canvas; node follows cursor. Release → pin clears, node drifts back under simulation forces.

### Step 6.2: Tick [SPEC-6] in checklist, commit

```bash
git add docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-6 drag-to-pin (covered by Task 5 handler, verified manually) (#17)"
```

---

## Task 7 — [SPEC-7]: Pan + zoom

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Add the wheel handler to `<BrainGraph>`. Pan is already partially implemented in `handleMouseMove` / `handleMouseUp`. Add `onWheel`:

```jsx
function handleWheel(e) {
  e.preventDefault();
  const rect = canvasRef.current.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const factor = Math.exp(-e.deltaY * 0.001);
  const newK = Math.max(0.4, Math.min(3, viewRef.current.k * factor));
  // zoom toward cursor: keep world-point under cursor fixed
  const wx = (mx - viewRef.current.x) / viewRef.current.k;
  const wy = (my - viewRef.current.y) / viewRef.current.k;
  viewRef.current.x = mx - wx * newK;
  viewRef.current.y = my - wy * newK;
  viewRef.current.k = newK;
}
```

Add `onWheel={handleWheel}` to the `<canvas>` element. Because `onWheel` in React is passive by default, add a `useEffect` to attach it as a non-passive listener:

```jsx
React.useEffect(() => {
  const canvas = canvasRef.current;
  if (!canvas) return;
  const handler = (e) => { e.preventDefault(); handleWheel(e); };
  canvas.addEventListener('wheel', handler, { passive: false });
  return () => canvas.removeEventListener('wheel', handler);
}, [size]); // re-attach when size changes (canvas ref stays stable)
```

Remove `onWheel` from the JSX `<canvas>` element since it's attached imperatively above.

### Step 7.1: Manual verification anchor

Scroll wheel → zoom toward cursor. Click+drag on background → graph pans. Cursor switches between `grab` and `grabbing` appropriately.

### Step 7.2: Tick [SPEC-7] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-7 pan + zoom (#17)"
```

---

## Task 8 — [SPEC-8]: Edge rendering refinement

**Files:**
- Modify: `backend/src/brain/static/brain.html`

The `render()` function written in Task 4 already implements the full edge-rendering logic per spec. Task 8 is: confirm the `edgeFocusSet` computation for O(1) per-edge lookup is present (it is, in the `render` function above). No new code needed.

### Step 8.1: Manual verification anchor

With no focus: edges are dim grey by default, brighten when a recently-activated endpoint has a halo. With focus on a node: edges to neighbors are bright accent-colored; all other edges fade to ~5% opacity.

### Step 8.2: Tick [SPEC-8] in checklist, commit

```bash
git add docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-8 edge rendering with focus/activation alpha (covered by Task 4 render(), verified manually) (#17)"
```

---

## Task 9 — [SPEC-9]: Activation halos

**Files:**
- Modify: `backend/src/brain/static/brain.html`

The halo rendering is already implemented inside `render()` in Task 4. Task 9 is: confirm the halo path reads `activatedAtRef.current` (not a React state), which the rAF loop accesses directly without triggering re-renders.

### Step 9.1: Manual verification anchor

After a `curl -X POST http://localhost:8621/store` with content, the corresponding node lights up with a soft halo within ≤2 s (the `useThoughts` polling interval), fading out over 5 s.

### Step 9.2: Tick [SPEC-9] in checklist, commit

```bash
git add docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-9 activation halos (covered by Task 4 render(), verified manually) (#17)"
```

---

## Task 10 — [SPEC-10]: Refresh button overlay

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Inside `<BrainGraph>`'s return, inside the wrapper `<div>`, add the refresh button after the `<canvas>`:

```jsx
<button
  onMouseDown={e => e.stopPropagation()}
  onClick={onRefresh}
  disabled={isLoading}
  style={{
    position: 'absolute', top: '8px', right: '8px',
    background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)',
    color: 'var(--fg)', borderRadius: '4px', padding: '3px 8px',
    cursor: isLoading ? 'default' : 'pointer',
    fontFamily: 'var(--font)', fontSize: '11px', display: 'flex', gap: '6px', alignItems: 'center',
  }}
>
  {isLoading ? 'loading…' : '↻ refresh'}
  {!isLoading && lastFetchedAt && (
    <span style={{ opacity: 0.5 }}>
      {formatRelative(new Date(lastFetchedAt).toISOString())}
    </span>
  )}
</button>
```

The `onMouseDown={e => e.stopPropagation()}` prevents the canvas pan-start handler from firing when the button is clicked.

### Step 10.1: Manual verification anchor

Click the refresh button → network tab shows a new `/graph` fetch; relative time updates; button briefly shows "loading…" and re-enables on success.

### Step 10.2: Tick [SPEC-10] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-10 refresh button overlay (#17)"
```

---

## Task 11 — [SPEC-11]: `useThoughts()` hook + activation halo updates

**Files:**
- Modify: `backend/src/brain/static/brain.html`

Add `useThoughts` next to `useEvents`:

```jsx
// ── useThoughts ──────────────────────────────────────────────────────────────
function useThoughts(speed, paused, nodeSet, activatedAtRef) {
  const [state, setState] = React.useState({ events: [], lastError: null });
  const prevEventsRef = React.useRef([]);

  React.useEffect(() => {
    if (paused) return;
    const ctrl = new AbortController();
    const intervalMs = Math.round(2000 / speed);

    async function fetchData() {
      try {
        const r = await fetch('/events?limit=20', { signal: ctrl.signal });
        const data = await r.json();
        const newEvents = [...(data.events ?? [])].reverse();

        // Update activatedAt for nodes that appear in new events
        const prevSet = new Set(prevEventsRef.current.map(e => e.timestamp));
        for (const ev of newEvents) {
          if (prevSet.has(ev.timestamp)) continue;
          const entryId = ev.metadata?.entry_id ?? (ev.node_id || null);
          if (entryId && nodeSet.has(entryId)) {
            activatedAtRef.current[entryId] = Date.now();
          }
        }
        prevEventsRef.current = newEvents;
        setState({ events: newEvents, lastError: null });
      } catch (err) {
        if (err.name !== 'AbortError') {
          setState(s => ({ ...s, lastError: err.message }));
        }
      }
    }

    fetchData();
    const id = setInterval(fetchData, intervalMs);
    return () => { clearInterval(id); ctrl.abort(); };
  }, [speed, paused, nodeSet]);

  return state;
}
```

In `<App>`, after `const graph = useGraph();`, add:

```jsx
const nodeSet = React.useMemo(() => new Set(graph.nodes.map(n => n.id)), [graph.nodes]);
const thoughts = useThoughts(tweaks.speed, paused, nodeSet, activatedAtRef);
```

### Step 11.1: Manual verification anchor

Trigger a `/store` then watch a graph node halo appear within ≤2 s.

### Step 11.2: Tick [SPEC-11] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-11 useThoughts hook + activatedAt updates (#17)"
```

---

## Task 12 — [SPEC-12]: `<ThoughtStream>` component

**Files:**
- Modify: `backend/src/brain/static/brain.html`

```jsx
// ── ThoughtStream ─────────────────────────────────────────────────────────────
function ThoughtStream({ events, focus, setFocus }) {
  function badgeColor(type) {
    if (type === 'hook_wake_up') return 'var(--ok)';
    if (type === 'hook_post_turn') return 'var(--accent)';
    if (type.includes('reject')) return 'var(--swap)';
    if (type.includes('error') || type.includes('failed')) return 'var(--err)';
    return '#555';
  }

  const filtered = focus
    ? events.filter(ev => ev.node_id === focus || ev.metadata?.entry_id === focus)
    : events;

  return (
    <div className="thought-stream">
      <div style={{
        padding: '6px 10px',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'rgba(255,255,255,0.02)', flexShrink: 0,
        fontSize: '11px',
      }}>
        {focus ? (
          <>
            <span style={{ color: 'var(--accent)' }}>focused: {focus.slice(0, 8)}</span>
            <button
              onClick={() => setFocus(null)}
              style={{ background: 'none', border: 'none', color: 'var(--fg)', cursor: 'pointer', padding: '0 4px', fontSize: '12px' }}
            >×</button>
          </>
        ) : (
          <span style={{ opacity: 0.5 }}>all events</span>
        )}
      </div>
      <ul style={{ listStyle: 'none', overflowY: 'auto', flex: 1, padding: '4px 0' }}>
        {filtered.map((ev, i) => {
          const type = ev.event_type ?? '';
          const details = (ev.details ?? '').slice(0, 40);
          const meta = ev.metadata ?? {};
          return (
            <li key={`${ev.timestamp}-${i}`} style={{
              padding: '3px 10px',
              borderBottom: '1px solid rgba(255,255,255,0.04)',
              fontSize: '11px',
              display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'baseline',
            }}>
              <span style={{ padding: '0 3px', borderRadius: '2px', background: badgeColor(type), color: '#000', fontSize: '10px', flexShrink: 0 }}>
                {type}
              </span>
              <span style={{ opacity: 0.7, flexShrink: 0 }}>{ev.agent ?? ''}</span>
              {details && <span style={{ opacity: 0.6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '120px' }}>{details}</span>}
              {meta.duration_ms != null && <span style={{ opacity: 0.45, flexShrink: 0 }}>{meta.duration_ms}ms</span>}
              {meta.tokens_approx != null && <span style={{ opacity: 0.45, flexShrink: 0 }}>{meta.tokens_approx}t</span>}
              <span style={{ opacity: 0.4, flexShrink: 0, marginLeft: 'auto' }}>{formatRelative(ev.timestamp)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

In `<App>`, the `<ThoughtStream>` element is already wired from Task 1 with `events={thoughts.events}`.

### Step 12.1: Manual verification anchor

With a busy session, the right column shows newest 20 events with badges. Clicking a graph node filters the list. Clicking × restores all events.

### Step 12.2: Tick [SPEC-12] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-12 ThoughtStream component (#17)"
```

---

## Task 13 — [SPEC-13]: `useTimeline()` hook + `<ActivitySparkline>` component

**Files:**
- Modify: `backend/src/brain/static/brain.html`

```jsx
// ── useTimeline ───────────────────────────────────────────────────────────────
function useTimeline() {
  const [state, setState] = React.useState({ buckets: [], lastError: null });

  React.useEffect(() => {
    const ctrl = new AbortController();

    async function fetchData() {
      if (document.hidden) return;
      try {
        const r = await fetch('/events/timeline', { signal: ctrl.signal });
        const data = await r.json();
        setState({ buckets: data.timeline ?? [], lastError: null });
      } catch (err) {
        if (err.name !== 'AbortError') {
          setState(s => ({ ...s, lastError: err.message }));
        }
      }
    }

    fetchData();
    const id = setInterval(fetchData, 60000);
    return () => { clearInterval(id); ctrl.abort(); };
  }, []);

  return state;
}

// ── ActivitySparkline ─────────────────────────────────────────────────────────
function ActivitySparkline({ buckets }) {
  const [tooltip, setTooltip] = React.useState(null); // { i, x, y }

  if (!buckets || buckets.length === 0) {
    return (
      <svg viewBox="0 0 120 16" width="120" height="16" style={{ flexShrink: 0 }}>
        <rect width="120" height="16" fill="var(--dim)" opacity="0.2" />
      </svg>
    );
  }

  const TYPES = ['archived', 'merged', 'reinforced', 'searched', 'stored'];
  const COLORS = {
    stored:     'var(--ok)',
    searched:   'var(--accent)',
    reinforced: '#7da9d8',
    merged:     'var(--swap)',
    archived:   'var(--dim)',
  };

  const totals = buckets.map(b => TYPES.reduce((s, t) => s + (b[t] ?? 0), 0));
  const maxTotal = Math.max(1, ...totals);

  const allZero = totals.every(t => t === 0);
  if (allZero) {
    return (
      <svg viewBox="0 0 120 16" width="120" height="16" style={{ flexShrink: 0 }}>
        <rect width="120" height="16" fill="var(--dim)" opacity="0.2" />
      </svg>
    );
  }

  const bars = buckets.map((b, i) => {
    const barX = i * 5; // 4px bar + 1px gap
    let yOff = 16;
    const rects = [];
    for (const t of TYPES) {
      const count = b[t] ?? 0;
      if (count === 0) continue;
      const h = (count / maxTotal) * 16;
      yOff -= h;
      rects.push(<rect key={t} x={barX} y={yOff} width="4" height={h} fill={COLORS[t]} />);
    }
    return (
      <g key={i}
        onMouseEnter={e => setTooltip({ i, x: barX, y: 0, b })}
        onMouseLeave={() => setTooltip(null)}
        style={{ cursor: 'default' }}
      >
        {rects}
      </g>
    );
  });

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <svg viewBox="0 0 120 16" width="120" height="16" style={{ flexShrink: 0, display: 'block' }}>
        {bars}
      </svg>
      {tooltip && (
        <div style={{
          position: 'absolute', bottom: '20px', left: `${tooltip.x}px`,
          background: 'rgba(10,10,18,0.95)', border: '1px solid rgba(255,255,255,0.15)',
          borderRadius: '3px', padding: '4px 6px', fontSize: '10px', whiteSpace: 'nowrap',
          pointerEvents: 'none', zIndex: 10,
        }}>
          {TYPES.filter(t => tooltip.b[t] > 0).map(t => (
            <div key={t}>{t}: {tooltip.b[t]}</div>
          ))}
        </div>
      )}
    </div>
  );
}
```

Add `--dim` CSS variable if not already present (it is used by `ActivitySparkline`):

```css
/* In <style> :root block — add if missing */
--dim: #5d6478;
```

In `<App>`, add:

```jsx
const timeline = useTimeline();
```

In the `<Header>` component, add `buckets={timeline.buckets}` prop and render `<ActivitySparkline buckets={buckets} />` inside the header's top-right div (next to the existing total/uptime/phase badges):

```jsx
// Inside <Header>, in the right-side flex div after the phase badge:
<ActivitySparkline buckets={buckets} />
```

Update `<Header>` signature to accept `buckets`:

```jsx
function Header({ stats, queue, lastError, startMs, buckets }) {
```

In `<App>`, update the `<Header>` call:

```jsx
<Header stats={stats} queue={queue} lastError={lastError} startMs={startMs} buckets={timeline.buckets} />
```

### Step 13.1: Manual verification anchor

After a few minutes of session traffic, the header right side shows a 24-bucket stacked bar chart with non-zero colored bars. On a fresh brain with empty event log, the strip is uniformly grey.

### Step 13.2: Tick [SPEC-13] in checklist, commit

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "🧠 Feature: SPEC-13 useTimeline + ActivitySparkline (#17)"
```

---

## Final Task — Verification gates

### Step F.1: Ruff

```bash
cd backend && python -m ruff check .
```

Expected: 0 errors. The only new Python file is `test_graph_route.py` — it follows the same patterns as existing test files.

### Step F.2: Pytest

```bash
cd backend && python -m pytest -q
```

Expected: ≥193 passed (192 baseline + 1 new `test_graph_route_returns_expected_schema`). Both the new [TEST-1] and the Phase 1 [TEST-1] (`test_monitor_route.py::test_monitor_route_serves_html`) must be green.

### Step F.3: Frontend gates — skipped

No `frontend/` package touched. `brain.html` is served as static HTML; no `pnpm` workspace exists yet.

### Step F.4: Tick [GATE-1/2/3] in checklist, push, open PR

```bash
git add docs/specs/2026-04-27-brain-monitor-phase2-checklist.md
git commit -m "📓 Docs: tick GATE-1/2/3 in Phase 2 checklist (#17)"
git push origin feat/17-monitor-phase2
gh pr create --title "Brain monitor Phase 2: graph viz + thought stream" --body "$(cat <<'EOF'
Closes #17

## Summary
- 3-column grid layout replacing Phase 1 single-column middle row
- Force-directed graph (canvas, Verlet simulation) in center column
- Thought stream with click-to-focus in right column
- Activity sparkline (24-bucket stacked SVG) in header
- Schema smoke test for GET /graph

## Test plan
- [x] `ruff check .` passes
- [x] `pytest -q` passes (≥193 tests, including new test_graph_route_returns_expected_schema)
- [ ] Manual dogfood: open /monitor, verify graph renders + focus + drag + sparkline
EOF
)"
```

---

## Dependency analysis

| System | Impact |
|--------|--------|
| HTTP API | No change. Reads `/graph`, `/events?limit=20`, `/events/timeline` — all pre-existing. |
| MCP tools | No change. |
| Storage | No change. No SQLite migration, no ChromaDB re-index. |
| Frontend | `brain.html` modified (single file). No `frontend/` package. |
| Installer | No change. |
| Hooks | No change. `wake_up`/`post_turn`/`statusline` contracts unchanged. |
| Benchmarks | No impact. Monitor is read-only. |
| Docs | Checklist ticked per task. No README/CLAUDE.md update needed. |
| Consumers | Money (`:8611`): no impact. Marcel: no impact. |

## Risks

1. **`O(n²)` repulsion at N > 200.** Hard cap at 500 nodes in `useGraph` short-circuit. Brain dogfood is O(100s). Acceptable for Phase 2.
2. **`activatedAtRef` shared between `<BrainGraph>` (reads) and `useThoughts` (writes).** Must be passed as a prop, not recreated. Scoped in `<App>` via `useRef({})`. If the builder creates it inside `<BrainGraph>` instead, halos will never fire.
3. **`simulate`'s `dragNode` comparison (`n === dragNode`).** The dragged node is a direct object reference from `nodes` array. Must not be reconstructed on every render — keep nodes array stable (mutate positions in place, do not `setState` per tick).
4. **`useThoughts` and `useEvents` are two parallel fetchers at 2 s.** If the builder accidentally merges them into one hook that returns 200 events, the `useThoughts` filtering for focus-halo updates will not work correctly. Keep them separate.
5. **`??=` operator** (`sums[n.memory_type] ??= { ... }`) requires Chrome ≥85/Firefox ≥79/Safari ≥14. Since this runs in-browser (developer dogfood only), it is acceptable — no IE support needed. Babel standalone will transpile it anyway.
6. **Wheel event passivity.** React attaches `onWheel` as a passive listener by default in React 17+. The builder must attach it imperatively with `{ passive: false }` via `useEffect` to call `e.preventDefault()` (suppress default scroll behavior). Covered in Task 7.
7. **`ResizeObserver` + `canvas.width` reassignment.** Setting `canvas.width` clears the canvas content. The rAF loop redraws immediately on next frame, so there is a single blank frame on resize — acceptable.
