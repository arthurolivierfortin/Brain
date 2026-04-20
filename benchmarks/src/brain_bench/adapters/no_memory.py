"""No-memory adapter — true zero baseline for the 3-way ablation.

Reader gets NO retrieved context. Answers questions from its own parametric
knowledge only. The delta between `none` and `chromadb_raw` isolates what
raw vector search contributes; the delta between `chromadb_raw` and `brain`
isolates what Brain's structure adds on top.
"""
from __future__ import annotations

from brain_bench.types import Memory, Session


class NoMemoryAdapter:
    """Returns no memories. Exists to measure the reader's standalone ability."""

    def reset(self) -> None:
        return None

    def ingest(self, session: Session) -> None:
        return None

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        return []
