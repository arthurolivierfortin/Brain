"""Unit tests for brain_post_turn.py (Stop hook, replacement for brain_hook.py)."""
from __future__ import annotations

import json
from pathlib import Path

import brain_post_turn as hook


def test_parse_transcript_into_turn_extracts_latest_user_and_assistant(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "first message"}) + "\n"
        + json.dumps({"role": "assistant", "content": "first reply"}) + "\n"
        + json.dumps({"role": "user", "content": "second message"}) + "\n"
        + json.dumps({"role": "assistant", "content": "second reply"}) + "\n",
        encoding="utf-8",
    )
    turn = hook.parse_delta_to_turn(transcript, offset=0)
    assert turn["user"] == "second message"
    assert turn["assistant"] == "second reply"


def test_parse_transcript_honors_offset(tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    line1 = json.dumps({"role": "user", "content": "old"}) + "\n"
    line2 = json.dumps({"role": "user", "content": "new"}) + "\n"
    transcript.write_text(line1 + line2, encoding="utf-8")
    offset = len(line1.encode("utf-8"))
    turn = hook.parse_delta_to_turn(transcript, offset=offset)
    assert turn["user"] == "new"


def test_main_posts_structured_turn(monkeypatch, tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "do X " * 40}) + "\n"
        + json.dumps({"role": "assistant", "content": "done " * 40}) + "\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    pending = tmp_path / "pending.jsonl"

    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["body"] = json
        return _FakeResp(200, {"extracted": [], "rejected_by_gate": 0,
                               "extraction_cost_usd": 0.0, "extraction_ms": 10})
    monkeypatch.setattr(hook.httpx, "post", fake_post)

    rc = hook.main(
        stdin_data=json.dumps({"session_id": "s1",
                               "transcript_path": str(transcript),
                               "cwd": "C:/Brain"}),
        state_dir=state_dir, pending_path=pending,
    )
    assert rc is True
    assert "/hook/post_turn" in captured["url"]
    assert captured["body"]["agent"] == "brain"
    assert captured["body"]["turn"]["user"].startswith("do X")
    assert captured["body"]["turn"]["assistant"].startswith("done")


def test_main_enqueues_on_brain_down(monkeypatch, tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "a" * 200}) + "\n"
        + json.dumps({"role": "assistant", "content": "b" * 200}) + "\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    pending = tmp_path / "pending.jsonl"

    def _raise(*a, **kw):
        raise RuntimeError("down")
    monkeypatch.setattr(hook.httpx, "post", _raise)

    hook.main(
        stdin_data=json.dumps({"session_id": "s1",
                               "transcript_path": str(transcript),
                               "cwd": "C:/Brain"}),
        state_dir=state_dir, pending_path=pending,
    )
    assert pending.exists()
    lines = [line for line in pending.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1


def test_main_skips_under_min_delta(monkeypatch, tmp_path: Path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "content": "hi"}) + "\n",
        encoding="utf-8",
    )
    called: list[int] = []

    def _tracking_post(*a, **kw):
        called.append(1)
        return _FakeResp(200, {})
    monkeypatch.setattr(hook.httpx, "post", _tracking_post)

    hook.main(
        stdin_data=json.dumps({"session_id": "s1",
                               "transcript_path": str(transcript),
                               "cwd": "C:/Brain"}),
        state_dir=tmp_path / "state", pending_path=tmp_path / "p.jsonl",
    )
    assert called == []


class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
