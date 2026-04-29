"""Unit tests for WakeUpHandler cascade paths — mocked store."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from brain.events import EventLog
from brain.hook import HookRequest, WakeUpHandler


def _make_req(**kwargs) -> HookRequest:
    defaults = {
        "agent": "test-agent",
        "project": "/proj",
        "session_id": "s1",
        "git_branch": "",
        "git_recent_commits": "",
        "claude_md_excerpt": "",
    }
    defaults.update(kwargs)
    return HookRequest(**defaults)


def _mock_store(identity=None, prefs=None):
    store = MagicMock()
    identity = identity or []
    prefs = prefs or []

    def _by_tag(tag, agent=None, top_k=5):
        if tag == "identity":
            return list(identity)
        if tag == "preference":
            return list(prefs)
        return []

    store.search_by_tag.side_effect = _by_tag
    store.search.return_value = []
    return store


def _events(tmp_path: Path) -> EventLog:
    return EventLog(path=tmp_path / "events.jsonl")


def test_embedding_failure_logs_degraded(tmp_path: Path) -> None:
    store = _mock_store()
    store.search.side_effect = RuntimeError("OOM")
    events = _events(tmp_path)
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

    store = _mock_store()
    store.search.side_effect = slow_search
    events = _events(tmp_path)
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
    """No git_branch, no commits, no claude_md -> topic_query="" -> L2=0, no degraded event."""
    store = _mock_store()
    events = _events(tmp_path)
    handler = WakeUpHandler(store, events)
    req = _make_req()
    handler.handle(req)

    logged = events.recent(limit=10)
    degraded = [e for e in logged if e["event_type"] == "degraded_wake_up"]
    assert degraded == []
    store.search.assert_not_called()


def test_all_below_threshold_is_silent(tmp_path: Path) -> None:
    """All candidates have distance > 1.1 (cosine < 0.45) -> L2=0, no degraded event."""
    low_score = [
        {"id": "x", "content": "irrelevant", "distance": 1.5,
         "access_count": 0, "created_at": ""}
    ]
    store = _mock_store()
    store.search.return_value = low_score
    events = _events(tmp_path)
    handler = WakeUpHandler(store, events)
    req = _make_req(git_branch="main")
    handler.handle(req)

    logged = events.recent(limit=10)
    degraded = [e for e in logged if e["event_type"] == "degraded_wake_up"]
    assert degraded == []
