# Brain Monitor — Fidelity Pass — Design

**Goal:** Bring the live monitor to dogfood-grade visual fidelity (mockup `tmp/brain*.jsx`) and add debug-first surfaces (layer rings, animations, memory_type co-occurrence, hash-routed inspectors) so an operator can semantically verify "ça fait du sens" — not just that metrics tick.

**Roadmap phase:** R:phase-2b
**Source brainstorm:** [data/brainstorm-monitor-fidelity.md](../../data/brainstorm-monitor-fidelity.md) (Q1–Q16 locked)
**Budget:** 1.5 days, single PR, single file.
**File touched:** `backend/src/brain/static/brain.html` (only). ~600–800 LOC additions/modifications.

## Scope (in)

- Header redesign per Q13: tabs migrated FROM center area TO header right side; agent attach dropdown; L2 indicator badge; `brain v0.2 · pid 1` identity block; stats row `up HH:MM:SS · thoughts N · evt/s X.X`; status dot; tabs receive their own button group on the right.
- Layer ring rendering in `<BrainGraph>` per Q8: outer ring color encodes layer (`L0=gold`, `L1=cyan`, `L2=magenta`, untiered=no ring); fill stays memory_type palette.
- Animation system in `<BrainGraph>` per Q9: entry fade-in for `event_type=stored`, pulse for `reinforced`, halo-decay (60 s) for L2-loaded, edge-grow for newly-linked. Concurrency cap = 20 oldest-dropped. Skippable via tweaks panel toggle `animations`.
- `<MatrixView>` replaced by memory_type × memory_type co-occurrence (Q10) WITH a secondary toggle "view: agents | types" preserving the Phase 3 agent×type heatmap (mitigates risk #5).
- `<ConsoleView>` format refinement (Q11): `[HH:MM:SS] event_type · agent · brief_details`, color-coded; auto-scroll + follow pill kept.
- `<Footer>` (Q12): right-aligned cosmetic `tail -f /var/log/brain/events.jsonl` indicator + italic dim empty state `waiting for system events…` when `events.length === 0 && !lastError`.
- Hash router (Q14): new `<HashRouter>` reads `window.location.hash` and switches App between dashboard / `<MemoryInspector>` / `<HookReplay>` / `<AgentProfile>` views. Drawer-style overlay reusable. j/k next/prev event navigation. Esc closes; back-button restores dashboard hash.
- Tweaks panel: add `animations: true` to `TWEAK_DEFAULTS`; persist via existing localStorage helper.
- App-level agent filter (Q4): single `agentFilter` state lifted into `<App>`, scopes `<BrainGraph>`, `<ThoughtStream>`, `<Footer>`. Default `'all'`. Persisted in tweaks (`tweaks.agentFilter`).
- Layer mapping helpers (`tagToLayer`, `inferLayer(memory, l2Recents)`, `layerRingColor(layer)`, `useL2Recents(events)`).

## Scope (out — explicit YAGNI)

- Backend changes. L2-A already enriched `hook_wake_up` events with `memory_ids`, `cosine_scores`, `tokens_per_layer`, `topic_query_used`. No new routes, no new event_types.
- Queue history persistence (`queue_log.jsonl`). Buffered in-memory only; lost on reload. Acceptable for dogfood per Q2.
- Playwright tests. Phase 4 territory.
- Mobile responsiveness, multi-language, theme switcher.
- Memory edit/delete from inspector. Read-only inspectors only.
- L3 invocation from monitor — L3 is model-driven via MCP, not user-driven.

## Constraints

- ZERO new pytest tests (Q15). Phase 1+2+3+L2-B baseline (220 backend tests as of 2026-04-28) acts as no-regression coverage. `[GATE-1]` ruff and `[GATE-2]` pytest must remain green.
- ZERO regression on Phase 1+2+3 surfaces. The header htop bars + uptime + version + sparkline; the footer events list + filter + matches badge; the tweaks panel toggles + persistence; the graph tab with focus / drag-pin / pan / zoom / refresh / activation halos; the matrix tab with the agent×type heatmap (now demoted to a toggleable secondary view); the console tab with auto-scroll + follow pill; the thought stream with focus filter; the keyboard shortcuts (`g`, `m`, `c`, `space`, `r`, `t`, `Escape`, `/`); the localStorage tweaks helper. ALL must continue to work after the fidelity pass.
- Single file modified: `backend/src/brain/static/brain.html`. No new files. No backend Python touched. No frontend `package.json`.
- mypy is NOT a hard gate (CLAUDE.md, 99+ pre-existing errors).

## Architecture

The monitor stays a single inline-React static HTML file served from FastAPI at `/monitor`. The fidelity pass is purely additive on top of Phase 3's component tree.

**New components added to the existing tree:**

- `<HashRouter>` (≈ 50 LOC) — wraps `<App>`; subscribes to `hashchange`; matches `#/memory/<id>` → `<MemoryInspector memId>`, `#/hook/<eventId>` → `<HookReplay eventId>`, `#/agent/<name>` → `<AgentProfile name>`; otherwise renders the dashboard. Routed views render in a 600 px right-side overlay panel (drawer-style, `position: fixed; right: 0; top: 0; height: 100vh; width: 600px`); the dashboard remains visible behind dimmed at `opacity: 0.35`. `Esc` clears the hash to `''`. Browser back-button works because routing is hash-based.
- `<MemoryInspector memId>` (≈ 100 LOC) — pulls `useGraph()` and `useEvents()`, finds the matching node, renders content + memory_type + tags + confidence + agent + created_at + access_count + last_accessed + linked memories + (when applicable) the L2 cosine score from the most recent `hook_wake_up.metadata.cosine_scores` (resolves Open Question 4).
- `<HookReplay eventId>` (≈ 100 LOC) — pulls `useEvents(limit=200)`, finds the event whose `event_id` matches, renders full request body (left column) + full response body (right column) + per-layer breakdown table (rows: L0, L1, L2; columns: memory_ids, tokens_used / tokens_budget, cosine_scores when L2). j/k navigates next/prev event without closing.
- `<AgentProfile name>` (≈ 100 LOC) — filters `useGraph()` and `useEvents()` by `agent === name`, renders 3 sections: created memories (via `event_type=stored` from this agent), loaded memories (via `event_type=hook_wake_up` for this agent, expanded to `metadata.memory_ids` flattened across layers), recent activity timeline (last 50 events).
- `<MemoryTypeCooccurrence entries>` (≈ 100 LOC) — replaces the Phase 3 `<MatrixView>` for the default cell. Builds an N×N matrix where N = number of distinct `memory_type` values present. For each entry, splits its `links` field, looks up each linked entry, increments `matrix[entry.memory_type][linkedEntry.memory_type]`. Symmetric: `matrix[a][b]` and `matrix[b][a]` both incremented (the cell is interpreted as "co-occurrence", not direction). Cell intensity = `Math.log(count + 1) / Math.log(maxCount + 1)`. Click cell → drawer opens to `#/memory/<firstLinkedId>` (deep-link affordance). Above the SVG: a `<button>` toggle pair "view: agents | types"; "agents" routes back to the existing Phase 3 `<MatrixView>` (which is renamed `<AgentTypeMatrix>` and kept; resolves risk #5). Default = "types".
- `<LayerRing radius layer>` (≈ 20 LOC) — sub-component of `<BrainGraph>` rendering an outer `arc()` ring 2 px thick, color from `layerRingColor(layer)`, drawn AFTER the node fill in `render()`.
- Animation hooks (≈ 80 LOC total): `useEntryAnimation(events, ttl=600)`, `usePulseAnimation(events, ttl=400)`, `useHaloDecayAnimation(l2Recents)` (re-uses existing `activatedAtRef` plus a new `l2HaloAtRef` for the magenta-tinted L2 halo), `useEdgeGrowAnimation(edges)` (animates new edges over 800 ms after their endpoint nodes finished entry animation).
- `useL2Recents(events)` (≈ 30 LOC) — derives a `Map<memId, expiryTimestampMs>` by scanning `events` for the latest `hook_wake_up`, reading `metadata.memory_ids.L2 ?? []`, and stamping each id with `Date.now() + 60000`. Stale entries pruned on every poll. Used by the layer ring renderer (`inferLayer`) to decide L2 vs untiered. **L2 transient timer is anchored to the wake_up event timestamp, not the local clock**: `expiryTimestampMs = new Date(event.timestamp).getTime() + 60000` (resolves risk #4: a freshly-opened monitor that polls a 5-minute-old wake_up will not show a stale L2 ring).

**Modified components:**

- `<App>` — wrapped by `<HashRouter>`. Adds two pieces of lifted state: `agentFilter` (sourced from `tweaks.agentFilter`, default `'all'`) and `l2Recents` (from `useL2Recents(events)`). Passes `agentFilter` down to `<BrainGraph>` (filters `nodes` by agent), `<ThoughtStream>` (filters `events` by agent), `<Footer>` (filters its events list). When `agentFilter === 'all'` the filter is a no-op (every component sees the unfiltered data).
- `<Header>` — restructured (Q13). Left half: cluster cores (Phase 1, unchanged) + mem/swap bars (Phase 1, unchanged). Right half (NEW): identity row `brain v0.2 · pid 1` (literals, resolves Open Question 1+2 from brainstorm — version stays hardcoded `v0.2` per simplicity, `pid 1` is correct because Brain runs as PID 1 inside Docker), stats row `up HH:MM:SS · thoughts N · evt/s X.X` (uptime since page-load, `thoughts = events.length`, `evt/s = events filtered to last 60 s / 60`), tab buttons `[graph] [matrix] [console]` (migrated from the center-area `<TabBar>` — `<TabBar>` is deleted from `<App>`'s center-area JSX), `agent: ▼` dropdown, `L2: N` badge (count of memory ids in last `hook_wake_up.metadata.memory_ids.L2`; `0` → badge dimmed; click → opens `#/hook/<lastWakeUpEventId>`), status dot (existing).
- `<BrainGraph>` — `render()` extended: ring drawing pass after node fill pass; entry/pulse/edge-grow animation passes integrated; cap=20 enforced via a sliding-window queue; respects `tweaks.animations` (when `false`, all animation hooks no-op and `render()` skips the animation passes — the rings still draw, since they're persistent state, not animations). Click on a node now also calls `setLocation('#/memory/<id>')` in addition to setting focus.
- `<TweaksPanel>` — adds an `animations` toggle (default `on`); CSS pattern matches existing `polling on` toggle.
- `<Footer>` — adds a right-aligned `<span className="tail-indicator">tail -f /var/log/brain/events.jsonl</span>` (cosmetic, dim, italic, monospace); when `(filter === '' && events.length === 0 && !lastError)`, render `<div className="empty-state">waiting for system events…</div>` italic dim in place of the events list (search row stays visible — toggling between empty state and list is purely a function of `events.length`).
- `<TweaksPanel>` (already covered above).
- `TWEAK_DEFAULTS` — extended with `animations: true`, `agentFilter: 'all'`, `matrixSubview: 'types'`. Existing localStorage helper handles persistence automatically (Phase 3 `useTweaks` already merges `{ ...defaults, ...parsed }`, so old persisted state without these keys gracefully picks up defaults; resolves Open Question 3).

**Hash routing flow (resolves risk #3):**

`window.location.hash` is the single source of truth. The drawer overlay opens iff `hash` matches one of the routed patterns. Clicking a graph node calls `history.replaceState(null, '', '#/memory/<id>')` and dispatches `hashchange` so `<HashRouter>` re-renders. Pressing `Esc` calls `history.replaceState(null, '', window.location.pathname)` clearing the hash. The browser back-button automatically navigates the hash history; `<HashRouter>` re-renders accordingly. j/k inside `<HookReplay>` calls `history.pushState(null, '', '#/hook/<prevOrNextId>')` so the back-button can step back through inspected events.

## Affected systems

- **HTTP API:** read-only — `/stats`, `/queue/status`, `/events`, `/events/timeline`, `/graph` (all already consumed by Phase 3). No new routes.
- **MCP tools:** unchanged.
- **Storage:** unchanged. No SQLite migration. No vector re-index.
- **Frontend:** the inline-React `brain.html` only. No `frontend/` directory exists yet (Phase 4 territory).
- **Installer (`npx brain`):** unchanged. The static file is served by the existing `/monitor` route.
- **Scripts (Claude Code hooks):** unchanged. `wake_up` and `post_turn` scripts produce events that the monitor consumes; they are not modified.
- **Benchmarks:** unchanged. The fidelity pass cannot affect LongMemEval / LoCoMo scores — it adds no tokens to any LLM call.
- **Tests:** zero new pytest tests (Q15). Manual HTML/JSX dogfood is the verification surface, mirroring Phase 1/2/3 precedent. Each `[SPEC-N]` documents a manual verification anchor.

## Risks

1. **Layer ring depends on `metadata.tags` presence.** Memories created via `post_turn` Gemini Flash extractor get tags; pre-L2 legacy memories may not. Untagged-and-never-L2-loaded memories render with no ring (intentional — visual signal that they're untiered). Spot-check 20 memories during dogfood to confirm tag coverage.
2. **Animation perf at 200+ active nodes.** Mitigated by hard cap of 20 concurrent animations (oldest-dropped), and by the `animations: false` toggle for low-end machines. Worst case: pulse/halo passes skipped for that frame.
3. **Hash router ↔ drawer race.** Mitigated by making `window.location.hash` the single source of truth — the drawer is a derived view, not a separate state. `Esc`, click-out, back-button, and j/k all funnel through `history.{push,replace}State` + `hashchange`.
4. **L2 60-second timer source.** Anchored to event `timestamp`, not local clock. Stale wake_up events (>60 s old) on a freshly-opened monitor never trigger the magenta ring. `useL2Recents` filters on every poll.
5. **MatrixView breaking change.** Phase 3 shipped agent×type. Phase 2b-fidelity replaces the default with memory_type×memory_type, but the agent×type matrix is preserved as the secondary `tweaks.matrixSubview === 'agents'` view, accessible via the toggle pair above the SVG. No data lost; user mental model bridged.
6. **600-800 LOC stretches the budget.** If [SPEC-N] count exceeds 14 during decomposition, spec-writer outputs `needs_decomposition` and proposes splitting into PR1 (header + animations + matrix + console + footer + tweaks + helpers) and PR2 (hash routing + 3 inspectors). Tracked in spec_verdict.

## Consumer impact

- Money: no impact. Money still talks to its embedded Brain at `:8611`. This repo's monitor at `:8621/monitor` is independent.
- Marcel: no consumer yet.
- Future Brain installer (`npx brain`): no impact. The static file is shipped as-is in the Docker image.
