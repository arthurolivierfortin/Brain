"""Brain HTTP adapter — wires LongMemEval sessions into Brain's /store and /search."""
from __future__ import annotations

import httpx

from brain_bench.types import Memory, Session


class BrainAdapter:
    """Uses Brain's HTTP API (localhost:8621 in docker compose setup)."""

    _AGENT = "longmemeval"

    def __init__(self, brain_url: str, timeout: float = 30.0) -> None:
        self._url = brain_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def reset(self) -> None:
        """Wipe the longmemeval agent's memories between dataset entries.

        Uses Brain's POST /reset endpoint scoped to this adapter's agent so
        that unrelated memories in the same Brain instance are not touched.
        A failure here would silently pollute subsequent entries — so we
        raise, never swallow.
        """
        resp = self._client.post(
            f"{self._url}/reset",
            json={"agent": self._AGENT},
        )
        resp.raise_for_status()

    def ingest(self, session: Session) -> None:
        for i, turn in enumerate(session.turns):
            content = f"[{turn.role}] {turn.content}"
            payload = {
                "content": content,
                "agent": self._AGENT,
                "memory_type": "context",
                "metadata": {
                    "session_id": session.session_id,
                    "session_date": session.session_date,
                    "turn_idx": i,
                    "role": turn.role,
                },
                "skip_gate": True,
            }
            resp = self._client.post(f"{self._url}/store", json=payload)
            resp.raise_for_status()

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        resp = self._client.get(
            f"{self._url}/search",
            params={"query": query, "top_k": k},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            Memory(
                id=r["id"],
                content=r["content"],
                score=r.get("score", 0.0),
                session_id=(r.get("metadata") or {}).get("session_id"),
                metadata=r.get("metadata") or {},
            )
            for r in data.get("results", [])
        ]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BrainAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
