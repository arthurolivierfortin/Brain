"""Integration tests — full L2 pipeline against real ChromaDB with seeded fixture."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.events import EventLog  # noqa: E402
from brain.hook import HookRequest, WakeUpHandler  # noqa: E402
from brain.store import BrainStore  # noqa: E402

_FIXTURE_MEMORIES = [
    ("FastAPI route testing with pytest and httpx", "backend"),
    ("SQLite WAL mode enables concurrent readers", "backend"),
    ("ChromaDB cosine distance space for embeddings", "backend"),
    ("Python ruff linter enforces no trailing whitespace", "tooling"),
    ("Docker compose explicit name prevents orphan collision", "docker"),
    ("Git branch naming convention: feat/NNN-slug", "git"),
    ("Gemini Flash 2.5 used for memory extraction", "llm"),
    ("Brain event log is append-only JSONL", "backend"),
    ("French-first communication style", "identity"),
    ("No backwards-compat shims without approval", "preference"),
]


def _seed_fixture(store: BrainStore, agent: str = "fixture-agent") -> None:
    for content, tag in _FIXTURE_MEMORIES:
        store.store(content, agent=agent, memory_type="fact",
                    metadata={"tags": tag}, skip_gate=True)


def test_full_l2_pipeline_against_real_chromadb(tmp_path: Path) -> None:
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    events = EventLog(path=tmp_path / "events.jsonl")
    _seed_fixture(store)

    handler = WakeUpHandler(store, events)
    req = HookRequest(
        agent="test-requester",
        project="/brain",
        session_id="integration-1",
        git_branch="feat/backend-api",
        git_recent_commits="add FastAPI route for backend HTTP search endpoint",
        claude_md_excerpt="Python backend (FastAPI), ChromaDB storage",
    )
    resp = handler.handle(req)

    assert resp.layers_loaded["L2"] >= 1
    assert "## Topic" in resp.context
    for m in resp.topic:
        assert "distance" in m
        assert 0.0 <= m["distance"] <= 2.0
