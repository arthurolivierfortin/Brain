"""Persistent pending queue for brain_store calls that fail due to ChromaDB being down.

When ChromaDB is unavailable, store requests are buffered to a JSONL file on disk.
On recovery, entries are drained (replayed) through the normal store pipeline.

The queue file lives at /data/brain_pending.jsonl (brain-data Docker volume) so it
persists across container restarts. File locking via threading.Lock protects against
concurrent access within the same process. Atomic file rewrites via tmp + os.rename
prevent corruption if the process is killed mid-drain.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Use /data in containers (Docker volume), data/ locally
DEFAULT_QUEUE_PATH = (
    Path("/data/brain_pending.jsonl")
    if Path("/data").exists()
    else Path("data/brain_pending.jsonl")
)

DEFAULT_MAX_SIZE = 1000
MAX_DRAIN_ATTEMPTS = 10


class PendingQueue:
    """Thread-safe JSONL-backed queue for failed brain_store requests.

    Entries are appended to a JSONL file. On drain, each entry is passed to a
    store function. Successfully stored entries are removed; failed entries
    remain for the next drain cycle. Entries that fail MAX_DRAIN_ATTEMPTS times
    are discarded to prevent queue poisoning.

    Args:
        path: Path to the JSONL queue file.
        max_size: Maximum number of entries. When exceeded, oldest entries are
            evicted (FIFO) to make room for new ones.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        max_size: int = DEFAULT_MAX_SIZE,
    ) -> None:
        self._path = Path(path) if path else DEFAULT_QUEUE_PATH
        self._max_size = max_size
        self._lock = threading.Lock()
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def enqueue(self, entry: dict[str, Any]) -> bool:
        """Append an entry to the queue.

        Args:
            entry: Dict with at minimum 'content' and 'agent' keys.

        Returns:
            True if enqueued successfully, False on error.
        """
        record = {
            "id": entry.get("id", str(uuid.uuid4())[:12]),
            "content": entry.get("content", ""),
            "agent": entry.get("agent", "unknown"),
            "memory_type": entry.get("memory_type", "context"),
            "metadata": entry.get("metadata"),
            "links": entry.get("links"),
            "skip_gate": entry.get("skip_gate", False),
            "queued_at": datetime.now(UTC).isoformat(),
            "drain_attempts": 0,
        }

        with self._lock:
            try:
                # Read existing entries to check size cap
                entries = self._read_entries()

                # Evict oldest entries (FIFO) if at capacity
                if len(entries) >= self._max_size:
                    evict_count = len(entries) - self._max_size + 1
                    evicted = entries[:evict_count]
                    entries = entries[evict_count:]
                    for ev in evicted:
                        logger.warning(
                            "Queue full (%d), evicting oldest entry: %s",
                            self._max_size,
                            ev.get("id", "?"),
                        )

                entries.append(record)
                self._write_entries(entries)
                logger.info(
                    "Queued brain_store request: id=%s agent=%s (queue size: %d)",
                    record["id"],
                    record["agent"],
                    len(entries),
                )
                return True
            except Exception as e:
                logger.error("Failed to enqueue brain_store request: %s", e)
                return False

    def drain(
        self,
        store_fn: Callable[..., dict | None],
    ) -> dict[str, int]:
        """Replay queued entries through the store function.

        Args:
            store_fn: Callable matching BrainStore.store() signature:
                store_fn(content, agent, memory_type, metadata, links, skip_gate)

        Returns:
            Dict with counts: stored, failed, discarded.
        """
        with self._lock:
            entries = self._read_entries()
            if not entries:
                return {"stored": 0, "failed": 0, "discarded": 0}

            remaining: list[dict] = []
            stats = {"stored": 0, "failed": 0, "discarded": 0}

            for entry in entries:
                attempts = entry.get("drain_attempts", 0) + 1

                if attempts > MAX_DRAIN_ATTEMPTS:
                    logger.warning(
                        "Discarding entry %s after %d failed drain attempts",
                        entry.get("id", "?"),
                        attempts - 1,
                    )
                    stats["discarded"] += 1
                    continue

                try:
                    result = store_fn(
                        content=entry.get("content", ""),
                        agent=entry.get("agent", "unknown"),
                        memory_type=entry.get("memory_type", "context"),
                        metadata=entry.get("metadata"),
                        links=entry.get("links"),
                        skip_gate=entry.get("skip_gate", False),
                    )
                    # store_fn returns None if rejected by gate, dict on success
                    # Both cases mean the entry was processed -- remove from queue
                    if result is not None:
                        stats["stored"] += 1
                        logger.info(
                            "Drained entry %s successfully (id=%s)",
                            entry.get("id", "?"),
                            result.get("id", "?"),
                        )
                    else:
                        # Gate rejected it -- don't retry, just count as stored
                        stats["stored"] += 1
                        logger.info(
                            "Drained entry %s (rejected by gate, removing from queue)",
                            entry.get("id", "?"),
                        )
                except Exception as e:
                    logger.warning(
                        "Drain failed for entry %s (attempt %d): %s",
                        entry.get("id", "?"),
                        attempts,
                        e,
                    )
                    entry["drain_attempts"] = attempts
                    remaining.append(entry)
                    stats["failed"] += 1

            # Atomically rewrite file with only the failed entries
            self._write_entries(remaining)

            if stats["stored"] > 0 or stats["discarded"] > 0:
                logger.info(
                    "Queue drain complete: stored=%d, failed=%d, discarded=%d, remaining=%d",
                    stats["stored"],
                    stats["failed"],
                    stats["discarded"],
                    len(remaining),
                )

            return stats

    def pending_count(self) -> int:
        """Return the number of entries currently in the queue."""
        with self._lock:
            return len(self._read_entries())

    def clear(self) -> None:
        """Remove all entries from the queue."""
        with self._lock:
            self._write_entries([])

    def _read_entries(self) -> list[dict]:
        """Read all entries from the JSONL file (caller must hold _lock)."""
        if not self._path.exists():
            return []

        entries = []
        try:
            with open(self._path) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(
                            "Malformed JSON at %s line %d, skipping",
                            self._path,
                            line_num,
                        )
        except OSError as e:
            logger.error("Failed to read queue file %s: %s", self._path, e)

        return entries

    def _write_entries(self, entries: list[dict]) -> None:
        """Atomically rewrite the queue file (caller must hold _lock).

        Uses write-to-tmpfile + os.replace for atomicity (works on both Linux and Windows).
        """
        try:
            # Write to temp file in the same directory (same filesystem for atomic rename)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._path.parent),
                prefix=".brain_pending_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w") as f:
                    for entry in entries:
                        f.write(json.dumps(entry, default=str) + "\n")
                os.replace(tmp_path, str(self._path))
            except Exception:
                # Clean up temp file on error
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise
        except Exception as e:
            logger.error("Failed to write queue file %s: %s", self._path, e)
            raise
