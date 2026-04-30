"""L1 raw episodic buffer (Phase 2c.1).

Append-only JSONL store with daily rotation and 7-day TTL purge. Keeps
every user prompt, assistant turn and tool-use entry verbatim, separate
from the Gemini-extracted L2 layer in ChromaDB.

Concurrency model: a single dedicated daemon thread drains a SimpleQueue
of pending writes. Callers (`append`) never block on disk I/O. No fcntl,
no msvcrt — single-thread serialization keeps Windows + Linux identical.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_FILE_PREFIX = "brain_raw_buffer."
_FILE_SUFFIX = ".jsonl"
_FILE_DATE_RE = re.compile(r"^brain_raw_buffer\.(\d{4}-\d{2}-\d{2})\.jsonl$")

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key\s*=\s*)[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(apikey\s*=\s*)[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(key\s*=\s*)[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(token\s*=\s*)[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(password\s*=\s*)[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9_\-\.]{20,}"),
)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _redact(text: str) -> str:
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(r"\1<redacted>", out)
    return out


RawEventKind = Literal["user_message", "assistant_message", "tool_use"]


class RawEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime
    kind: RawEventKind
    agent: str
    session_id: str
    project: str
    content: str
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output_excerpt: str | None = None
    metadata: dict = Field(default_factory=dict)


class RawBuffer:
    """Daily-rotated JSONL append store with single-thread write queue."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._queue: queue.SimpleQueue[tuple[RawEvent | None, threading.Event | None]] = queue.SimpleQueue()
        self._current_day: date | None = None
        self._stopped = threading.Event()
        self._writer = threading.Thread(
            target=self._run, name="raw-buffer-writer", daemon=True,
        )
        self._writer.start()

    def append(self, event: RawEvent) -> None:
        redacted = event.model_copy(update={
            "content": _redact(event.content),
            "tool_output_excerpt": (
                _redact(event.tool_output_excerpt)
                if event.tool_output_excerpt is not None else None
            ),
        })
        self._queue.put((redacted, None))

    def flush(self, timeout: float = 5.0) -> None:
        """Block until the writer thread has drained outstanding events."""
        done = threading.Event()
        self._queue.put((None, done))
        if not done.wait(timeout=timeout):
            logger.warning("RawBuffer.flush timed out")

    def list_since(self, ts: datetime, limit: int = 1000) -> list[RawEvent]:
        out: list[RawEvent] = []
        for path in sorted(self._root.glob(f"{_FILE_PREFIX}*{_FILE_SUFFIX}")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            event = RawEvent.model_validate(data)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if event.timestamp >= ts:
                            out.append(event)
                            if len(out) >= limit:
                                return out
            except OSError as e:
                logger.warning("list_since failed to read %s: %s", path, e)
        return out

    def rotate_if_needed(self) -> Path | None:
        today = _now_utc().date()
        if self._current_day != today:
            self._current_day = today
            return self._path_for(today)
        return None

    def purge_older_than(self, days: int) -> int:
        cutoff = (_now_utc() - timedelta(days=days)).date()
        deleted = 0
        for path in self._root.glob(f"{_FILE_PREFIX}*{_FILE_SUFFIX}"):
            m = _FILE_DATE_RE.match(path.name)
            if not m:
                continue
            try:
                file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    path.unlink()
                    deleted += 1
                except OSError as e:
                    logger.warning("purge failed for %s: %s", path, e)
        return deleted

    def stop(self) -> None:
        self._queue.put((None, None))
        self._stopped.set()
        self._writer.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            event, done = self._queue.get()
            if event is None:
                if done is not None:
                    done.set()
                    continue
                return
            try:
                self._write_one(event)
            except Exception as e:
                logger.warning("RawBuffer write failed: %s", e)

    def _write_one(self, event: RawEvent) -> None:
        day = event.timestamp.astimezone(UTC).date()
        path = self._path_for(day)
        with path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
            f.flush()

    def _path_for(self, day: date) -> Path:
        return self._root / f"{_FILE_PREFIX}{day.isoformat()}{_FILE_SUFFIX}"
