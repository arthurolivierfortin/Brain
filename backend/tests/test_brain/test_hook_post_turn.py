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
        ExtractedMemory(content="fact number one about backend", type="fact", tags=["backend"], confidence=0.9),
        ExtractedMemory(content="fact number two about testing", type="decision", tags=["testing"], confidence=1.0),
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
        ExtractedMemory(content="content long enough for gate", type="fact",
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


def test_rejected_by_gate_increments_counter(tmp_path: Path):
    """Content < 10 chars triggers BrainGate Rule 1 (REJECT). Handler must count it."""
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = [
        ExtractedMemory(content="short", type="fact", tags=["backend"], confidence=0.9),
    ]
    handler = PostTurnHandler(store, extractor, events)
    resp = handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    assert resp.rejected_by_gate == 1
    assert resp.extracted == []
    assert store._collection.count() == 0
    # Event log reflects the rejection, not a false "extracted"
    recent = events.recent(limit=10)
    hook_events = [e for e in recent if e.get("event_type") == "hook_post_turn"]
    assert len(hook_events) == 1
    assert hook_events[0]["metadata"]["extracted_count"] == 0
    assert hook_events[0]["metadata"]["rejected_count"] == 1


def test_mixed_accepted_and_rejected_memories(tmp_path: Path):
    """One memory passes gate, one fails. Both paths exercised in same call."""
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = [
        ExtractedMemory(content="this memory is long enough for gate", type="fact",
                        tags=["backend"], confidence=0.9),
        ExtractedMemory(content="tiny", type="fact", tags=["backend"], confidence=0.9),
    ]
    handler = PostTurnHandler(store, extractor, events)
    resp = handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    assert len(resp.extracted) == 1
    assert resp.extracted[0]["content"].startswith("this memory")
    assert resp.rejected_by_gate == 1
    assert store._collection.count() == 1


def test_hook_post_turn_event_logged(tmp_path: Path):
    store, events = _new(tmp_path)
    extractor = MagicMock()
    extractor.extract.return_value = [
        ExtractedMemory(content="content long enough for gate", type="fact", tags=[], confidence=0.9),
    ]
    handler = PostTurnHandler(store, extractor, events)
    handler.handle(
        HookRequest(agent="t", project="/p", session_id="s1"),
        Turn(user="u", assistant="a"),
    )
    recent = events.recent(limit=10)
    hook_events = [e for e in recent if e.get("event_type") == "hook_post_turn"]
    assert len(hook_events) == 1
