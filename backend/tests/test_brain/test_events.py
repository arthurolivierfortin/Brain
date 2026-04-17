"""Tests for brain event log."""

from __future__ import annotations

from pathlib import Path

from brain.events import EventLog


class TestEventLog:

    def test_log_and_read(self, tmp_path: Path):
        log = EventLog(path=tmp_path / "events.jsonl")
        log.log(event_type="stored", agent="test", node_id="n1", details="test memory")

        events = log.recent()
        assert len(events) == 1
        assert events[0]["event_type"] == "stored"
        assert events[0]["node_id"] == "n1"

    def test_multiple_events(self, tmp_path: Path):
        log = EventLog(path=tmp_path / "events.jsonl")
        log.log(event_type="stored", agent="a")
        log.log(event_type="searched", agent="b")
        log.log(event_type="reinforced", node_id="n1")

        events = log.recent()
        assert len(events) == 3

    def test_recent_limit(self, tmp_path: Path):
        log = EventLog(path=tmp_path / "events.jsonl")
        for i in range(10):
            log.log(event_type="stored", node_id=f"n{i}")

        events = log.recent(limit=3)
        assert len(events) == 3

    def test_empty_log(self, tmp_path: Path):
        log = EventLog(path=tmp_path / "nope.jsonl")
        assert log.recent() == []

    def test_stats_over_time(self, tmp_path: Path):
        log = EventLog(path=tmp_path / "events.jsonl")
        log.log(event_type="stored", agent="test")
        log.log(event_type="searched", agent="test")

        timeline = log.stats_over_time(buckets=4)
        assert len(timeline) == 4
        total_stored = sum(b["stored"] for b in timeline)
        assert total_stored >= 1
