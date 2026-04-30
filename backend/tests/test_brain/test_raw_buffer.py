"""Tests for the L1 raw episodic buffer (Phase 2c.1)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from brain.raw_buffer import RawBuffer, RawEvent


def _build_event(
    *,
    timestamp: datetime | None = None,
    kind: str = "user_message",
    content: str = "hello brain",
    agent: str = "brain",
    session_id: str = "s1",
    project: str = "/x",
    tool_name: str | None = None,
    tool_input: dict | None = None,
    tool_output_excerpt: str | None = None,
) -> RawEvent:
    return RawEvent(
        timestamp=timestamp or datetime.now(UTC),
        kind=kind,
        agent=agent,
        session_id=session_id,
        project=project,
        content=content,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_output_excerpt=tool_output_excerpt,
    )


def test_append_writes_jsonl_line(tmp_path: Path):
    buf = RawBuffer(tmp_path)
    ts = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
    event = _build_event(timestamp=ts, content="hello brain")
    buf.append(event)
    buf.flush()

    expected = tmp_path / "brain_raw_buffer.2026-04-30.jsonl"
    assert expected.exists()
    lines = expected.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == "user_message"
    assert parsed["content"] == "hello brain"
    assert parsed["agent"] == "brain"
    assert parsed["session_id"] == "s1"
    assert parsed["project"] == "/x"
    assert "event_id" in parsed and len(parsed["event_id"]) > 0
    assert parsed["timestamp"].startswith("2026-04-30T12:00:00")


def test_list_since_filters_by_timestamp(tmp_path: Path):
    buf = RawBuffer(tmp_path)
    base = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
    events = [
        _build_event(timestamp=base + timedelta(minutes=i), content=f"msg{i}")
        for i in range(5)
    ]
    for e in events:
        buf.append(e)
    buf.flush()

    cutoff = events[2].timestamp
    out = buf.list_since(cutoff)
    contents = sorted(e.content for e in out)
    assert contents == ["msg2", "msg3", "msg4"]


def test_rotate_if_needed_creates_new_file_at_midnight(tmp_path: Path):
    buf = RawBuffer(tmp_path)

    day1 = datetime(2026, 4, 30, 23, 59, 0, tzinfo=UTC)
    buf.append(_build_event(timestamp=day1, content="late night"))
    buf.flush()

    day2 = datetime(2026, 5, 1, 0, 0, 30, tzinfo=UTC)
    with patch("brain.raw_buffer._now_utc", return_value=day2):
        buf.rotate_if_needed()
        buf.append(_build_event(timestamp=day2, content="new day"))
        buf.flush()

    f1 = tmp_path / "brain_raw_buffer.2026-04-30.jsonl"
    f2 = tmp_path / "brain_raw_buffer.2026-05-01.jsonl"
    assert f1.exists()
    assert f2.exists()
    assert "late night" in f1.read_text(encoding="utf-8")
    assert "new day" in f2.read_text(encoding="utf-8")


def test_purge_older_than_drops_old_files(tmp_path: Path):
    for date_str in ("2026-04-20", "2026-04-21", "2026-04-25", "2026-04-30"):
        (tmp_path / f"brain_raw_buffer.{date_str}.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "unrelated.jsonl").write_text("nope\n", encoding="utf-8")

    buf = RawBuffer(tmp_path)
    now = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
    with patch("brain.raw_buffer._now_utc", return_value=now):
        deleted = buf.purge_older_than(7)

    assert deleted == 2
    assert not (tmp_path / "brain_raw_buffer.2026-04-20.jsonl").exists()
    assert not (tmp_path / "brain_raw_buffer.2026-04-21.jsonl").exists()
    assert (tmp_path / "brain_raw_buffer.2026-04-25.jsonl").exists()
    assert (tmp_path / "brain_raw_buffer.2026-04-30.jsonl").exists()
    assert (tmp_path / "unrelated.jsonl").exists()


def test_redaction_strips_secrets(tmp_path: Path):
    buf = RawBuffer(tmp_path)
    ts = datetime(2026, 4, 30, 12, 0, 0, tzinfo=UTC)
    event = _build_event(
        timestamp=ts,
        content="api_key=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123",
        tool_output_excerpt="token=abcdefghij1234567890ZZZZ",
    )
    buf.append(event)
    buf.flush()

    f = tmp_path / "brain_raw_buffer.2026-04-30.jsonl"
    text = f.read_text(encoding="utf-8")
    assert "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123" not in text
    assert "abcdefghij1234567890ZZZZ" not in text
    assert "<redacted>" in text


def test_raw_event_pydantic_validation():
    with pytest.raises(Exception):
        RawEvent(
            timestamp=datetime.now(UTC),
            kind="not_a_valid_kind",  # type: ignore[arg-type]
            agent="a",
            session_id="s",
            project="/p",
            content="x",
        )
