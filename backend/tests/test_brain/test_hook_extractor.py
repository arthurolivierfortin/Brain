"""Unit tests for GeminiFlashExtractor — httpx mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from brain.hook import ExtractedMemory, GeminiFlashExtractor, Turn


def _gemini_response(memories: list[dict]) -> MagicMock:
    text = json.dumps({"memories": memories})
    resp = MagicMock()
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
    }
    resp.raise_for_status = MagicMock()
    return resp


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GeminiFlashExtractor()


def test_parses_memories_from_response(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.return_value = _gemini_response([
        {"content": "User prefers French", "type": "preference",
         "tags": ["preference", "communication"], "confidence": 0.95},
        {"content": "Fixed bug #12", "type": "bug-fix",
         "tags": ["backend"], "confidence": 1.0},
    ])
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    turn = Turn(user="u", assistant="a", tool_calls=[])
    memories = ext.extract(turn)
    assert len(memories) == 2
    assert memories[0] == ExtractedMemory(
        content="User prefers French", type="preference",
        tags=["preference", "communication"], confidence=0.95,
    )


def test_returns_empty_on_http_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.side_effect = RuntimeError("boom")
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    assert ext.extract(Turn(user="u", assistant="a")) == []


def test_returns_empty_on_malformed_json(monkeypatch):
    fake_client = MagicMock()
    broken = MagicMock()
    broken.json.return_value = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
    broken.raise_for_status = MagicMock()
    fake_client.post.return_value = broken
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    assert ext.extract(Turn(user="u", assistant="a")) == []


def test_skips_malformed_memory_entries(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.return_value = _gemini_response([
        {"content": "ok", "type": "fact", "tags": [], "confidence": 0.8},
        {"type": "fact", "tags": [], "confidence": 0.8},  # missing content
        "not a dict",
    ])
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    memories = ext.extract(Turn(user="u", assistant="a"))
    assert len(memories) == 1
    assert memories[0].content == "ok"


def test_prompt_includes_user_assistant_and_tool_calls(monkeypatch):
    fake_client = MagicMock()
    fake_client.post.return_value = _gemini_response([])
    ext = GeminiFlashExtractor(api_key="fake", _client=fake_client)
    turn = Turn(
        user="fix the bug",
        assistant="done",
        tool_calls=[{"name": "Bash", "input": "pytest"}],
    )
    ext.extract(turn)
    call_kwargs = fake_client.post.call_args.kwargs
    body = call_kwargs["json"]
    prompt_text = body["contents"][0]["parts"][0]["text"]
    assert "USER: fix the bug" in prompt_text
    assert "ASSISTANT: done" in prompt_text
    assert "TOOL: Bash" in prompt_text
