"""Brain event log -- append-only record of all brain activity.

Every store, search, reinforce, merge, archive, and connection event
is logged here. The dashboard reads this log to show the brain evolving.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path("data/brain_events.jsonl")


@dataclass
class BrainEvent:
    """A single brain event."""

    event_type: str   # stored, searched, reinforced, merged, archived, connected
    timestamp: str
    agent: str = ""
    node_id: str = ""
    details: str = ""
    metadata: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["metadata"] is None:
            del d["metadata"]
        return d


class EventLog:
    """Append-only event log for brain activity tracking."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_LOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        event_type: str,
        agent: str = "",
        node_id: str = "",
        details: str = "",
        metadata: dict | None = None,
    ) -> BrainEvent:
        """Append an event to the log."""
        event = BrainEvent(
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            agent=agent,
            node_id=node_id,
            details=details,
            metadata=metadata,
        )
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except OSError as e:
            logger.error("Failed to write brain event: %s", e)
        return event

    def recent(self, limit: int = 50) -> list[dict]:
        """Read the most recent events."""
        if not self._path.exists():
            return []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            events = []
            for line in lines[-limit:]:
                if line.strip():
                    events.append(json.loads(line))
            return events
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read brain events: %s", e)
            return []

    def stats_over_time(self, buckets: int = 24) -> list[dict]:
        """Aggregate event counts into time buckets for timeline charts."""
        events = self.recent(limit=5000)
        if not events:
            return []

        now = time.time()
        bucket_size = 3600  # 1 hour per bucket
        result: list[dict] = []

        for i in range(buckets):
            bucket_start = now - (buckets - i) * bucket_size
            bucket_end = bucket_start + bucket_size
            bucket_events = [
                e for e in events
                if bucket_start <= _parse_ts(e.get("timestamp", "")) < bucket_end
            ]
            result.append({
                "hour": i - buckets,
                "stored": sum(1 for e in bucket_events if e["event_type"] == "stored"),
                "searched": sum(1 for e in bucket_events if e["event_type"] == "searched"),
                "reinforced": sum(1 for e in bucket_events if e["event_type"] == "reinforced"),
                "merged": sum(1 for e in bucket_events if e["event_type"] == "merged"),
                "archived": sum(1 for e in bucket_events if e["event_type"] == "archived"),
            })
        return result


def _parse_ts(ts: str) -> float:
    """Parse ISO timestamp to epoch seconds."""
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, AttributeError):
        return 0.0
