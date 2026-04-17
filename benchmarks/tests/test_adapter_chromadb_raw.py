from __future__ import annotations

from pathlib import Path

from brain_bench.adapters.chromadb_raw import ChromaDBRawAdapter
from brain_bench.types import Session, Turn


def test_ingest_and_retrieve_roundtrip(tmp_path: Path):
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chromadb")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[
            Turn(role="user", content="I love sailing on Lake Michigan"),
            Turn(role="assistant", content="Great hobby."),
        ],
    ))
    mems = adapter.retrieve("sailing", k=5)
    assert len(mems) >= 1
    assert any("sailing" in m.content.lower() for m in mems)


def test_reset_clears_collection(tmp_path: Path):
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chromadb")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="some content")],
    ))
    assert len(adapter.retrieve("content", k=5)) >= 1
    adapter.reset()
    assert adapter.retrieve("content", k=5) == []


def test_score_is_similarity_not_distance(tmp_path: Path):
    """ChromaDB returns distances by default; adapter converts to similarity."""
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chromadb")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="The sky is blue")],
    ))
    mems = adapter.retrieve("sky is blue", k=1)
    assert 0.0 <= mems[0].score <= 1.0
    assert mems[0].score > 0.5  # close match → high similarity
