from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from brain_bench.adapters.brain import BrainAdapter
from brain_bench.types import Session, Turn


@respx.mock
def test_ingest_posts_each_turn():
    respx.post("http://brain:8611/store").mock(
        return_value=Response(200, json={"stored": True, "id": "m1"})
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="hi"), Turn(role="assistant", content="hey")],
    ))
    assert respx.calls.call_count == 2
    body = json.loads(respx.calls[0].request.content)
    assert body["skip_gate"] is True
    assert body["agent"] == "longmemeval"
    assert body["memory_type"] == "context"


@respx.mock
def test_retrieve_returns_memories():
    respx.get("http://brain:8611/search").mock(
        return_value=Response(200, json={
            "results": [
                {"id": "m1", "content": "hi", "score": 0.9,
                 "metadata": {"session_id": "s1"}},
                {"id": "m2", "content": "hello", "score": 0.7,
                 "metadata": {"session_id": "s1"}},
            ],
            "count": 2,
        })
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    memories = adapter.retrieve("greetings", k=5)
    assert len(memories) == 2
    assert memories[0].id == "m1"
    assert memories[0].score == pytest.approx(0.9)
    assert memories[0].session_id == "s1"


@respx.mock
def test_reset_posts_to_reset_endpoint_scoped_to_agent():
    respx.post("http://brain:8611/reset").mock(
        return_value=Response(200, json={"deleted": 7, "agent": "longmemeval"})
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    adapter.reset()
    assert respx.calls.call_count == 1
    body = json.loads(respx.calls[0].request.content)
    assert body == {"agent": "longmemeval"}


@respx.mock
def test_reset_raises_on_http_error():
    """A silent reset failure would poison benchmark integrity (leaky state)."""
    from httpx import HTTPStatusError
    respx.post("http://brain:8611/reset").mock(
        return_value=Response(500, json={"error": "boom"})
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    with pytest.raises(HTTPStatusError):
        adapter.reset()
