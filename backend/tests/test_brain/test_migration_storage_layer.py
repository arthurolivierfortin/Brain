"""Idempotent storage_layer migration on BrainStore boot (Phase 2c.1)."""
from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.events import EventLog  # noqa: E402
from brain.store import BrainStore  # noqa: E402


def test_migration_tags_unflagged_entries(tmp_path: Path):
    persist = str(tmp_path / "chromadb")

    # Seed two entries via the standard pipeline (no storage_layer tag yet).
    events = EventLog(path=tmp_path / "events.jsonl")
    store = BrainStore(persist_dir=persist, event_log=events)
    store.store(content="content c1 long enough to pass gate", agent="t",
                memory_type="fact", skip_gate=True)
    store.store(content="content c2 long enough to pass gate", agent="t",
                memory_type="fact", skip_gate=True)

    # Strip storage_layer if it's already there to simulate an old DB.
    raw = store._collection.get(include=["metadatas"])
    for i, meta in enumerate(raw["metadatas"]):
        new_meta = {k: v for k, v in (meta or {}).items() if k != "storage_layer"}
        store._collection.update(ids=[raw["ids"][i]], metadatas=[new_meta])

    # Reopen → migration should run on init.
    store2 = BrainStore(persist_dir=persist, event_log=events)
    after = store2._collection.get(include=["metadatas"])
    layers = [m.get("storage_layer") for m in after["metadatas"]]
    assert layers == ["extracted", "extracted"]

    # Re-running is a no-op (idempotent).
    migrated_again = store2.migrate_storage_layer()
    assert migrated_again == 0


def test_migration_skips_when_no_collection_entries(tmp_path: Path):
    events = EventLog(path=tmp_path / "events.jsonl")
    store = BrainStore(persist_dir=str(tmp_path / "chromadb"), event_log=events)
    n = store.migrate_storage_layer()
    assert n == 0
