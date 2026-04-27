# Brain Monitor — Phase 2 (graph + thought stream) — Design

**Goal:** Make the memory store's *shape* and Brain's *live action* visible inside the Phase 1 monitor by adding a force-directed graph, a real-time thought stream, and a header activity sparkline — all consuming existing HTTP endpoints, no backend changes.
**Roadmap phase:** R:phase-2b
**Cycle invocation:** Phase 2 of 3. Builds on the Phase 1 spec ([2026-04-27-brain-monitor-phase1-design.md](2026-04-27-brain-monitor-phase1-design.md)). Phase 3 (left panel + matrix/console + search/shortcuts/keybindings/localStorage) follows.

## Scope (in)

- **Layout migration in `brain.html`.** Phase 1 grid was `grid-template-rows: auto 1fr 180px` with a single empty placeholder for the middle row. Phase 2 changes the grid to `grid-template-columns: 280px 1fr 320px` × `grid-template-rows: auto 1fr 180px`. Header and footer keep spanning all 3 columns. The middle row gains three children: left placeholder (reserved for Phase 3), center `<BrainGraph>`, right `<ThoughtStream>`. Phase 1's `<Header>`, `<Footer>`, `<TweaksPanel>` continue to render unchanged.
- **`useGraph()` hook** — fetches `GET /graph` once on mount and on a manual refresh trigger. Returns `{ nodes, edges, lastError, lastFetchedAt, refresh }`. Parses each entry's `links` CSV string into individual neighbor IDs. Builds an undirected edge set deduped via the unordered pair `(min(a,b), max(a,b))`. Computes derived per-node fields (`color` via deterministic palette keyed by `memory_type`, `size = 4 + Math.log(access_count + 1) * 2`, initial random `x/y/vx/vy = 0`).
- **`<BrainGraph>` component** — canvas-rendered force-directed simulation, ~250 lines. Mounts a `<canvas>` element, runs a `requestAnimationFrame` tick loop calling `simulate(nodes, edges, size, dragNode)` then `render(ctx, nodes, edges, view, activatedAt, focus)`. Pauses when `tweaks.running === false` or `document.hidden`.
- **Click-to-focus** — picking by brute-force nearest-node-within-`size+4`-px on `mousedown` (canvas coordinates → world coordinates via the inverse view transform). Click sets `focus = node.id` (lifted state in `<App>`). Clicking the same node again clears focus. Clicking the empty background clears focus.
- **Drag-to-pin** — `mousedown` on a node + `mousemove` updates `node.fx, node.fy` to follow cursor (world coords). On `mouseup`, the pin clears (`node.fx = node.fy = null`) — the brainstorm specifies "temporarily pin", not persistent. Drag is mutually exclusive with pan.
- **Pan + zoom** — wheel zooms toward cursor by `Math.exp(-deltaY * 0.001)` clamped `[0.4, 3]`. Background `mousedown` (no node hit) starts a pan that updates `view.x, view.y`. Single shared `view = { x, y, k }` ref.
- **Edge rendering** — straight lines, 1 px, `globalAlpha = focus ? (edgeIsInFocusSet ? 0.9 : 0.05) : (edgeEitherActivated ? 0.5 : 0.15)`. No arrowheads (graph is undirected). Same-`memory_type` edges colored by that type; cross-type edges colored grey (`#3a3f4d`).
- **Activation halos** — when a `useThoughts` poll returns events with `metadata.entry_id` (or, fallback, `node_id` if `metadata` is absent — see [Architecture](#architecture)), `activatedAt[id] = Date.now()`. Render a halo around the node with `globalAlpha = 1 - (now - activatedAt[id]) / 5000` while `now - activatedAt[id] < 5000`, then fade out. Halo radius = `node.size + 6`.
- **Refresh button** — overlaid on the graph canvas, top-right corner of the center column, button label `↻ refresh`. Clicking calls `useGraph().refresh()`. Disabled while a refresh fetch is in flight; shows the formatted-relative `lastFetchedAt` next to the button (e.g. "fetched 2m ago").
- **`useThoughts(speed, paused)` hook** — like Phase 1's `useEvents` but `?limit=20` and a 2 s base interval (`2000 / speed`). Returns `{ events, lastError }`. Pauses on `document.hidden` and `paused === true`. **`useThoughts` runs in addition to the existing `useEvents` hook** — `useEvents` keeps polling 200 events at 2 s for the footer log, `useThoughts` polls 20 events at 2 s for the right sidebar plus activation halo updates. Two parallel fetches every 2 s ≈ 5 KB/s — acceptable.
- **`<ThoughtStream>` component** — sticky header showing the active focus filter (or "all events"), with a "× clear" button when focus is set. Body is a scrollable `<ul>` (real list, screen-reader compatible) of up to 20 events newest-first. When `focus` is set, the list filters to events where `node_id === focus` OR `metadata.entry_id === focus`. Each `<li>` shows `[colored badge for event_type] [event_type] · [agent] · [details truncated 40] · [duration_ms · tokens] · [relative time via Phase 1's formatRelative]`. Reuses Phase 1's flash-on-new-entry CSS keyframe.
- **`useTimeline()` hook** — polls `GET /events/timeline` every 60 s. Returns `{ buckets, lastError }` where `buckets` is the array of 24 dicts `{ hour, stored, searched, reinforced, merged, archived }` returned by the backend.
- **`<ActivitySparkline>` component** — inline SVG, 24 bars × stacked sub-bars by event type, total width ~120 px × height 16 px. Bar width = 4 px, gap = 1 px. Stacked colors: `stored` = green (`--ok`), `searched` = cyan (`--accent`), `reinforced` = blue (`--mem-blue`, new CSS var `#7da9d8`), `merged` = yellow (`--swap`), `archived` = grey (`--dim`). Hover on a bar shows a small tooltip with the bucket counts. When all 24 buckets are zero, render a uniform grey strip (no `Math.max(0)` divide-by-zero).
- **`focus` state lifted to `<App>`** — declared as `const [focus, setFocus] = useState(null)`. Passed to `<BrainGraph>` (drives node highlighting + edge focus-set rendering) and to `<ThoughtStream>` (drives event filtering).
- **Tests:** one new pytest schema-smoke test for `GET /graph`, validating that response entries contain the keys the JS depends on (`id`, `memory_type`, `links`, `access_count`). Phase 1's existing tests remain green (no regression).

## Scope (out — explicit YAGNI)

- Left-panel cluster meters, top-accessed memory list, matrix view, console view — all Phase 3.
- Search / filter UI on the thought stream — Phase 3.
- Keyboard shortcuts — Phase 3.
- localStorage tweak persistence — Phase 3.
- Editing memories from the graph (delete, merge, supersede) — read-only.
- Quadtree / barnes-hut / WebGL acceleration — `O(n²)` repulsion is fine at ≤300 nodes.
- 3D graph, three.js, d3-force from CDN.
- Adding new HTTP endpoints — strictly read-only consumption of `/graph`, `/events`, `/events/timeline`.
- SSE / WebSocket transport — polling stays.
- Mobile responsive layout.
- Persisting `view` (zoom/pan) across page reloads — Phase 3 with localStorage.

## Constraints

- Phase 2 modifies the same single self-contained file `backend/src/brain/static/brain.html` created by Phase 1. NO new HTML/JSX/CSS file is added; everything is appended/edited inside that one file.
- Phase 2 does NOT delete any Phase 1 feature. The header htop bars, footer event log, tweaks panel must continue working unchanged.
- Phase 2 adds NO new HTTP route. `/graph` and `/events/timeline` already exist (`server.py` lines 221–224 and 229–231 respectively, confirmed pre-Phase-2). Phase 2 only consumes them.
- Babel-in-browser + React 18 from unpkg CDN must continue to work — no build step.
- Simulation must pause when `document.hidden` (visibility API) AND when `tweaks.running === false`. No CPU burn on hidden tabs.
- Simulation tick budget: target ~30 fps. Repulsion is `O(n²)` so ≤300 nodes; `useGraph` short-circuits if the entries list exceeds 500 (display "graph too large to render — use search instead" placeholder rather than freeze the browser).
- Canvas resizes via `ResizeObserver` on the graph wrapper. On resize, only the view transform rescales — no re-simulation, no node-position reset.
- Manual dogfood is the verification path for HTML/JSX [SPEC-N]s (per Phase 1 policy). The single new pytest [TEST-N] is automated.

## Architecture

### File layout (after this PR)

```
backend/src/brain/
├── server.py                           # unchanged
└── static/
    └── brain.html                      # MODIFIED — adds ~600 lines (graph + stream + sparkline + grid migration)

backend/tests/test_brain/
└── test_graph_route.py                 # NEW — schema smoke test
```

### Component tree (additions vs Phase 1)

```
<App>
  <Header>
    [Phase 1 cluster bars / mem / swap / status / since / total / version]
    <ActivitySparkline buckets={timeline.buckets} />          ← NEW
  </Header>
  <Main className="phase2-grid">                              ← UPDATED layout
    <LeftPlaceholder />                                       ← NEW (empty 280 px column)
    <BrainGraph                                               ← NEW
      nodes={graph.nodes}
      edges={graph.edges}
      focus={focus}
      setFocus={setFocus}
      activatedAt={activatedAt}
      paused={paused}
      onRefresh={graph.refresh}
      lastFetchedAt={graph.lastFetchedAt}
    />
    <ThoughtStream                                            ← NEW
      events={thoughts.events}
      focus={focus}
      setFocus={setFocus}
    />
  </Main>
  <Footer events={events} />                                  [Phase 1, unchanged]
  <TweaksPanel tweaks={tweaks} setTweaks={setTweaks} />       [Phase 1, unchanged]
</App>
```

### Data flow

1. `useGraph()` calls `GET /graph` once on mount, returns `{ entries: [...] }`. The hook parses each entry — splitting `links` (CSV string) on comma, trimming whitespace, dropping empties — and builds `nodes` (with derived `color`, `size`, plus initial `x = canvasW/2 + jitter`, `y = canvasH/2 + jitter`, `vx = vy = 0`, `pinned = false`). Edges are constructed once: for each entry, for each `linkId` in its parsed link list, if `linkId` exists as a node id, add the unordered pair `(min(a, b), max(a, b))` to a `Set` to dedupe.
2. `useThoughts(speed, paused)` polls `GET /events?limit=20` every 2 s. After each poll, walk new events; for each event whose `metadata.entry_id` (or, fallback, `node_id` when `metadata` is undefined and `node_id` is non-empty — `EventLog.recent` returns either) maps to a node id present in `useGraph().nodes`, set `activatedAt[id] = Date.now()`. The `activatedAt` map is held in a `useRef` (no re-render on update) and read directly by the canvas render loop.
3. `useTimeline()` polls `GET /events/timeline` every 60 s. Returns 24 buckets matching `EventLog.stats_over_time`'s shape (`{ hour, stored, searched, reinforced, merged, archived }`). `<ActivitySparkline>` reads the buckets and renders the SVG.
4. `<BrainGraph>` runs a `requestAnimationFrame` loop: `simulate()` mutates `nodes` velocities/positions in place, `render(ctx, ...)` draws the frame. The loop short-circuits when `paused === true`.

### `/graph` response shape (confirmed from `store.py::get_all_for_graph`, lines 846–867)

```json
{
  "entries": [
    {
      "id": "<uuid>",
      "content": "<truncated to 60 chars>",
      "memory_type": "fact",
      "agent": "...",
      "confidence": 1.0,
      "access_count": 0,
      "links": "id1,id2,id3",
      "symbols": "...",
      "strategies": "...",
      "source": "...",
      "superseded_by": ""
    },
    ...
  ]
}
```

### `/events/timeline` response shape (from `events.py::stats_over_time`)

```json
{
  "timeline": [
    { "hour": -24, "stored": 0, "searched": 0, "reinforced": 0, "merged": 0, "archived": 0 },
    ...
    { "hour": -1,  "stored": 5, "searched": 12, "reinforced": 1, "merged": 0, "archived": 0 }
  ]
}
```

24 entries. When the event log file does not exist or is empty, `stats_over_time` returns `[]` (empty list). The sparkline renders that as a uniform grey strip (no bars, no crash).

### `/events?limit=20` response shape

```json
{
  "events": [
    {
      "event_type": "stored|searched|reinforced|merged|archived|hook_wake_up|hook_post_turn|gate_reject|...",
      "timestamp": "<iso>",
      "agent": "...",
      "node_id": "...",
      "details": "...",
      "metadata": { "entry_id": "...", ... }
    }
  ]
}
```

`metadata` is omitted (rather than `null`) when the event was logged without metadata, per `BrainEvent.to_dict()` (events.py lines 32–36).

### Color palette (memory_type → CSS hex, deterministic)

```
fact          #6fd6c9   (cyan, also --accent)
preference    #b48ead   (mauve)
context       #ebcb8b   (yellow)
decision      #a3be8c   (green)
event         #88c0d0   (light blue)
strategy      #d08770   (orange)
relationship  #bf616a   (red)
default       #5d6478   (grey)
```

A small `paletteFor(memoryType)` helper returns the hex; unknown types fall through to `default`. The same palette colors are reused for the type bars in Phase 1's header (`<Header>`) — Phase 2 unifies the color source by introducing the helper, but DOES NOT change Phase 1's existing rendering logic. (If Phase 1's `<Header>` already hardcodes accent for all bars, this PR optionally calls `paletteFor` there for visual consistency, but that is treated as a minor polish — the spec lists no [SPEC-N] item for it.)

### Force-directed simulation algorithm (described in code form — self-contained, NOT a "port from tmp")

```js
function simulate(nodes, edges, size, dragNode) {
  const cx = size.w / 2, cy = size.h / 2;
  const REPULSE_SAME = 220;
  const REPULSE_CROSS = 380;
  const SPRING_K = 0.02;
  const CENTER_K = 0.0005;
  const CLUSTER_K = 0.001;
  const DAMP = 0.85;
  const DT = 0.5;
  const MARGIN = 30;

  // 1. Repulsion — O(n²) Coulomb. Sample only when nodes.length > 200 (skip every other pair).
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
    const d = Math.sqrt(dx*dx + dy*dy) || 1;
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

  // 4. Cluster gravity — pull each node toward the centroid of its memory_type group.
  //    Centroids are recomputed once per tick (cheap; ≤8 distinct types in practice).
  const sums = {};  // type -> { x, y, n }
  for (const n of nodes) {
    const s = sums[n.memory_type] ||= { x: 0, y: 0, n: 0 };
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
    if (n === dragNode || (n.fx != null)) {
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

### Render loop (canvas)

```js
function render(ctx, nodes, edges, view, activatedAt, focus) {
  ctx.save();
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.translate(view.x, view.y);
  ctx.scale(view.k, view.k);

  // Edges first (under nodes).
  ctx.lineWidth = 1;
  for (const [aId, bId] of edges) {
    const a = nodeById.get(aId), b = nodeById.get(bId);
    if (!a || !b) continue;
    const inFocus = focus && (focus === aId || focus === bId);
    const eitherActive = (now - (activatedAt[aId] || 0) < 5000) || (now - (activatedAt[bId] || 0) < 5000);
    ctx.globalAlpha = focus ? (inFocus ? 0.9 : 0.05) : (eitherActive ? 0.5 : 0.15);
    ctx.strokeStyle = a.memory_type === b.memory_type ? a.color : '#3a3f4d';
    ctx.beginPath();
    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }

  // Halos.
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
  ctx.globalAlpha = 1;
  for (const n of nodes) {
    const dim = focus && focus !== n.id && !edgeSetTouchingFocus.has(n.id);
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

`now` is captured once per frame at the top of the rAF callback. `nodeById` is rebuilt whenever the entries set changes (kept in a `useRef` to avoid re-creation on every tick).

### Click resolution (canvas)

`mousedown` → convert client coordinates to world coordinates via `(clientX - rect.left - view.x) / view.k`, ditto for y. Iterate `nodes` and find the nearest one within `node.size + 4` pixels; if found, start a drag (`dragNode = node`, `node.fx = wx, node.fy = wy`); if not, start a pan. `mouseup` ends drag (clears `fx/fy`) or pan. A drag with total displacement < 3 px is reinterpreted as a click and toggles `focus = node.id` (or clears if same).

### Resize handling

`ResizeObserver` watches the wrapping `<div>` of the canvas. On change, the canvas's `width` / `height` attributes are set to the new dimensions and `view` is preserved. Simulation continues — node positions are not reset; nodes near the previous edge will drift back inward via center gravity.

### Open questions resolved (from brainstorm)

1. **`links` is a CSV string, not array** — Resolved in `useGraph()`: `entry.links.split(',').map(s => s.trim()).filter(Boolean)`. Documented in [SPEC-2] (`useGraph` hook). No standalone helper test ([TEST-N]) — the parsing is exercised end-to-end via the schema smoke test [TEST-1] which confirms `links` is a string field, plus manual dogfood verification that connected entries actually render as connected nodes.
2. **Isolated nodes (`links: ""`)** — Spring-attraction skips entries with no edges. Repulsion + center gravity together leave them drifting near canvas edges, which is fine. The simulation handles them naturally; no special case in code.
3. **`/graph` is heavy → no polling** — Resolved by [SPEC-10] (refresh button). Mount-once + manual refresh. The button overlay's exact position is `position: absolute; top: 8px; right: 8px;` inside `<BrainGraph>`'s wrapper.
4. **Canvas resize** — Resolved by [SPEC-7] (pan + zoom + ResizeObserver), see [Resize handling](#resize-handling).
5. **Empty timeline (all 24 buckets zero, or `[]` from backend)** — Resolved by [SPEC-13] (`<ActivitySparkline>`): when `buckets.length === 0` OR `Math.max(...stacks) === 0`, render a single grey `<rect>` filling the SVG viewBox with `fill="var(--dim)"` opacity 0.2. No division by zero, no crash.

## Affected systems

- **HTTP API:** unchanged. Phase 2 reads `/graph`, `/events?limit=20`, `/events/timeline` — all already exist and were already used (or available) before Phase 2.
- **MCP tools:** unchanged. No new tool, no schema change.
- **Storage:** unchanged. No SQLite migration. No ChromaDB re-index. No metadata schema change.
- **Frontend:** modified `backend/src/brain/static/brain.html`. No `frontend/` package created. No new files. No build tooling.
- **Installer (`npx brain`):** unchanged in this PR.
- **Scripts (Claude Code hooks):** unchanged.
- **Benchmarks:** unchanged. The monitor is a passive read-only consumer.
- **Tests:** ONE new pytest test file `backend/tests/test_brain/test_graph_route.py` with one test `test_graph_route_returns_expected_schema`.

## Risks

- **`O(n²)` repulsion at large N.** Brain has O(100s) entries in dogfood; even 500 entries → 125k pairs per tick × 30 fps = 3.75M ops/sec, which a modern browser handles. The 500-node hard cap keeps a runaway brain from freezing the dashboard.
- **Activation halos depend on `metadata.entry_id`.** Some legacy events were logged with only `node_id` and no metadata. The spec mitigates by also matching `node_id === entryNodeId` when `metadata` is missing — covered in [Data flow](#data-flow) item 2.
- **Two parallel pollers (`useEvents` 200 + `useThoughts` 20) at 2 s interval.** Total ~24 KB/s during dogfood — acceptable. Both pause on `document.hidden`.
- **Graph-fetch on mount is heavy.** A multi-MB JSON deserialization could lag a fresh page. Acceptable for dogfood; revisited in Phase 4 if it bites.
- **Canvas a11y is poor.** Documented trade-off (brainstorm Decision §accessibility): graph is dev-facing dashboard, not customer-facing UI. The thought stream is a real `<ul>` so screen readers cover the live event surface.
- **Clicking inside the refresh button must stop propagation** so it doesn't trigger a pan-start on the canvas underneath. Covered by `e.stopPropagation()` in [SPEC-10].

## Consumer impact

- **Money** (legacy embedded Brain on `:8611`): no impact. Money never calls `/monitor` or its sub-resources.
- **Marcel / future consumers:** no impact. Phase 2 is purely additive UI; HTTP/MCP surfaces unchanged.
- **Phase 1 consumers (i.e., the dogfood operator using the Phase 1 dashboard):** the Phase 1 zones (header htop, footer event log, tweaks panel) continue to work unchanged. The middle row that was a placeholder in Phase 1 now hosts the graph + thought stream + left placeholder. No regression — verified by Phase 1's `[TEST-1]` (still green) and Phase 2's manual dogfood checklist.
