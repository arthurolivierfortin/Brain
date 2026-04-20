---
id: 0002
title: Hook architecture — MVP shape, contract, L0/L1 by tags
status: accepted
date: 2026-04-19
supersedes:
superseded_by:
---

## Context

Brain needed a way to *automatically* enrich agent sessions with memory — not via tool calls the model has to remember to use, but via lifecycle hooks the platform fires on its own. The first concrete platform is Claude Code, whose `SessionStart` and `Stop` hooks map naturally to Brain's needs. The full design space (6 hook points, L0–L3 layering, dynamic types, multi-platform adapters) was too large for one increment — this ADR captures the MVP shape we locked for Phase 2b.

## Decision

**Two hooks, HTTP-JSON contract, L0/L1 by tags, LLM extraction on ingest:**

- `POST /hook/wake_up` — retrieval-side, returns `identity` and `preference`-tagged memories formatted for system-prompt injection, 500-token budget
- `POST /hook/post_turn` — ingestion-side, invokes an `Extractor` (Gemini Flash default) to produce N atomic `ExtractedMemory` objects, runs them through the existing gate, stores them
- Platform-agnostic JSON contract; first implementer is Claude Code via `scripts/brain_wake_up.py` + `scripts/brain_post_turn.py`
- L0/L1 identified by `tag="identity"` and `tag="preference"` (substring match, enables namespacing like `identity-core`)
- Memory schema extended with `tags` (comma-separated string) and `confidence` (float), both passed through existing `RESERVED_META_KEYS` passthrough — no migration
- Graceful degradation absolute: no hook error blocks a session

## Alternatives considered

**A. MCP tool interface instead of HTTP hooks**
- Rejected: MCP tools are model-invoked. Hooks are platform-lifecycle-invoked. Different mechanism — HTTP is the natural fit.

**B. Verbatim session-blob ingestion (current `brain_hook.py` approach)**
- Rejected: incompatible with "structure parfaite" goal. Blobs are noisy and hard to retrieve atomically. Zep/Graphiti's win over mem0 is LLM extraction.

**C. Hybrid (blob + extracted facts)**
- Rejected for MVP: over-engineering. Two systems to maintain, two decay policies. Can add raw-fallback later if B misses too much; in fact, failure path already stores a raw-fallback memory when extraction fails.

**D. `memory_type="identity"` / `memory_type="preference"` for L0/L1**
- Rejected: would conflict with the P0 "dynamic memory types" direction. `memory_type` stays a free-form string. L0/L1 is orthogonal — better served by tags.

**E. Build wake_up + pre_turn + post_turn + post_tool_use + session_end all at once**
- Rejected: scope too large for one increment. The other four hooks are deferred; their contract slots are pre-defined so they can land incrementally.

**F. Full L0/L1/L2/L3 layering in MVP**
- Rejected: L2 (topic-triggered) requires scoring the latest user message against memory embeddings on every turn — a tight latency budget + a new retrieval path. Defer. L0/L1 alone cover the "always-on identity" vision.

## Consequences

**Gains**
- Claude Code sessions wake up with Brain's context without any tool call
- Every turn's atomic facts become retrievable memories
- Contract is platform-agnostic — Cursor/Codex adapters cost only the client-side script when they land
- Existing `brain_hook.py` machinery (byte offsets, pending queue) survives into the new adapter
- `Extractor` Protocol isolates the LLM choice; switching from Gemini Flash to Haiku or Ollama is a one-line config change later

**Costs**
- Gemini Flash API dependency for ingestion quality (cheap — free tier, but a dependency)
- `GOOGLE_API_KEY` now Docker-side env var, not just client-side
- `/hook/post_turn` adds ~850ms per turn (extraction) — acceptable within the 30s Stop-hook timeout
- MVP has no topic-triggered retrieval, so L2-level needs aren't served yet (and sessions that drift off-topic won't get fresh relevance)

**Reversal cost**
- Low for the contract (HTTP + JSON, backward-compat easy)
- Higher for the tag-based L0/L1 scheme if we ever decide to switch to `memory_type`-based (would need a re-tagging pass)
- None for the schema extensions — adding unused fields is cheap, removing them requires a migration

## Follow-up actions

- [ ] Dogfood ≥ 7 days on Brain sessions, record metrics per `docs/runbooks/phase2b-dogfood.md`
- [ ] After dogfood merge: open follow-up issues for each deferred item in README Phase 2b
- [ ] When agent-loop benchmarks land (Phase 5b+), measure delta: Claude Haiku + Brain hooks vs Claude Haiku alone
