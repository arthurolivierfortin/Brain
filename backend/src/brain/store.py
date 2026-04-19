"""Brain store -- ChromaDB-backed vector store for agent memories.

Replaces the old JSON-based MemoryStore. All memories are stored as
documents with embeddings in ChromaDB, enabling semantic search.

Brain v2 adds:
- Consolidation engine (level promotion 0->1->2)
- Contradiction detection (supersede older conflicting entries)
- Composite scoring (similarity * 0.5 + recency * 0.3 + importance * 0.2)
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import chromadb

from brain.enrichment import enrich
from brain.events import EventLog
from brain.gate import BrainGate, GateVerdict

logger = logging.getLogger(__name__)

# Use /data/chromadb in containers (Docker volume), data/chromadb locally
DEFAULT_PERSIST_DIR = "/data/chromadb" if Path("/data").exists() else "data/chromadb"

# ChromaDB metadata keys owned by Brain itself (not overwritable by caller-
# supplied metadata). Anything else in the input `metadata` dict that is a
# scalar (str/int/float/bool) gets persisted alongside and surfaced back in
# search results under a nested `metadata` dict.
RESERVED_META_KEYS: frozenset[str] = frozenset({
    "agent", "memory_type", "created_at", "access_count", "confidence",
    "sentiment", "level", "symbols", "strategies", "concepts", "links",
    "source", "dedup_key", "superseded", "consolidated_into", "superseded_by",
    "occurrence_count", "event_type",
})
COLLECTION_NAME = "brain"

# Composite scoring: decay constant in days per hierarchy level
# At t=decay_constant, recency factor = exp(-1) ≈ 0.37
_DECAY_CONSTANTS = {0: 7, 1: 30, 2: 90, 3: 365}

# Opposite sentiments for contradiction detection
_OPPOSITE_SENTIMENTS = {
    ("success", "failure"),
    ("failure", "success"),
}


class BrainStore:
    """ChromaDB-backed vector store with gate, enrichment, and reinforcement."""

    def __init__(
        self,
        persist_dir: str | None = None,
        event_log: EventLog | None = None,
    ) -> None:
        self._persist_dir = persist_dir or DEFAULT_PERSIST_DIR
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._gate = BrainGate()
        self._events = event_log or EventLog()
        self._graph: object | None = None  # Lazy-loaded KnowledgeGraph

    def _get_graph(self):
        """Build or return cached knowledge graph."""
        if self._graph is None:
            from brain.graph import KnowledgeGraph
            graph = KnowledgeGraph()
            graph.build_from_brain_store(self)
            self._graph = graph
        return self._graph

    def invalidate_graph(self) -> None:
        """Called after store/consolidate/forget to force graph rebuild."""
        self._graph = None

    def store(
        self,
        content: str,
        agent: str,
        memory_type: str = "context",
        metadata: dict | None = None,
        links: list[str] | None = None,
        skip_gate: bool = False,
    ) -> dict | None:
        """Store a memory through the gate -> enrich -> contradict -> embed pipeline.

        Args:
            content: The text content to store.
            agent: Which agent is storing this.
            memory_type: One of: architecture, strategy, bug, context, decision.
            metadata: Optional extra metadata.
            links: Explicit links to other entries/concepts.
            skip_gate: Bypass the gate (for bootstrap/migration).

        Returns:
            Entry dict with id, or None if rejected by gate.
        """
        metadata = metadata or {}

        # Gate
        gate_result = None
        if not skip_gate:
            gate_result = self._gate.evaluate(
                content=content,
                event_type=metadata.get("event_type", ""),
                agent=agent,
                metadata=metadata,
            )
            if gate_result.verdict == GateVerdict.REJECT:
                logger.debug("Gate rejected: %s", gate_result.reason)
                return None
            if gate_result.verdict == GateVerdict.INCREMENT:
                return self._increment_existing(gate_result.dedup_key, agent)

        # Enrich
        enriched = enrich(content, existing_metadata=metadata)

        # Build ChromaDB metadata (must be flat: str, int, float, bool)
        entry_id = str(uuid.uuid4())[:12]
        now = datetime.now(UTC).isoformat()

        chroma_meta: dict[str, str | int | float | bool] = {
            "agent": agent,
            "memory_type": memory_type,
            "created_at": now,
            "access_count": 0,
            "confidence": 1.0,
            "sentiment": enriched.sentiment,
            "level": 0,  # Hierarchy: 0=raw, 1=summary, 2=knowledge, 3=principle
        }

        # Store dedup_key so _increment_existing() can find this entry later
        if gate_result and gate_result.dedup_key:
            chroma_meta["dedup_key"] = gate_result.dedup_key

        # Add enriched fields
        if enriched.symbols:
            chroma_meta["symbols"] = ",".join(enriched.symbols)
        if enriched.strategies:
            chroma_meta["strategies"] = ",".join(enriched.strategies)
        if enriched.concepts:
            chroma_meta["concepts"] = ",".join(enriched.concepts[:10])
        if links:
            chroma_meta["links"] = ",".join(links)

        # Source tracking (docs, feed, agent)
        if "source" in metadata:
            chroma_meta["source"] = metadata["source"]

        # Preserve caller-supplied metadata (e.g. session_id from benchmarks).
        # Only scalars — ChromaDB rejects nested structures.
        for key, value in metadata.items():
            if key in RESERVED_META_KEYS:
                continue
            if isinstance(value, (str, int, float, bool)):
                chroma_meta[key] = value

        # Contradiction detection: check for semantically similar entries
        # with opposite sentiment before storing
        self._detect_contradictions(content, enriched.sentiment, entry_id)

        # Store in ChromaDB (embedding generated automatically by fastembed if configured,
        # or by ChromaDB's default embedding function)
        self._collection.add(
            ids=[entry_id],
            documents=[content],
            metadatas=[chroma_meta],
        )

        # Log event
        self._events.log(
            event_type="stored",
            agent=agent,
            node_id=entry_id,
            details=content[:100],
            metadata={"memory_type": memory_type, "sentiment": enriched.sentiment},
        )

        self.invalidate_graph()
        logger.info("Brain stored [%s/%s]: %s", agent, entry_id, content[:80])
        return {"id": entry_id, "agent": agent, "type": memory_type}

    def search(
        self,
        query: str,
        agent: str | None = None,
        memory_type: str | None = None,
        top_k: int = 5,
        max_results: int = 10,
        reinforce: bool = True,
        include_superseded: bool = False,
    ) -> list[dict]:
        """Semantic search with composite scoring and superseded filtering.

        Results are ranked by composite score:
            score = similarity * 0.5 + recency * 0.3 + importance * 0.2

        Level 3 (principle) entries are always included regardless of score.
        Superseded entries are excluded by default.

        Args:
            query: Natural language search query.
            agent: Filter by agent name.
            memory_type: Filter by memory type.
            top_k: Number of results to fetch from ChromaDB before ranking.
            max_results: Hard cap on returned results (default 10) to avoid
                flooding agents with low-quality context.
            reinforce: Bump access_count on matched entries.
            include_superseded: If True, include entries marked as superseded.

        Returns:
            List of result dicts with id, content, metadata, distance, score.
        """
        if self._collection.count() == 0:
            return []

        # Build where filter
        where: dict | None = None
        conditions: list[dict] = []
        if agent:
            conditions.append({"agent": {"$eq": agent}})
        if memory_type:
            conditions.append({"memory_type": {"$eq": memory_type}})

        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        # Fetch more candidates than max_results so we can re-rank
        fetch_count = min(max(top_k, max_results) * 2, self._collection.count())

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=fetch_count,
                where=where,
            )
        except Exception as e:
            logger.warning("Brain search failed: %s", e)
            return []

        if not results or not results["ids"] or not results["ids"][0]:
            return []

        entries = []
        for i, entry_id in enumerate(results["ids"][0]):
            meta = (results["metadatas"][0][i] if results["metadatas"] else None) or {}
            doc = results["documents"][0][i] if results["documents"] else ""
            distance = results["distances"][0][i] if results["distances"] else 0.0

            entries.append({
                "id": entry_id,
                "content": doc,
                "distance": round(distance, 4),
                "level": meta.get("level", 0),
                "agent": meta.get("agent", ""),
                "memory_type": meta.get("memory_type", ""),
                "confidence": meta.get("confidence", 1.0),
                "access_count": meta.get("access_count", 0),
                "sentiment": meta.get("sentiment", "neutral"),
                "symbols": meta.get("symbols", ""),
                "strategies": meta.get("strategies", ""),
                "concepts": meta.get("concepts", ""),
                "links": meta.get("links", ""),
                "created_at": meta.get("created_at", ""),
                "source": meta.get("source", ""),
                "superseded": meta.get("superseded", False),
                "consolidated_into": meta.get("consolidated_into", ""),
                "metadata": {
                    k: v for k, v in meta.items() if k not in RESERVED_META_KEYS
                },
            })

        # Graph-augmented search: expand with 1-hop neighbors
        existing_ids = {e["id"] for e in entries}
        try:
            graph = self._get_graph()
            neighbor_ids = graph.get_neighbors(list(existing_ids), hops=1)
            # Remove IDs we already have
            new_neighbor_ids = [nid for nid in neighbor_ids if nid not in existing_ids]
            if new_neighbor_ids:
                # Fetch neighbor entries from ChromaDB
                try:
                    neighbor_data = self._collection.get(
                        ids=new_neighbor_ids,
                        include=["documents", "metadatas"],
                    )
                    for i, nid in enumerate(neighbor_data["ids"]):
                        nmeta = (
                            neighbor_data["metadatas"][i]
                            if neighbor_data["metadatas"] else None
                        ) or {}
                        ndoc = (
                            neighbor_data["documents"][i]
                            if neighbor_data["documents"] else ""
                        )
                        entries.append({
                            "id": nid,
                            "content": ndoc,
                            "distance": 0.8,  # Penalty: worse than direct matches
                            "level": nmeta.get("level", 0),
                            "agent": nmeta.get("agent", ""),
                            "memory_type": nmeta.get("memory_type", ""),
                            "confidence": nmeta.get("confidence", 1.0),
                            "access_count": nmeta.get("access_count", 0),
                            "sentiment": nmeta.get("sentiment", "neutral"),
                            "symbols": nmeta.get("symbols", ""),
                            "strategies": nmeta.get("strategies", ""),
                            "concepts": nmeta.get("concepts", ""),
                            "links": nmeta.get("links", ""),
                            "created_at": nmeta.get("created_at", ""),
                            "source": nmeta.get("source", ""),
                            "superseded": nmeta.get("superseded", False),
                            "consolidated_into": nmeta.get("consolidated_into", ""),
                            "metadata": {
                                k: v for k, v in nmeta.items()
                                if k not in RESERVED_META_KEYS
                            },
                        })
                except Exception as e:
                    logger.debug("Graph neighbor fetch failed: %s", e)
        except Exception as e:
            logger.debug("Graph expansion failed: %s", e)

        # Filter superseded entries unless explicitly requested
        if not include_superseded:
            entries = [e for e in entries if not e.get("superseded")]

        # Composite scoring
        now = datetime.now(UTC)
        for entry in entries:
            entry["score"] = _composite_score(entry, now)

        # Separate principles (level >= 3) -- they always appear first
        principles = [e for e in entries if e["level"] >= 3]
        rest = [e for e in entries if e["level"] < 3]

        # Sort by composite score descending
        principles.sort(key=lambda e: e["score"], reverse=True)
        rest.sort(key=lambda e: e["score"], reverse=True)

        # Combine: principles first, then rest by score
        ranked = principles + rest

        # Honor caller's top_k; max_results remains a safety ceiling.
        ranked = ranked[:min(top_k, max_results)]

        # Reinforce returned entries
        for entry in ranked:
            if reinforce:
                entry_id = entry["id"]
                # Rebuild meta dict for reinforcement
                meta_for_reinforce = {
                    k: entry[k]
                    for k in ("agent", "memory_type", "confidence", "access_count",
                              "sentiment", "symbols", "strategies", "concepts",
                              "links", "created_at", "source", "level")
                }
                self._reinforce(entry_id, meta_for_reinforce)

        # Log search event
        self._events.log(
            event_type="searched",
            agent=agent or "all",
            details=query[:100],
            metadata={"results": len(ranked), "top_distance": ranked[0]["distance"] if ranked else 0},
        )

        return ranked

    def consolidate(self) -> dict:
        """Promote entries up the level hierarchy.

        Level 0 entries grouped by (strategy, symbol) with 5+ members
        get summarized into a level-1 entry. Level 1 entries grouped
        by concept with 3+ members get promoted to level-2.

        This method is idempotent: entries already marked with
        consolidated_into are skipped.

        Returns:
            Stats dict with counts of created summaries and processed entries.
        """
        stats = {"level_1_created": 0, "level_2_created": 0, "entries_processed": 0}

        # --- Level 0 -> Level 1 ---
        stats = self._consolidate_level_0_to_1(stats)

        # --- Level 1 -> Level 2 ---
        stats = self._consolidate_level_1_to_2(stats)

        self.invalidate_graph()
        logger.info(
            "Consolidation complete: L1=%d, L2=%d, processed=%d",
            stats["level_1_created"], stats["level_2_created"], stats["entries_processed"],
        )
        return stats

    def _consolidate_level_0_to_1(self, stats: dict) -> dict:
        """Group level-0 entries by (strategy, symbol) and create level-1 summaries."""
        level_0 = self._get_entries_by_level(0)
        if not level_0:
            return stats

        # Group by (strategy, symbol) -- use first strategy and first symbol
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for entry in level_0:
            meta = entry["meta"]
            # Skip already-consolidated entries
            if meta.get("consolidated_into"):
                continue
            strategy = meta.get("strategies", "").split(",")[0].strip() if meta.get("strategies") else "_none"
            symbol = meta.get("symbols", "").split(",")[0].strip() if meta.get("symbols") else "_none"
            # Only group entries that have at least a strategy or symbol
            if strategy == "_none" and symbol == "_none":
                continue
            groups[(strategy, symbol)].append(entry)

        for (strategy, symbol), entries in groups.items():
            if len(entries) < 5:
                continue

            stats["entries_processed"] += len(entries)
            original_ids = [e["id"] for e in entries]

            # Synthesize summary from metadata
            sentiments = [e["meta"].get("sentiment", "neutral") for e in entries]
            success_count = sentiments.count("success")
            failure_count = sentiments.count("failure")
            neutral_count = sentiments.count("neutral")

            summary_parts = []
            if strategy != "_none":
                summary_parts.append(f"Strategy: {strategy}")
            if symbol != "_none":
                summary_parts.append(f"Symbol: {symbol}")
            summary_parts.append(f"Observations: {len(entries)}")
            summary_parts.append(f"Successes: {success_count}, Failures: {failure_count}, Neutral: {neutral_count}")

            # Extract unique concepts across the group
            all_concepts: set[str] = set()
            for e in entries:
                concepts_str = e["meta"].get("concepts", "")
                if concepts_str:
                    all_concepts.update(c.strip() for c in concepts_str.split(",") if c.strip())
            if all_concepts:
                summary_parts.append(f"Concepts: {', '.join(sorted(all_concepts)[:5])}")

            summary_content = " | ".join(summary_parts)

            # Create level-1 summary entry
            summary_id = str(uuid.uuid4())[:12]
            now = datetime.now(UTC).isoformat()

            summary_meta: dict[str, str | int | float | bool] = {
                "agent": "brain-consolidation",
                "memory_type": "strategy",
                "created_at": now,
                "access_count": 0,
                "confidence": 1.0,
                "sentiment": "success" if success_count > failure_count else (
                    "failure" if failure_count > success_count else "neutral"
                ),
                "level": 1,
                "links": ",".join(original_ids),
            }
            if strategy != "_none":
                summary_meta["strategies"] = strategy
            if symbol != "_none":
                summary_meta["symbols"] = symbol
            if all_concepts:
                summary_meta["concepts"] = ",".join(sorted(all_concepts)[:10])

            self._collection.add(
                ids=[summary_id],
                documents=[summary_content],
                metadatas=[summary_meta],
            )

            # Mark originals as consolidated
            for eid in original_ids:
                self._mark_consolidated(eid, summary_id)

            self._events.log(
                event_type="consolidated",
                agent="brain-consolidation",
                node_id=summary_id,
                details=f"Level-1 summary for ({strategy}, {symbol}): {len(entries)} entries",
                metadata={"level": 1, "originals": len(entries)},
            )

            stats["level_1_created"] += 1

        return stats

    def _consolidate_level_1_to_2(self, stats: dict) -> dict:
        """Group level-1 entries by shared concept and create level-2 knowledge."""
        level_1 = self._get_entries_by_level(1)
        if not level_1:
            return stats

        # Group by primary concept
        groups: dict[str, list[dict]] = defaultdict(list)
        for entry in level_1:
            meta = entry["meta"]
            if meta.get("consolidated_into"):
                continue
            concepts_str = meta.get("concepts", "")
            if not concepts_str:
                continue
            primary_concept = concepts_str.split(",")[0].strip()
            if primary_concept:
                groups[primary_concept].append(entry)

        for concept, entries in groups.items():
            if len(entries) < 3:
                continue

            stats["entries_processed"] += len(entries)
            original_ids = [e["id"] for e in entries]

            # Build knowledge summary
            all_strategies: set[str] = set()
            all_symbols: set[str] = set()
            for e in entries:
                strat = e["meta"].get("strategies", "")
                if strat:
                    all_strategies.update(s.strip() for s in strat.split(",") if s.strip())
                sym = e["meta"].get("symbols", "")
                if sym:
                    all_symbols.update(s.strip() for s in sym.split(",") if s.strip())

            knowledge_content = (
                f"Knowledge: {concept} | "
                f"Based on {len(entries)} summaries | "
                f"Strategies: {', '.join(sorted(all_strategies)[:5]) or 'various'} | "
                f"Symbols: {', '.join(sorted(all_symbols)[:5]) or 'various'}"
            )

            knowledge_id = str(uuid.uuid4())[:12]
            now = datetime.now(UTC).isoformat()

            knowledge_meta: dict[str, str | int | float | bool] = {
                "agent": "brain-consolidation",
                "memory_type": "architecture",
                "created_at": now,
                "access_count": 0,
                "confidence": 1.0,
                "sentiment": "neutral",
                "level": 2,
                "links": ",".join(original_ids),
                "concepts": concept,
            }
            if all_strategies:
                knowledge_meta["strategies"] = ",".join(sorted(all_strategies)[:5])
            if all_symbols:
                knowledge_meta["symbols"] = ",".join(sorted(all_symbols)[:5])

            self._collection.add(
                ids=[knowledge_id],
                documents=[knowledge_content],
                metadatas=[knowledge_meta],
            )

            for eid in original_ids:
                self._mark_consolidated(eid, knowledge_id)

            self._events.log(
                event_type="consolidated",
                agent="brain-consolidation",
                node_id=knowledge_id,
                details=f"Level-2 knowledge for concept '{concept}': {len(entries)} summaries",
                metadata={"level": 2, "originals": len(entries)},
            )

            stats["level_2_created"] += 1

        return stats

    def _get_entries_by_level(self, level: int) -> list[dict]:
        """Fetch all entries at a given hierarchy level."""
        try:
            result = self._collection.get(
                where={"level": level},
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.warning("Failed to fetch level-%d entries: %s", level, e)
            return []

        if not result["ids"]:
            return []

        entries = []
        for i, eid in enumerate(result["ids"]):
            meta = (result["metadatas"][i] if result["metadatas"] else None) or {}
            doc = result["documents"][i] if result["documents"] else ""
            entries.append({"id": eid, "doc": doc, "meta": meta})

        return entries

    def _mark_consolidated(self, entry_id: str, summary_id: str) -> None:
        """Mark an entry as consolidated into a higher-level summary."""
        try:
            raw = self._collection.get(ids=[entry_id], include=["metadatas"])
            if raw["ids"]:
                meta = (raw["metadatas"][0] if raw["metadatas"] else None) or {}
                meta["consolidated_into"] = summary_id
                self._collection.update(ids=[entry_id], metadatas=[meta])
        except Exception as e:
            logger.warning("Failed to mark %s as consolidated: %s", entry_id, e)

    def _detect_contradictions(
        self, content: str, new_sentiment: str, new_entry_id: str,
    ) -> None:
        """Detect and mark contradictions with existing entries.

        If a very similar entry exists (distance < 0.15) with the opposite
        sentiment, mark the older entry as superseded.
        """
        if self._collection.count() == 0:
            return
        if new_sentiment == "neutral":
            return  # Cannot contradict without a clear sentiment

        try:
            results = self._collection.query(
                query_texts=[content],
                n_results=1,
            )
        except Exception as e:
            logger.warning("Contradiction search failed: %s", e)
            return

        if not results or not results["ids"] or not results["ids"][0]:
            return

        distance = results["distances"][0][0] if results["distances"] else 1.0
        if distance >= 0.15:
            return  # Not similar enough

        existing_id = results["ids"][0][0]
        existing_meta = (results["metadatas"][0][0] if results["metadatas"] else None) or {}
        existing_sentiment = existing_meta.get("sentiment", "neutral")

        # Check for opposite sentiments
        if (existing_sentiment, new_sentiment) not in _OPPOSITE_SENTIMENTS:
            return  # Same sentiment or neutral -- not a contradiction

        # Mark older entry as superseded
        try:
            existing_meta["superseded"] = True
            existing_meta["superseded_by"] = new_entry_id
            self._collection.update(
                ids=[existing_id],
                metadatas=[existing_meta],
            )
            self._events.log(
                event_type="superseded",
                agent="brain-consolidation",
                node_id=existing_id,
                details=f"Superseded by {new_entry_id} (sentiment: {existing_sentiment} -> {new_sentiment})",
                metadata={"superseded_by": new_entry_id},
            )
            logger.info("Superseded entry %s (was %s, now %s)", existing_id, existing_sentiment, new_sentiment)
        except Exception as e:
            logger.warning("Failed to supersede %s: %s", existing_id, e)

    def related(self, entry_id: str, top_k: int = 5) -> list[dict]:
        """Find memories related to a given entry.

        Uses 3 types of connections:
        1. Explicit links (links field in metadata)
        2. Semantic similarity (cosine distance via ChromaDB)
        3. Shared metadata (same symbols, strategies)
        """
        # Get the entry
        try:
            result = self._collection.get(ids=[entry_id], include=["documents", "metadatas"])
        except Exception:
            return []

        if not result["documents"]:
            return []

        doc = result["documents"][0]
        meta = (result["metadatas"][0] if result["metadatas"] else None) or {}

        # Semantic search using the document content
        related = self.search(doc, top_k=top_k + 1, reinforce=False)

        # Filter out self
        related = [r for r in related if r["id"] != entry_id][:top_k]

        # Also find entries with matching explicit links
        links = meta.get("links", "")
        if links:
            for link in links.split(","):
                link = link.strip()
                if link:
                    try:
                        linked = self._collection.get(ids=[link], include=["documents", "metadatas"])
                        if linked["documents"]:
                            related.append({
                                "id": link,
                                "content": linked["documents"][0],
                                "distance": 0.0,
                                "relation": "explicit_link",
                                **dict((linked["metadatas"][0] or {}).items()),
                            })
                    except Exception:  # noqa: S110 — linked entry may not exist
                        pass

        return related

    def forget(self, entry_id: str) -> bool:
        """Remove a memory entry."""
        try:
            self._collection.delete(ids=[entry_id])
            self.invalidate_graph()
            self._events.log(event_type="archived", node_id=entry_id, details="manually removed")
            return True
        except Exception as e:
            logger.warning("Brain forget failed for %s: %s", entry_id, e)
            return False

    def stats(self) -> dict:
        """Get brain statistics."""
        count = self._collection.count()
        if count == 0:
            return {"total": 0, "agents": {}, "types": {}, "top_accessed": []}

        # Get all metadata for stats
        all_data = self._collection.get(include=["metadatas"])
        metas = all_data["metadatas"] or []

        agents: dict[str, int] = {}
        types: dict[str, int] = {}
        top_accessed: list[tuple[int, str, str]] = []

        for i, meta in enumerate(metas):
            meta = meta or {}
            agent = meta.get("agent", "unknown")
            agents[agent] = agents.get(agent, 0) + 1
            mtype = meta.get("memory_type", "context")
            types[mtype] = types.get(mtype, 0) + 1
            ac = meta.get("access_count", 0)
            if ac > 0:
                top_accessed.append((ac, meta.get("agent", ""), all_data["ids"][i]))

        top_accessed.sort(reverse=True)

        return {
            "total": count,
            "agents": agents,
            "types": types,
            "top_accessed": [
                {"access_count": ac, "agent": ag, "id": eid}
                for ac, ag, eid in top_accessed[:10]
            ],
        }

    def get_all_for_graph(self) -> list[dict]:
        """Get all entries with metadata for knowledge graph building."""
        if self._collection.count() == 0:
            return []
        result = self._collection.get(include=["documents", "metadatas"])
        entries = []
        for i, entry_id in enumerate(result["ids"]):
            meta = (result["metadatas"][i] if result["metadatas"] else None) or {}
            entries.append({
                "id": entry_id,
                "content": (result["documents"][i] or "")[:60],
                "memory_type": meta.get("memory_type", "context"),
                "agent": meta.get("agent", ""),
                "confidence": meta.get("confidence", 1.0),
                "access_count": meta.get("access_count", 0),
                "links": meta.get("links", ""),
                "symbols": meta.get("symbols", ""),
                "strategies": meta.get("strategies", ""),
                "source": meta.get("source", ""),
                "superseded_by": meta.get("superseded_by", ""),
            })
        return entries

    def _reinforce(self, entry_id: str, current_meta: dict) -> None:
        """Bump access_count and confidence on search hit."""
        new_count = current_meta.get("access_count", 0) + 1
        new_confidence = min(1.0, current_meta.get("confidence", 1.0) + 0.05)

        try:
            self._collection.update(
                ids=[entry_id],
                metadatas=[{
                    **current_meta,
                    "access_count": new_count,
                    "confidence": new_confidence,
                    "last_accessed": datetime.now(UTC).isoformat(),
                }],
            )
            self._events.log(
                event_type="reinforced",
                node_id=entry_id,
                details=f"access_count={new_count}, confidence={new_confidence:.2f}",
            )
        except Exception as e:
            logger.debug("Reinforce failed for %s: %s", entry_id, e)

    def _increment_existing(self, dedup_key: str, agent: str) -> dict | None:
        """Increment occurrence counter for a duplicate entry."""
        # Search for existing entry with this dedup key
        try:
            results = self._collection.get(
                where={"dedup_key": {"$eq": dedup_key}},
                include=["metadatas"],
            )
            if results["ids"]:
                entry_id = results["ids"][0]
                meta = (results["metadatas"][0] if results["metadatas"] else None) or {}
                new_count = meta.get("occurrence_count", 1) + 1
                self._collection.update(
                    ids=[entry_id],
                    metadatas=[{**meta, "occurrence_count": new_count}],
                )
                return {"id": entry_id, "incremented": True, "count": new_count}
        except Exception as e:
            logger.debug("Increment lookup failed: %s", e)
        return None


def _composite_score(entry: dict, now: datetime) -> float:
    """Compute composite score for search ranking.

    score = similarity * 0.5 + recency * 0.3 + importance * 0.2

    Where:
    - similarity = max(1.0 - distance, 0)
    - recency = exp(-days / half_life)  with tier-based half-life
    - importance = level * 0.25 + confidence * 0.25
    """
    level = entry.get("level", 0)
    created_at = entry.get("created_at", "")

    # Recency
    try:
        accessed_dt = datetime.fromisoformat(created_at)
        days = max((now - accessed_dt).total_seconds() / 86400, 0.01)
    except (ValueError, TypeError):
        days = 30  # default for unparseable timestamps

    decay = _DECAY_CONSTANTS.get(level, 30)
    recency = math.exp(-days / decay)

    # Importance
    confidence = entry.get("confidence", 1.0)
    if not isinstance(confidence, (int, float)):
        confidence = 1.0
    importance = level * 0.25 + confidence * 0.25

    # Similarity (cosine distance: 0 = identical, 2 = opposite)
    distance = entry.get("distance", 0.0)
    if not isinstance(distance, (int, float)):
        distance = 0.0
    similarity = max(1.0 - distance, 0.0)

    return similarity * 0.5 + recency * 0.3 + importance * 0.2
