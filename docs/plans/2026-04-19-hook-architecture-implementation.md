# Phase 2b Hook Architecture MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire agnostic `wake_up` and `post_turn` hooks so Claude Code sessions automatically receive L0/L1 context at start and structured memories flow into Brain at turn end — no tool-use required.

**Architecture:** Backend module `brain.hook` owns the handlers + Gemini Flash extractor. Thin HTTP routes in `server.py` delegate to them. Two Python hook scripts sit in `scripts/` and talk to Brain via `$BRAIN_URL`. Memory schema extends via existing `RESERVED_META_KEYS` passthrough — no migration.

**Tech Stack:** Python 3.12 + ChromaDB (backend), httpx (HTTP + Gemini API), Gemini Flash 2.5 (default extractor), Claude Code SessionStart/Stop hooks (first implementer).

**Spec:** [`docs/specs/2026-04-19-hook-architecture-design.md`](../specs/2026-04-19-hook-architecture-design.md)

---

## File structure

### Create
- `backend/src/brain/hook.py` — dataclasses, Extractor Protocol, GeminiFlashExtractor, WakeUpHandler, PostTurnHandler
- `backend/tests/test_brain/test_hook_dataclasses.py` — dataclass construction
- `backend/tests/test_brain/test_hook_extractor.py` — GeminiFlashExtractor unit tests
- `backend/tests/test_brain/test_hook_wake_up.py` — WakeUpHandler tests
- `backend/tests/test_brain/test_hook_post_turn.py` — PostTurnHandler tests
- `backend/tests/test_brain/test_hook_http.py` — HTTP route integration tests
- `scripts/brain_wake_up.py` — Claude Code SessionStart adapter
- `scripts/brain_post_turn.py` — Claude Code Stop adapter (replaces brain_hook.py)
- `scripts/seed_brain.py` — one-off bootstrap of initial identity/preference memories
- `scripts/tests/__init__.py`
- `scripts/tests/conftest.py` — sys.path shim for scripts/
- `scripts/tests/test_brain_wake_up.py`
- `scripts/tests/test_brain_post_turn.py`
- `docs/decisions/0002-hook-architecture.md` — ADR capturing durable decisions

### Modify
- `backend/src/brain/store.py` — add `BrainStore.search_by_tag()`
- `backend/src/brain/server.py` — register `/hook/wake_up`, `/hook/post_turn` routes + `_get_extractor` helper
- `backend/tests/test_brain/test_store_chromadb.py` — add tests for `search_by_tag`
- `docker/compose.yml` — pass `GOOGLE_API_KEY` env var into brain container
- `.claude/settings.json` — add SessionStart hook, update Stop hook script name

### Delete
- `scripts/brain_hook.py` — legacy (superseded by `brain_post_turn.py`)

---

## Dependency graph

```
A1 (dataclasses) ─┬─> B1 (extractor) ─┐
                  ├─> C1 (wake_up)    ├─> D1/D2 (HTTP) ─> F1/F2 (adapters) ─> G (integration)
A3 (search_by_tag)┘   C2 (post_turn) ──┘
                       ↑
A2 (Extractor protocol) included in A1

E1 (docker env) is parallel with D, required before F runs end-to-end
```

**Parallelizable batches:** A1/A2/A3 can run in parallel (different files). B1/C1/C2 can run in parallel once A is done. D1/D2/E1 can run in parallel. F1/F2 can run in parallel. G tasks are sequential.

**Total: 16 tasks.** Expected: ~1 working day for an experienced implementer following TDD.

---

## Batch A — Foundation

### Task A1: Dataclasses + Extractor Protocol

**Files:**
- Create: `backend/src/brain/hook.py`
- Create: `backend/tests/test_brain/test_hook_dataclasses.py`

- [ ] **Step 1: Write the failing test**

File `backend/tests/test_brain/test_hook_dataclasses.py`:
```python
"""Tests for hook dataclasses + Extractor protocol."""
from __future__ import annotations


def test_turn_defaults_empty_tool_calls() -> None:
    from brain.hook import Turn
    t = Turn(user="hi", assistant="hey")
    assert t.user == "hi"
    assert t.assistant == "hey"
    assert t.tool_calls == []


def test_hook_request_has_expected_fields() -> None:
    from brain.hook import HookRequest
    r = HookRequest(agent="a", project="/p", session_id="s")
    assert (r.agent, r.project, r.session_id) == ("a", "/p", "s")


def test_wake_up_response_has_expected_fields() -> None:
    from brain.hook import WakeUpResponse
    r = WakeUpResponse(context="x", layers_loaded={"L0": 1}, tokens_approx=42, duration_ms=7)
    assert r.context == "x"
    assert r.layers_loaded == {"L0": 1}
    assert r.tokens_approx == 42
    assert r.duration_ms == 7


def test_extracted_memory_has_expected_fields() -> None:
    from brain.hook import ExtractedMemory
    m = ExtractedMemory(content="c", type="fact", tags=["a", "b"], confidence=0.9)
    assert m.content == "c"
    assert m.type == "fact"
    assert m.tags == ["a", "b"]
    assert m.confidence == 0.9


def test_post_turn_response_has_expected_fields() -> None:
    from brain.hook import PostTurnResponse
    r = PostTurnResponse(extracted=[], rejected_by_gate=0, extraction_cost_usd=0.0, extraction_ms=5)
    assert r.extracted == []
    assert r.rejected_by_gate == 0
    assert r.extraction_cost_usd == 0.0
    assert r.extraction_ms == 5


def test_extractor_protocol_structurally_typed() -> None:
    from brain.hook import Extractor, ExtractedMemory, Turn

    class _MiniExtractor:
        def extract(self, turn: Turn) -> list[ExtractedMemory]:
            return []

    ext: Extractor = _MiniExtractor()
    assert ext.extract(Turn(user="", assistant="")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_dataclasses.py -v`
Expected: `ModuleNotFoundError: No module named 'brain.hook'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/src/brain/hook.py`:
```python
"""Hook architecture — Extractor Protocol, dataclasses, handlers.

See docs/specs/2026-04-19-hook-architecture-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Turn:
    user: str
    assistant: str
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class HookRequest:
    agent: str
    project: str
    session_id: str


@dataclass
class WakeUpResponse:
    context: str
    layers_loaded: dict[str, int]
    tokens_approx: int
    duration_ms: int


@dataclass
class ExtractedMemory:
    content: str
    type: str
    tags: list[str]
    confidence: float


@dataclass
class PostTurnResponse:
    extracted: list[dict]
    rejected_by_gate: int
    extraction_cost_usd: float
    extraction_ms: int


class Extractor(Protocol):
    def extract(self, turn: Turn) -> list[ExtractedMemory]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_dataclasses.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add backend/src/brain/hook.py backend/tests/test_brain/test_hook_dataclasses.py
git commit -m "$(cat <<'EOF'
🧠 Feature: hook dataclasses + Extractor Protocol

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task A3: BrainStore.search_by_tag()

**Files:**
- Modify: `backend/src/brain/store.py` (append new method after `related()`)
- Modify: `backend/tests/test_brain/test_store_chromadb.py` (append new test class)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_brain/test_store_chromadb.py` (after `class TestReset`):
```python
class TestSearchByTag:
    """search_by_tag — powers wake_up L0/L1 retrieval."""

    def test_returns_memories_with_matching_tag(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("I'm Arthur, French-first", agent="brain-dev",
                    memory_type="context",
                    metadata={"tags": "identity,persona"}, skip_gate=True)
        store.store("Unrelated note", agent="brain-dev",
                    memory_type="context",
                    metadata={"tags": "bug"}, skip_gate=True)
        results = store.search_by_tag("identity", agent="brain-dev")
        assert len(results) == 1
        assert "Arthur" in results[0]["content"]

    def test_scopes_to_agent(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("A1", agent="brain-dev", memory_type="context",
                    metadata={"tags": "identity"}, skip_gate=True)
        store.store("A2", agent="money-dev", memory_type="context",
                    metadata={"tags": "identity"}, skip_gate=True)
        results = store.search_by_tag("identity", agent="brain-dev")
        assert len(results) == 1
        assert results[0]["content"] == "A1"

    def test_respects_top_k(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(7):
            store.store(f"pref {i}", agent="t", memory_type="context",
                        metadata={"tags": "preference"}, skip_gate=True)
        results = store.search_by_tag("preference", agent="t", top_k=3)
        assert len(results) == 3

    def test_orders_by_access_count_desc(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        r_low = store.store("low-access", agent="t", memory_type="context",
                             metadata={"tags": "identity"}, skip_gate=True)
        r_high = store.store("high-access", agent="t", memory_type="context",
                              metadata={"tags": "identity"}, skip_gate=True)
        # Manually bump access_count on r_high
        raw = store._collection.get(ids=[r_high["id"]], include=["metadatas"])
        meta = raw["metadatas"][0] or {}
        store._collection.update(ids=[r_high["id"]],
                                 metadatas=[{**meta, "access_count": 10}])
        results = store.search_by_tag("identity", agent="t")
        assert results[0]["content"] == "high-access"
        assert results[1]["content"] == "low-access"

    def test_substring_matches_namespaced_tag(self, tmp_path: Path):
        """identity-core should match a search for identity (tag namespacing)."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("namespaced", agent="t", memory_type="context",
                    metadata={"tags": "identity-core,persona"}, skip_gate=True)
        results = store.search_by_tag("identity", agent="t")
        assert len(results) == 1

    def test_empty_collection_returns_empty(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        assert store.search_by_tag("identity", agent="t") == []

    def test_no_match_returns_empty(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("content", agent="t", memory_type="context",
                    metadata={"tags": "bug"}, skip_gate=True)
        assert store.search_by_tag("identity", agent="t") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_store_chromadb.py::TestSearchByTag -v`
Expected: 7 failures, `AttributeError: 'BrainStore' object has no attribute 'search_by_tag'`

- [ ] **Step 3: Write minimal implementation**

In `backend/src/brain/store.py`, add this method immediately after the `related()` method (before `forget()`):

```python
    def search_by_tag(self, tag: str, agent: str, top_k: int = 5) -> list[dict]:
        """Return memories whose tags contain `tag`, scoped to agent, ordered by access_count desc.

        Used by the hook `wake_up` handler to fetch L0 (identity) and L1 (preference)
        memories. Substring matching on tags enables namespacing (identity-core matches
        identity). See docs/specs/2026-04-19-hook-architecture-design.md.
        """
        if self._collection.count() == 0:
            return []
        results = self._collection.get(
            where={"agent": {"$eq": agent}},
            include=["documents", "metadatas"],
        )
        ids = results.get("ids") or []
        docs = results.get("documents") or []
        metas = results.get("metadatas") or []
        entries: list[dict] = []
        for i, entry_id in enumerate(ids):
            meta = metas[i] or {}
            meta_tags = str(meta.get("tags", ""))
            if tag not in meta_tags:
                continue
            entries.append({
                "id": entry_id,
                "content": docs[i] if i < len(docs) else "",
                "tags": meta_tags,
                "access_count": meta.get("access_count", 0),
                "memory_type": meta.get("memory_type", ""),
                "agent": meta.get("agent", ""),
                "confidence": meta.get("confidence", 1.0),
            })
        entries.sort(key=lambda e: e["access_count"], reverse=True)
        return entries[:top_k]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_store_chromadb.py::TestSearchByTag -v`
Expected: `7 passed`

Also run full backend suite to check no regression:
Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest -q`
Expected: previous count + 7 new = all green.

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add backend/src/brain/store.py backend/tests/test_brain/test_store_chromadb.py
git commit -m "$(cat <<'EOF'
🧠 Feature: BrainStore.search_by_tag() for wake_up L0/L1 retrieval

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Batch B — Extractor

### Task B1: GeminiFlashExtractor

**Files:**
- Modify: `backend/src/brain/hook.py` (append class + prompt)
- Create: `backend/tests/test_brain/test_hook_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_brain/test_hook_extractor.py`:
```python
"""Unit tests for GeminiFlashExtractor — httpx mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brain.hook import ExtractedMemory, GeminiFlashExtractor, Turn


def _gemini_response(memories: list[dict]) -> MagicMock:
    text = json.dumps({"memories": memories})
    resp = MagicMock()
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
    }
    resp.raise_for_status = MagicMock()
    return resp


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GeminiFlashExtractor()


def test_parses_memories_from_response(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.return_value = _gemini_response([
        {"content": "User prefers French", "type": "preference",
         "tags": ["preference", "communication"], "confidence": 0.95},
        {"content": "Fixed bug #12", "type": "bug-fix",
         "tags": ["backend"], "confidence": 1.0},
    ])
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    turn = Turn(user="u", assistant="a", tool_calls=[])
    memories = ext.extract(turn)
    assert len(memories) == 2
    assert memories[0] == ExtractedMemory(
        content="User prefers French", type="preference",
        tags=["preference", "communication"], confidence=0.95,
    )


def test_returns_empty_on_http_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.side_effect = RuntimeError("boom")
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    assert ext.extract(Turn(user="u", assistant="a")) == []


def test_returns_empty_on_malformed_json(monkeypatch):
    fake_client = MagicMock()
    broken = MagicMock()
    broken.json.return_value = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
    broken.raise_for_status = MagicMock()
    fake_client.post.return_value = broken
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    assert ext.extract(Turn(user="u", assistant="a")) == []


def test_skips_malformed_memory_entries(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.return_value = _gemini_response([
        {"content": "ok", "type": "fact", "tags": [], "confidence": 0.8},
        {"type": "fact", "tags": [], "confidence": 0.8},  # missing content
        "not a dict",
    ])
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    memories = ext.extract(Turn(user="u", assistant="a"))
    assert len(memories) == 1
    assert memories[0].content == "ok"


def test_prompt_includes_user_assistant_and_tool_calls(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.return_value = _gemini_response([])
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    turn = Turn(
        user="fix the bug",
        assistant="done",
        tool_calls=[{"name": "Bash", "input": "pytest"}],
    )
    ext.extract(turn)
    call_kwargs = fake_client.post.call_args.kwargs
    body = call_kwargs["json"]
    prompt_text = body["contents"][0]["parts"][0]["text"]
    assert "USER: fix the bug" in prompt_text
    assert "ASSISTANT: done" in prompt_text
    assert "TOOL: Bash" in prompt_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_extractor.py -v`
Expected: `ImportError: cannot import name 'GeminiFlashExtractor' from 'brain.hook'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/src/brain/hook.py`:
```python
import json
import os
from typing import Any

import httpx


class GeminiFlashExtractor:
    """Default Extractor — uses Google's Gemini Flash 2.5 free tier.

    Requires GOOGLE_API_KEY env var. Returns [] on any failure; caller
    (PostTurnHandler) handles fallback to raw-blob storage.
    """

    SYSTEM_PROMPT = (
        "Extract structured memories from a development conversation turn. "
        "Output ONLY a JSON object with shape: "
        '{"memories": [{"content": "...", "type": "...", "tags": [...], "confidence": 0.0}, ...]}. '
        "Each memory must be ATOMIC (one fact, decision, or preference — not a summary blob). "
        "Types are open strings (fact, decision, preference, bug, lesson, code-change, tool-use, etc.). "
        "Use tag 'identity' for persona/role/communication-style memories. "
        "Use tag 'preference' for durable user rules. "
        "Other tags describe the topic domain (backend, testing, docker, etc.). "
        "Confidence is 0.0-1.0. Skip memories with confidence < 0.5 rather than emitting noise."
    )

    _API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        timeout: float = 30.0,
        _client: Any = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError("GOOGLE_API_KEY not set — cannot initialize GeminiFlashExtractor")
        self._api_key = key
        self._model = model
        self._client = _client if _client is not None else httpx.Client(timeout=timeout)

    def extract(self, turn: Turn) -> list[ExtractedMemory]:
        prompt = self._build_prompt(turn)
        url = f"{self._API_URL}/{self._model}:generateContent?key={self._api_key}"
        try:
            resp = self._client.post(url, json={
                "systemInstruction": {"parts": [{"text": self.SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 2048,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
            })
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except Exception:
            return []
        out: list[ExtractedMemory] = []
        for mem in parsed.get("memories", []):
            if not isinstance(mem, dict):
                continue
            try:
                out.append(ExtractedMemory(
                    content=mem["content"],
                    type=mem.get("type", "context"),
                    tags=list(mem.get("tags", [])),
                    confidence=float(mem.get("confidence", 1.0)),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def _build_prompt(self, turn: Turn) -> str:
        parts = [f"USER: {turn.user}", f"ASSISTANT: {turn.assistant}"]
        for tc in turn.tool_calls or []:
            name = tc.get("name", "")
            tool_input = json.dumps(tc.get("input", ""))[:200]
            parts.append(f"TOOL: {name} input={tool_input}")
        return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_extractor.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add backend/src/brain/hook.py backend/tests/test_brain/test_hook_extractor.py
git commit -m "$(cat <<'EOF'
🧠 Feature: GeminiFlashExtractor (default extractor for post_turn hook)

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Batch C — Handlers

### Task C1: WakeUpHandler

**Files:**
- Modify: `backend/src/brain/hook.py` (append class)
- Create: `backend/tests/test_brain/test_hook_wake_up.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_brain/test_hook_wake_up.py`:
```python
"""WakeUpHandler tests — uses real BrainStore with in-memory ChromaDB."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.hook import HookRequest, WakeUpHandler  # noqa: E402
from brain.store import BrainStore  # noqa: E402


def _seed_memories(store, agent="brain-dev"):
    store.store("Arthur, French-first, blunt, no glazing",
                agent=agent, memory_type="context",
                metadata={"tags": "identity,persona"}, skip_gate=True)
    store.store("Always use the 🧠 emoji for new features in commit messages",
                agent=agent, memory_type="context",
                metadata={"tags": "preference,git"}, skip_gate=True)
    store.store("An unrelated bug memory",
                agent=agent, memory_type="bug",
                metadata={"tags": "bug"}, skip_gate=True)


def test_empty_store_returns_empty_context(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert resp.context == ""
    assert resp.layers_loaded == {"L0": 0, "L1": 0}


def test_populates_identity_and_preference_sections(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    _seed_memories(store)
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert "## Identity" in resp.context
    assert "Arthur" in resp.context
    assert "## Preferences" in resp.context
    assert "🧠" in resp.context
    assert resp.layers_loaded == {"L0": 1, "L1": 1}
    assert "bug" not in resp.context.lower()


def test_scopes_to_agent(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    _seed_memories(store, agent="brain-dev")
    _seed_memories(store, agent="money-dev")
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert resp.layers_loaded == {"L0": 1, "L1": 1}


def test_budget_caps_output_tokens(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    # Seed enough memories to blow a 500-token budget
    for i in range(30):
        store.store("x" * 400, agent="brain-dev", memory_type="context",
                    metadata={"tags": "preference"}, skip_gate=True)
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert resp.tokens_approx <= WakeUpHandler.BUDGET_TOKENS


def test_duration_ms_is_reported(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="x", project="/", session_id="s"))
    assert resp.duration_ms >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_wake_up.py -v`
Expected: `ImportError: cannot import name 'WakeUpHandler' from 'brain.hook'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/src/brain/hook.py`:
```python
import time


class WakeUpHandler:
    """Selects L0 + L1 memories and formats them as a system-prompt injection."""

    L0_TAG = "identity"
    L1_TAG = "preference"
    BUDGET_TOKENS = 500

    def __init__(self, store: Any) -> None:
        self._store = store

    def handle(self, req: HookRequest) -> WakeUpResponse:
        t0 = time.monotonic()
        identity = self._store.search_by_tag(self.L0_TAG, agent=req.agent, top_k=5)
        prefs = self._store.search_by_tag(self.L1_TAG, agent=req.agent, top_k=10)

        context = self._format(identity, prefs)
        # Drop least-accessed prefs first, then identity, to respect the budget.
        while self._tokens(context) > self.BUDGET_TOKENS and (identity or prefs):
            if prefs:
                prefs.pop()
            else:
                identity.pop()
            context = self._format(identity, prefs)

        duration_ms = int((time.monotonic() - t0) * 1000)
        return WakeUpResponse(
            context=context,
            layers_loaded={"L0": len(identity), "L1": len(prefs)},
            tokens_approx=self._tokens(context),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _format(identity: list[dict], prefs: list[dict]) -> str:
        lines: list[str] = []
        if identity:
            lines.append("## Identity")
            for m in identity:
                lines.append(f"- {m['content']}")
        if prefs:
            if identity:
                lines.append("")
            lines.append("## Preferences")
            for m in prefs:
                lines.append(f"- {m['content']}")
        return "\n".join(lines)

    @staticmethod
    def _tokens(text: str) -> int:
        return len(text) // 4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_wake_up.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add backend/src/brain/hook.py backend/tests/test_brain/test_hook_wake_up.py
git commit -m "$(cat <<'EOF'
🧠 Feature: WakeUpHandler — L0/L1 selection with 500-token budget

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task C2: PostTurnHandler

**Files:**
- Modify: `backend/src/brain/hook.py` (append class)
- Create: `backend/tests/test_brain/test_hook_post_turn.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_brain/test_hook_post_turn.py`:
```python
"""PostTurnHandler tests — extractor mocked, store + events real."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.events import EventLog  # noqa: E402
from brain.hook import ExtractedMemory, HookRequest, PostTurnHandler, Turn  # noqa: E402
from brain.store import BrainStore  # noqa: E402


def _new(tmp_path: Path):
    events = EventLog(path=tmp_path / "events.jsonl")
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"), event_log=events)
    return store, events


def test_happy_path_stores_all_extracted_memories(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = [
        ExtractedMemory(content="fact 1", type="fact", tags=["backend"], confidence=0.9),
        ExtractedMemory(content="fact 2", type="decision", tags=["testing"], confidence=1.0),
    ]
    handler = PostTurnHandler(store, extractor, events)
    resp = handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    assert len(resp.extracted) == 2
    assert resp.rejected_by_gate == 0
    # Verify the store actually has them
    search = store.search("fact", agent="t")
    assert len(search) == 2


def test_extractor_empty_triggers_raw_fallback(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = []
    handler = PostTurnHandler(store, extractor, events)
    resp = handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="my question", assistant="the answer"),
    )
    assert len(resp.extracted) == 1
    assert resp.extracted[0]["type"] == "raw-fallback"
    # Content combines user + assistant
    search = store.search("my question", agent="t")
    assert len(search) == 1


def test_extractor_raises_triggers_raw_fallback(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.side_effect = RuntimeError("gemini down")
    handler = PostTurnHandler(store, extractor, events)
    resp = handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    assert len(resp.extracted) == 1
    assert resp.extracted[0]["type"] == "raw-fallback"


def test_tags_are_sanitized(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = [
        ExtractedMemory(content="c", type="fact",
                        tags=["With Space", "comma,tag", "UPPER"], confidence=0.9),
    ]
    handler = PostTurnHandler(store, extractor, events)
    handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    # Inspect persisted metadata
    raw = store._collection.get(include=["metadatas"])
    tags = raw["metadatas"][0].get("tags", "")
    assert "with-space" in tags
    assert "comma-tag" in tags
    assert "upper" in tags
    assert " " not in tags


def test_extraction_ms_is_reported(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = []
    handler = PostTurnHandler(store, extractor, events)
    resp = handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    assert resp.extraction_ms >= 0


def test_hook_post_turn_event_logged(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = [
        ExtractedMemory(content="c", type="fact", tags=[], confidence=0.9),
    ]
    handler = PostTurnHandler(store, extractor, events)
    handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    recent = events.recent(limit=10)
    hook_events = [e for e in recent if e.get("event_type") == "hook_post_turn"]
    assert len(hook_events) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_post_turn.py -v`
Expected: `ImportError: cannot import name 'PostTurnHandler' from 'brain.hook'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/src/brain/hook.py`:
```python
import re


class PostTurnHandler:
    """Extracts, gates, stores. Fallback to raw-blob if extractor returns [] or raises."""

    def __init__(self, store: Any, extractor: Extractor, events: Any) -> None:
        self._store = store
        self._extractor = extractor
        self._events = events

    def handle(self, req: HookRequest, turn: Turn) -> PostTurnResponse:
        t0 = time.monotonic()
        try:
            memories = self._extractor.extract(turn)
        except Exception:
            memories = []
        extraction_ms = int((time.monotonic() - t0) * 1000)

        extracted: list[dict] = []
        rejected = 0

        if not memories:
            raw = self._fallback_content(turn)
            if raw:
                result = self._store.store(
                    content=raw,
                    agent=req.agent,
                    memory_type="raw-fallback",
                    metadata={
                        "tags": "",
                        "confidence": 0.3,
                        "session_id": req.session_id,
                        "project": req.project,
                    },
                    skip_gate=False,
                )
                if result:
                    extracted.append({
                        "id": result.get("id", ""),
                        "type": "raw-fallback",
                        "content": raw[:200],
                        "tags": [],
                    })
                else:
                    rejected += 1
        else:
            for em in memories:
                sanitized = [self._sanitize_tag(t) for t in em.tags]
                result = self._store.store(
                    content=em.content,
                    agent=req.agent,
                    memory_type=em.type,
                    metadata={
                        "tags": ",".join(t for t in sanitized if t),
                        "confidence": em.confidence,
                        "session_id": req.session_id,
                        "project": req.project,
                    },
                    skip_gate=False,
                )
                if result:
                    extracted.append({
                        "id": result.get("id", ""),
                        "type": em.type,
                        "content": em.content,
                        "tags": sanitized,
                    })
                else:
                    rejected += 1

        self._events.log(
            event_type="hook_post_turn",
            agent=req.agent,
            metadata={
                "extracted_count": len(extracted),
                "rejected_count": rejected,
                "extraction_ms": extraction_ms,
            },
        )
        return PostTurnResponse(
            extracted=extracted,
            rejected_by_gate=rejected,
            extraction_cost_usd=0.0,
            extraction_ms=extraction_ms,
        )

    @staticmethod
    def _fallback_content(turn: Turn) -> str:
        parts = []
        if turn.user:
            parts.append(f"USER: {turn.user}")
        if turn.assistant:
            parts.append(f"ASSISTANT: {turn.assistant}")
        return "\n".join(parts)[:2000]

    @staticmethod
    def _sanitize_tag(tag: str) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", tag.lower()).strip("-")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_post_turn.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add backend/src/brain/hook.py backend/tests/test_brain/test_hook_post_turn.py
git commit -m "$(cat <<'EOF'
🧠 Feature: PostTurnHandler — extract, gate, store + raw-fallback

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Batch D — HTTP endpoints

### Task D1: POST /hook/wake_up route

**Files:**
- Modify: `backend/src/brain/server.py` (add route + helper)
- Create: `backend/tests/test_brain/test_hook_http.py` (also covers D2)

- [ ] **Step 1: Write the failing tests** (covers both D1 and D2)

Create `backend/tests/test_brain/test_hook_http.py`:
```python
"""HTTP route integration tests — uses the real HTTP handler against mocked backend state."""
from __future__ import annotations

import json
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

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


def test_wake_up_returns_empty_context_for_fresh_brain(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/wake_up", json={
            "agent": "brain-dev", "project": "/", "session_id": "s"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["context"] == ""
        assert body["layers_loaded"] == {"L0": 0, "L1": 0}
    finally:
        srv.shutdown()


def test_wake_up_missing_agent_returns_400(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/wake_up", json={"project": "/", "session_id": "s"})
        assert resp.status_code == 400
    finally:
        srv.shutdown()


def test_post_turn_stores_extracted_memories(tmp_path: Path):
    from brain.hook import ExtractedMemory

    srv, url = _start_server(tmp_path)
    try:
        fake_memories = [
            ExtractedMemory(content="c1", type="fact", tags=["backend"], confidence=0.9),
        ]
        with patch.object(server, "_get_extractor") as mock_get:
            mock_extractor = mock_get.return_value
            mock_extractor.extract.return_value = fake_memories
            resp = httpx.post(f"{url}/hook/post_turn", json={
                "agent": "brain-dev", "project": "/", "session_id": "s",
                "turn": {"user": "u", "assistant": "a", "tool_calls": []},
            })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["extracted"]) == 1
        assert body["extracted"][0]["type"] == "fact"
    finally:
        srv.shutdown()


def test_post_turn_missing_agent_returns_400(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/post_turn", json={
            "project": "/", "session_id": "s",
            "turn": {"user": "u", "assistant": "a"}
        })
        assert resp.status_code == 400
    finally:
        srv.shutdown()


def test_post_turn_without_api_key_returns_503(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    srv, url = _start_server(tmp_path, api_key="")
    # Clear the env after server start
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    try:
        resp = httpx.post(f"{url}/hook/post_turn", json={
            "agent": "t", "project": "/", "session_id": "s",
            "turn": {"user": "u", "assistant": "a"},
        })
        assert resp.status_code == 503
    finally:
        srv.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_http.py -v`
Expected: All fail with 404 (route not registered).

- [ ] **Step 3: Write minimal implementation (both routes + helper)**

In `backend/src/brain/server.py`, add module-level state + helper after the existing `_queue` declaration:
```python
_extractor: Any = None


def _get_extractor() -> Any:
    """Lazy singleton for the Extractor. Reads GOOGLE_API_KEY from env."""
    global _extractor
    if _extractor is None:
        from brain.hook import GeminiFlashExtractor
        _extractor = GeminiFlashExtractor()
    return _extractor
```

Also add `from typing import Any` to the imports at the top if not present.

In the `do_POST` method of `BrainHTTPHandler`, add two new route branches **before** `else: self._json_response({"error": "not found"}, status=404)`:

```python
            elif self.path == "/hook/wake_up":
                from brain.hook import HookRequest, WakeUpHandler
                agent = data.get("agent", "")
                if not agent:
                    self._json_response({"error": "missing 'agent'"}, status=400)
                    return
                store = get_store()
                events = get_events()
                req = HookRequest(
                    agent=agent,
                    project=data.get("project", ""),
                    session_id=data.get("session_id", ""),
                )
                handler = WakeUpHandler(store)
                r = handler.handle(req)
                events.log(
                    event_type="hook_wake_up",
                    agent=req.agent,
                    metadata={
                        "tokens_approx": r.tokens_approx,
                        "layers_loaded": r.layers_loaded,
                        "duration_ms": r.duration_ms,
                    },
                )
                self._json_response({
                    "context": r.context,
                    "layers_loaded": r.layers_loaded,
                    "tokens_approx": r.tokens_approx,
                    "duration_ms": r.duration_ms,
                })
            elif self.path == "/hook/post_turn":
                from brain.hook import HookRequest, PostTurnHandler, Turn
                agent = data.get("agent", "")
                if not agent:
                    self._json_response({"error": "missing 'agent'"}, status=400)
                    return
                try:
                    extractor = _get_extractor()
                except ValueError as e:
                    self._json_response({"error": str(e)}, status=503)
                    return
                store = get_store()
                events = get_events()
                req = HookRequest(
                    agent=agent,
                    project=data.get("project", ""),
                    session_id=data.get("session_id", ""),
                )
                turn_data = data.get("turn", {})
                turn = Turn(
                    user=turn_data.get("user", ""),
                    assistant=turn_data.get("assistant", ""),
                    tool_calls=turn_data.get("tool_calls", []),
                )
                handler = PostTurnHandler(store, extractor, events)
                r = handler.handle(req, turn)
                self._json_response({
                    "extracted": r.extracted,
                    "rejected_by_gate": r.rejected_by_gate,
                    "extraction_cost_usd": r.extraction_cost_usd,
                    "extraction_ms": r.extraction_ms,
                })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest tests/test_brain/test_hook_http.py -v`
Expected: `5 passed`

Also run full backend suite:
Run: `cd C:/Brain/backend && .venv/Scripts/python -m pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add backend/src/brain/server.py backend/tests/test_brain/test_hook_http.py
git commit -m "$(cat <<'EOF'
🧠 Feature: POST /hook/wake_up + POST /hook/post_turn HTTP routes

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Batch E — Deployment config

### Task E1: docker/compose.yml — pass GOOGLE_API_KEY

**Files:**
- Modify: `docker/compose.yml`

- [ ] **Step 1: Inspect current compose.yml**

Run: `cat C:/Brain/docker/compose.yml`
Look for the `environment:` block under the `brain` service.

- [ ] **Step 2: Add GOOGLE_API_KEY passthrough**

In `docker/compose.yml`, add to the `brain` service's `environment:` block:
```yaml
      GOOGLE_API_KEY: ${GOOGLE_API_KEY:-}
```

Full block should look like (existing values + new line):
```yaml
    environment:
      BRAIN_HTTP_PORT: "8611"
      BRAIN_MCP_PORT: "8610"
      BRAIN_HOST: "0.0.0.0"
      BRAIN_PERSIST_DIR: "/data/chromadb"
      BRAIN_SERVICE_HOST: "brain"
      GOOGLE_API_KEY: ${GOOGLE_API_KEY:-}
```

- [ ] **Step 3: Rebuild the container**

Run:
```bash
cd C:/Brain && docker compose -f docker/compose.yml build brain
docker compose -f docker/compose.yml up -d brain
```

- [ ] **Step 4: Verify the env var made it through**

Run: `docker exec brain printenv GOOGLE_API_KEY`
Expected: the value of `$GOOGLE_API_KEY` from the shell environment (or empty if unset).
If empty but you expected a value: check that `GOOGLE_API_KEY` is set in your host shell.

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add docker/compose.yml
git commit -m "$(cat <<'EOF'
🧹 Chore: pass GOOGLE_API_KEY into brain container for hook extractor

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Batch F — Adapter scripts

### Task F1: scripts/brain_wake_up.py

**Files:**
- Create: `scripts/brain_wake_up.py`
- Create: `scripts/tests/__init__.py` (empty)
- Create: `scripts/tests/conftest.py`
- Create: `scripts/tests/test_brain_wake_up.py`

- [ ] **Step 1: Create the test scaffolding**

Create `scripts/tests/__init__.py` — empty file.

Create `scripts/tests/conftest.py`:
```python
"""Add scripts/ to sys.path so test files can import brain_wake_up etc."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 2: Write the failing test**

Create `scripts/tests/test_brain_wake_up.py`:
```python
"""Unit tests for brain_wake_up.py (SessionStart CC hook adapter)."""
from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

import brain_wake_up as hook


def _capture_stdout(fn):
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        fn()
    return buf.getvalue()


def test_derive_agent_uses_cwd_basename():
    assert hook.derive_agent("C:/Brain") == "brain"
    assert hook.derive_agent("/home/user/Money") == "money"


def test_derive_agent_handles_generic_basename():
    assert hook.derive_agent("C:/someproject/src") == "someproject-src"
    assert hook.derive_agent("/a/Marcel/docker") == "marcel-docker"


def test_successful_wake_up_returns_cc_contract(monkeypatch):
    fake_post = lambda url, json, timeout: _FakeResp(200, {
        "context": "## Identity\n- Arthur", "layers_loaded": {"L0": 1, "L1": 0},
        "tokens_approx": 10, "duration_ms": 5,
    })
    monkeypatch.setattr(hook.httpx, "post", fake_post)
    out = _capture_stdout(lambda: hook.main(
        stdin_data=json.dumps({"cwd": "C:/Brain", "session_id": "s1"})
    ))
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Arthur" in parsed["hookSpecificOutput"]["additionalContext"]


def test_brain_unreachable_yields_empty_context(monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(hook.httpx, "post", _raise)
    out = _capture_stdout(lambda: hook.main(
        stdin_data=json.dumps({"cwd": "C:/Brain", "session_id": "s1"})
    ))
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["additionalContext"] == ""


def test_malformed_stdin_yields_empty_context(monkeypatch):
    out = _capture_stdout(lambda: hook.main(stdin_data="{not json"))
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["additionalContext"] == ""


def test_http_500_yields_empty_context(monkeypatch):
    monkeypatch.setattr(hook.httpx, "post",
                        lambda *a, **kw: _FakeResp(500, {"error": "boom"}))
    out = _capture_stdout(lambda: hook.main(
        stdin_data=json.dumps({"cwd": "/x", "session_id": "s"})
    ))
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["additionalContext"] == ""


class _FakeResp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body
    def json(self): return self._body
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up.py -v`
Expected: `ModuleNotFoundError: No module named 'brain_wake_up'`

- [ ] **Step 4: Write minimal implementation**

Create `scripts/brain_wake_up.py`:
```python
"""Claude Code SessionStart hook — fetches wake-up context from Brain.

Reads CC's stdin JSON (cwd, session_id, etc.), POSTs to Brain's
/hook/wake_up endpoint, and writes Claude Code's SessionStart
contract to stdout. On any failure (Brain unreachable, timeout,
bad stdin), writes empty additionalContext so the session proceeds
unblocked.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
TIMEOUT_SECONDS = 0.5

_GENERIC_BASENAMES = frozenset({"docker", "src", "app", "project", "repo", "code"})


def derive_agent(cwd: str) -> str:
    p = Path(cwd)
    basename = p.name.lower() or "default"
    if basename in _GENERIC_BASENAMES:
        parent = p.parent.name.lower() or "root"
        basename = f"{parent}-{basename}"
    return basename


def main(stdin_data: str | None = None) -> int:
    raw = stdin_data if stdin_data is not None else sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        _write_empty()
        return 0

    cwd = data.get("cwd", "") or os.getcwd()
    session_id = data.get("session_id", "")
    agent = derive_agent(cwd)

    try:
        resp = httpx.post(
            f"{BRAIN_URL}/hook/wake_up",
            json={"agent": agent, "project": cwd, "session_id": session_id},
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception:
        _write_empty()
        return 0

    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": body.get("context", ""),
        },
    }))
    return 0


def _write_empty() -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "",
        },
    }))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up.py -v`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
cd C:/Brain && git add scripts/brain_wake_up.py scripts/tests/__init__.py scripts/tests/conftest.py scripts/tests/test_brain_wake_up.py
git commit -m "$(cat <<'EOF'
🧠 Feature: brain_wake_up.py — Claude Code SessionStart adapter

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task F2: scripts/brain_post_turn.py (refactor of brain_hook.py)

**Files:**
- Create: `scripts/brain_post_turn.py`
- Create: `scripts/tests/test_brain_post_turn.py`
- (Do NOT delete `brain_hook.py` yet — delete in Batch G after cutover verified.)

- [ ] **Step 1: Write the failing tests**

Create `scripts/tests/test_brain_post_turn.py`:
```python
"""Unit tests for brain_post_turn.py (Stop hook, replacement for brain_hook.py)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import brain_post_turn as hook


def test_parse_transcript_into_turn_extracts_latest_user_and_assistant(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "first message"}) + "\n"
        + json.dumps({"role": "assistant", "content": "first reply"}) + "\n"
        + json.dumps({"role": "user", "content": "second message"}) + "\n"
        + json.dumps({"role": "assistant", "content": "second reply"}) + "\n",
        encoding="utf-8",
    )
    turn = hook.parse_delta_to_turn(transcript, offset=0)
    assert turn["user"] == "second message"
    assert turn["assistant"] == "second reply"


def test_parse_transcript_honors_offset(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    line1 = json.dumps({"role": "user", "content": "old"}) + "\n"
    line2 = json.dumps({"role": "user", "content": "new"}) + "\n"
    transcript.write_text(line1 + line2, encoding="utf-8")
    offset = len(line1.encode("utf-8"))
    turn = hook.parse_delta_to_turn(transcript, offset=offset)
    assert turn["user"] == "new"


def test_main_posts_structured_turn(monkeypatch, tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "do X"}) + "\n"
        + json.dumps({"role": "assistant", "content": "done"}) + "\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    pending = tmp_path / "pending.jsonl"

    captured = {}
    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["body"] = json
        return _FakeResp(200, {"extracted": [], "rejected_by_gate": 0,
                               "extraction_cost_usd": 0.0, "extraction_ms": 10})
    monkeypatch.setattr(hook.httpx, "post", fake_post)

    hook.main(
        stdin_data=json.dumps({"session_id": "s1",
                               "transcript_path": str(transcript),
                               "cwd": "C:/Brain"}),
        state_dir=state_dir, pending_path=pending,
    )
    assert "/hook/post_turn" in captured["url"]
    assert captured["body"]["agent"] == "brain"
    assert captured["body"]["turn"]["user"] == "do X"
    assert captured["body"]["turn"]["assistant"] == "done"


def test_main_enqueues_on_brain_down(monkeypatch, tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "a" * 200}) + "\n"
        + json.dumps({"role": "assistant", "content": "b" * 200}) + "\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    pending = tmp_path / "pending.jsonl"

    def _raise(*a, **kw): raise RuntimeError("down")
    monkeypatch.setattr(hook.httpx, "post", _raise)

    hook.main(
        stdin_data=json.dumps({"session_id": "s1",
                               "transcript_path": str(transcript),
                               "cwd": "C:/Brain"}),
        state_dir=state_dir, pending_path=pending,
    )
    assert pending.exists()
    lines = [line for line in pending.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1


def test_main_skips_under_min_delta(monkeypatch, tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "hi"}) + "\n",
        encoding="utf-8",
    )
    called = []
    def _tracking_post(*a, **kw): called.append(1); return _FakeResp(200, {})
    monkeypatch.setattr(hook.httpx, "post", _tracking_post)

    hook.main(
        stdin_data=json.dumps({"session_id": "s1",
                               "transcript_path": str(transcript),
                               "cwd": "C:/Brain"}),
        state_dir=tmp_path / "state", pending_path=tmp_path / "p.jsonl",
    )
    assert called == []  # too short, nothing posted


class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
    def json(self): return self._body
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_post_turn.py -v`
Expected: `ModuleNotFoundError: No module named 'brain_post_turn'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/brain_post_turn.py`:
```python
"""Claude Code Stop hook — posts turn delta to Brain /hook/post_turn.

Replaces the legacy scripts/brain_hook.py. Differences:
- Parses transcript delta into structured Turn (user/assistant/tool_calls)
  instead of flattening
- POSTs to /hook/post_turn instead of /store
- Extraction is done backend-side (no more client Gemini call)

Preserves:
- Byte-offset tracking per session_id in data/brain_hook_state/
- Pending queue at data/brain_pending_local.jsonl with opportunistic drain
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

HOOK_STATE_DIR = Path("data/brain_hook_state")
PENDING_PATH = Path("data/brain_pending_local.jsonl")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
BRAIN_TIMEOUT = 30.0
MIN_DELTA_CHARS = 100
MAX_PENDING_ATTEMPTS = 50

_GENERIC_BASENAMES = frozenset({"docker", "src", "app", "project", "repo", "code"})


def derive_agent(cwd: str) -> str:
    p = Path(cwd)
    basename = p.name.lower() or "default"
    if basename in _GENERIC_BASENAMES:
        parent = p.parent.name.lower() or "root"
        basename = f"{parent}-{basename}"
    return basename


def load_offset(state_dir: Path, session_id: str) -> int:
    f = state_dir / f"{session_id}.offset"
    if not f.exists(): return 0
    try: return int(f.read_text(encoding="utf-8").strip())
    except (ValueError, OSError): return 0


def save_offset(state_dir: Path, session_id: str, offset: int) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f"{session_id}.offset").write_text(str(offset), encoding="utf-8")


def parse_delta_to_turn(transcript_path: Path, offset: int) -> dict:
    """Parse transcript JSONL from offset. Returns {user, assistant, tool_calls}
    using the LAST user message and LAST assistant message in the delta."""
    if not transcript_path.exists():
        return {"user": "", "assistant": "", "tool_calls": []}
    with transcript_path.open("rb") as fh:
        fh.seek(offset)
        raw = fh.read()
    user, assistant = "", ""
    tool_calls: list[dict] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = obj.get("role", "")
        content = obj.get("content", "")
        if role == "user" and isinstance(content, str):
            user = content
        elif role == "assistant":
            if isinstance(content, str):
                assistant = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "name": block.get("name", ""),
                                "input": block.get("input", ""),
                            })
                if text_parts: assistant = "\n".join(text_parts)
    return {"user": user, "assistant": assistant, "tool_calls": tool_calls}


def read_delta_size(transcript_path: Path, offset: int) -> int:
    if not transcript_path.exists(): return 0
    with transcript_path.open("rb") as fh:
        fh.seek(offset)
        return len(fh.read())


def get_new_offset(transcript_path: Path) -> int:
    if not transcript_path.exists(): return 0
    return transcript_path.stat().st_size


def append_pending(path: Path, entry: dict) -> None:
    enriched = {**entry, "queued_at": datetime.now(tz=UTC).isoformat(), "attempts": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(enriched) + "\n")


def read_pending(path: Path) -> list[dict]:
    if not path.exists(): return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        with contextlib.suppress(json.JSONDecodeError):
            out.append(json.loads(line))
    return out


def write_pending(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        path.write_text("", encoding="utf-8"); return
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def drain_pending(pending_path: Path) -> None:
    entries = read_pending(pending_path)
    if not entries: return
    remaining: list[dict] = []
    for entry in entries:
        attempts = entry.get("attempts", 0)
        if attempts >= MAX_PENDING_ATTEMPTS:
            continue  # discard
        try:
            resp = httpx.post(
                f"{BRAIN_URL}/hook/post_turn",
                json=entry.get("payload", entry),
                timeout=BRAIN_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception:
            remaining.append({**entry, "attempts": attempts + 1})
    write_pending(pending_path, remaining)


def main(
    stdin_data: str | None = None,
    state_dir: Path | None = None,
    pending_path: Path | None = None,
) -> bool:
    resolved_state = state_dir or HOOK_STATE_DIR
    resolved_pending = pending_path or PENDING_PATH

    raw = stdin_data if stdin_data is not None else sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False

    session_id = data.get("session_id", "")
    transcript_str = data.get("transcript_path", "")
    cwd = data.get("cwd", "") or os.getcwd()
    if not transcript_str:
        return False
    transcript_path = Path(transcript_str)

    offset = load_offset(resolved_state, session_id)
    delta_size = read_delta_size(transcript_path, offset)
    if delta_size < MIN_DELTA_CHARS:
        save_offset(resolved_state, session_id, get_new_offset(transcript_path))
        return False

    turn = parse_delta_to_turn(transcript_path, offset)
    agent = derive_agent(cwd)
    payload = {"agent": agent, "project": cwd, "session_id": session_id, "turn": turn}

    drain_pending(resolved_pending)

    try:
        resp = httpx.post(f"{BRAIN_URL}/hook/post_turn", json=payload, timeout=BRAIN_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        append_pending(resolved_pending, {"payload": payload})

    save_offset(resolved_state, session_id, get_new_offset(transcript_path))
    return True


if __name__ == "__main__":
    main()
    sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_post_turn.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd C:/Brain && git add scripts/brain_post_turn.py scripts/tests/test_brain_post_turn.py
git commit -m "$(cat <<'EOF'
🧠 Feature: brain_post_turn.py — Stop hook adapter (replaces brain_hook.py)

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Batch G — Integration & cutover

### Task G1: Seed script + seed the dogfood memories

**Files:**
- Create: `scripts/seed_brain.py`

- [ ] **Step 1: Write the seed script**

Create `scripts/seed_brain.py`:
```python
"""One-off bootstrap — store initial identity/preference memories for dogfood.

Run once after the hook endpoints are live and before the first dogfood session.
Idempotent: safe to re-run (the store's dedup gate handles duplicates).
"""
from __future__ import annotations

import os

import httpx

BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
AGENT = os.environ.get("BRAIN_SEED_AGENT", "brain")

SEEDS: list[dict] = [
    # Identity
    {"content": "User is Arthur (arthurolivier.fortin@gmail.com), building Brain as a drop-in memory system for LLM agents.",
     "type": "context", "tags": ["identity", "persona"]},
    {"content": "Communicate in French by default. Technical terms stay English when clearer.",
     "type": "context", "tags": ["identity", "communication"]},
    {"content": "Blunt, no glazing, no trailing summaries. This is infrastructure — ambiguity costs time.",
     "type": "context", "tags": ["identity", "communication"]},

    # Preferences
    {"content": "Commit emoji convention: 🧠 Feature / 🩹 Fix / 📓 Docs / 🧹 Chore / 🧪 Test / 🧬 Refactor. Always include Co-Authored-By trailer.",
     "type": "context", "tags": ["preference", "git"]},
    {"content": "Docker safety: never --remove-orphans without audit, always explicit `name:` in compose.yml. Incident 2026-04-17 deleted Money containers.",
     "type": "context", "tags": ["preference", "docker", "safety"]},
    {"content": "Issue-first workflow: every non-trivial change gets a GitHub issue before code. PRs reference Closes #N.",
     "type": "context", "tags": ["preference", "workflow"]},
    {"content": "No `--no-verify` on git operations without explicit user approval.",
     "type": "context", "tags": ["preference", "git", "safety"]},
    {"content": "Doc structure: every doc lives under docs/ in a disciplined subfolder (architecture, research, specs, plans, runbooks, benchmarks, improvements, decisions). Specs and plans are append-only.",
     "type": "context", "tags": ["preference", "docs"]},
]


def main() -> None:
    seeded = 0
    for seed in SEEDS:
        payload = {
            "content": seed["content"],
            "agent": AGENT,
            "memory_type": seed["type"],
            "metadata": {"tags": ",".join(seed["tags"])},
            "skip_gate": False,
        }
        try:
            resp = httpx.post(f"{BRAIN_URL}/store", json=payload, timeout=5.0)
            resp.raise_for_status()
            body = resp.json()
            if body.get("stored"):
                seeded += 1
                print(f"[seeded] {seed['tags']} — {seed['content'][:60]}...")
            else:
                print(f"[skipped] {seed['content'][:60]}... reason={body.get('reason', 'unknown')}")
        except Exception as e:
            print(f"[error] {e}")
    print(f"\nTotal seeded: {seeded}/{len(SEEDS)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the seed script against a live Brain**

Prerequisite: Brain is up at `localhost:8621` and empty (or at least the `brain` agent scope).

Run:
```bash
cd C:/Brain && backend/.venv/Scripts/python scripts/seed_brain.py
```
Expected output: 8 lines with `[seeded]` or `[skipped]`, then `Total seeded: N/8`.

- [ ] **Step 3: Verify the seeds landed**

Run: `curl -s "http://localhost:8621/search?query=identity&agent=brain"`
Expected: JSON with `results` array containing memories with `tags` including `identity` or `preference`.

- [ ] **Step 4: Commit**

```bash
cd C:/Brain && git add scripts/seed_brain.py
git commit -m "$(cat <<'EOF'
🧠 Feature: seed_brain.py — bootstrap identity/preference memories for dogfood

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task G2: Wire .claude/settings.json

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Write the new settings**

Replace the contents of `.claude/settings.json` with:
```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Edit",
      "Bash(*)",
      "Glob",
      "Grep",
      "WebFetch",
      "WebSearch",
      "Agent",
      "NotebookEdit"
    ]
  },
  "statusLine": {
    "type": "command",
    "command": "python \"$CLAUDE_PROJECT_DIR/scripts/brain_statusline.py\"",
    "refreshInterval": 30
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/scripts/brain_wake_up.py\"",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python \"$CLAUDE_PROJECT_DIR/scripts/brain_post_turn.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `cd C:/Brain && backend/.venv/Scripts/python -m json.tool .claude/settings.json > /dev/null && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd C:/Brain && git add .claude/settings.json
git commit -m "$(cat <<'EOF'
🧹 Chore: wire SessionStart + Stop hooks to new adapter scripts

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task G3: Delete legacy brain_hook.py

**Files:**
- Delete: `scripts/brain_hook.py`

- [ ] **Step 1: Verify no references remain**

Run: `cd C:/Brain && grep -r "brain_hook" --include="*.py" --include="*.json" --include="*.md" .`
Expected: Only references are in `.claude/settings.json` (already updated) and possibly docs/history files.

If any live code references `brain_hook.py`, update them to `brain_post_turn.py` first.

- [ ] **Step 2: Delete the file**

Run: `cd C:/Brain && git rm scripts/brain_hook.py`

- [ ] **Step 3: Commit**

```bash
cd C:/Brain && git commit -m "$(cat <<'EOF'
🧹 Chore: delete legacy brain_hook.py (superseded by brain_post_turn.py)

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task G4: Dogfood measurement + success criteria

**Files:**
- Create: `docs/runbooks/phase2b-dogfood.md`

- [ ] **Step 1: Capture a baseline before dogfooding**

Run:
```bash
curl -s http://localhost:8621/stats | python -m json.tool
```
Record the initial `total`, `agents`, `types` counts. These are the pre-dogfood baseline.

- [ ] **Step 2: Write the dogfood runbook**

Create `docs/runbooks/phase2b-dogfood.md`:
```markdown
# Phase 2b Dogfood Runbook

Measurement and acceptance procedure for the hook architecture MVP. Run this over ≥ 7 days of real Brain sessions before declaring Phase 2b merge-ready.

## Prerequisites

- Docker brain container up and healthy: `curl http://localhost:8621/health`
- `$GOOGLE_API_KEY` set in the environment that launched Docker
- Seeds landed (Task G1 ran successfully)
- `.claude/settings.json` references `brain_wake_up.py` + `brain_post_turn.py`
- Legacy `brain_hook.py` deleted

## Hard criteria (gate the Phase 2b merge)

| # | Metric | Target | How to measure |
|---|--------|--------|----------------|
| 1 | `/hook/wake_up` p95 latency | < 500 ms | Query events: `curl "http://localhost:8621/events?limit=500" \| jq '[.events[] \| select(.event_type=="hook_wake_up") \| .metadata.duration_ms] \| sort \| .[(length*0.95 \| floor)]'` |
| 2 | `/hook/post_turn` p95 latency | < 2000 ms | Same as above with `hook_post_turn` and `extraction_ms` |
| 3 | Session blocks from hook timeout | 0 | Scan Claude Code session logs for any aborted starts |
| 4 | Backend tests green | 100% | `cd backend && .venv/Scripts/python -m pytest -q` |
| 5 | Adapter tests green | 100% | `backend/.venv/Scripts/python -m pytest scripts/tests/ -q` |
| 6 | Dogfood sessions | ≥ 50 | Event log count: `curl .../events?limit=10000 \| jq '[.events[] \| select(.event_type=="hook_wake_up")] \| length'` |
| 7 | Coherent events | No silent drops | Compare count of `hook_wake_up` events vs. actual CC sessions started (qualitative) |

## Soft criteria (guide iteration)

- Subjective: "Brain knows who I am at session start, I don't re-explain preferences"
- Extracted memories per session: 5–20. < 5 = under-extraction, > 50 = over-extraction → tune Extractor prompt
- No massive duplicates, no 2k-token blobs — inspect via `curl .../search?query=X&agent=brain`

## Observability commands

```bash
# Activity over time
curl -s http://localhost:8621/events/timeline | python -m json.tool

# Recent hook events
curl -s "http://localhost:8621/events?limit=50" | python -c \
  "import json,sys; [print(e['event_type'], e.get('metadata',{})) \
   for e in json.load(sys.stdin).get('events',[]) \
   if e['event_type'].startswith('hook_')]"

# Current brain totals
curl -s http://localhost:8621/stats | python -m json.tool

# Inspect extracted memories
curl -s "http://localhost:8621/search?query=IDENTITY&agent=brain&top_k=10" | python -m json.tool
```

## Iteration loop during dogfood

1. Session happens → events logged
2. Review `curl .../stats` and new memories in `.../search`
3. If quality is off: adjust `GeminiFlashExtractor.SYSTEM_PROMPT`, rebuild Docker, next session uses new prompt
4. If latency is off: profile which step is slow (extraction vs. gate vs. store), optimize

## Exit criteria

Phase 2b MVP merges when:
- [ ] All 7 hard criteria above are green
- [ ] Legacy `brain_hook.py` deleted (Task G3)
- [ ] ADR 0002 written (Task G5)
- [ ] Phase 2b README checkboxes all checked

Deferred post-MVP items stay in the roadmap un-checked. Each becomes its own sub-project.
```

- [ ] **Step 3: Commit**

```bash
cd C:/Brain && git add docs/runbooks/phase2b-dogfood.md
git commit -m "$(cat <<'EOF'
📓 Docs: Phase 2b dogfood runbook (acceptance procedure)

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task G5: Write ADR 0002

**Files:**
- Create: `docs/decisions/0002-hook-architecture.md`

- [ ] **Step 1: Write the ADR**

Create `docs/decisions/0002-hook-architecture.md`:
```markdown
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
```

- [ ] **Step 2: Commit**

```bash
cd C:/Brain && git add docs/decisions/0002-hook-architecture.md
git commit -m "$(cat <<'EOF'
📓 Docs: ADR 0002 — hook architecture decision record

Refs #<phase2b-issue>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (run before handing off)

- [ ] Every spec "Decisions locked" item (11 total) maps to at least one task above
- [ ] Every file listed in "File structure" appears in a task
- [ ] No "TBD", "TODO", or "similar to Task X" in any step
- [ ] Every test step has complete code
- [ ] Every implementation step has complete code
- [ ] Every commit step has full commit message
- [ ] Method signatures match across tasks:
  - `BrainStore.search_by_tag(tag, agent, top_k=5)` in A3 → called with same signature in C1
  - `Extractor.extract(turn) -> list[ExtractedMemory]` in A1 → conformed to in B1 → used in C2
  - `HookRequest(agent, project, session_id)` in A1 → constructed in C1, C2, D1, D2, F1, F2
  - `Turn(user, assistant, tool_calls=[])` in A1 → constructed in C2, D2, F2
  - `WakeUpResponse(context, layers_loaded, tokens_approx, duration_ms)` in A1 → returned from C1 → serialized in D1
  - `PostTurnResponse(extracted, rejected_by_gate, extraction_cost_usd, extraction_ms)` in A1 → returned from C2 → serialized in D2
- [ ] Hard success criteria from spec Section 4 appear as measurables in G4 runbook
- [ ] All 11 locked decisions from spec traceable: A1/A2 (5), A3/C1 (6), B1 (5), C2 (4, 7), D1/D2 (1), F1 (8, 9), G3 (10), G4 (11), G5 (all)
