"""Tests for the decision log."""

from __future__ import annotations

from pathlib import Path

from brain.decisions import DecisionLog


class TestDecisionLog:

    def test_log_and_retrieve(self, tmp_path: Path):
        log = DecisionLog("test-agent", base_dir=tmp_path)
        d = log.log("D001", what="chose EMA over SMA", why="faster response to trends")
        assert d.id == "D001"
        assert d.agent == "test-agent"

        recent = log.recent()
        assert len(recent) == 1
        assert recent[0].what == "chose EMA over SMA"

    def test_update_outcome(self, tmp_path: Path):
        log = DecisionLog("test-agent", base_dir=tmp_path)
        log.log("D002", what="relaxed thresholds", why="too few signals")
        assert log.update_outcome("D002", "signal count increased 3x") is True

        recent = log.recent()
        assert recent[0].outcome == "signal count increased 3x"

    def test_update_nonexistent(self, tmp_path: Path):
        log = DecisionLog("test-agent", base_dir=tmp_path)
        assert log.update_outcome("NOPE", "nothing") is False

    def test_persistence(self, tmp_path: Path):
        log1 = DecisionLog("test-agent", base_dir=tmp_path)
        log1.log("D003", what="added BTC", why="market benchmark")

        log2 = DecisionLog("test-agent", base_dir=tmp_path)
        assert len(log2.recent()) == 1

    def test_multiple_decisions(self, tmp_path: Path):
        log = DecisionLog("test-agent", base_dir=tmp_path)
        log.log("D010", what="first", why="reason1")
        log.log("D011", what="second", why="reason2")
        log.log("D012", what="third", why="reason3")

        recent = log.recent(limit=2)
        assert len(recent) == 2
        assert recent[-1].id == "D012"
