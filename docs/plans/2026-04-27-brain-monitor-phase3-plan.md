# Brain Monitor Phase 3 Implementation Plan

**Linked spec:** [2026-04-27-brain-monitor-phase3-design.md](../specs/2026-04-27-brain-monitor-phase3-design.md)
**Linked checklist:** [2026-04-27-brain-monitor-phase3-checklist.md](../specs/2026-04-27-brain-monitor-phase3-checklist.md)
**Goal:** Close the Brain monitor MVP by filling the empty 280 px left column (cluster meters + top-accessed list), adding a tab switcher in the center area (graph / matrix / console), and shipping three QoL features (footer search, keyboard shortcuts, localStorage tweak persistence).
**Branch:** `feat/18-monitor-phase3`

---

## Pre-conditions

- Phase 1 PR #20 and Phase 2 PR #21 are merged.
- `backend/src/brain/static/brain.html` (948 lines) contains Phase 1 skeleton + Phase 2 graph/stream.
- `backend/tests/test_brain/test_monitor_route.py::test_monitor_route_serves_html` is green.
- `backend/tests/test_brain/test_graph_route.py::test_graph_route_returns_expected_schema` is green.
- `backend/tests/test_brain/test_monitor_route.py::test_monitor_route_serves_html` must remain green after Phase 3 — it checks for `<title>brain · live monitor</title>` and `<div id="root"></div>`, both of which are unchanged.

**Key observations from reading the current file:**
- Line 47: `const { useState, useEffect, useRef } = React;` — only three hooks destructured. Phase 2 additions use `React.useState`, `React.useRef`, `React.useEffect`, `React.useMemo` (qualified form). Phase 3 must do the same for any new hooks, OR add `useCallback, useMemo` to the destructure. The safest approach: add them to the top-level destructure (line 47) since Phase 2 already uses the qualified form — keep consistency: use `React.useCallback`, `React.useMemo` in new code without touching line 47.
- Phase 1's `useTweaks` (line 179-185) currently returns `{ tweaks, setTweaks }` with `useState({ accent, speed, running })`. No `tab` field is present. The spec states `tab` is in `TWEAK_DEFAULTS` — but the current code has no `TWEAK_DEFAULTS` constant and no `tab` field. Phase 3 must introduce `TWEAK_DEFAULTS` and add `tab: 'graph'` when replacing the `useState` inside `useTweaks`.
- Phase 1's `TweaksPanel` (line 187-231) keeps `[open, setOpen]` local. Phase 3 lifts that to `<App>` for the `t` keyboard shortcut.
- Phase 2's `<App>` (line 896-943) renders `<div className="left-placeholder" />` (line 921) and `<BrainGraph .../>` directly (line 922-933). Both are replaced by Phase 3.
- `useGraph()` returns `{ nodes, edges, lastError, lastFetchedAt, isLoading, refresh }`. `nodes` has `{ id, memory_type, color, access_count, x, y, vx, vy, fx, fy }`. The `/graph` route also provides `agent` in each raw entry (`rawEntries`) — but `useGraph` does NOT forward `agent` or `content` onto the node objects. **`<TopAccessed>` and `<MatrixView>` need `agent` and `content`.**

  This is a gap. Current `useGraph` maps nodes as:
  ```js
  const nodes = rawEntries.map(e => ({
    id: e.id,
    memory_type: e.memory_type,
    color: paletteFor(e.memory_type),
    size: 4 + Math.log((e.access_count ?? 0) + 1) * 2,
    access_count: e.access_count ?? 0,
    x: ..., y: ..., vx: 0, vy: 0, fx: null, fy: null,
  }));
  ```
  `agent` and `content` are NOT forwarded. `<TopAccessed>` needs `entry.content` for the snippet; `<MatrixView>` needs `entry.agent` for axis grouping. **The builder must add `agent: e.agent ?? '∅'` and `content: e.content ?? ''` to the node mapping inside `useGraph` (Task 0 below).** This is a minor but necessary deviation from the spec's stated "read entries from useGraph unchanged" — the raw entries carry the fields, they just aren't mapped through.

  Alternatively: pass `rawEntries` alongside `nodes` from `useGraph`. Either approach works; forwarding fields on the node is cleaner.

- The `classifyEvent` function needed by `<ConsoleView>` is not yet defined in the file (Phase 1's `<Footer>` uses inline `if` chains, no named helper). The builder must define it.

---

## Task 0 — Pre-flight: add `agent` + `content` to `useGraph` node mapping

Phase 3 components (`<TopAccessed>`, `<MatrixView>`) read `entry.agent` and `entry.content` from `graph.nodes`. The current `useGraph` does not forward these fields. This is a one-line-per-field addition inside the node-mapping `rawEntries.map(...)` block.

**File:**
- Modify: `backend/src/brain/static/brain.html` lines 470-480 (the `nodes = rawEntries.map(e => ({...}))` block)

- [ ] **Step 0.1: Add `agent` and `content` to the node object in `useGraph`**

Locate the block starting at approximately line 470:
```js
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
```

Change to:
```js
const nodes = rawEntries.map(e => ({
  id: e.id,
  memory_type: e.memory_type,
  agent: e.agent ?? '∅',
  content: e.content ?? '',
  color: paletteFor(e.memory_type),
  size: 4 + Math.log((e.access_count ?? 0) + 1) * 2,
  access_count: e.access_count ?? 0,
  x: (Math.random() - 0.5) * 200,
  y: (Math.random() - 0.5) * 200,
  vx: 0, vy: 0,
  fx: null, fy: null,
}));
```

- [ ] **Step 0.2: Verify Phase 2 graph still renders** — open `/monitor` after the edit; the force-directed graph should be unchanged (the two new fields are ignored by `simulate()` and `render()`).

- [ ] **Step 0.3: Commit**

```bash
git add backend/src/brain/static/brain.html
git commit -m "🧠 Feature: forward agent+content on useGraph nodes for Phase 3 consumers (#18)"
```

---

## Task 1 — [SPEC-9]: Upgrade `useTweaks` with localStorage persistence

Do this first because every subsequent task that sets `tweaks.tab` benefits from it. It also introduces `TWEAK_DEFAULTS` (which `<TabBar>` in Task 4 reads).

**File:**
- Modify: `backend/src/brain/static/brain.html` (replace `useTweaks` at lines 179-185)

- [ ] **Step 1.1: Replace `useTweaks` with the localStorage-persistent version**

Replace the current block:
```js
function useTweaks() {
  const [tweaks, setTweaks] = useState({ accent: "#6fd6c9", speed: 1, running: true });
  useEffect(() => {
    document.documentElement.style.setProperty("--accent", tweaks.accent);
  }, [tweaks.accent]);
  return { tweaks, setTweaks };
}
```

With:
```js
const TWEAK_DEFAULTS = { accent: '#6fd6c9', speed: 1, running: true, tab: 'graph' };
const STORAGE_KEY = 'brain-monitor-tweaks-v1';
let warnedAboutStorage = false;

function readStoredTweaks(defaults) {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    return { ...defaults, ...parsed };
  } catch (err) {
    if (!warnedAboutStorage) {
      console.warn('[brain-monitor] localStorage unavailable; tweaks will not persist this session');
      warnedAboutStorage = true;
    }
    return defaults;
  }
}

function useTweaks(defaults) {
  const [tweaks, setTweaksRaw] = useState(() => readStoredTweaks(defaults));
  const setTweaks = React.useCallback((updater) => {
    setTweaksRaw(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); }
      catch (err) {
        if (!warnedAboutStorage) {
          console.warn('[brain-monitor] localStorage unavailable; tweaks will not persist this session');
          warnedAboutStorage = true;
        }
      }
      return next;
    });
  }, []);
  useEffect(() => {
    document.documentElement.style.setProperty('--accent', tweaks.accent);
  }, [tweaks.accent]);
  return { tweaks, setTweaks };
}
```

Note: in `<App>`, the call site `useTweaks()` must become `useTweaks(TWEAK_DEFAULTS)` (line ~899 in the current file).

- [ ] **Step 1.2: Update the `useTweaks()` call in `<App>`**

Locate line ~899: `const { tweaks, setTweaks } = useTweaks();`
Change to: `const { tweaks, setTweaks } = useTweaks(TWEAK_DEFAULTS);`

- [ ] **Step 1.3: Manual verification**
  - Open `/monitor`, change accent to red, speed to 2×.
  - Reload — accent stays red, speed stays 2×.
  - Open DevTools → Application → localStorage → key `brain-monitor-tweaks-v1` exists with JSON.
  - Open private mode → page still works in-memory; console shows exactly one `[brain-monitor] localStorage unavailable…` warning.

- [ ] **Step 1.4: Tick [SPEC-9] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-9 localStorage persistence for useTweaks (#18)"
```

---

## Task 2 — [SPEC-1]: `<LeftPanel>` container wired into `<App>`

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 2.1: Add CSS for `.left-panel` inside the `<style>` block**

Inside the existing `<style>` block (before the closing `</style>`), add:
```css
.left-panel { display: flex; flex-direction: column; gap: 8px; padding: 8px; min-height: 0; border-right: 1px solid rgba(255,255,255,0.05); }
```
(The `border-right` was originally on `.left-placeholder`; keep it on `.left-panel` to preserve the visual separator.)

- [ ] **Step 2.2: Define `<LeftPanel>` component**

Add immediately before `// ── App` (after `ThoughtStream`):
```js
// ── LeftPanel ─────────────────────────────────────────────────────────────────
function LeftPanel({ children }) {
  return (
    <div className="left-panel">
      {children}
    </div>
  );
}
```

- [ ] **Step 2.3: Replace `<div className="left-placeholder" />` in `<App>`**

In `<App>`'s return, replace:
```js
<div className="left-placeholder" />
```
With:
```js
<LeftPanel>
  <ClusterMeters stats={stats} />
  <TopAccessed entries={graph.nodes} focus={focus} setFocus={setFocus} />
</LeftPanel>
```

(This references `ClusterMeters` and `TopAccessed` which are defined in Tasks 3 and 4 below. The builder defines all three components before wiring them. Alternatively the builder can do Tasks 3 + 4 first and wire `<LeftPanel>` last — the checklist order follows the spec numbering.)

- [ ] **Step 2.4: Remove the old `.left-placeholder` CSS rule**

Remove from the `<style>` block:
```css
.left-placeholder {
  background: rgba(255,255,255,0.01);
  border-right: 1px solid rgba(255,255,255,0.05);
}
```

- [ ] **Step 2.5: Manual verification anchor**
  - Open `/monitor`; left column is filled with two stacked sections; center graph and right thought stream are unchanged.

- [ ] **Step 2.6: Tick [SPEC-1] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-1 LeftPanel container wired into App grid (#18)"
```

---

## Task 3 — [SPEC-2]: `<ClusterMeters>` component

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 3.1: Add CSS for `.cluster-meters` inside `<style>`**

```css
.cluster-meters .meter-row { display: grid; grid-template-columns: 80px 1fr auto auto; gap: 6px; align-items: center; height: 24px; font-size: 11px; }
.cluster-meters .meter-bar { height: 6px; border-radius: 3px; background: #1a1d28; overflow: hidden; }
.cluster-meters .meter-bar > span { display: block; height: 100%; }
.cluster-meters .trend-up { color: var(--accent); }
.cluster-meters .trend-down { color: var(--err); }
.cluster-meters .trend-flat { color: var(--dim); }
```

- [ ] **Step 3.2: Define `<ClusterMeters>` component**

Add after `LeftPanel` and before `// ── App`:
```js
// ── ClusterMeters ─────────────────────────────────────────────────────────────
function ClusterMeters({ stats }) {
  const prevRef = React.useRef({});

  const total = stats?.total ?? 0;
  const entries = Object.entries(stats?.types ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 8);

  const arrows = entries.map(([type, count]) => {
    const prev = prevRef.current[type];
    if (prev === undefined) return { type, count, arrow: '→', cls: 'trend-flat' };
    if (count > prev) return { type, count, arrow: '↑', cls: 'trend-up' };
    if (count < prev) return { type, count, arrow: '↓', cls: 'trend-down' };
    return { type, count, arrow: '→', cls: 'trend-flat' };
  });

  React.useEffect(() => {
    prevRef.current = stats?.types ?? {};
  }, [stats]);

  return (
    <div className="cluster-meters">
      {arrows.map(({ type, count, arrow, cls }) => (
        <div key={type} className="meter-row">
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', opacity: 0.8 }}>{type}</span>
          <div className="meter-bar">
            <span style={{ width: `${total > 0 ? (count / total) * 100 : 0}%`, background: paletteFor(type) }} />
          </div>
          <span style={{ fontVariantNumeric: 'tabular-nums', minWidth: '24px', textAlign: 'right' }}>{count}</span>
          <span className={cls}>{arrow}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3.3: Manual verification anchor**
  - Open `/monitor` with seeded entries; left column top section shows up to 8 type rows with bars, counts, `→` arrows on first render.
  - POST `/store` a new entry; on next poll the matching row's count increments with a `↑` arrow; subsequent stable polls show `→`.

- [ ] **Step 3.4: Tick [SPEC-2] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-2 ClusterMeters component with trend arrows (#18)"
```

---

## Task 4 — [SPEC-3]: `<TopAccessed>` component

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 4.1: Add CSS for `.top-accessed` inside `<style>`**

```css
.top-accessed { flex: 1; min-height: 0; overflow-y: auto; list-style: none; padding: 0; margin: 0; }
.top-accessed li { display: grid; grid-template-columns: 8px 1fr auto; gap: 6px; align-items: center; padding: 4px 6px; cursor: pointer; font-size: 11px; }
.top-accessed li:hover { background: #161922; }
.top-accessed li.focused { background: #1f2433; outline: 1px solid var(--accent); }
.top-accessed .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.top-accessed .access-badge { font-variant-numeric: tabular-nums; color: var(--dim); font-size: 10px; }
```

- [ ] **Step 4.2: Define `<TopAccessed>` component**

Add after `ClusterMeters` and before `// ── App`:
```js
// ── TopAccessed ───────────────────────────────────────────────────────────────
function TopAccessed({ entries, focus, setFocus }) {
  const top10 = [...(entries ?? [])]
    .sort((a, b) => (b.access_count ?? 0) - (a.access_count ?? 0))
    .slice(0, 10);

  return (
    <ul className="top-accessed">
      {top10.map(entry => {
        const snippet = (entry.content ?? '').slice(0, 40) + ((entry.content ?? '').length > 40 ? '…' : '');
        const isFocused = focus === entry.id;
        return (
          <li
            key={entry.id}
            className={isFocused ? 'focused' : ''}
            onClick={() => setFocus(isFocused ? null : entry.id)}
          >
            <span className="dot" style={{ background: paletteFor(entry.memory_type) }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{snippet}</span>
            <span className="access-badge">{entry.access_count ?? 0}</span>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 4.3: Manual verification anchor**
  - Open `/monitor`; left column bottom section shows top-10 most-accessed entries with color dots and access counts.
  - Click a row → corresponding graph node highlights, thought stream filters. Click same row again → focus clears.

- [ ] **Step 4.4: Tick [SPEC-3] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-3 TopAccessed component with click-to-focus (#18)"
```

---

## Task 5 — [SPEC-4]: `<TabBar>` + center-area tab switcher

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 5.1: Add CSS for `.tab-bar` and `.center-area` inside `<style>`**

```css
.tab-bar { display: flex; gap: 4px; padding: 4px 8px; border-bottom: 1px solid #1a1d28; }
.tab-bar button { background: transparent; border: 1px solid #2a2f3d; color: var(--fg); padding: 2px 10px; cursor: pointer; font-family: inherit; font-size: 11px; }
.tab-bar button.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }
.center-area { display: flex; flex-direction: column; min-height: 0; }
.center-area > .tab-content { flex: 1; min-height: 0; position: relative; }
```

- [ ] **Step 5.2: Define `<TabBar>` component**

Add before `// ── App`:
```js
// ── TabBar ────────────────────────────────────────────────────────────────────
function TabBar({ tab, setTab }) {
  const tabs = ['graph', 'matrix', 'console'];
  return (
    <div className="tab-bar">
      {tabs.map(name => (
        <button
          key={name}
          className={tab === name ? 'active' : ''}
          onClick={() => setTab(name)}
        >
          {name}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 5.3: Add `setTab` to `<App>` and wire the center-area tab switcher**

In `<App>`, after `const { tweaks, setTweaks } = useTweaks(TWEAK_DEFAULTS);`, add:
```js
const setTab = React.useCallback(name => setTweaks(t => ({ ...t, tab: name })), [setTweaks]);
```

Replace the current `<BrainGraph .../>` block (lines ~922-933) with:
```js
<div className="center-area">
  <TabBar tab={tweaks.tab} setTab={setTab} />
  <div className="tab-content">
    {tweaks.tab === 'graph' && (
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
    )}
    {tweaks.tab === 'matrix' && <MatrixView entries={graph.nodes} />}
    {tweaks.tab === 'console' && <ConsoleView events={events} />}
  </div>
</div>
```

- [ ] **Step 5.4: Manual verification anchor**
  - Open `/monitor`; tab bar shows three buttons above the graph with `graph` active.
  - Click `matrix` → heatmap appears; click `console` → JSON tail appears; click `graph` → force-directed simulation returns.
  - Switch away from `graph` tab and back: no orphaned rAF timers (verify in DevTools Performance — frame rate settles after switching).

- [ ] **Step 5.5: Tick [SPEC-4] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-4 TabBar and center-area tab switcher (#18)"
```

---

## Task 6 — [SPEC-5]: `<MatrixView>` SVG heatmap

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 6.1: Add CSS for `.matrix-view` inside `<style>`**

```css
.matrix-view { width: 100%; height: 100%; position: relative; }
.matrix-view .cell-overlay { position: absolute; background: #1a1d28; border: 1px solid #2a2f3d; padding: 6px 8px; font-size: 11px; pointer-events: none; white-space: pre; }
```

- [ ] **Step 6.2: Define `<MatrixView>` component**

Add before `// ── TabBar`:
```js
// ── MatrixView ────────────────────────────────────────────────────────────────
function MatrixView({ entries }) {
  const [selected, setSelected] = React.useState(null);
  const wrapRef = React.useRef(null);
  const [svgSize, setSvgSize] = React.useState({ w: 600, h: 400 });

  React.useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSvgSize({ w: el.clientWidth || 600, h: el.clientHeight || 400 }));
    ro.observe(el);
    setSvgSize({ w: el.clientWidth || 600, h: el.clientHeight || 400 });
    return () => ro.disconnect();
  }, []);

  const { agents, types, counts, samples, maxCount } = React.useMemo(() => {
    const agentSet = new Set(), typeSet = new Set();
    const counts = {}, samples = {};
    let maxCount = 0;
    for (const e of entries || []) {
      const a = e.agent || '∅';
      const t = e.memory_type || 'default';
      agentSet.add(a); typeSet.add(t);
      counts[a] = counts[a] || {};
      counts[a][t] = (counts[a][t] || 0) + 1;
      const k = a + '\x00' + t;
      samples[k] = samples[k] || [];
      if (samples[k].length < 5) samples[k].push(e.id);
      if (counts[a][t] > maxCount) maxCount = counts[a][t];
    }
    return { agents: [...agentSet], types: [...typeSet], counts, samples, maxCount };
  }, [entries]);

  function truncLabel(label) {
    return label.length > 12 ? label.slice(0, 11) + '…' : label;
  }

  function cellAlpha(count) {
    if (!count) return 0;
    return Math.max(0.1, Math.log(count + 1) / Math.log(maxCount + 1));
  }

  const LABEL_GUTTER = 80;
  const TOP_GUTTER = 40;
  const cellW = agents.length > 0 ? (svgSize.w - LABEL_GUTTER) / agents.length : 0;
  const cellH = types.length > 0 ? (svgSize.h - TOP_GUTTER) / types.length : 0;

  return (
    <div ref={wrapRef} className="matrix-view">
      <svg
        width={svgSize.w}
        height={svgSize.h}
        onClick={e => { if (e.target.tagName === 'svg' || e.target.tagName === 'SVG') setSelected(null); }}
      >
        {agents.map((agent, ai) => (
          <text
            key={agent}
            x={LABEL_GUTTER + ai * cellW + cellW / 2}
            y={TOP_GUTTER - 6}
            textAnchor="middle"
            fontSize="9"
            fill="var(--dim)"
          >
            {truncLabel(agent)}
          </text>
        ))}
        {types.map((type, ti) => (
          <text
            key={type}
            x={LABEL_GUTTER - 4}
            y={TOP_GUTTER + ti * cellH + cellH / 2 + 4}
            textAnchor="end"
            fontSize="9"
            fill="var(--dim)"
          >
            {truncLabel(type)}
          </text>
        ))}
        {agents.map((agent, ai) =>
          types.map((type, ti) => {
            const count = (counts[agent] && counts[agent][type]) || 0;
            const alpha = cellAlpha(count);
            const k = agent + '\x00' + type;
            const sampleIds = samples[k] || [];
            const x = LABEL_GUTTER + ai * cellW;
            const y = TOP_GUTTER + ti * cellH;
            return (
              <rect
                key={k}
                x={x}
                y={y}
                width={Math.max(1, cellW - 2)}
                height={Math.max(1, cellH - 2)}
                fill={`hsla(180, 60%, 50%, ${alpha})`}
                style={{ cursor: count > 0 ? 'pointer' : 'default' }}
                onClick={e => {
                  e.stopPropagation();
                  if (count === 0) return;
                  setSelected({ agent, type, count, sampleIds, x, y });
                }}
              />
            );
          })
        )}
      </svg>
      {selected && (
        <div
          className="cell-overlay"
          style={{ left: selected.x + LABEL_GUTTER, top: selected.y + TOP_GUTTER }}
        >
          {selected.agent} × {selected.type}{'\n'}count: {selected.count}{'\n'}samples: {selected.sampleIds.join(', ')}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6.3: Manual verification anchor**
  - Open `/monitor`, switch to `matrix` tab.
  - Heatmap renders with axes labeled by agent and memory_type; non-zero cells are colored with intensity proportional to `log(count)`.
  - Click a cell → overlay shows count + up to 5 entry IDs.
  - Click empty SVG → overlay clears.

- [ ] **Step 6.4: Tick [SPEC-5] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-5 MatrixView SVG heatmap (#18)"
```

---

## Task 7 — [SPEC-6]: `<ConsoleView>` component

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 7.1: Add CSS for `.console-wrap`, `.console-line.*`, `.follow-pill` inside `<style>`**

```css
.console-wrap { position: relative; height: 100%; }
.console-wrap pre { height: 100%; margin: 0; padding: 6px 8px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; font-size: 10px; line-height: 1.4; background: #08090d; }
.console-line.console-green { color: var(--ok); }
.console-line.console-cyan { color: var(--accent); }
.console-line.console-yellow { color: var(--swap); }
.console-line.console-red { color: var(--err); }
.console-line.console-grey { color: var(--dim); }
.follow-pill { position: absolute; top: 8px; right: 8px; background: var(--accent); color: var(--bg); border: none; padding: 2px 8px; cursor: pointer; font-family: inherit; font-size: 10px; }
```

- [ ] **Step 7.2: Define `classifyEvent` helper and `<ConsoleView>` component**

Add before `// ── MatrixView` (or in the helpers section near the top, after `formatUptime`):
```js
function classifyEvent(eventType) {
  const t = eventType ?? '';
  if (t === 'hook_wake_up') return 'green';
  if (t === 'hook_post_turn') return 'cyan';
  if (t.includes('reject')) return 'yellow';
  if (t.includes('error') || t.includes('failed')) return 'red';
  return 'grey';
}
```

Then add `<ConsoleView>` before `// ── MatrixView`:
```js
// ── ConsoleView ───────────────────────────────────────────────────────────────
function ConsoleView({ events }) {
  const preRef = React.useRef(null);
  const followingRef = React.useRef(true);
  const [showFollowPill, setShowFollowPill] = React.useState(false);

  React.useEffect(() => {
    const pre = preRef.current;
    if (!pre) return;
    if (followingRef.current) pre.scrollTop = pre.scrollHeight;
  }, [events]);

  function onScroll() {
    const pre = preRef.current;
    if (!pre) return;
    const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
    followingRef.current = atBottom;
    setShowFollowPill(!atBottom);
  }

  function jumpToBottom() {
    const pre = preRef.current;
    if (!pre) return;
    pre.scrollTop = pre.scrollHeight;
    followingRef.current = true;
    setShowFollowPill(false);
  }

  const newest100 = (events ?? []).slice(0, 100);
  return (
    <div className="console-wrap">
      <pre ref={preRef} onScroll={onScroll}>
        {newest100.map((e, i) => (
          <span key={i} className={`console-line console-${classifyEvent(e.event_type)}`}>
            {JSON.stringify(e)}{'\n'}
          </span>
        ))}
      </pre>
      {showFollowPill && (
        <button className="follow-pill" onClick={jumpToBottom}>↓ follow</button>
      )}
    </div>
  );
}
```

- [ ] **Step 7.3: Manual verification anchor**
  - Open `/monitor`, switch to `console` tab.
  - Latest 100 events appear as JSON lines with type-color spans; view is scrolled to bottom by default.
  - Scroll up manually → `↓ follow` pill appears; new events stop pushing view.
  - Click pill → view jumps to bottom, follow re-engages.

- [ ] **Step 7.4: Tick [SPEC-6] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-6 ConsoleView with auto-scroll follow-mode (#18)"
```

---

## Task 8 — [SPEC-7]: Footer search input + filter logic + matches badge

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 8.1: Add CSS for `.footer-search` inside `<style>`**

```css
.footer-search { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-bottom: 1px solid rgba(255,255,255,0.06); }
.footer-search input { background: #08090d; border: 1px solid #2a2f3d; color: var(--fg); padding: 2px 6px; font-family: inherit; font-size: 11px; min-width: 200px; outline: none; }
.footer-search .matches-badge { color: var(--dim); font-size: 10px; font-variant-numeric: tabular-nums; }
```

- [ ] **Step 8.2: Rewrite `<Footer>` to accept `searchRef` prop and add filter state**

The current `<Footer>` signature is `function Footer({ events })`. Change to:

```js
function Footer({ events, searchRef }) {
  const [filter, setFilter] = React.useState('');
  const filtered = filter === '' ? events : (events ?? []).filter(
    e => JSON.stringify(e).toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <footer className="footer-row" style={{
      borderTop: "1px solid rgba(255,255,255,0.08)",
      overflowY: "auto",
      padding: "0",
    }}>
      <div className="footer-search">
        <input
          type="search"
          placeholder="filter…"
          ref={searchRef}
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        <span className="matches-badge">{filtered.length} / {(events ?? []).length} matches</span>
      </div>
      {(filtered ?? []).map((ev, i) => {
        const type = ev.event_type ?? "";
        let badgeColor = "#555";
        if (type === "hook_wake_up") badgeColor = "var(--ok)";
        else if (type === "hook_post_turn") badgeColor = "var(--accent)";
        else if (type.includes("reject")) badgeColor = "var(--swap)";
        else if (type.includes("error") || type.includes("failed")) badgeColor = "var(--err)";

        const details = (ev.details ?? "").slice(0, 120);
        return (
          <div key={i} style={{ display: "flex", gap: "8px", padding: "2px 12px", fontSize: "12px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
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
```

- [ ] **Step 8.3: Create `footerSearchRef` in `<App>` and forward to `<Footer>`**

In `<App>`, add after `activatedAtRef`:
```js
const footerSearchRef = React.useRef(null);
```

Update the `<Footer>` call site from:
```js
<Footer events={events} />
```
To:
```js
<Footer events={events} searchRef={footerSearchRef} />
```

- [ ] **Step 8.4: Manual verification anchor**
  - Open `/monitor`; footer now shows a search input at the top.
  - Type `wake_up` → events list narrows to matching rows in real time; badge shows `N / 200 matches`.
  - Clear input → full list restores; existing type-color badges and relative timestamps unchanged.

- [ ] **Step 8.5: Tick [SPEC-7] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-7 Footer search input + filter + matches badge (#18)"
```

---

## Task 9 — [SPEC-8]: Keyboard shortcuts handler + lift `TweaksPanel` open state

**File:**
- Modify: `backend/src/brain/static/brain.html`

- [ ] **Step 9.1: Lift `TweaksPanel` open state to `<App>`**

In `TweaksPanel`, change the signature from `function TweaksPanel({ tweaks, setTweaks })` to:
```js
function TweaksPanel({ tweaks, setTweaks, open, setOpen }) {
```

Remove the internal `const [open, setOpen] = useState(false);` line. The rest of `TweaksPanel`'s body is unchanged — it already reads `open` and calls `setOpen`.

In `<App>`, add:
```js
const [tweaksOpen, setTweaksOpen] = React.useState(false);
```

Update the `<TweaksPanel>` call site from:
```js
<TweaksPanel tweaks={tweaks} setTweaks={setTweaks} />
```
To:
```js
<TweaksPanel tweaks={tweaks} setTweaks={setTweaks} open={tweaksOpen} setOpen={setTweaksOpen} />
```

- [ ] **Step 9.2: Add keyboard shortcut `useEffect` in `<App>`**

Add after the `docHidden` visibility effect in `<App>`:
```js
useEffect(() => {
  function onKey(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'g') setTweaks(t => ({ ...t, tab: 'graph' }));
    else if (e.key === 'm') setTweaks(t => ({ ...t, tab: 'matrix' }));
    else if (e.key === 'c') setTweaks(t => ({ ...t, tab: 'console' }));
    else if (e.key === ' ') { e.preventDefault(); setTweaks(t => ({ ...t, running: !t.running })); }
    else if (e.key === 'r') { graph.refresh(); }
    else if (e.key === 't') { setTweaksOpen(o => !o); }
    else if (e.key === 'Escape') { setFocus(null); }
    else if (e.key === '/') { e.preventDefault(); footerSearchRef.current?.focus(); }
  }
  document.addEventListener('keydown', onKey);
  return () => document.removeEventListener('keydown', onKey);
}, [graph.refresh, setTweaks, setTweaksOpen, setFocus]);
```

Note: `graph` must be declared before this effect. In the current `<App>`, `graph = useGraph()` is called before `useThoughts`. The effect references `graph.refresh` — since `graph` is a stable object (its `refresh` function is the stable `doFetch` closure from `useGraph`), the dep array is correct.

- [ ] **Step 9.3: Manual verification anchor**
  - Open `/monitor`; press `g` → tab switches to graph; `m` → matrix; `c` → console.
  - `space` → polling pauses (status dot turns red); `space` again → polling resumes.
  - `r` → DevTools Network shows a `/graph` request.
  - `t` → tweaks panel opens/closes.
  - Click a graph node to focus it; press `Escape` → focus clears.
  - Press `/` → footer search input gains cursor focus.
  - While cursor is in search input, press `g` → tab does NOT switch (input guard works).

- [ ] **Step 9.4: Tick [SPEC-8] in checklist, commit**

```bash
git add backend/src/brain/static/brain.html docs/specs/2026-04-27-brain-monitor-phase3-checklist.md
git commit -m "🧠 Feature: SPEC-8 keyboard shortcuts handler + lift TweaksPanel open state (#18)"
```

---

## Final Task — [TEST-0] + [GATE-1/2/3]: Verification gates

- [ ] **Step F.1: Run ruff**

```bash
cd C:/Brain/backend && python -m ruff check .
```
Expected: no errors. Python is unchanged; this is the no-regression check.

- [ ] **Step F.2: Run pytest**

```bash
cd C:/Brain/backend && python -m pytest -q
```
Expected: 193 tests pass (baseline). Both `test_monitor_route_serves_html` and `test_graph_route_returns_expected_schema` must remain green. The `brain.html` content changes do not affect either test — `test_monitor_route` checks for `<title>brain · live monitor</title>` and `<div id="root"></div>`, both of which are unchanged. `test_graph_route` checks the `/graph` HTTP schema, which is unchanged.

- [ ] **Step F.3: Tick [GATE-1], [GATE-2], [GATE-3] in checklist**

GATE-3 (frontend pnpm) is skipped — no `frontend/` package exists; `brain.html` is served as a static file.

- [ ] **Step F.4: Push and open PR**

```bash
git push -u origin feat/18-monitor-phase3
gh pr create --title "Brain monitor — Phase 3: left panel + tabs + polish (#18)" --body "$(cat <<'EOF'
## Summary
- Fills 280px left column: `<ClusterMeters>` (per-type bars + trend arrows) + `<TopAccessed>` (top-10 by access_count, click-to-focus)
- Tab switcher in center: `[graph] [matrix] [console]`. Matrix = SVG agent×type heatmap. Console = raw /events JSONL tail with follow-mode.
- Footer search input + matches badge. Keyboard shortcuts (g/m/c/space/r/t/Esc//).
- `useTweaks` localStorage persistence (versioned key `brain-monitor-tweaks-v1`).

## Test plan
- [ ] `cd backend && python -m ruff check .` passes (no Python touched)
- [ ] `cd backend && python -m pytest -q` passes — 193 tests green, Phase 1 `test_monitor_route_serves_html` + Phase 2 `test_graph_route_returns_expected_schema` both green
- [ ] Manual: open `/monitor` — left panel shows type meters + top-accessed entries
- [ ] Manual: tab bar switches graph / matrix / console without rAF leak
- [ ] Manual: footer search filters in real time; matches badge updates
- [ ] Manual: keyboard shortcuts work; input guard suppresses shortcuts when typing in search
- [ ] Manual: reload after changing accent/speed/tab — settings persisted via localStorage
- [ ] No regression on Phase 1 + Phase 2 features (header bars, sparkline, footer log, tweaks, graph interactions, thought stream)

Closes #18

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Order summary

| Task | SPEC | Depends on |
|------|------|-----------|
| 0 | Pre-flight: forward `agent`+`content` in `useGraph` | — |
| 1 | SPEC-9: `useTweaks` localStorage + `TWEAK_DEFAULTS` | Task 0 |
| 2 | SPEC-1: `<LeftPanel>` wired into `<App>` | Tasks 3, 4 (define before wiring) |
| 3 | SPEC-2: `<ClusterMeters>` | Task 1 (needs `stats`, `paletteFor`) |
| 4 | SPEC-3: `<TopAccessed>` | Task 0 (needs `agent`/`content` on nodes) |
| 5 | SPEC-4: `<TabBar>` + center-area switcher | Task 1 (needs `tweaks.tab`) |
| 6 | SPEC-5: `<MatrixView>` | Task 0 (needs `agent`) |
| 7 | SPEC-6: `<ConsoleView>` + `classifyEvent` | — |
| 8 | SPEC-7: Footer search | Task 8's `footerSearchRef` used in Task 9 |
| 9 | SPEC-8: Keyboard shortcuts + lift TweaksPanel open | Tasks 1, 5, 8 |
| F | Gates | All tasks |

Recommended builder order: 0 → 1 → 3 → 4 → 2 → 7 → 6 → 5 → 8 → 9 → F.
(Define components before wiring them into `<App>`; do Tasks 3+4 before Task 2 so `<LeftPanel>`'s children exist.)
