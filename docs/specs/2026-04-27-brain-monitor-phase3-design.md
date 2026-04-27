# Brain Monitor — Phase 3 (polish + alt views) — Design

**Goal:** Close the Brain monitor MVP by filling the empty 280 px left column (cluster meters + top-accessed list), adding a tab switcher in the center area (graph / matrix / console), and shipping the three quality-of-life features (footer search, keyboard shortcuts, localStorage tweak persistence) so the dashboard is feature-complete enough to ride for a ≥7-day phase-2b dogfood without the operator re-opening the editor.
**Roadmap phase:** R:phase-2b
**Cycle invocation:** Phase 3 of 3. Builds on the Phase 1 spec ([2026-04-27-brain-monitor-phase1-design.md](2026-04-27-brain-monitor-phase1-design.md)) and the Phase 2 spec ([2026-04-27-brain-monitor-phase2-design.md](2026-04-27-brain-monitor-phase2-design.md)). **Phase 3 ships LAST** — it must merge after Phase 1 and Phase 2 are merged because it modifies the same `backend/src/brain/static/brain.html` and depends on hooks (`useStats`, `useGraph`, `useThoughts`, `useTimeline`, `useTweaks`) and components (`<BrainGraph>`, `<ThoughtStream>`, `<Footer>`, `<TweaksPanel>`, `<Header>`) created in those earlier phases.

## Scope (in)

- **`<LeftPanel>` container** — fills the previously empty 280 px left column from Phase 2. Mounted as a sibling of `<BrainGraph>` and `<ThoughtStream>` inside the middle row of the grid. CSS Flex column `display: flex; flex-direction: column; gap: 8px;`. Holds two stacked children: `<ClusterMeters>` (top), `<TopAccessed>` (bottom, scrollable). Phase 2's `<div className="left-placeholder" />` is replaced by `<LeftPanel />`.
- **`<ClusterMeters>` component** — reads `stats` from the existing Phase 1 `useStats` hook. Renders one row per memory_type (top 8 by count from `Object.entries(stats?.types ?? {})` sorted desc). Each row shows: type label, horizontal bar (% of `stats.total`, max width 100% of column), count, trend arrow (`↑` / `↓` / `→`). Uses Phase 2's `paletteFor(memoryType)` for the bar color. Total height ~200 px (8 rows × ~24 px).
- **Trend arrow logic in `<ClusterMeters>`** — keeps a `useRef({})` of the previous `stats.types` snapshot. On each render, for each type, compare `current count` vs `previous count`; emit `↑` (cyan, `var(--accent)`) when current > previous, `↓` (red, `var(--err)`) when current < previous, `→` (dim grey, `var(--dim)`) when equal or when no previous snapshot exists. After computing arrows, update the ref to the current snapshot. Flicker on a `12 → 13 → 12` two-poll oscillation is **expected** and accepted — this is dev signal, not a UX surface (resolves Open Question 1).
- **`<TopAccessed>` component** — reads `entries` from Phase 2's existing `useGraph` hook. Sorts entries by `access_count` desc and slices the top 10. Each row: a memory_type-color dot (`paletteFor(entry.memory_type)`), a content snippet truncated to 40 chars, and an `access_count` badge (right-aligned, monospace). Click on a row calls `setFocus(entry.id)` (the same `focus` state lifted into `<App>` by Phase 2); clicking the same already-focused row calls `setFocus(null)`. Container is a scrollable `<ul>` with `overflow-y: auto`, max-height fills the remaining left-panel space (~250 px).
- **`<TabBar>` component** — three buttons `[graph] [matrix] [console]` rendered above the center-column content. The active button is highlighted by `background: var(--accent); color: var(--bg);`; inactive buttons use the muted palette. Clicking a button writes the new value to `tweaks.tab` via `setTweaks(t => ({ ...t, tab: 'graph' | 'matrix' | 'console' }))`. The `tab` field already exists in `TWEAK_DEFAULTS` per Phase 1 (default `'graph'`).
- **Center-area tab switcher** — the middle column previously rendered `<BrainGraph>` directly (Phase 2). Phase 3 wraps that with the tab switcher: render `<TabBar>` above, then conditionally render exactly one of `<BrainGraph>` (when `tweaks.tab === 'graph'`), `<MatrixView>` (when `'matrix'`), or `<ConsoleView>` (when `'console'`). The Phase 2 `<BrainGraph>` props are passed through unchanged when active; when inactive, it is unmounted (the rAF loop ends via the existing Phase 2 cleanup). Manual dogfood confirms switching tabs does not leak rAF timers.
- **`<MatrixView>` component** — SVG heatmap. Reads `entries` from Phase 2's `useGraph`. Builds `agents = [...new Set(entries.map(e => e.agent || '∅'))]` and `types = [...new Set(entries.map(e => e.memory_type || 'default'))]`. Builds `counts[agent][type]` by single pass over entries. Renders an SVG with `width: 100%; height: 100%;` containing: column labels (X axis, agents) at the top, row labels (Y axis, types) on the left, and one `<rect>` per cell. Cell `fill = hsla(180, 60%, 50%, ${Math.log(count + 1) / Math.log(maxCount + 1)})` with a minimum alpha of `0.1` when `count > 0` so non-zero cells are still visible. Cell size adapts to the container: `cellW = (svgW - labelGutter) / agents.length`, `cellH = (svgH - labelGutter) / types.length`. Click on a cell sets a local `selectedCell = { agent, type, count, sampleIds }` state (where `sampleIds` is up to 5 entry ids drawn from that agent×type intersection); a small overlay `<div>` near the cell shows those values. Click on empty SVG background clears `selectedCell`. **Axis labels are truncated to 12 characters** (`label.length > 12 ? label.slice(0, 11) + '…' : label`) — no scrolling, no zoom (resolves Open Question 2).
- **`<ConsoleView>` component** — `<pre>` block with `overflow-y: auto`, `white-space: pre-wrap`, `word-break: break-all`, monospace, `height: 100%`. Reads the existing Phase 1 `useEvents` 200-event array, slices the newest 100, JSON-stringifies one event per line (each line wrapped in a `<span>` with the type-color class from Phase 1's badge palette). Auto-scroll behavior is **follow-mode-aware** (resolves Open Question 3): a `useRef(true)` `followingRef` starts true; on `scroll`, recompute `following = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20`; on each `events` change, if `following === true` then `pre.scrollTop = pre.scrollHeight` else do nothing. A small floating pill labeled `↓ follow` is rendered in the top-right when `following === false`; clicking it forces `pre.scrollTop = pre.scrollHeight` and resets `following = true`.
- **Footer search input + filter logic** — `<Footer>` (Phase 1) gains a left-aligned `<input type="search" placeholder="filter…" />` and a right-aligned matches badge `{filtered.length} / {events.length} matches`. The search state is held in a `useState('')` local to `<Footer>` (a `filter` string). Filtering: `filtered = events.filter(e => filter === '' || JSON.stringify(e).toLowerCase().includes(filter.toLowerCase()))`. Real-time on each keystroke; no debounce (200 events × substring match is microseconds). The existing Phase 1 events list rendering is fed `filtered` instead of `events`. The input element is exposed via a ref so the keyboard `/` shortcut can focus it (see below).
- **Keyboard shortcuts handler** — single `useEffect` in `<App>` registers a `keydown` listener on `document` (cleanup removes it). The handler ignores the event when `e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA'` (so typing in the search box never triggers shortcuts). Recognized keys:
  - `g` → `setTweaks(t => ({ ...t, tab: 'graph' }))`
  - `m` → `setTweaks(t => ({ ...t, tab: 'matrix' }))`
  - `c` → `setTweaks(t => ({ ...t, tab: 'console' }))`
  - `space` → `e.preventDefault(); setTweaks(t => ({ ...t, running: !t.running }))`
  - `r` → calls `useGraph().refresh()` (passed into `<App>` from the lifted hook call)
  - `t` → toggles the `<TweaksPanel>` open/closed state (the `open` flag inside `<TweaksPanel>` is lifted to `<App>` for this purpose, OR `<TweaksPanel>` accepts a `controlledOpen` prop driven by `<App>` — the spec picks lift-to-App for simplicity)
  - `Escape` → `setFocus(null)` (clears the lifted Phase 2 focus state)
  - `/` → `e.preventDefault(); footerSearchRef.current?.focus()` (the `e.preventDefault()` intentionally suppresses Firefox's quick-find — accepted as dev-tool override per Open Question 5)
  - all other keys: no-op
- **localStorage persistence in `useTweaks`** — Phase 1's `useTweaks(defaults)` is upgraded to (a) hydrate from `localStorage.getItem('brain-monitor-tweaks-v1')` on mount via lazy initial state, merging `{ ...defaults, ...JSON.parse(stored) }` so any new field added to `TWEAK_DEFAULTS` after a user's last visit is filled with its default rather than `undefined`; (b) persist on every `setTweaks` via `localStorage.setItem(...)` inside a `useCallback` that wraps the raw setter. The storage key is **versioned** as `brain-monitor-tweaks-v1` — bump the suffix on a breaking schema change (the v1 contract is documented inline in code as the set of keys present in `TWEAK_DEFAULTS` at the time of writing, plus the Phase 1 `tab`, `running`, `accent`, `speed` and any later additions). Both reads and writes are wrapped in `try/catch`. On the first failure within a session, log a single `console.warn('[brain-monitor] localStorage unavailable; tweaks will not persist this session')` and set a module-level boolean to suppress further warnings (resolves Open Question 4 — silent retry is the failure mode, no UI banner).

## Scope (out — explicit YAGNI)

- New backend HTTP routes — none. Phase 3 strictly consumes the existing `/stats`, `/queue/status`, `/graph`, `/events`, `/events/timeline` endpoints.
- New MCP tools or schema changes — none.
- SQLite migrations or ChromaDB re-index — none.
- Auth, multi-user, sharing.
- Mobile / responsive layout.
- Dark/light mode toggle (single dark theme is the brand).
- Memory editing from UI (delete, merge, supersede, tag-edit) — read-only.
- Notification API / desktop notifications on errors.
- Export to JSON/CSV.
- Time-travel (replay past sessions) — Phase 4 territory.
- `tweaks.tab` URL hash sync (e.g., `#tab=matrix`) — localStorage is enough.
- Migration of `tmp/` mockups (`art-*.jsx`, `tmp/brain.html`) — they stay as design inspiration for Phase 4 Next.js.
- Any change to the existing Phase 1 + Phase 2 [SPEC-N] items (those merged, are append-only per CLAUDE.md). Phase 3 only **adds** new components and **modifies** `<Footer>` (search) + `useTweaks` (persistence) + the center-row JSX (tab switcher wraps the existing `<BrainGraph>`).
- Console-view virtualization — 100 lines × ~200 bytes is trivial DOM weight.
- Matrix-view tooltip styling polish, hover transitions — basic floating div is sufficient.
- Debounced search input — 200 events × `String.prototype.includes` is sub-millisecond.
- Sliding-window or hysteresis on cluster-meter trend arrows — intentional, see Open Question 1 resolution.
- Settings export/import — out of scope; localStorage is single-browser anyway.

## Constraints

- Phase 3 modifies the same single self-contained file `backend/src/brain/static/brain.html` created by Phase 1 and extended by Phase 2. NO new HTML/JSX/CSS file is added; everything is appended/edited inside that one file.
- **Phase 3 does NOT delete any Phase 1 or Phase 2 feature.** The htop header bars + sparkline, footer event log, tweaks panel, force-directed graph, click-to-focus, drag-to-pin, pan + zoom, refresh button, activation halos, thought stream, focus filtering — all continue to work. The only Phase 1/2 code touched is: (a) `<Footer>` (search input + matches badge added; existing event list still renders, just filtered), (b) `useTweaks` (localStorage hydration + persistence wrapped around the existing setter), (c) the center-row JSX (was `<BrainGraph .../>` directly; becomes `<TabBar/>` + conditional render of `<BrainGraph>` / `<MatrixView>` / `<ConsoleView>`), (d) the `<div className="left-placeholder" />` (replaced by `<LeftPanel/>`).
- Phase 3 adds NO new HTTP route. Verified by inspection of the existing brain server endpoints.
- Babel-in-browser + React 18 from unpkg CDN must continue to work — no build step.
- `<MatrixView>` must not freeze the browser at dogfood scale (1–3 agents × ≤8 types). Grid is at most ~24 cells; SVG render is trivial. No memoization needed.
- `<ConsoleView>` must keep up with 100-line refresh on each `useEvents` poll (every 2 s by default). 100 × `JSON.stringify` is ~1 ms; acceptable.
- Keyboard shortcut handler must not interfere with text input in `<input>` or `<textarea>`. Verified by the `e.target.tagName` guard.
- localStorage write must not block re-render. The `setTweaks` updater performs the write synchronously inside the React state callback, but the data is small (<1 KB) so the cost is negligible.
- Manual dogfood is the verification path for HTML/JSX [SPEC-N]s (per the Phase 1 policy carried into Phase 2 and now Phase 3). **Zero new pytest tests** are added in Phase 3 — Phase 1's `[TEST-1]` and Phase 2's `[TEST-1]` MUST continue to pass (no backend regression). The Phase 3 PR runs `[GATE-1]` ruff, `[GATE-2]` mypy, `[GATE-3]` pytest on the unchanged Python and they all stay green; this acts as the no-regression test.

## Architecture

### File layout (after this PR)

```
backend/src/brain/
├── server.py                           # unchanged from Phase 2
└── static/
    └── brain.html                      # MODIFIED — adds ~400 lines (left panel, tabs, matrix, console, search, shortcuts, persistence)

backend/tests/test_brain/
├── test_monitor_route.py               # unchanged (Phase 1 [TEST-1] still green)
└── test_graph_route.py                 # unchanged (Phase 2 [TEST-1] still green)
```

### Component tree (additions vs Phase 2)

```
<App>
  <Header>
    [Phase 1: cluster bars / mem / swap / status / since / total / version]
    <ActivitySparkline />                                       [Phase 2, unchanged]
  </Header>
  <Main className="phase2-grid">
    <LeftPanel>                                                 ← NEW (replaces Phase 2 <div.left-placeholder/>)
      <ClusterMeters stats={stats} />                           ← NEW
      <TopAccessed entries={graph.nodes} setFocus={setFocus} /> ← NEW
    </LeftPanel>
    <CenterArea>                                                ← NEW wrapper (replaces direct <BrainGraph>)
      <TabBar tab={tweaks.tab} setTab={setTab} />               ← NEW
      {tweaks.tab === 'graph'   && <BrainGraph .../>}           [Phase 2 component, unchanged props]
      {tweaks.tab === 'matrix'  && <MatrixView entries={...}/>} ← NEW
      {tweaks.tab === 'console' && <ConsoleView events={...}/>} ← NEW
    </CenterArea>
    <ThoughtStream />                                           [Phase 2, unchanged]
  </Main>
  <Footer events={events} />                                    ← MODIFIED (search input + matches badge)
  <TweaksPanel tweaks={tweaks} setTweaks={setTweaks}            [Phase 1, controlledOpen wired to <App>]
               open={tweaksOpen} setOpen={setTweaksOpen} />     ← MODIFIED
</App>
```

### Data flow

1. **`useStats`** (Phase 1) keeps polling at the user-controlled interval. `<ClusterMeters>` consumes `stats` directly. The previous-snapshot ref lives inside `<ClusterMeters>` and is updated after each render via a `useEffect(() => { prevRef.current = stats?.types ?? {}; })` so subsequent renders compare against the prior poll.
2. **`useGraph`** (Phase 2) keeps its mount-once + manual-refresh contract. `<TopAccessed>` reads `entries` (which `useGraph` already exposes via `nodes`, since Phase 2 builds `nodes` from `entries`) and renders the top 10 by `access_count`. `<MatrixView>` also reads `entries` and pivots them into the agent×type grid.
3. **`useEvents`** (Phase 1) keeps its 200-event poll at 2 s. `<ConsoleView>` slices the newest 100. `<Footer>` gains its `filter` state and applies it client-side; the existing event-list rendering is unchanged except that the input array is `filtered` instead of `events`.
4. **`useThoughts`** (Phase 2) is unchanged — `<ThoughtStream>` keeps consuming it.
5. **`useTimeline`** (Phase 2) is unchanged — `<ActivitySparkline>` keeps consuming it.
6. **`useTweaks`** (Phase 1, modified) reads from localStorage on mount and writes on every state update. `tweaks.tab` is the source of truth for the center-area tab switcher. `tweaks.running` is the source of truth for pause across all hooks.
7. **`focus`** (Phase 2) lifted state in `<App>` is now also written by `<TopAccessed>` (click row → setFocus) and cleared by the `Escape` keyboard shortcut.

### Keyboard shortcut handler (canonical implementation)

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

`footerSearchRef` is created via `useRef(null)` in `<App>` and forwarded to `<Footer>` as a prop, which assigns it to the `ref` attribute of its `<input>`.

### localStorage persistence (canonical implementation)

```js
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
  const [tweaks, setTweaksRaw] = React.useState(() => readStoredTweaks(defaults));
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
  return { tweaks, setTweaks };
}
```

The `warnedAboutStorage` module-scoped flag ensures exactly one `console.warn` per session even if both read and write fail.

### Console-view follow-mode detection (canonical implementation)

```js
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

  const newest100 = events.slice(0, 100);
  return (
    <div className="console-wrap">
      <pre ref={preRef} onScroll={onScroll}>
        {newest100.map((e, i) => (
          <span key={i} className={`console-line console-${classifyEvent(e.event_type)}`}>
            {JSON.stringify(e)}{'\n'}
          </span>
        ))}
      </pre>
      {showFollowPill && <button className="follow-pill" onClick={jumpToBottom}>↓ follow</button>}
    </div>
  );
}
```

`classifyEvent` returns the same class suffix Phase 1's `<Footer>` uses for its badges (`green` / `cyan` / `yellow` / `red` / `grey`).

### Matrix view (canonical sketch)

```js
function MatrixView({ entries }) {
  const [selected, setSelected] = React.useState(null);
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

  // svg viewBox sized to wrapper via ResizeObserver; cell coords computed from agents.length × types.length
  // each cell <rect fill={hsla(180, 60%, 50%, alpha(count, maxCount))} onClick={() => setSelected({a, t, count, samples})}/>
  // label.length > 12 ? slice(0, 11) + '…' : label
}
```

`alpha(count, maxCount)` returns `Math.max(0.1, Math.log(count + 1) / Math.log(maxCount + 1))` when `count > 0`, else `0`.

### CSS additions

New CSS selectors added inside the existing `<style>` block:

- `.left-panel { display: flex; flex-direction: column; gap: 8px; padding: 8px; min-height: 0; }`
- `.cluster-meters .meter-row { display: grid; grid-template-columns: 80px 1fr auto auto; gap: 6px; align-items: center; height: 24px; font-size: 11px; }`
- `.cluster-meters .meter-bar { height: 6px; border-radius: 3px; background: #1a1d28; overflow: hidden; }`
- `.cluster-meters .meter-bar > span { display: block; height: 100%; }`
- `.cluster-meters .trend-up { color: var(--accent); }`
- `.cluster-meters .trend-down { color: var(--err); }`
- `.cluster-meters .trend-flat { color: var(--dim); }`
- `.top-accessed { flex: 1; min-height: 0; overflow-y: auto; list-style: none; padding: 0; margin: 0; }`
- `.top-accessed li { display: grid; grid-template-columns: 8px 1fr auto; gap: 6px; align-items: center; padding: 4px 6px; cursor: pointer; }`
- `.top-accessed li:hover { background: #161922; }`
- `.top-accessed li.focused { background: #1f2433; outline: 1px solid var(--accent); }`
- `.top-accessed .dot { width: 8px; height: 8px; border-radius: 50%; }`
- `.top-accessed .access-badge { font-variant-numeric: tabular-nums; color: var(--dim); font-size: 10px; }`
- `.tab-bar { display: flex; gap: 4px; padding: 4px 8px; border-bottom: 1px solid #1a1d28; }`
- `.tab-bar button { background: transparent; border: 1px solid #2a2f3d; color: var(--fg); padding: 2px 10px; cursor: pointer; font-family: inherit; font-size: 11px; }`
- `.tab-bar button.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }`
- `.center-area { display: flex; flex-direction: column; min-height: 0; }`
- `.center-area > .tab-content { flex: 1; min-height: 0; position: relative; }`
- `.matrix-view { width: 100%; height: 100%; }`
- `.matrix-view .cell-overlay { position: absolute; background: #1a1d28; border: 1px solid #2a2f3d; padding: 6px 8px; font-size: 11px; pointer-events: none; }`
- `.console-wrap { position: relative; height: 100%; }`
- `.console-wrap pre { height: 100%; margin: 0; padding: 6px 8px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; font-size: 10px; line-height: 1.4; background: #08090d; }`
- `.console-line.console-green { color: var(--ok); }`
- `.console-line.console-cyan { color: var(--accent); }`
- `.console-line.console-yellow { color: var(--swap); }`
- `.console-line.console-red { color: var(--err); }`
- `.console-line.console-grey { color: var(--dim); }`
- `.follow-pill { position: absolute; top: 8px; right: 8px; background: var(--accent); color: var(--bg); border: none; padding: 2px 8px; cursor: pointer; font-family: inherit; font-size: 10px; }`
- `.footer-search { display: flex; align-items: center; gap: 8px; padding: 4px 8px; }`
- `.footer-search input { background: #08090d; border: 1px solid #2a2f3d; color: var(--fg); padding: 2px 6px; font-family: inherit; font-size: 11px; min-width: 200px; }`
- `.footer-search .matches-badge { color: var(--dim); font-size: 10px; font-variant-numeric: tabular-nums; }`

### Open questions resolved (from brainstorm)

1. **`<ClusterMeters>` trend arrow flicker** — accepted. No debounce, no sliding window. Documented in [SPEC-2] as expected behavior; the trend arrow is dev signal, not user-facing UX.
2. **`<MatrixView>` size at 20 agents × 12 types** — out of scope (dogfood is 1–3 agents). Axis labels are truncated to 12 characters; no scrolling, no zoom. Documented in [SPEC-5].
3. **`<ConsoleView>` auto-scroll** — follow-mode detection: `pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20` is the threshold. When the user scrolls up beyond 20 px from the bottom, follow mode disengages and a `↓ follow` pill appears in the top-right; clicking it (or scrolling back to the bottom manually) re-engages follow mode. Documented in [SPEC-6].
4. **localStorage failures (private mode, full quota)** — `try/catch` swallows silently. A single `console.warn` is logged per session via a module-scoped `warnedAboutStorage` flag. No UI banner. Documented in [SPEC-9].
5. **Keyboard shortcut `/` collision with browser quick-find** — `e.preventDefault()` intentionally suppresses the browser's default. This is a dev tool; the override is acceptable. Documented in [SPEC-8].

## Affected systems

- **HTTP API:** unchanged. Phase 3 reads `/stats`, `/queue/status`, `/graph`, `/events`, `/events/timeline` — all already exist and were already used in Phase 1 and Phase 2.
- **MCP tools:** unchanged. No new tool, no schema change.
- **Storage:** unchanged. No SQLite migration. No ChromaDB re-index. No metadata schema change.
- **Frontend:** modified `backend/src/brain/static/brain.html` only. No `frontend/` package created. No new files. No build tooling.
- **Installer (`npx brain`):** unchanged in this PR.
- **Scripts (Claude Code hooks — wake_up / post_turn / statusline):** unchanged.
- **Benchmarks:** unchanged. The monitor is a passive read-only consumer.
- **Tests:** ZERO new pytest tests in Phase 3 (HTML/JSX-only changes). Phase 1's `test_monitor_route.py::test_monitor_route_serves_html` and Phase 2's `test_graph_route.py::test_graph_route_returns_expected_schema` remain unchanged and must stay green; they collectively cover the no-regression invariant on the backend side.

## Risks

- **localStorage quota exhausted in private-mode browsers.** Mitigation: `try/catch` everywhere, `console.warn` once, fall through to in-memory defaults — covered in [SPEC-9].
- **Trend arrow flicker on rapid count oscillation.** Accepted and documented (Open Question 1). Dev signal, not UX.
- **Matrix view at unusual agent counts.** Cell becomes tiny but still renders. No freeze. Out-of-scope for Phase 3 polish.
- **Console auto-scroll fights the user.** Mitigated by follow-mode detection (Open Question 3 resolution).
- **Keyboard `/` shortcut suppresses Firefox quick-find.** Intentional, documented (Open Question 5).
- **Tab unmount of `<BrainGraph>` could leak the rAF loop.** Phase 2's `<BrainGraph>` cleanup already cancels the rAF in its `useEffect` cleanup; unmount triggers cleanup. Verified manually during dogfood.
- **Tab switching loses graph node positions.** Acceptable: when re-mounting `<BrainGraph>`, `useGraph` returns the same nodes from its cache (Phase 2 hook), but Phase 2's component initializes positions to `cx + jitter, cy + jitter` on mount. Documented as an accepted minor regression (positions reset on tab cycle). Phase 3 explicitly does NOT add position persistence — that's a Phase 4 concern.
- **localStorage tweaks key version mismatch on rollback.** If the user's browser stored a v2 schema and we roll the code back to v1, the spread `{ ...defaults, ...parsed }` keeps unknown keys; React state happily ignores them. Forward-only renames are safe. Backward-incompatible changes require bumping the storage key suffix.

## Consumer impact

- **Money** (legacy embedded Brain on `:8611`): no impact. Money never calls `/monitor`.
- **Marcel / future consumers:** no impact. Phase 3 is purely additive UI; HTTP/MCP surfaces unchanged.
- **Phase 1 + Phase 2 consumers (the dogfood operator using the dashboard):** all existing zones (header htop + sparkline, footer event log, tweaks panel, force-directed graph with all interactions, thought stream with focus filtering) keep working unchanged. The Phase 2 left placeholder is replaced by the `<LeftPanel>`. The Phase 2 center column gains a tab bar above the graph; the graph itself is unchanged when its tab is active. The Phase 1 footer gains a search input and a matches badge; the existing event list rendering is unchanged except for the filter input array. The Phase 1 tweaks now persist to localStorage. **No regression** is verified by Phase 1 `[TEST-1]` + Phase 2 `[TEST-1]` continuing to pass and by manual dogfood verification anchors documented per [SPEC-N] in the checklist.
