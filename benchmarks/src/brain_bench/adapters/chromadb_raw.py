"""Raw ChromaDB adapter — ablation baseline with no Brain logic."""
from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb import QueryResult
from chromadb.api.types import Metadata as ChromaMetadata

from brain_bench.types import Memory, Session


class ChromaDBRawAdapter:
    """Baseline: bare ChromaDB with default embeddings.

    This is what an app gets with just `chromadb.PersistentClient`. If Brain
    does not outperform this on LongMemEval, then Brain's structure (gate,
    graph, decay, consolidation) is not contributing — the embedding model is.
    """

    def __init__(self, persist_dir: str | Path, collection_name: str = "longmemeval_raw") -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._name = collection_name
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        self._client.delete_collection(self._name)
        self._collection = self._client.get_or_create_collection(
            name=self._name,
            metadata={"hnsw:space": "cosine"},
        )

    def ingest(self, session: Session) -> None:
        if not session.turns:
            return
        ids: list[str] = []
        docs: list[str] = []
        metas: list[ChromaMetadata] = []
        for i, turn in enumerate(session.turns):
            ids.append(f"{session.session_id}_{i}")
            docs.append(f"[{turn.role}] {turn.content}")
            metas.append({
                "session_id": session.session_id,
                "session_date": session.session_date,
                "turn_idx": i,
                "role": turn.role,
            })
        self._collection.upsert(ids=ids, documents=docs, metadatas=metas)

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        count = self._collection.count()
        if count == 0:
            return []
        res: QueryResult = self._collection.query(query_texts=[query], n_results=min(k, count))
        ids_row = res["ids"][0]
        distances_row = res["distances"][0] if res["distances"] is not None else []
        metadatas_row = res["metadatas"][0] if res["metadatas"] is not None else []
        documents_row = res["documents"][0] if res["documents"] is not None else []
        memories: list[Memory] = []
        for i in range(len(ids_row)):
            distance = float(distances_row[i])
            similarity = max(0.0, 1.0 - distance)
            raw_meta = metadatas_row[i] or {}
            session_id_val = raw_meta.get("session_id")
            memories.append(Memory(
                id=ids_row[i],
                content=str(documents_row[i]),
                score=similarity,
                session_id=str(session_id_val) if session_id_val is not None else None,
                metadata=dict(raw_meta),
            ))
        return memories
