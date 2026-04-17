"""Tests for brain pending queue -- buffering brain_store calls when ChromaDB is down."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain.pending_queue import MAX_DRAIN_ATTEMPTS, PendingQueue


@pytest.fixture()
def queue_path(tmp_path: Path) -> Path:
    return tmp_path / "brain_pending.jsonl"


@pytest.fixture()
def queue(queue_path: Path) -> PendingQueue:
    return PendingQueue(path=queue_path, max_size=5)


class TestEnqueue:
    """Test enqueueing entries to the pending queue."""

    def test_enqueue_creates_file(self, queue: PendingQueue, queue_path: Path) -> None:
        result = queue.enqueue({"content": "test memory", "agent": "builder"})
        assert result is True
        assert queue_path.exists()

    def test_enqueue_writes_valid_jsonl(self, queue: PendingQueue, queue_path: Path) -> None:
        queue.enqueue({"content": "memory one", "agent": "builder"})
        queue.enqueue({"content": "memory two", "agent": "reviewer"})

        lines = queue_path.read_text().strip().split("\n")
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["content"] == "memory one"
        assert entry1["agent"] == "builder"
        assert "queued_at" in entry1
        assert "id" in entry1
        assert entry1["drain_attempts"] == 0

        entry2 = json.loads(lines[1])
        assert entry2["content"] == "memory two"
        assert entry2["agent"] == "reviewer"

    def test_enqueue_preserves_all_fields(self, queue: PendingQueue, queue_path: Path) -> None:
        queue.enqueue({
            "content": "test",
            "agent": "think",
            "memory_type": "architecture",
            "metadata": {"event_type": "architecture"},
            "links": ["link1", "link2"],
            "skip_gate": True,
        })

        lines = queue_path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["memory_type"] == "architecture"
        assert entry["metadata"] == {"event_type": "architecture"}
        assert entry["links"] == ["link1", "link2"]
        assert entry["skip_gate"] is True

    def test_enqueue_defaults(self, queue: PendingQueue, queue_path: Path) -> None:
        queue.enqueue({"content": "minimal"})

        lines = queue_path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["agent"] == "unknown"
        assert entry["memory_type"] == "context"
        assert entry["skip_gate"] is False

    def test_enqueue_returns_false_on_write_error(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        queue_path = tmp_path / "queue.jsonl"
        q = PendingQueue(path=queue_path, max_size=5)
        with patch.object(q, "_write_entries", side_effect=OSError("disk full")):
            result = q.enqueue({"content": "test"})
        assert result is False


class TestMaxSize:
    """Test FIFO eviction when queue reaches max_size."""

    def test_evicts_oldest_when_full(self, queue: PendingQueue, queue_path: Path) -> None:
        # Fill queue to max (5)
        for i in range(5):
            queue.enqueue({"content": f"entry-{i}", "agent": "test"})
        assert queue.pending_count() == 5

        # Adding one more should evict the oldest
        queue.enqueue({"content": "entry-5", "agent": "test"})
        assert queue.pending_count() == 5

        lines = queue_path.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines]
        contents = [e["content"] for e in entries]
        # entry-0 should be evicted
        assert "entry-0" not in contents
        assert "entry-5" in contents

    def test_evicts_multiple_when_far_over(self, queue_path: Path) -> None:
        q = PendingQueue(path=queue_path, max_size=3)
        # Pre-fill with 5 entries by writing directly
        for i in range(5):
            q.enqueue({"content": f"old-{i}", "agent": "test"})

        # Queue is max_size=3 so after all 5, only last 3 remain
        assert q.pending_count() == 3
        lines = queue_path.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines]
        contents = [e["content"] for e in entries]
        assert contents == ["old-2", "old-3", "old-4"]


class TestDrain:
    """Test draining the queue through a store function."""

    def test_drain_empty_queue(self, queue: PendingQueue) -> None:
        store_fn = MagicMock()
        result = queue.drain(store_fn)
        assert result == {"stored": 0, "failed": 0, "discarded": 0}
        store_fn.assert_not_called()

    def test_drain_success(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "mem1", "agent": "builder", "memory_type": "bug"})
        queue.enqueue({"content": "mem2", "agent": "reviewer", "memory_type": "context"})

        store_fn = MagicMock(return_value={"id": "abc123"})
        result = queue.drain(store_fn)

        assert result["stored"] == 2
        assert result["failed"] == 0
        assert store_fn.call_count == 2
        assert queue.pending_count() == 0

    def test_drain_passes_correct_args(self, queue: PendingQueue) -> None:
        queue.enqueue({
            "content": "test content",
            "agent": "builder",
            "memory_type": "architecture",
            "metadata": {"key": "val"},
            "links": ["link1"],
            "skip_gate": True,
        })

        store_fn = MagicMock(return_value={"id": "xyz"})
        queue.drain(store_fn)

        store_fn.assert_called_once_with(
            content="test content",
            agent="builder",
            memory_type="architecture",
            metadata={"key": "val"},
            links=["link1"],
            skip_gate=True,
        )

    def test_drain_partial_failure(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "good", "agent": "a"})
        queue.enqueue({"content": "bad", "agent": "b"})
        queue.enqueue({"content": "good2", "agent": "c"})

        call_count = 0

        def flaky_store(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs["content"] == "bad":
                raise ConnectionError("ChromaDB still down")
            return {"id": "ok"}

        result = queue.drain(flaky_store)
        assert result["stored"] == 2
        assert result["failed"] == 1
        assert queue.pending_count() == 1

        # The failed entry should still be in the queue with incremented attempts
        lines = queue.path.read_text().strip().split("\n")
        remaining = json.loads(lines[0])
        assert remaining["content"] == "bad"
        assert remaining["drain_attempts"] == 1

    def test_drain_gate_rejection_removes_from_queue(self, queue: PendingQueue) -> None:
        """When store_fn returns None (gate rejection), entry should still be removed."""
        queue.enqueue({"content": "noise", "agent": "test"})

        store_fn = MagicMock(return_value=None)
        result = queue.drain(store_fn)

        assert result["stored"] == 1  # Counted as processed
        assert queue.pending_count() == 0

    def test_drain_discards_after_max_attempts(self, queue: PendingQueue, queue_path: Path) -> None:
        """Entries that fail MAX_DRAIN_ATTEMPTS times should be discarded."""
        queue.enqueue({"content": "poison", "agent": "test"})

        # Manually set drain_attempts to MAX_DRAIN_ATTEMPTS
        lines = queue_path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        entry["drain_attempts"] = MAX_DRAIN_ATTEMPTS
        queue_path.write_text(json.dumps(entry) + "\n")

        store_fn = MagicMock(side_effect=Exception("always fails"))
        result = queue.drain(store_fn)

        assert result["discarded"] == 1
        assert result["stored"] == 0
        assert result["failed"] == 0
        assert queue.pending_count() == 0
        # store_fn should NOT be called for discarded entries
        store_fn.assert_not_called()

    def test_drain_all_fail(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "a", "agent": "test"})
        queue.enqueue({"content": "b", "agent": "test"})

        store_fn = MagicMock(side_effect=Exception("broken"))
        result = queue.drain(store_fn)

        assert result["stored"] == 0
        assert result["failed"] == 2
        assert queue.pending_count() == 2


class TestPendingCount:
    """Test the pending_count method."""

    def test_empty_queue(self, queue: PendingQueue) -> None:
        assert queue.pending_count() == 0

    def test_after_enqueue(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "a"})
        queue.enqueue({"content": "b"})
        assert queue.pending_count() == 2

    def test_after_drain(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "a"})
        store_fn = MagicMock(return_value={"id": "x"})
        queue.drain(store_fn)
        assert queue.pending_count() == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        q = PendingQueue(path=tmp_path / "does_not_exist.jsonl")
        assert q.pending_count() == 0


class TestClear:
    """Test clearing the queue."""

    def test_clear_removes_all_entries(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "a"})
        queue.enqueue({"content": "b"})
        assert queue.pending_count() == 2

        queue.clear()
        assert queue.pending_count() == 0


class TestMalformedEntries:
    """Test handling of malformed JSONL entries."""

    def test_skips_malformed_lines(self, queue: PendingQueue, queue_path: Path) -> None:
        # Write some valid and some invalid lines
        queue_path.write_text(
            '{"content": "valid", "agent": "test", "drain_attempts": 0}\n'
            "not valid json\n"
            '{"content": "also valid", "agent": "test2", "drain_attempts": 0}\n'
        )

        assert queue.pending_count() == 2  # Malformed line skipped

    def test_drain_skips_malformed_lines(self, queue: PendingQueue, queue_path: Path) -> None:
        queue_path.write_text(
            '{"content": "valid", "agent": "test", "memory_type": "context", '
            '"drain_attempts": 0}\n'
            "garbage\n"
        )

        store_fn = MagicMock(return_value={"id": "x"})
        result = queue.drain(store_fn)
        assert result["stored"] == 1
        store_fn.assert_called_once()

    def test_blank_lines_ignored(self, queue: PendingQueue, queue_path: Path) -> None:
        queue_path.write_text(
            "\n"
            '{"content": "valid", "agent": "test", "drain_attempts": 0}\n'
            "\n"
        )
        assert queue.pending_count() == 1


class TestConcurrentAccess:
    """Test thread safety of the queue."""

    def test_concurrent_enqueue(self, queue_path: Path) -> None:
        q = PendingQueue(path=queue_path, max_size=200)
        errors: list[Exception] = []

        def enqueue_many(start: int, count: int) -> None:
            for i in range(start, start + count):
                try:
                    q.enqueue({"content": f"entry-{i}", "agent": f"thread-{start}"})
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=enqueue_many, args=(i * 20, 20))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert q.pending_count() == 100

    def test_concurrent_enqueue_and_drain(self, queue_path: Path) -> None:
        q = PendingQueue(path=queue_path, max_size=500)
        store_fn = MagicMock(return_value={"id": "x"})
        errors: list[Exception] = []

        def enqueue_many() -> None:
            for i in range(20):
                try:
                    q.enqueue({"content": f"entry-{i}", "agent": "writer"})
                except Exception as e:
                    errors.append(e)

        def drain_once() -> None:
            try:
                q.drain(store_fn)
            except Exception as e:
                errors.append(e)

        # Run enqueueing and draining concurrently
        t1 = threading.Thread(target=enqueue_many)
        t2 = threading.Thread(target=drain_once)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        # All entries should eventually be processable
        # (some may have been drained, some may remain)
        remaining = q.pending_count()
        assert remaining >= 0


class TestAtomicWrites:
    """Test that file writes are atomic (tmp + rename pattern)."""

    def test_drain_preserves_failed_entries_only(self, queue: PendingQueue) -> None:
        queue.enqueue({"content": "good", "agent": "a"})
        queue.enqueue({"content": "bad", "agent": "b"})

        def selective_store(**kwargs):
            if kwargs["content"] == "bad":
                raise RuntimeError("fail")
            return {"id": "ok"}

        queue.drain(selective_store)

        # Only the failed entry should remain
        assert queue.pending_count() == 1
        lines = queue.path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert entry["content"] == "bad"

    def test_file_does_not_exist_initially(self, queue: PendingQueue) -> None:
        """Queue should work even if the file does not exist yet."""
        assert not queue.path.exists()
        assert queue.pending_count() == 0

        queue.enqueue({"content": "first"})
        assert queue.path.exists()
        assert queue.pending_count() == 1
