"""WakeUpHandler tests — uses real BrainStore with in-memory ChromaDB."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.hook import HookRequest, WakeUpHandler  # noqa: E402
from brain.store import BrainStore  # noqa: E402


def _seed_memories(store, agent="brain-dev"):
    store.store("Arthur, French-first, blunt, no glazing",
                agent=agent, memory_type="context",
                metadata={"tags": "identity,persona"}, skip_gate=True)
    store.store("Always use the 🧠 emoji for new features in commit messages",
                agent=agent, memory_type="context",
                metadata={"tags": "preference,git"}, skip_gate=True)
    store.store("An unrelated bug memory",
                agent=agent, memory_type="bug",
                metadata={"tags": "bug"}, skip_gate=True)


def test_empty_store_returns_empty_context(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert resp.context == ""
    assert resp.layers_loaded == {"L0": 0, "L1": 0}


def test_populates_identity_and_preference_sections(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    _seed_memories(store)
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert "## Identity" in resp.context
    assert "Arthur" in resp.context
    assert "## Preferences" in resp.context
    assert "🧠" in resp.context
    assert resp.layers_loaded == {"L0": 1, "L1": 1}
    assert "bug" not in resp.context.lower()


def test_scopes_to_agent(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    _seed_memories(store, agent="brain-dev")
    _seed_memories(store, agent="money-dev")
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert resp.layers_loaded == {"L0": 1, "L1": 1}


def test_budget_caps_output_tokens(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    for _ in range(30):
        store.store("x" * 400, agent="brain-dev", memory_type="context",
                    metadata={"tags": "preference"}, skip_gate=True)
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="brain-dev", project="/", session_id="s"))
    assert resp.tokens_approx <= WakeUpHandler.BUDGET_TOKENS


def test_duration_ms_is_reported(tmp_path: Path):
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
    handler = WakeUpHandler(store)
    resp = handler.handle(HookRequest(agent="x", project="/", session_id="s"))
    assert resp.duration_ms >= 0
