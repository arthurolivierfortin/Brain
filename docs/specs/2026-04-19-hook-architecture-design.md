---
id: 2026-04-19-hook-architecture
title: Hook architecture MVP (wake_up + post_turn)
status: approved
date: 2026-04-19
supersedes: (none)
relates_to:
  - docs/decisions/0001-project-meta-conventions.md
  - docs/improvements/README.md (P0 dynamic types, P2 L0/L1/L2/L3 layering)
  - README.md Phase 2b
---

# Hook architecture — MVP design

## Goal

Make Brain **automatically** inject relevant context at session start (`wake_up`) and **automatically** capture structured memories at turn end (`post_turn`). Agents no longer need to invoke MCP tools to benefit from Brain — the hook lifecycle does it for them. This is what separates "memory API" from "cerveau parfait" for agents.

## Context

Brain today exposes memory via HTTP endpoints (`/store`, `/search`, `/reset`, `/stats`) and MCP tools (`brain_store`, `brain_search`, `brain_related`, `brain_stats`, `brain_forget`). Using these requires the model to explicitly call them — tool-use, which is bandwidth-limited and often forgotten.

The current `scripts/brain_hook.py` wires one Claude Code hook (`Stop`) that summarizes the session delta via Gemini Flash and posts it to `/store`. This is Claude-Code-specific, post-session-only, and stores verbatim blobs rather than structured atomic memories. It covers ~20% of the vision.

This spec defines a **platform-agnostic hook contract** and its first concrete implementer (Claude Code), scoped to two hooks — `wake_up` and `post_turn` — as the minimum viable slice of the cerveau-parfait vision.

## Scope

### In scope (MVP)

- Agnostic JSON-over-HTTP contract for two hooks: `wake_up` and `post_turn`
- Brain backend endpoints implementing the contract
- `Extractor` Protocol with `GeminiFlashExtractor` as default implementation
- Memory schema extensions: `tags` (comma-separated string) and `confidence` (float), passed through existing `RESERVED_META_KEYS` passthrough
- Claude Code adapter scripts (`brain_wake_up.py` new, `brain_post_turn.py` renamed/refactored from `brain_hook.py`)
- Update to Brain's own `.claude/settings.json` wiring SessionStart + Stop
- Dogfood plan: Brain consumes Brain for ≥ 7 days before considering the MVP done

### Out of scope (deferred — tracked in README Phase 2b)

- Remaining hooks: `pre_turn` (L2 topic-triggered), `pre_tool_use`, `post_tool_use`, explicit `session_end` consolidation
- Bootstrap flow (interactive seeding of initial identity/preference memories)
- Adaptive token budget per layer
- Multi-platform adapters (Cursor, Codex, Cline)
- L2 topic-triggered retrieval + L3 deep semantic search
- Dynamic memory type normalization (paired with P0 improvement)
- Extractor fallback chains (Flash → Haiku → Ollama → raw blob)
- Frontend observability for hooks (Phase 4)

### Non-goals

- No authentication layer — localhost-only drop-in
- No multi-tenant isolation beyond `agent` scoping — single-user tool
- No real-time streaming of context injection — sync request/response
- No replacement of existing MCP tools — they stay for explicit model-driven access

## Architecture overview

```
Claude Code session
│
├── SessionStart hook fires
│   └── scripts/brain_wake_up.py reads stdin (CC payload)
│       └── POST http://localhost:8621/hook/wake_up
│           └── Brain: select L0 (tag=identity) + L1 (tag=preference)
│               → format as markdown, budget 500 tokens
│           └── Returns {context, layers_loaded, tokens_approx}
│       └── Wrap into CC SessionStart contract → stdout
│   └── Claude Code injects context into system prompt
│
├── User + assistant turns happen
│
└── Stop hook fires (per assistant turn completion)
    └── scripts/brain_post_turn.py reads stdin + transcript delta
        └── POST http://localhost:8621/hook/post_turn with structured turn
            └── Brain: Extractor.extract(turn) via Gemini Flash
                → N ExtractedMemory objects
            └── For each: gate → dedup → store
            └── Returns {extracted, rejected_by_gate, cost_usd, ms}
        └── On Brain unreachable: enqueue to data/brain_pending_local.jsonl
        └── Drain pending queue opportunistically
```

## Section 1 — Agnostic hook contract

All interactions are `POST` HTTP + JSON in/out, targeted at localhost Brain (default `:8621`).

### `POST /hook/wake_up`

**Request**:
```json
{
  "agent": "brain-dev",
  "project": "/c/Brain",
  "session_id": "cc-session-abc123"
}
```

**Response**:
```json
{
  "context": "## Identity\n- French-first, blunt style, no trailing summaries\n\n## Preferences\n- Commit emoji convention: 🧠 🩹 📓 🧹 🧪 🧬\n...",
  "layers_loaded": {"L0": 3, "L1": 7},
  "tokens_approx": 340,
  "duration_ms": 42
}
```

**Semantics**:
- Brain selects memories tagged `identity` (L0) and `preference` (L1), scoped to `agent`.
- Formats as markdown with `## Identity` and `## Preferences` sections.
- Hard budget of 500 tokens (MVP constant — configurable via env var later). If selection exceeds budget, drop least-accessed memories first.
- Token count uses the simple `len(context) // 4` heuristic (char/4 ≈ token). Good enough for budget enforcement; swap for a real tokenizer in a future iteration if drift becomes a problem.
- `duration_ms` reported for client-side monitoring.

### `POST /hook/post_turn`

**Request**:
```json
{
  "agent": "brain-dev",
  "project": "/c/Brain",
  "session_id": "cc-session-abc123",
  "turn": {
    "user": "fix les bugs du smoke",
    "assistant": "J'ai corrigé #1 et #2...",
    "tool_calls": [
      {"name": "Bash", "input": "pytest"},
      {"name": "Read", "input": "backend/src/brain/store.py"}
    ]
  }
}
```

**Response**:
```json
{
  "extracted": [
    {"id": "a1b2", "type": "decision", "content": "...", "tags": ["backend", "testing"]},
    {"id": "c3d4", "type": "bug-fix", "content": "...", "tags": ["benchmarks"]}
  ],
  "rejected_by_gate": 1,
  "extraction_cost_usd": 0.0023,
  "extraction_ms": 850
}
```

**Semantics**:
- The `turn` object is **structured** (separate fields), not flattened — the extractor can distinguish user vs assistant vs tool calls.
- Brain invokes the Extractor, which returns N `ExtractedMemory` objects.
- Each memory goes through the existing gate + dedup pipeline before being stored.
- `extracted` list returned for observability and debugging.
- `extraction_cost_usd` tracked per call for budget monitoring.

### L0/L1 identification

- **L0 memories**: any memory with `tag` containing `identity`
- **L1 memories**: any memory with `tag` containing `preference`
- **Orthogonal to `memory_type`**: type stays a free-form string (P0 compat — dynamic types). A memory can be `type="decision"` AND `tag="preference"` if it captures a preferred way of deciding.
- **Orthogonal to `level`**: `level` remains the existing consolidation hierarchy (raw → summary → knowledge → principle).

### Failure modes

| Condition | `wake_up` | `post_turn` |
|-----------|-----------|-------------|
| Brain unreachable | stdout empty context, session continues, client logs warning | Enqueue payload to `data/brain_pending_local.jsonl`, drain later |
| HTTP 500 from Brain | Same as unreachable | Same as unreachable |
| Extractor LLM down (e.g. Gemini Flash API fail) | N/A (retrieval only) | Fallback: store raw delta as single memory with `type=raw-fallback`, `confidence=0.3` |
| Timeout exceeded | Abort, return empty/enqueue | Abort, enqueue |

Principle: **no hook error may ever block a Claude Code session**. Graceful degradation is absolute.

## Section 2 — Backend implementation

### Module layout

New file: `backend/src/brain/hook.py`. Contains:

- Dataclasses: `HookRequest`, `WakeUpResponse`, `PostTurnResponse`, `ExtractedMemory`, `Turn`
- `Extractor` Protocol
- `GeminiFlashExtractor` implementation (reuses `GOOGLE_API_KEY` env var)
- `WakeUpHandler` class (uses `BrainStore.search_by_tag`)
- `PostTurnHandler` class (orchestrates Extractor → gate → store)

`server.py` HTTP handler stays thin: parses JSON body, delegates to the handlers, serializes response.

### Extractor Protocol

```python
class Extractor(Protocol):
    def extract(self, turn: Turn) -> list[ExtractedMemory]: ...

@dataclass
class ExtractedMemory:
    content: str
    type: str              # free-form, dynamic (P0 compat)
    tags: list[str]        # may include "identity", "preference" markers
    confidence: float      # 0.0 – 1.0
```

The Gemini Flash impl uses a prompt asking for a JSON object of the form `{"memories": [...]}`, with explicit guidance to produce multiple atomic facts rather than one blob summary.

### Memory schema extensions

Two new fields persisted in ChromaDB metadata:

- **`tags`**: comma-separated string (ChromaDB requires flat scalars, no lists). Individual tags are sanitized to `[a-z0-9-]+` at ingest (lowercased, commas/whitespace replaced by `-`) to make the comma-separated representation lossless. Query via a top-level `tags` LIKE-substring filter. Example: `where={"tags": {"$contains": "identity"}}` if ChromaDB supports `$contains`, else adapter-side filtering post-fetch. Substring matching means `"identity-core"` also matches a search for `"identity"` — this is **intentional** (enables tag namespacing like `identity/persona`, `identity/role`) and the Extractor must emit tags accordingly.
- **`confidence`**: float, default 1.0 for existing memories without the field.

Existing memories without these fields return `None` from ChromaDB. Handle via `meta.get("tags", "")` and `meta.get("confidence", 1.0)`. **No migration required.**

`BrainStore.store()` already has `RESERVED_META_KEYS` passthrough (fix for issue #1). The new fields flow through without code changes — they're not reserved, so they're stored as custom metadata and surfaced in search results via the nested `metadata` dict.

### New store method: `search_by_tag`

```python
def search_by_tag(self, tag: str, agent: str, top_k: int = 5) -> list[dict]:
    """Return memories whose tags field contains `tag`, ordered by access_count desc."""
    ...
```

Used by `WakeUpHandler` to fetch L0 and L1 candidates. Sort by `access_count` desc — the more often a memory has been used, the stronger the signal that it's foundational (true identity/preference).

### Gate integration

No modifications to `gate.py` for MVP. The flow:

```python
extracted_memories = extractor.extract(turn)
for em in extracted_memories:
    store.store(
        content=em.content,
        agent=request.agent,
        memory_type=em.type,
        metadata={
            "tags": ",".join(em.tags),
            "confidence": em.confidence,
            "session_id": request.session_id,
            "project": request.project,
        },
        skip_gate=False,  # gate still handles noise filtering + dedup
    )
```

The gate works on content, independent of type. It filters correctly even with dynamic `memory_type` values coming from the extractor.

### Event log additions

Two new `event_type` values in `events.py`:

- `hook_wake_up` — fields: `tokens_approx`, `layers_loaded`, `duration_ms`, `agent`
- `hook_post_turn` — fields: `extracted_count`, `rejected_count`, `extraction_cost_usd`, `extraction_ms`, `agent`

Enables future hook-by-hook tracing via `/events/timeline` and frontend dashboard (Phase 4).

### Tests

**Unit** (mocked):
- `test_hook_extractor_gemini.py` — mock httpx, verify prompt structure + JSON parse
- `test_hook_wake_up.py` — store identity/preference memories, call `WakeUpHandler`, assert context format + budget respected + layers_loaded accurate
- `test_hook_post_turn.py` — mock Extractor, assert flow: extract → gate → store → response
- `test_store_search_by_tag.py` — cover new method (with agent filter, access_count ordering)

**Integration** (real Brain, real ChromaDB, mocked extractor):
- `test_hook_e2e.py` — POST `/hook/post_turn` with a realistic turn, verify memories created with correct tags, subsequent POST `/hook/wake_up` returns them

## Section 3 — Claude Code adapter

### Claude Code hook mapping

| CC hook | Brain hook | Why |
|---------|-----------|-----|
| `SessionStart` | `POST /hook/wake_up` | Only CC hook that can inject `additionalContext` into system prompt |
| `Stop` | `POST /hook/post_turn` | Fires after each assistant turn; transcript delta readable via byte offset |

Not mapped (future work): `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SessionEnd`, `PreCompact`.

### Scripts

```
scripts/
├── brain_wake_up.py      # NEW — SessionStart hook
├── brain_post_turn.py    # Renamed from brain_hook.py, refactored
├── brain_save_now.py     # Unchanged — manual save trigger
└── brain_statusline.py   # Unchanged — not hook-related
```

Scripts live in Brain repo for MVP. `npx brain` installer (Phase 3) will copy them into consumer repos. Brain's own `.claude/settings.json` references them via `$CLAUDE_PROJECT_DIR/scripts/`.

### `brain_wake_up.py` flow

1. Read stdin JSON (Claude Code provides `session_id`, `cwd`, etc.)
2. Derive `agent_id` from `cwd` basename (e.g. `cwd=C:/Brain` → `agent=brain-dev`)
3. `POST http://localhost:8621/hook/wake_up` with `{agent, project, session_id}`
4. Timeout 500ms — on timeout, write empty `additionalContext` and exit 0
5. On success, wrap response in Claude Code's SessionStart contract:
   ```json
   {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}
   ```
6. Print to stdout, exit 0

### `brain_post_turn.py` flow (evolution of existing `brain_hook.py`)

Keep the machinery that works:
- Byte offset tracking per `session_id` in `data/brain_hook_state/`
- Pending queue at `data/brain_pending_local.jsonl` with opportunistic drain
- Transcript JSONL parsing

Change:
- No more client-side Gemini summarization (moves to backend Extractor)
- POST target: `/hook/post_turn` (was `/store`)
- Payload shape: `{agent, project, session_id, turn: {user, assistant, tool_calls}}` (was flat `{content}`)
- Parse the JSONL delta into structured `turn` object before posting (user + assistant + tool calls separated)

`GOOGLE_API_KEY` migrates from client-side env var to Brain Docker container env var.

### Updated `.claude/settings.json`

```json
{
  "permissions": { /* unchanged */ },
  "statusLine": { /* unchanged */ },
  "hooks": {
    "SessionStart": [
      {"matcher": "", "hooks": [{
        "type": "command",
        "command": "python \"$CLAUDE_PROJECT_DIR/scripts/brain_wake_up.py\"",
        "timeout": 5
      }]}
    ],
    "Stop": [
      {"matcher": "", "hooks": [{
        "type": "command",
        "command": "python \"$CLAUDE_PROJECT_DIR/scripts/brain_post_turn.py\"",
        "timeout": 30
      }]}
    ]
  }
}
```

### Migration from current `brain_hook.py`

Breaking changes (intentional, clean cut):
- Script renamed → `.claude/settings.json` updated
- Payload format changed → old script no longer compatible with new backend
- Gemini Flash call removed from client → moves to backend

Preserved:
- Byte-offset tracking files (`data/brain_hook_state/*.offset`) — same format, same location
- Pending queue file (`data/brain_pending_local.jsonl`) — same schema, drain reroutes to new endpoint

Cutover timing: Phase 2b MVP PR landing. No period of dual-mode support — Brain is an early project with one user, clean cut is cheaper than maintaining a compat shim.

## Section 4 — Migration + dogfood + success

### Implementation sequencing

1. **Backend first**: Extractor + `/hook/wake_up` + `/hook/post_turn` + `BrainStore.search_by_tag` + schema extensions + all tests.
2. **Adapter scripts**: `brain_wake_up.py` + `brain_post_turn.py`, with subprocess-based tests that validate stdin/stdout contract.
3. **Settings + seed**: update `.claude/settings.json`, seed initial identity/preference memories via `brain_save_now.py`.
4. **Deploy**: Docker rebuild with `GOOGLE_API_KEY` env var. Verify `/health` + `/hook/wake_up` returns non-empty for `agent=brain-dev`.
5. **Cutover**: delete legacy `brain_hook.py`, clean cut.

### Dogfood plan

**Primary target: Brain consumes Brain.** Every Claude Code session on the Brain repo uses the new hooks. If the cerveau doesn't help build the cerveau, no one else should use it.

**Initial seed before cutover** — user stores ~6-10 memories via `brain_save_now.py`:
- 3-5 `tag=identity` (Arthur's persona, French-blunt style, communication preferences)
- 3-5 `tag=preference` (Docker safety invariants, no `--no-verify`, issue-first workflow, doc structure)

These seeds are both the wake_up input AND the cerveau-parfait demo: every new session, Claude Code sees these rules without manual re-typing in `CLAUDE.md`.

**Secondary target (post-7-days)**: Money (user flagged this earlier — pointing Money's `BRAIN_URL` to the new container). Marcel after that.

### Success criteria

**Hard criteria (measurable, gate the Phase 2b merge)**:

- [ ] `/hook/wake_up` p95 latency < 500ms across 100 invocations
- [ ] `/hook/post_turn` p95 latency < 2s (extraction included) across 100 invocations
- [ ] Zero CC sessions blocked by hook timeout (absolute tolerance)
- [ ] Backend tests 100% green (new + existing), ruff clean
- [ ] Adapter tests 100% green (new subprocess tests + existing)
- [ ] ≥ 50 Brain sessions dogfooded without hook-related crash
- [ ] Events log contains coherent `hook_wake_up` + `hook_post_turn` records (no silent drops)

**Soft criteria (qualitative signal, guide iteration, don't gate merge)**:

- User subjectively confirms: "Brain knows who I am at session start, I no longer re-explain my preferences"
- Extracted memories post-session have coherent types, no massive duplicates, atomic content (not 2k-token blobs)
- Brain growth rate: ~5-20 memories per active session. Not 200 (over-extraction signal), not 0 (under-extraction signal).

### Observability during dogfood

Before the frontend lands (Phase 4), CLI-based observability:

```bash
curl localhost:8621/events/timeline                    # activity over time
curl "localhost:8621/events?limit=50"                  # recent events
curl "localhost:8621/search?query=X&agent=brain-dev"   # inspect what's stored
curl localhost:8621/stats                              # totals by agent + type
```

When extraction quality is poor (too many memories, vague, duplicated) — iterate on the Extractor prompt. All logic centralized backend-side means the feedback loop is fast: change prompt → rebuild Docker → next session uses new prompt.

### Exit criteria for Phase 2b MVP

Phase 2b MVP is "done" when:

1. All hard success criteria above are met
2. Legacy `brain_hook.py` is deleted
3. Brain's `.claude/settings.json` wires the two new scripts
4. ADR `docs/decisions/0002-hook-architecture.md` is written, capturing the durable design choices from this spec
5. Phase 2b checkboxes in `README.md` Roadmap are all checked

Deferred items (bootstrap flow, other hooks, L2/L3, multi-platform) stay unchecked — each becomes its own sub-project and its own spec.

## Decisions locked

1. **Transport: HTTP POST + JSON.** Not MCP. Hooks are lifecycle-driven by the platform, not model-invoked tool calls. HTTP is the natural fit.
2. **MVP hooks: `wake_up` + `post_turn` only.** Four other hooks deferred.
3. **L0/L1 only at wake_up.** Hardcoded via tags. L2/L3 deferred.
4. **Ingestion: LLM extract (option B).** Not verbatim blob (A). Not hybrid (C).
5. **Default extractor: Gemini Flash 2.5.** Free tier, reuses existing `GOOGLE_API_KEY`. Configurable via env var.
6. **L0/L1 identification: by tag** (`tag="identity"`, `tag="preference"`). Not by `memory_type`, not by `level`.
7. **Schema extensions: `tags` + `confidence`.** Added via existing `RESERVED_META_KEYS` passthrough. No migration needed.
8. **Agent scoping: by `cwd` basename, with collision fallback.** Primary: `basename(cwd)` lowercased. If the basename is generic (e.g. `"docker"`, `"src"`), fall back to `basename(parent) + "-" + basename(cwd)`. Full path hash is the last-resort tiebreaker. Documented in the implementation plan — spec requires that two different projects **must never** share an `agent_id`.
9. **Failure mode: graceful degradation absolute.** No hook error ever blocks a CC session.
10. **Clean cut migration.** No compat shims. One user, one consumer — delete old code.
11. **Primary dogfood: Brain consumes Brain.** Meta but necessary. 7-day stability before extending to Money/Marcel.

## Open questions (acknowledged, deferred)

- Exact shape of the Extractor Gemini prompt — iterate in implementation
- Precise `agent_id` derivation if `cwd` is ambiguous (symlinks, network mounts) — handle case by case
- Whether `search_by_tag` should use ChromaDB's native `$contains` operator or adapter-side filtering — determined by testing during implementation
- Token budget adjustment if 500 tokens proves too tight or too loose in practice — revisit after week-1 dogfood

## References

- `docs/decisions/0001-project-meta-conventions.md` — issue-first workflow, doc structure rules, agent cadence
- `docs/improvements/README.md` — P0 dynamic types, P2 L0/L1/L2/L3 layering (this spec partially addresses P2)
- `README.md` Phase 2b — roadmap entry for hook architecture
- `scripts/brain_hook.py` — legacy Stop hook being superseded
- `.claude/settings.json` — current hook wiring
- `backend/src/brain/store.py` — `RESERVED_META_KEYS` (from fix #1), gate integration point

---

## Update 2026-04-28

"L2 topic-triggered retrieval" and "L3 deep semantic search" moved from Out-of-scope to In-scope.

- **L2** implemented in `backend/src/brain/hook.py:WakeUpHandler` — topic-triggered semantic retrieval at `wake_up`. See [2026-04-28-l2-a-backend-design.md](2026-04-28-l2-a-backend-design.md) and [ADR 0003](../decisions/0003-l2-l3-design.md).
- **L3** clarified: `brain_search` MCP tool already implements L3 (explicit model-invoked deep semantic search). No new code. See [ADR 0003](../decisions/0003-l2-l3-design.md).
