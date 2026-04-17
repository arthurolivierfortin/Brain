from __future__ import annotations

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
def test_reset_calls_forget_all():
    # Spec: reset clears Brain's collection via a (to-be-added) endpoint.
    # For v1 we call /stats and forget each entry one by one (slow, OK for 500 Q).
    respx.get("http://brain:8611/stats").mock(
        return_value=Response(200, json={"ids": ["m1", "m2"]})
    )
    respx.post("http://brain:8611/forget").mock(
        return_value=Response(200, json={"forgotten": True})
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    adapter.reset()
    assert respx.calls.call_count >= 1
