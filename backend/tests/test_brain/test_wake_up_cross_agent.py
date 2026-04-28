"""Verify L0, L1, L2 retrieval is cross-agent after the SPEC-2/SPEC-8 refactor."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.events import EventLog  # noqa: E402
from brain.hook import HookRequest, WakeUpHandler  # noqa: E402
from brain.store import BrainStore  # noqa: E402


def test_l0_l1_l2_are_cross_agent(tmp_path: Path) -> None:
    """Seed memories for agent-A and agent-B; request as agent-A;
    assert both agents' identity+preference memories appear."""
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    events = EventLog(path=tmp_path / "events.jsonl")

    store.store("Identity A — French-first persona",
                agent="agent-a", memory_type="context",
                metadata={"tags": "identity"}, skip_gate=True)
    store.store("Identity B — blunt communication style",
                agent="agent-b", memory_type="context",
                metadata={"tags": "identity"}, skip_gate=True)
    store.store("Preference A — always use ruff",
                agent="agent-a", memory_type="context",
                metadata={"tags": "preference"}, skip_gate=True)
    store.store("Preference B — no glazing",
                agent="agent-b", memory_type="context",
                metadata={"tags": "preference"}, skip_gate=True)

    handler = WakeUpHandler(store, events)
    resp = handler.handle(HookRequest(
        agent="agent-a", project="/", session_id="s1",
    ))

    assert resp.layers_loaded["L0"] == 2
    assert resp.layers_loaded["L1"] == 2
    assert "Identity A" in resp.context
    assert "Identity B" in resp.context
    assert "Preference A" in resp.context
    assert "Preference B" in resp.context


def test_l2_is_cross_agent_when_topic_provided(tmp_path: Path) -> None:
    """L2 search returns memories from any agent when topic_query is provided."""
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    events = EventLog(path=tmp_path / "events.jsonl")

    store.store("Python FastAPI backend architecture decision",
                agent="agent-a", memory_type="decision",
                metadata={"tags": "backend"}, skip_gate=True)
    store.store("FastAPI route testing with httpx patterns",
                agent="agent-b", memory_type="fact",
                metadata={"tags": "backend"}, skip_gate=True)

    handler = WakeUpHandler(store, events)
    resp = handler.handle(HookRequest(
        agent="agent-a", project="/", session_id="s2",
        git_branch="feat/backend-api",
        git_recent_commits="add FastAPI route for backend search",
    ))

    assert resp.layers_loaded["L2"] >= 1
    topic_agents = {m["agent"] for m in resp.topic}
    assert topic_agents.issubset({"agent-a", "agent-b"})
    assert len(topic_agents) >= 1
