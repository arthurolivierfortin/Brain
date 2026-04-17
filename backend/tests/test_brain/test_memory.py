"""Tests for the brain memory system."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from brain.memory import (
    MemoryEntry,
    MemoryStore,
    MemoryType,
)


class TestMemoryEntry:

    def test_new_entry_has_full_confidence(self):
        entry = MemoryEntry(id="t1", content="test", memory_type="context", agent="dev")
        assert entry.compute_confidence() >= 0.99

    def test_architecture_never_decays(self):
        entry = MemoryEntry(
            id="t2", content="arch decision", memory_type="architecture", agent="dev",
            created_at=(datetime.now(UTC) - timedelta(days=365)).isoformat(),
        )
        assert entry.compute_confidence() == 1.0

    def test_context_decays_fast(self):
        entry = MemoryEntry(
            id="t3", content="temp context", memory_type="context", agent="dev",
            created_at=(datetime.now(UTC) - timedelta(days=14)).isoformat(),
        )
        # After 14 days (one half-life), confidence should be ~0.5
        conf = entry.compute_confidence()
        assert 0.4 <= conf <= 0.6

    def test_strategy_decays_slow(self):
        entry = MemoryEntry(
            id="t4", content="strategy learning", memory_type="strategy", agent="dev",
            created_at=(datetime.now(UTC) - timedelta(days=30)).isoformat(),
        )
        # After 30 days with 90-day half-life, confidence should be ~0.79
        conf = entry.compute_confidence()
        assert 0.7 <= conf <= 0.9

    def test_roundtrip_dict(self):
        entry = MemoryEntry(
            id="t5", content="test", memory_type="bug", agent="dev",
            tags=["ruff", "lint"], links=["[[IMP-001]]"],
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.id == "t5"
        assert restored.tags == ["ruff", "lint"]
        assert restored.links == ["[[IMP-001]]"]


class TestMemoryStore:

    def test_store_and_retrieve(self, tmp_path: Path):
        store = MemoryStore("test-agent", base_dir=tmp_path)
        entry = store.store("learned something", MemoryType.STRATEGY, tags=["ema"])
        assert store.count == 1
        assert entry.agent == "test-agent"

    def test_persistence(self, tmp_path: Path):
        store1 = MemoryStore("test-agent", base_dir=tmp_path)
        store1.store("fact 1", MemoryType.ARCHITECTURE)

        store2 = MemoryStore("test-agent", base_dir=tmp_path)
        assert store2.count == 1

    def test_search_keyword(self, tmp_path: Path):
        store = MemoryStore("test-agent", base_dir=tmp_path)
        store.store("RSI strategy works well on ETH", MemoryType.STRATEGY, tags=["rsi"])
        store.store("momentum needs volume filter", MemoryType.STRATEGY, tags=["momentum"])
        store.store("architecture decision about Decimal", MemoryType.ARCHITECTURE)

        results = store.search("RSI")
        assert len(results) >= 1
        assert "RSI" in results[0].content

    def test_search_by_tag(self, tmp_path: Path):
        store = MemoryStore("test-agent", base_dir=tmp_path)
        store.store("something about momentum", MemoryType.STRATEGY, tags=["momentum"])
        results = store.search("momentum")
        assert len(results) >= 1

    def test_consolidate_archives_old(self, tmp_path: Path):
        store = MemoryStore("test-agent", base_dir=tmp_path)
        # Add a very old context entry (should be archived)
        old_entry = MemoryEntry(
            id="old1", content="old context", memory_type="context", agent="test",
            created_at=(datetime.now(UTC) - timedelta(days=200)).isoformat(),
        )
        store._entries.append(old_entry)
        store._save()

        # Add a fresh entry (should survive)
        store.store("fresh fact", MemoryType.ARCHITECTURE)

        stats = store.consolidate()
        assert stats["archived"] >= 1
        assert stats["active"] >= 1

    def test_get_by_type(self, tmp_path: Path):
        store = MemoryStore("test-agent", base_dir=tmp_path)
        store.store("bug pattern", MemoryType.BUG)
        store.store("strategy insight", MemoryType.STRATEGY)
        store.store("another bug", MemoryType.BUG)

        bugs = store.get_by_type(MemoryType.BUG)
        assert len(bugs) == 2
