from __future__ import annotations

from brain_bench.adapters.no_memory import NoMemoryAdapter
from brain_bench.types import Session, Turn


def test_retrieve_always_empty() -> None:
    adapter = NoMemoryAdapter()
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="I love sailing")],
    ))
    assert adapter.retrieve("sailing", k=5) == []


def test_reset_and_ingest_are_noops() -> None:
    adapter = NoMemoryAdapter()
    adapter.reset()
    adapter.ingest(Session(session_id="s1", session_date="2025-01-01", turns=[]))
    adapter.reset()
    assert adapter.retrieve("anything", k=10) == []


def test_conforms_to_adapter_protocol() -> None:
    from brain_bench.adapters.base import Adapter
    adapter: Adapter = NoMemoryAdapter()
    assert adapter.retrieve("q") == []
