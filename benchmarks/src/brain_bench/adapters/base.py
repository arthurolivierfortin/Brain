"""Adapter protocol: what every memory backend must implement."""
from __future__ import annotations

from typing import Protocol

from brain_bench.types import Memory, Session


class Adapter(Protocol):
    """Memory backend contract.

    An adapter ingests conversation sessions and retrieves the top-k most
    relevant memories for a query. Implementations exist for Brain (HTTP
    API) and ChromaDB raw (direct, used as ablation baseline).
    """

    def reset(self) -> None:
        """Clear all stored memories. Called once per dataset entry."""
        ...

    def ingest(self, session: Session) -> None:
        """Store all turns of a session as retrievable memories."""
        ...

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        """Return top-k memories ranked by relevance to query."""
        ...
