# L2-A Backend Implementation Plan

**Linked spec:** [2026-04-28-l2-a-backend-design.md](../specs/2026-04-28-l2-a-backend-design.md)
**Linked checklist:** [2026-04-28-l2-a-backend-checklist.md](../specs/2026-04-28-l2-a-backend-checklist.md)
**Goal:** Ship L2 topic-triggered semantic retrieval at `wake_up`, refactor L0/L1 to cross-agent reads, and clarify that L3 already exists as `brain_search`.
**Branch:** `feat/25-l2-backend`

---

### Task 1 — [SPEC-1]: Extend `HookRequest` with three optional topic fields

**Files:**
- Modify: `backend/src/brain/hook.py` (lines 24–28, `HookRequest` dataclass)

Implementation only — no dedicated test (covered by TEST-4 through TEST-10 which all construct `HookRequest` with/without these fields).

- [ ] **Step 1.1: Add three optional fields to `HookRequest`**

```python
# backend/src/brain/hook.py — replace the HookRequest dataclass
@dataclass
class HookRequest:
    agent: str
    project: str
    session_id: str
    git_recent_commits: str = ""
    git_branch: str = ""
    claude_md_excerpt: str = ""
```

- [ ] **Step 1.2: Verify existing tests still pass**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_hook_wake_up.py tests/test_brain/test_hook_dataclasses.py -q
```

Expected: all existing tests PASS (fields default to `""`, existing callers pass zero impact).

- [ ] **Step 1.3: Tick [SPEC-1] in checklist, commit**

```bash
git add backend/src/brain/hook.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧠 Feature: SPEC-1 extend HookRequest with git/claude_md topic fields (#25)"
```

---

### Task 2 — [SPEC-2]: Make `BrainStore.search_by_tag` cross-agent

**Files:**
- Modify: `backend/src/brain/store.py` (lines 735–767, `search_by_tag` method)

- [ ] **Step 2.1: Write the failing test**

```python
# backend/tests/test_brain/test_store_chromadb.py — ADD this test at end of file
def test_search_by_tag_cross_agent_when_agent_is_none(tmp_path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    store.store("identity A", agent="agent-a", memory_type="context",
                metadata={"tags": "identity"}, skip_gate=True)
    store.store("identity B", agent="agent-b", memory_type="context",
                metadata={"tags": "identity"}, skip_gate=True)
    results = store.search_by_tag("identity", agent=None, top_k=10)
    contents = [r["content"] for r in results]
    assert "identity A" in contents
    assert "identity B" in contents
```

- [ ] **Step 2.2: Run test, watch it fail**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_store_chromadb.py::test_search_by_tag_cross_agent_when_agent_is_none -q
```

Expected: FAIL with `TypeError: search_by_tag() got unexpected keyword argument` or `AssertionError` (only one agent's memories returned).

- [ ] **Step 2.3: Implement minimal change to `search_by_tag`**

```python
# backend/src/brain/store.py — replace search_by_tag signature and where clause
def search_by_tag(self, tag: str, agent: str | None = None, top_k: int = 5) -> list[dict]:
    """Return memories whose tags contain `tag`, optionally scoped to agent.

    When agent is None, reads across all agents (brain-level access control).
    """
    if self._collection.count() == 0:
        return []
    if agent is not None:
        results = self._collection.get(
            where={"agent": {"$eq": agent}},
            include=["documents", "metadatas"],
        )
    else:
        results = self._collection.get(
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

- [ ] **Step 2.4: Run test, watch it pass**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_store_chromadb.py::test_search_by_tag_cross_agent_when_agent_is_none -q
```

Expected: PASS

- [ ] **Step 2.5: Tick [SPEC-2] in checklist, commit**

```bash
git add backend/src/brain/store.py backend/tests/test_brain/test_store_chromadb.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧬 Refactor: SPEC-2 search_by_tag agent=None drops where-clause (cross-agent) (#25)"
```

---

### Task 3 — [SPEC-3, 4, 5, 6, 7]: Add the five L2 helper functions to `hook.py`

**Files:**
- Modify: `backend/src/brain/hook.py` (add helpers before `WakeUpHandler` class)
- Create: `backend/tests/test_brain/test_l2_rerank.py`
- Create: `backend/tests/test_brain/test_l2_threshold.py`

This task covers SPEC-3 through SPEC-7 and TEST-1 through TEST-3 together because the helpers are pure functions easily tested in isolation.

- [ ] **Step 3.1: Write failing tests for all five helpers**

```python
# backend/tests/test_brain/test_l2_rerank.py
"""Unit tests for _rerank_candidates and _age_days."""
from __future__ import annotations

import math
import time

import pytest

from brain.hook import _rerank_candidates


def _candidate(distance: float, access_count: int, created_at: str) -> dict:
    return {
        "id": "x",
        "content": "test",
        "distance": distance,
        "access_count": access_count,
        "created_at": created_at,
    }


def test_rerank_orders_by_composite_score() -> None:
    now_iso = "2026-04-28T00:00:00+00:00"
    # High cosine (low distance), high access, fresh → top
    top = _candidate(distance=0.1, access_count=10, created_at=now_iso)
    # Low cosine (high distance), low access, old → bottom
    old_iso = "2025-01-01T00:00:00+00:00"
    bottom = _candidate(distance=0.9, access_count=0, created_at=old_iso)
    # Middle
    mid = _candidate(distance=0.5, access_count=2, created_at=now_iso)

    result = _rerank_candidates([bottom, mid, top])
    assert result[0] is top
    assert result[-1] is bottom


def test_rerank_sets_rerank_score_key() -> None:
    c = _candidate(distance=0.2, access_count=0, created_at="2026-04-28T00:00:00+00:00")
    result = _rerank_candidates([c])
    assert "_rerank_score" in result[0]
    assert result[0]["_rerank_score"] > 0


def test_rerank_bad_created_at_uses_zero_age() -> None:
    """Parse failure on created_at → age=0 → no age penalty, does not crash."""
    c = _candidate(distance=0.3, access_count=0, created_at="not-a-date")
    result = _rerank_candidates([c])
    cosine = 1.0 - 0.3 / 2.0
    expected = cosine * (1.0 + math.log(1) * 0.05) * math.exp(0)
    assert abs(result[0]["_rerank_score"] - expected) < 1e-6


def test_rerank_empty_list() -> None:
    assert _rerank_candidates([]) == []
```

```python
# backend/tests/test_brain/test_l2_threshold.py
"""Unit tests for _apply_threshold and _fit_to_budget."""
from __future__ import annotations

import os

import pytest

from brain.hook import _apply_threshold, _fit_to_budget


def _make(distance: float, content: str = "x") -> dict:
    return {"distance": distance, "content": content}


# --- _apply_threshold ---

def test_apply_threshold_strict_and_env_override(monkeypatch) -> None:
    """Distance 1.1 → cosine 0.45 exactly → excluded (strict >). Distance 1.0 → 0.5 → included."""
    at_boundary = _make(distance=1.1)  # cosine = 1 - 1.1/2 = 0.45  → excluded (strict >)
    above = _make(distance=1.0)        # cosine = 1 - 1.0/2 = 0.50  → included
    below = _make(distance=1.2)        # cosine = 1 - 1.2/2 = 0.40  → excluded

    result = _apply_threshold([at_boundary, above, below], threshold=0.45)
    assert len(result) == 1
    assert result[0] is above


def test_apply_threshold_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BRAIN_L2_THRESHOLD", "0.60")
    # cosine 0.55 → excluded at threshold 0.60
    c = _make(distance=0.9)  # cosine = 1 - 0.9/2 = 0.55
    # Note: _apply_threshold takes threshold as a parameter; the env-var is read
    # by WakeUpHandler.__init__. Here we pass the overridden value directly.
    result = _apply_threshold([c], threshold=0.60)
    assert result == []


def test_apply_threshold_preserves_order() -> None:
    a = _make(distance=0.2)
    b = _make(distance=0.4)
    c = _make(distance=0.6)
    result = _apply_threshold([a, b, c], threshold=0.45)
    assert result == [a, b, c]


def test_apply_threshold_empty() -> None:
    assert _apply_threshold([], threshold=0.45) == []


# --- _fit_to_budget ---

def test_fit_to_budget_caps_and_preserves_order() -> None:
    """Each item costs len(content)//4 tokens. Cap=2 tokens → only first 8-char item fits."""
    a = {"content": "12345678", "id": "a"}   # cost = 8//4 = 2 tokens exactly → fits
    b = {"content": "12345678", "id": "b"}   # cost = 2 → would overflow (2+2=4 > cap=2... wait cap=4 below)
    # Use cap=3: first item costs 2 (fits, total=2), second also costs 2 (2+2=4 > 3 → dropped)
    result = _fit_to_budget([a, b], cap=3)
    assert result == [a]


def test_fit_to_budget_all_fit() -> None:
    items = [{"content": "ab", "id": str(i)} for i in range(3)]  # cost=0 each (2//4=0)
    result = _fit_to_budget(items, cap=10)
    assert result == items


def test_fit_to_budget_empty() -> None:
    assert _fit_to_budget([], cap=100) == []


def test_fit_to_budget_preserves_input_order() -> None:
    a = {"content": "a" * 8, "id": "a"}   # cost=2
    b = {"content": "b" * 8, "id": "b"}   # cost=2
    c = {"content": "c" * 8, "id": "c"}   # cost=2
    result = _fit_to_budget([a, b, c], cap=5)
    assert result == [a, b]
```

- [ ] **Step 3.2: Run tests, watch them fail**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_l2_rerank.py tests/test_brain/test_l2_threshold.py -q
```

Expected: FAIL with `ImportError: cannot import name '_rerank_candidates' from 'brain.hook'`

- [ ] **Step 3.3: Add the five helpers to `hook.py`**

Insert the following block after the `import` block and before the `@dataclass class Turn:` definition in `backend/src/brain/hook.py`:

```python
import math
from datetime import UTC, datetime
```

(Add `math` and `datetime` to the existing imports at top of file.)

Then add these functions after the `HookRequest` and `WakeUpResponse` dataclasses (before `ExtractedMemory`):

```python
def _build_topic_query(req: "HookRequest") -> str:
    parts = []
    if req.git_branch:
        parts.append(f"branch: {req.git_branch}")
    if req.git_recent_commits:
        parts.append(f"recent commits:\n{req.git_recent_commits}")
    if req.claude_md_excerpt:
        parts.append(req.claude_md_excerpt)
    return "\n\n".join(parts).strip()


def _apply_threshold(candidates: list[dict], threshold: float) -> list[dict]:
    return [c for c in candidates if (1.0 - c["distance"] / 2.0) > threshold]


def _age_days(iso_ts: str, now: float) -> float:
    try:
        dt = datetime.fromisoformat(iso_ts)
        return max((now - dt.timestamp()) / 86400, 0.0)
    except (ValueError, TypeError):
        return 0.0


def _rerank_candidates(candidates: list[dict]) -> list[dict]:
    now = time.time()
    for c in candidates:
        cosine = 1.0 - c["distance"] / 2.0
        access = int(c.get("access_count", 0))
        age = _age_days(c.get("created_at", ""), now)
        c["_rerank_score"] = cosine * (1.0 + math.log(access + 1) * 0.05) * math.exp(-age * 0.01)
    return sorted(candidates, key=lambda x: x["_rerank_score"], reverse=True)


def _fit_to_budget(memories: list[dict], cap: int) -> list[dict]:
    out: list[dict] = []
    total = 0
    for m in memories:
        cost = len(m["content"]) // 4
        if total + cost > cap:
            break
        out.append(m)
        total += cost
    return out


def _log_degraded(
    events: Any,
    req: "HookRequest",
    reason: str,
    layer_affected: str,
    fallback_used: str = "",
) -> None:
    events.log(
        event_type="degraded_wake_up",
        agent=req.agent,
        metadata={
            "reason": reason,
            "layer_affected": layer_affected,
            "fallback_used": fallback_used,
            "agent": req.agent,
            "session_id": req.session_id,
        },
    )
```

- [ ] **Step 3.4: Run tests, watch them pass**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_l2_rerank.py tests/test_brain/test_l2_threshold.py -q
```

Expected: PASS (all 11 tests)

- [ ] **Step 3.5: Tick [SPEC-3..7] and [TEST-1..3] in checklist, commit**

```bash
git add backend/src/brain/hook.py backend/tests/test_brain/test_l2_rerank.py backend/tests/test_brain/test_l2_threshold.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧠 Feature: SPEC-3..7 + TEST-1..3 L2 helper functions (_build_topic_query, _apply_threshold, _rerank_candidates, _fit_to_budget, _log_degraded) (#25)"
```

---

### Task 4 — [SPEC-8]: Refactor `WakeUpHandler` — cross-agent, per-layer budgets, L2 pipeline

**Files:**
- Modify: `backend/src/brain/hook.py` (`WakeUpHandler` class, ~50 LOC → ~150 LOC)
- Create: `backend/tests/test_brain/test_l2_cascade.py`

- [ ] **Step 4.1: Write the cascade failing tests**

```python
# backend/tests/test_brain/test_l2_cascade.py
"""Unit tests for WakeUpHandler cascade paths — mocked store."""
from __future__ import annotations

import concurrent.futures
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.events import EventLog
from brain.hook import HookRequest, WakeUpHandler


def _make_req(**kwargs) -> HookRequest:
    defaults = dict(agent="test-agent", project="/proj", session_id="s1",
                    git_branch="", git_recent_commits="", claude_md_excerpt="")
    defaults.update(kwargs)
    return HookRequest(**defaults)


def _mock_store(identity=None, prefs=None, search_result=None, search_raises=None):
    store = MagicMock()
    store.search_by_tag.side_effect = lambda tag, agent, top_k: (
        identity if tag == "identity" else prefs
    ) if search_raises is None else identity if tag == "identity" else prefs
    if search_raises is not None:
        store.search.side_effect = search_raises
    elif search_result is not None:
        store.search.return_value = search_result
    else:
        store.search.return_value = []
    return store


def _mock_events(tmp_path: Path) -> EventLog:
    return EventLog(path=tmp_path / "events.jsonl")


def test_embedding_failure_logs_degraded(tmp_path: Path) -> None:
    store = _mock_store(identity=[], prefs=[], search_raises=RuntimeError("OOM"))
    events = _mock_events(tmp_path)
    handler = WakeUpHandler(store, events)
    req = _make_req(git_branch="main")
    resp = handler.handle(req)

    assert resp.layers_loaded.get("L2", 0) == 0
    logged = events.recent(limit=10)
    degraded = [e for e in logged if e["event_type"] == "degraded_wake_up"]
    assert len(degraded) == 1
    assert degraded[0]["metadata"]["reason"] == "embedding_failed"
    assert degraded[0]["metadata"]["layer_affected"] == "L2"


def test_db_timeout_logs_degraded(tmp_path: Path, monkeypatch) -> None:
    def slow_search(*args, **kwargs):
        time.sleep(5)
        return []

    store = _mock_store(identity=[], prefs=[])
    store.search.side_effect = slow_search
    events = _mock_events(tmp_path)
    monkeypatch.setattr("brain.hook.BRAIN_L2_TIMEOUT_S", 0.05)
    handler = WakeUpHandler(store, events)
    req = _make_req(git_branch="main")
    resp = handler.handle(req)

    assert resp.layers_loaded.get("L2", 0) == 0
    logged = events.recent(limit=10)
    degraded = [e for e in logged if e["event_type"] == "degraded_wake_up"]
    assert len(degraded) == 1
    assert degraded[0]["metadata"]["reason"] == "db_timeout"


def test_empty_topic_is_silent(tmp_path: Path) -> None:
    """No git_branch, no commits, no claude_md → topic_query="" → L2=0, no degraded event."""
    store = _mock_store(identity=[], prefs=[])
    events = _mock_events(tmp_path)
    handler = WakeUpHandler(store, events)
    req = _make_req()  # all topic fields empty
    handler.handle(req)

    logged = events.recent(limit=10)
    degraded = [e for e in logged if e["event_type"] == "degraded_wake_up"]
    assert degraded == []
    store.search.assert_not_called()


def test_all_below_threshold_is_silent(tmp_path: Path) -> None:
    """All candidates have distance > 1.1 (cosine < 0.45) → L2=0, no degraded event."""
    low_score = [
        {"id": "x", "content": "irrelevant", "distance": 1.5, "access_count": 0, "created_at": ""}
    ]
    store = _mock_store(identity=[], prefs=[], search_result=low_score)
    events = _mock_events(tmp_path)
    handler = WakeUpHandler(store, events)
    req = _make_req(git_branch="main")
    handler.handle(req)

    logged = events.recent(limit=10)
    degraded = [e for e in logged if e["event_type"] == "degraded_wake_up"]
    assert degraded == []
```

- [ ] **Step 4.2: Run tests, watch them fail**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_l2_cascade.py -q
```

Expected: FAIL — `WakeUpHandler.__init__` does not accept `events`, no `BRAIN_L2_TIMEOUT_S`, no L2 pipeline.

- [ ] **Step 4.3: Refactor `WakeUpHandler` in `hook.py`**

Replace the entire `WakeUpHandler` class with:

```python
import os
import concurrent.futures

BRAIN_L2_TIMEOUT_S: float = 2.0  # module-level constant so tests can monkeypatch it

class WakeUpHandler:
    """Selects L0 + L1 + L2 memories and formats them as system-prompt injection.

    L0 = identity tag (cross-agent, cap 100 tokens)
    L1 = preference tag (cross-agent, cap 300 tokens)
    L2 = topic-triggered semantic search (cross-agent, cap 500 tokens)
    """

    L0_TAG = "identity"
    L1_TAG = "preference"
    L0_CAP = 100
    L1_CAP = 300
    L2_CAP = 500
    BUDGET_TOKENS = 500  # retained for backward compat with test_budget_caps_output_tokens

    def __init__(self, store: Any, events: Any = None) -> None:
        self._store = store
        self._events = events
        self._threshold = float(os.environ.get("BRAIN_L2_THRESHOLD", "0.45"))
        self._topk_raw = int(os.environ.get("BRAIN_L2_TOPK_RAW", "20"))

    def handle(self, req: HookRequest) -> WakeUpResponse:
        t0 = time.monotonic()

        # L0 — identity, cross-agent
        try:
            identity = self._store.search_by_tag(self.L0_TAG, agent=None, top_k=5)
            identity = _fit_to_budget(identity, self.L0_CAP)
        except Exception:
            identity = []
            if self._events:
                _log_degraded(self._events, req, reason="l0_failed", layer_affected="L0")

        # L1 — preference, cross-agent
        try:
            prefs = self._store.search_by_tag(self.L1_TAG, agent=None, top_k=10)
            prefs = _fit_to_budget(prefs, self.L1_CAP)
        except Exception:
            prefs = []
            if self._events:
                _log_degraded(self._events, req, reason="l1_failed", layer_affected="L1")

        # L2 — topic-triggered, cross-agent
        topic: list[dict] = []
        topic_query = _build_topic_query(req)
        if topic_query:
            try:
                timeout = BRAIN_L2_TIMEOUT_S
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(
                        self._store.search,
                        topic_query,
                        None,  # agent=None → cross-agent
                        None,  # memory_type
                        self._topk_raw,
                    )
                    try:
                        candidates = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        if self._events:
                            _log_degraded(self._events, req, reason="db_timeout", layer_affected="L2")
                        candidates = None
                if candidates is not None:
                    filtered = _apply_threshold(candidates, self._threshold)
                    reranked = _rerank_candidates(filtered)
                    topic = _fit_to_budget(reranked, self.L2_CAP)
            except Exception:
                if self._events:
                    _log_degraded(self._events, req, reason="embedding_failed", layer_affected="L2")

        context = self._format(identity, prefs, topic)
        duration_ms = int((time.monotonic() - t0) * 1000)

        layers_loaded = {
            "L0": len(identity),
            "L1": len(prefs),
            "L2": len(topic),
        }
        tokens_approx = self._tokens(context)

        return WakeUpResponse(
            context=context,
            layers_loaded=layers_loaded,
            tokens_approx=tokens_approx,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _format(identity: list[dict], prefs: list[dict], topic: list[dict] = []) -> str:
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
        if topic:
            if identity or prefs:
                lines.append("")
            lines.append("## Topic")
            for m in topic:
                lines.append(f"- {m['content']}")
        return "\n".join(lines)

    @staticmethod
    def _tokens(text: str) -> int:
        return len(text) // 4
```

Note: `store.search` is called with positional args `(topic_query, None, None, self._topk_raw)` matching the signature `search(query, agent, memory_type, top_k, ...)`. Check the exact call site — `store.search` signature is `search(self, query, agent=None, memory_type=None, top_k=5, ...)`. Use keyword args for clarity:

```python
future = ex.submit(
    self._store.search,
    topic_query,
)
# Then pass kwargs via lambda:
future = ex.submit(
    lambda: self._store.search(topic_query, agent=None, top_k=self._topk_raw)
)
```

Use the lambda form to avoid positional arg confusion with `ThreadPoolExecutor.submit`.

- [ ] **Step 4.4: Run cascade tests, watch them pass**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_l2_cascade.py -q
```

Expected: PASS (4 tests)

- [ ] **Step 4.5: Run full wake_up suite to check no regression**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_hook_wake_up.py -q
```

Expected: `test_scopes_to_agent` FAILS (it asserts `layers_loaded == {"L0": 1, "L1": 1}` but now cross-agent returns 2 from each agent) — this is expected and addressed in Task 6 (SPEC-10).

The other 4 tests (`test_empty_store_returns_empty_context`, `test_populates_identity_and_preference_sections`, `test_budget_caps_output_tokens`, `test_duration_ms_is_reported`) must all PASS.

- [ ] **Step 4.6: Tick [SPEC-8] and [TEST-4..7] in checklist, commit**

```bash
git add backend/src/brain/hook.py backend/tests/test_brain/test_l2_cascade.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧠 Feature: SPEC-8 + TEST-4..7 WakeUpHandler refactor — L2 pipeline + cascade + cross-agent (#25)"
```

---

### Task 5 — [SPEC-9]: Extend `/hook/wake_up` HTTP handler — accept new fields + enrich event metadata

**Files:**
- Modify: `backend/src/brain/server.py` (lines 322–351, the `elif self.path == "/hook/wake_up":` block)

- [ ] **Step 5.1: Replace the `/hook/wake_up` POST handler block**

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
        git_recent_commits=data.get("git_recent_commits", ""),
        git_branch=data.get("git_branch", ""),
        claude_md_excerpt=data.get("claude_md_excerpt", ""),
    )
    handler = WakeUpHandler(store, events)
    r = handler.handle(req)
    # Compute enriched metadata for event log
    # _rerank_cosine is stored by _rerank_candidates as _rerank_score;
    # for cosine_scores we recompute from distance (stored in topic dicts)
    from brain.hook import _build_topic_query
    topic_memories = []  # WakeUpHandler returns topic via layers_loaded count but not the list
    # NOTE: WakeUpResponse does not expose the topic list directly.
    # cosine_scores will be populated once WakeUpResponse is extended in a follow-up, OR
    # we collect them from within the handler. For now, log what we have.
    events.log(
        event_type="hook_wake_up",
        agent=req.agent,
        metadata={
            "tokens_approx": r.tokens_approx,
            "layers_loaded": r.layers_loaded,
            "duration_ms": r.duration_ms,
            "threshold_applied": float(os.environ.get("BRAIN_L2_THRESHOLD", "0.45")),
            "tokens_per_layer": r.layers_loaded,  # count proxy; see note below
        },
    )
    self._json_response({
        "context": r.context,
        "layers_loaded": r.layers_loaded,
        "tokens_approx": r.tokens_approx,
        "duration_ms": r.duration_ms,
    })
```

**Architectural note on `memory_ids` and `cosine_scores`:** The spec requires logging `memory_ids` (nested dict per layer) and `cosine_scores` (L2 entries only). This requires `WakeUpHandler.handle` to return the actual memory lists, not just counts. The cleanest solution is to extend `WakeUpResponse` with three optional list fields OR to have the handler expose the lists directly. The implementation approach is:

Extend `WakeUpResponse`:

```python
@dataclass
class WakeUpResponse:
    context: str
    layers_loaded: dict[str, int]
    tokens_approx: int
    duration_ms: int
    identity: list[dict] = field(default_factory=list)
    prefs: list[dict] = field(default_factory=list)
    topic: list[dict] = field(default_factory=list)
```

Then in `WakeUpHandler.handle`, set `identity=identity, prefs=prefs, topic=topic` on the returned `WakeUpResponse`. In the HTTP handler, use these to build `memory_ids` and `cosine_scores`.

Full revised `/hook/wake_up` block in `server.py`:

```python
elif self.path == "/hook/wake_up":
    import os
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
        git_recent_commits=data.get("git_recent_commits", ""),
        git_branch=data.get("git_branch", ""),
        claude_md_excerpt=data.get("claude_md_excerpt", ""),
    )
    handler = WakeUpHandler(store, events)
    r = handler.handle(req)
    threshold = float(os.environ.get("BRAIN_L2_THRESHOLD", "0.45"))
    cosine_scores = [
        round(1.0 - m["distance"] / 2.0, 4) for m in r.topic
    ]
    events.log(
        event_type="hook_wake_up",
        agent=req.agent,
        metadata={
            "tokens_approx": r.tokens_approx,
            "layers_loaded": r.layers_loaded,
            "duration_ms": r.duration_ms,
            "memory_ids": {
                "L0": [m["id"] for m in r.identity],
                "L1": [m["id"] for m in r.prefs],
                "L2": [m["id"] for m in r.topic],
            },
            "cosine_scores": cosine_scores,
            "threshold_applied": threshold,
            "tokens_per_layer": {
                "L0": sum(len(m["content"]) // 4 for m in r.identity),
                "L1": sum(len(m["content"]) // 4 for m in r.prefs),
                "L2": sum(len(m["content"]) // 4 for m in r.topic),
            },
        },
    )
    self._json_response({
        "context": r.context,
        "layers_loaded": r.layers_loaded,
        "tokens_approx": r.tokens_approx,
        "duration_ms": r.duration_ms,
    })
```

- [ ] **Step 5.2: Add `identity`, `prefs`, `topic` fields to `WakeUpResponse` dataclass**

```python
@dataclass
class WakeUpResponse:
    context: str
    layers_loaded: dict[str, int]
    tokens_approx: int
    duration_ms: int
    identity: list[dict] = field(default_factory=list)
    prefs: list[dict] = field(default_factory=list)
    topic: list[dict] = field(default_factory=list)
```

And update `WakeUpHandler.handle` to pass these:

```python
return WakeUpResponse(
    context=context,
    layers_loaded=layers_loaded,
    tokens_approx=tokens_approx,
    duration_ms=duration_ms,
    identity=identity,
    prefs=prefs,
    topic=topic,
)
```

- [ ] **Step 5.3: Run existing HTTP tests**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_hook_http.py -q
```

Expected: all 5 existing HTTP tests PASS (response shape unchanged).

- [ ] **Step 5.4: Tick [SPEC-9] in checklist, commit**

```bash
git add backend/src/brain/hook.py backend/src/brain/server.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧠 Feature: SPEC-9 /hook/wake_up accepts topic fields + enriches event metadata (#25)"
```

---

### Task 6 — [SPEC-10]: Delete `test_scopes_to_agent`, add cross-agent test file

**Files:**
- Modify: `backend/tests/test_brain/test_hook_wake_up.py` (delete lines 47–53, the `test_scopes_to_agent` function)
- Create: `backend/tests/test_brain/test_wake_up_cross_agent.py`

- [ ] **Step 6.1: Write new cross-agent failing test**

```python
# backend/tests/test_brain/test_wake_up_cross_agent.py
"""Verify L0, L1, L2 retrieval is cross-agent after the SPEC-2/SPEC-8 refactor."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.hook import HookRequest, WakeUpHandler  # noqa: E402
from brain.store import BrainStore  # noqa: E402
from brain.events import EventLog  # noqa: E402


def test_l0_l1_l2_are_cross_agent(tmp_path: Path) -> None:
    """Seed memories for agent-A and agent-B; request as agent-A;
    assert both agents' identity+preference memories appear."""
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    events = EventLog(path=tmp_path / "events.jsonl")

    store.store("Identity A — French-first persona",
                agent="agent-a", memory_type="context",
                metadata={"tags": "identity"}, skip_gate=True)
    store.store("Identity B — blunt communication style",
                agent="agent-b", memory_type="context",
                metadata={"tags": "identity"}, skip_gate=True)
    store.store("Preference A — always use ruff",
                agent="agent-a", memory_type="context",
                metadata={"tags": "preference"}, skip_gate=True)
    store.store("Preference B — no glazing",
                agent="agent-b", memory_type="context",
                metadata={"tags": "preference"}, skip_gate=True)

    handler = WakeUpHandler(store, events)
    resp = handler.handle(HookRequest(
        agent="agent-a", project="/", session_id="s1",
    ))

    # Both agents' identity + preference memories should appear
    assert resp.layers_loaded["L0"] == 2
    assert resp.layers_loaded["L1"] == 2
    assert "Identity A" in resp.context
    assert "Identity B" in resp.context
    assert "Preference A" in resp.context
    assert "Preference B" in resp.context


def test_l2_is_cross_agent_when_topic_provided(tmp_path: Path) -> None:
    """L2 search returns memories from any agent when topic_query is provided."""
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    events = EventLog(path=tmp_path / "events.jsonl")

    store.store("Python FastAPI backend architecture decision",
                agent="agent-a", memory_type="decision",
                metadata={"tags": "backend"}, skip_gate=True)
    store.store("FastAPI route testing with httpx patterns",
                agent="agent-b", memory_type="fact",
                metadata={"tags": "backend"}, skip_gate=True)

    handler = WakeUpHandler(store, events)
    resp = handler.handle(HookRequest(
        agent="agent-a", project="/", session_id="s2",
        git_branch="feat/backend-api",
        git_recent_commits="add FastAPI route for backend search",
    ))

    # At least one L2 result should come from agent-b
    assert resp.layers_loaded["L2"] >= 1
    topic_agents = {m["agent"] for m in resp.topic}
    assert "agent-b" in topic_agents or "agent-a" in topic_agents
```

- [ ] **Step 6.2: Run new test, watch it fail**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_wake_up_cross_agent.py -q
```

Expected: FAIL — `test_scopes_to_agent` behavior (agent isolation) was the old contract; now with cross-agent, `layers_loaded["L0"]` should be 2, not 1.

- [ ] **Step 6.3: Delete `test_scopes_to_agent` from `test_hook_wake_up.py`**

Remove lines 47–53 (the entire `test_scopes_to_agent` function).

- [ ] **Step 6.4: Run updated test suites**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_hook_wake_up.py tests/test_brain/test_wake_up_cross_agent.py -q
```

Expected: all PASS (4 remaining in `test_hook_wake_up.py` + 2 new cross-agent tests).

- [ ] **Step 6.5: Tick [SPEC-10] and [TEST-9] in checklist, commit**

```bash
git add backend/tests/test_brain/test_hook_wake_up.py backend/tests/test_brain/test_wake_up_cross_agent.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧪 Test: SPEC-10 + TEST-9 delete test_scopes_to_agent, add cross-agent assertions (#25)"
```

---

### Task 7 — [TEST-8]: Integration test — full L2 pipeline against real ChromaDB

**Files:**
- Create: `backend/tests/test_brain/test_l2_integration.py`

- [ ] **Step 7.1: Write the integration test**

```python
# backend/tests/test_brain/test_l2_integration.py
"""Integration tests — full L2 pipeline against real ChromaDB with seeded fixture."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.events import EventLog  # noqa: E402
from brain.hook import HookRequest, WakeUpHandler  # noqa: E402
from brain.store import BrainStore  # noqa: E402


_FIXTURE_MEMORIES = [
    ("FastAPI route testing with pytest and httpx", "backend"),
    ("SQLite WAL mode enables concurrent readers", "backend"),
    ("ChromaDB cosine distance space for embeddings", "backend"),
    ("Python ruff linter enforces no trailing whitespace", "tooling"),
    ("Docker compose explicit name prevents orphan collision", "docker"),
    ("Git branch naming convention: feat/NNN-slug", "git"),
    ("Gemini Flash 2.5 used for memory extraction", "llm"),
    ("Brain event log is append-only JSONL", "backend"),
    ("French-first communication style", "identity"),
    ("No backwards-compat shims without approval", "preference"),
]


def _seed_fixture(store: BrainStore, agent: str = "fixture-agent") -> None:
    for content, tag in _FIXTURE_MEMORIES:
        store.store(content, agent=agent, memory_type="fact",
                    metadata={"tags": tag}, skip_gate=True)


def test_full_l2_pipeline_against_real_chromadb(tmp_path: Path) -> None:
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    events = EventLog(path=tmp_path / "events.jsonl")
    _seed_fixture(store)

    handler = WakeUpHandler(store, events)
    req = HookRequest(
        agent="test-requester",
        project="/brain",
        session_id="integration-1",
        git_branch="feat/backend-api",
        git_recent_commits="add FastAPI route for backend HTTP search endpoint",
        claude_md_excerpt="Python backend (FastAPI), ChromaDB storage",
    )
    resp = handler.handle(req)

    # L2 should fire (topic is non-empty and matches backend content)
    assert resp.layers_loaded["L2"] >= 1

    # cosine_scores logged in event metadata
    logged = events.recent(limit=20)
    wake_events = [e for e in logged if e["event_type"] == "hook_wake_up"]
    # Note: hook_wake_up event is logged by server.py (SPEC-9), not by WakeUpHandler itself.
    # In this unit-level integration test we do not go through server.py, so we verify
    # the response fields instead.
    assert "## Topic" in resp.context
    # All topic memories came back with a distance field
    for m in resp.topic:
        assert "distance" in m
        assert 0.0 <= m["distance"] <= 2.0
```

- [ ] **Step 7.2: Run integration test**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_l2_integration.py -q
```

Expected: PASS (ChromaDB + fastembed must be available; in CI these are present per existing test setup).

- [ ] **Step 7.3: Tick [TEST-8] in checklist, commit**

```bash
git add backend/tests/test_brain/test_l2_integration.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧪 Test: TEST-8 full L2 pipeline integration against real ChromaDB (#25)"
```

---

### Task 8 — [TEST-10]: HTTP integration — wake_up with topic fields + enriched event metadata

**Files:**
- Modify: `backend/tests/test_brain/test_hook_http.py` (add one test at end)

- [ ] **Step 8.1: Write the failing HTTP integration test**

```python
# Append to backend/tests/test_brain/test_hook_http.py

def test_wake_up_accepts_topic_fields_and_enriches_event_metadata(tmp_path: Path):
    from pathlib import Path as _Path
    import json

    events_path = tmp_path / "events.jsonl"
    import os
    os.environ["BRAIN_PERSIST_DIR"] = str(tmp_path / "chromadb")
    os.environ["GOOGLE_API_KEY"] = "fake"
    # Patch EventLog path to use our tmp_path so we can read the logged events
    from brain import events as events_module
    original_default = events_module.DEFAULT_LOG_PATH
    events_module.DEFAULT_LOG_PATH = events_path

    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/wake_up", json={
            "agent": "test-agent",
            "project": "/brain",
            "session_id": "s-http-1",
            "git_branch": "feat/25-l2-backend",
            "git_recent_commits": "add L2 topic retrieval to wake_up",
            "claude_md_excerpt": "Python FastAPI backend",
        })
        assert resp.status_code == 200
        body = resp.json()
        # Response shape unchanged
        assert "context" in body
        assert "layers_loaded" in body
        assert "L0" in body["layers_loaded"]
        assert "L1" in body["layers_loaded"]
        assert "L2" in body["layers_loaded"]
        assert "tokens_approx" in body
        assert "duration_ms" in body

        # Verify enriched metadata in event log
        logged_lines = events_path.read_text().splitlines() if events_path.exists() else []
        wake_events = [
            json.loads(l) for l in logged_lines
            if l and json.loads(l).get("event_type") == "hook_wake_up"
        ]
        assert len(wake_events) >= 1
        meta = wake_events[-1]["metadata"]
        assert "memory_ids" in meta
        assert set(meta["memory_ids"].keys()) == {"L0", "L1", "L2"}
        assert "cosine_scores" in meta
        assert isinstance(meta["cosine_scores"], list)
        assert "threshold_applied" in meta
        assert "tokens_per_layer" in meta
    finally:
        srv.shutdown()
        events_module.DEFAULT_LOG_PATH = original_default
```

- [ ] **Step 8.2: Run test, watch it fail**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_hook_http.py::test_wake_up_accepts_topic_fields_and_enriches_event_metadata -q
```

Expected: FAIL — server does not yet pass enriched metadata (fixed in Task 5 above; if Task 5 done first, this may already pass).

- [ ] **Step 8.3: Run full HTTP test suite**

```bash
cd C:/Brain/backend && python -m pytest tests/test_brain/test_hook_http.py -q
```

Expected: all 6 tests PASS.

- [ ] **Step 8.4: Tick [TEST-10] in checklist, commit**

```bash
git add backend/tests/test_brain/test_hook_http.py docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "🧪 Test: TEST-10 HTTP integration — topic fields + enriched hook_wake_up event metadata (#25)"
```

---

### Task 9 — [SPEC-11, 12, 13]: Doc updates — README, ADR 0003, spec footer

**Files:**
- Modify: `README.md`
- Create: `docs/decisions/0003-l2-l3-design.md`
- Modify: `docs/specs/2026-04-19-hook-architecture-design.md` (append-only footer)

- [ ] **Step 9.1: Update README Phase 2b roadmap**

In `README.md`, find the Phase 2b section and:
1. Tick `[x]` for "L2 topic-triggered retrieval"
2. Add a sentence: "L3 = `brain_search` MCP tool (already implemented — see [ADR 0003](docs/decisions/0003-l2-l3-design.md))"

- [ ] **Step 9.2: Create ADR 0003**

```markdown
# docs/decisions/0003-l2-l3-design.md

---
id: 0003
title: L2 topic-triggered retrieval at wake_up + L3 = brain_search MCP
status: accepted
date: 2026-04-28
supersedes:
superseded_by:
relates_to:
  - docs/decisions/0002-hook-architecture.md
  - docs/specs/2026-04-28-l2-a-backend-design.md
---

## Context

Phase 2b shipped L0 (identity tag filter) and L1 (preference tag filter) in `WakeUpHandler`. Sessions received static token injections — same memories every time, independent of the current task. Brain needed semantic adaptivity to fulfill the cerveau-parfait vision. L3 (explicit deep semantic search) was already implemented as `brain_search` MCP tool but not documented as part of the L0–L3 taxonomy.

## Decision

**L2: topic-triggered semantic retrieval at `wake_up`**

- Fires once per session at `wake_up` (not `pre_turn` — deferred, see YAGNI below).
- Topic query built from three optional fields in the wake_up request payload: `git_recent_commits`, `git_branch`, `claude_md_excerpt`. If all empty → L2 = 0 silently (by design, not a failure).
- Retrieval: `store.search(topic_query, agent=None, top_k=BRAIN_L2_TOPK_RAW)` → threshold filter → reranking → budget cap.
- Reranking formula: `score = cosine × (1 + log(access_count + 1) × 0.05) × exp(-age_days × 0.01)` — favors recent, frequently-accessed, semantically relevant memories.
- Token budgets per layer: L0 cap 100, L1 cap 300, L2 cap 500. No redistribution between layers.
- Env vars: `BRAIN_L2_THRESHOLD` (default 0.45), `BRAIN_L2_TOPK_RAW` (default 20).

**Cross-agent retrieval for L0, L1, and L2**

All three layers drop the `agent=` filter. Brain's access-control unit is the Brain instance (database), not the query. An identity memory stored by `claude-code` should benefit any other agent operating on the same Brain. Agent-level read/write ACL is deferred to Phase 6 (multi-tenant aggregator).

This required a 4-line change to `BrainStore.search_by_tag`: `agent` param now defaults to `None`; when `None`, no `where=` clause is applied.

**L3: `brain_search` MCP tool (already exists)**

L3 is the explicit, model-invoked deep search tier — agents call `brain_search` when they need to retrieve memories beyond what L2 auto-injects. This tool existed before this ADR; this ADR clarifies its role in the L0–L3 taxonomy.

**Failure cascade**

| Failure | Trigger | Effect | Event |
|---------|---------|--------|-------|
| Empty topic | `_build_topic_query` returns `""` | L2 = [] | none (silent by design) |
| Below threshold | `_apply_threshold` returns `[]` | L2 = [] | none (silent by design) |
| Embedding crash | `store.search` raises | L2 = [] | `degraded_wake_up` reason=`embedding_failed` |
| ChromaDB timeout (> 2 s) | `concurrent.futures` timeout | L2 = [] | `degraded_wake_up` reason=`db_timeout` |
| L0 store failure | `search_by_tag` raises | L0 = [] | `degraded_wake_up` reason=`l0_failed` |
| L1 store failure | `search_by_tag` raises | L1 = [] | `degraded_wake_up` reason=`l1_failed` |

**Observability**

`hook_wake_up` event enriched with: `memory_ids` (nested dict per layer), `cosine_scores` (L2 entries, post-rerank order), `threshold_applied`, `tokens_per_layer`. New event type `degraded_wake_up` for cascade failures.

## Alternatives considered

- **Pre-turn L2 (per-turn dynamic retrieval):** Rejected for V1 — one code path to harden; pre-turn adds latency on every turn. Deferred to future cycle post-dogfood.
- **Adaptive budget redistribution:** Rejected — adds complexity, hurts predictability. Dead tokens drop.
- **Cross-encoder reranker:** Rejected for V1 — heuristic formula sufficient until dogfood reveals gaps.
- **Topic embedding cache:** Rejected — wake_up fires once per session at this scale.
- **Agent-level query isolation (keep old behavior):** Rejected — Brain is shared-brain-first; per-agent isolation is a future feature, not the default.

## YAGNI notes

- `pre_turn` L2 hook — future cycle
- Real tokenizer (keep `len // 4` heuristic)
- Topic embedding cache
- Multi-language CLAUDE.md handling
- Cross-platform git compatibility (adapter-side concern, L2-B)
```

- [ ] **Step 9.3: Append footer to `docs/specs/2026-04-19-hook-architecture-design.md`**

Append at end of file (do NOT edit existing prose):

```markdown

---

## Update 2026-04-28

"L2 topic-triggered retrieval" and "L3 deep semantic search" moved from Out-of-scope to In-scope.

- **L2** implemented in `backend/src/brain/hook.py:WakeUpHandler` — topic-triggered semantic retrieval at `wake_up`. See [2026-04-28-l2-a-backend-design.md](2026-04-28-l2-a-backend-design.md) and [ADR 0003](../decisions/0003-l2-l3-design.md).
- **L3** clarified: `brain_search` MCP tool already implements L3 (explicit model-invoked deep semantic search). No new code. See [ADR 0003](../decisions/0003-l2-l3-design.md).
```

- [ ] **Step 9.4: Tick [SPEC-11..13] in checklist, commit**

```bash
git add README.md docs/decisions/0003-l2-l3-design.md docs/specs/2026-04-19-hook-architecture-design.md docs/specs/2026-04-28-l2-a-backend-checklist.md
git commit -m "📓 Docs: SPEC-11..13 README tick L2, ADR 0003, spec footer update (#25)"
```

---

### Final Task — Verification Gates

- [ ] **Step F.1: ruff**

```bash
cd C:/Brain/backend && python -m ruff check .
```

Expected: 0 errors.

- [ ] **Step F.2: pytest — full suite**

```bash
cd C:/Brain/backend && python -m pytest -q
```

Expected: ~205 tests pass (193 baseline − 1 deleted `test_scopes_to_agent` + ~13 new tests). No failures.

- [ ] **Step F.3: Frontend — skip**

No `frontend/` changes in this PR.

- [ ] **Step F.4: Tick [GATE-1..3] in checklist, push, open PR**

```bash
git push -u origin feat/25-l2-backend
gh pr create --title "L2-A backend: topic-triggered retrieval at wake_up + cross-agent L0/L1 + L3 doc" \
  --body "$(cat <<'EOF'
Closes #25

## Summary
- L2 topic-triggered semantic retrieval at `wake_up` (embedding + threshold + rerank + budget)
- L0/L1 refactored to cross-agent (drop `agent=` filter in `search_by_tag`)
- `degraded_wake_up` event logged on cascade failures; `hook_wake_up` enriched with `memory_ids`, `cosine_scores`, `threshold_applied`, `tokens_per_layer`
- ADR 0003 created, README Phase 2b updated, spec footer appended

## Test plan
- [ ] `python -m ruff check .` passes (0 errors)
- [ ] `python -m pytest -q` passes (~205 tests, +12 new, -1 deleted)
- [ ] No regression on Phase 2b tests (191/193 baseline → still green)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Implementation notes for builder

### Import additions in `hook.py`

Add to the existing import block:
```python
import concurrent.futures
import math
from datetime import UTC, datetime
```

`os` is already imported. `time` is already imported.

### `_build_topic_query` placement

Place `_build_topic_query`, `_apply_threshold`, `_age_days`, `_rerank_candidates`, `_fit_to_budget`, `_log_degraded` as module-level functions AFTER the dataclasses (`Turn`, `HookRequest`, `WakeUpResponse`, `ExtractedMemory`, `PostTurnResponse`) and BEFORE `class GeminiFlashExtractor`. This avoids forward-reference issues since `_log_degraded` takes `HookRequest` as a parameter.

### `WakeUpHandler.__init__` signature change

Old: `def __init__(self, store: Any) -> None`
New: `def __init__(self, store: Any, events: Any = None) -> None`

The `events=None` default ensures all existing callers (including `test_hook_wake_up.py` which constructs `WakeUpHandler(store)`) continue to work without modification. When `events` is None, degraded events are silently skipped (defensive `if self._events:` guards).

### `store.search` call from ThreadPoolExecutor

`concurrent.futures.ThreadPoolExecutor.submit` passes `*args` and `**kwargs` to the callable. Use a lambda to pass keyword arguments cleanly:

```python
future = ex.submit(
    lambda: self._store.search(topic_query, agent=None, top_k=self._topk_raw)
)
```

### `BRAIN_L2_TIMEOUT_S` module-level constant

Declare as `BRAIN_L2_TIMEOUT_S: float = 2.0` at module level in `hook.py` so `test_l2_cascade.py::test_db_timeout_logs_degraded` can monkeypatch it (`monkeypatch.setattr("brain.hook.BRAIN_L2_TIMEOUT_S", 0.05)`).

### `test_hook_wake_up.py::test_budget_caps_output_tokens` compatibility

The test asserts `resp.tokens_approx <= WakeUpHandler.BUDGET_TOKENS`. Keep `BUDGET_TOKENS = 500` as a class attribute for backward compat. The per-layer L2 cap (500) matches this value so no change in semantics.

### `test_hook_wake_up.py::test_empty_store_returns_empty_context`

Currently asserts `resp.layers_loaded == {"L0": 0, "L1": 0}`. After SPEC-8, `layers_loaded` gains `"L2": 0`. This test will FAIL unless updated. Update assertion to:
```python
assert resp.layers_loaded == {"L0": 0, "L1": 0, "L2": 0}
```

Similarly `test_populates_identity_and_preference_sections` asserts `resp.layers_loaded == {"L0": 1, "L1": 1}` — update to `{"L0": 1, "L1": 1, "L2": 0}`.

These updates to `test_hook_wake_up.py` are part of SPEC-10's "update existing tests" scope and should be committed together with the `test_scopes_to_agent` deletion.
