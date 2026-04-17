"""Knowledge graph -- parse wikilinks and build a relationship graph.

Scans memory entries for [[wikilink]] patterns and builds a graph
of connections between entries, features, strategies, etc.

Brain v2 adds:
- Typed edges (supersedes, contradicts, supports, relates_to) with weights
- build_from_brain_store() for direct BrainStore integration
- get_neighbors() BFS for 1-hop graph expansion in search
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.store import BrainStore

logger = logging.getLogger(__name__)

WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass(frozen=True)
class GraphNode:
    id: str
    label: str
    node_type: str  # memory, decision, strategy, feature, bug
    confidence: float = 1.0
    agent: str = ""


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str = "relates_to"  # supersedes, contradicts, supports, relates_to
    weight: float = 1.0


class KnowledgeGraph:
    """Build and query a knowledge graph from memory entries."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        # Adjacency list for fast BFS: node_id -> list of (neighbor_id, edge)
        self._adjacency: dict[str, list[tuple[str, GraphEdge]]] = {}

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)
        # Update adjacency list (bidirectional for BFS)
        self._adjacency.setdefault(edge.source, []).append((edge.target, edge))
        self._adjacency.setdefault(edge.target, []).append((edge.source, edge))

    def build_from_memories(self, stores: dict[str, list[dict]]) -> None:
        """Build graph from multiple agent memory stores.

        Args:
            stores: Map of agent_name -> list of memory entry dicts
        """
        for agent, entries in stores.items():
            for entry in entries:
                node_id = entry.get("id", "")
                self.add_node(GraphNode(
                    id=node_id,
                    label=entry.get("content", "")[:60],
                    node_type=entry.get("memory_type", "context"),
                    confidence=entry.get("confidence", 1.0),
                    agent=agent,
                ))

                # Parse wikilinks from content
                content = entry.get("content", "")
                for link_target in WIKILINK_PATTERN.findall(content):
                    self.add_edge(GraphEdge(source=node_id, target=link_target))

                # Add explicit links
                for link in entry.get("links", []):
                    self.add_edge(GraphEdge(source=node_id, target=link))

    def build_from_brain_store(self, brain_store: BrainStore) -> None:
        """Build graph from a BrainStore instance.

        Creates nodes for all entries and edges from:
        - [[wikilinks]] in content -> relates_to
        - Explicit links in metadata -> relates_to
        - superseded_by metadata -> supersedes edge
        - Shared strategies -> relates_to with weight=0.5
        - Shared symbols -> relates_to with weight=0.3

        Args:
            brain_store: The BrainStore to read entries from.
        """
        entries = brain_store.get_all_for_graph()
        if not entries:
            return

        for entry in entries:
            node_id = entry["id"]
            self.add_node(GraphNode(
                id=node_id,
                label=entry.get("content", "")[:60],
                node_type=entry.get("memory_type", "context"),
                confidence=entry.get("confidence", 1.0),
                agent=entry.get("agent", ""),
            ))

            # Parse wikilinks from content
            content = entry.get("content", "")
            for link_target in WIKILINK_PATTERN.findall(content):
                self.add_edge(GraphEdge(
                    source=node_id, target=link_target, relation="relates_to",
                ))

            # Parse explicit links from metadata (comma-separated string)
            links_str = entry.get("links", "")
            if links_str:
                for link in links_str.split(","):
                    link = link.strip()
                    if link:
                        self.add_edge(GraphEdge(
                            source=node_id, target=link, relation="relates_to",
                        ))

            # Parse superseded_by -> supersedes edge (source=old, target=new)
            superseded_by = entry.get("superseded_by", "")
            if superseded_by:
                self.add_edge(GraphEdge(
                    source=node_id, target=superseded_by, relation="supersedes",
                ))

        # Build shared-metadata edges (strategy and symbol)
        self._build_shared_metadata_edges(entries)

    def _build_shared_metadata_edges(self, entries: list[dict]) -> None:
        """Create edges between entries sharing strategies or symbols."""
        # Group entries by strategy
        by_strategy: dict[str, list[str]] = {}
        for entry in entries:
            strategies_str = entry.get("strategies", "")
            if not strategies_str:
                continue
            for strategy in strategies_str.split(","):
                strategy = strategy.strip()
                if strategy:
                    by_strategy.setdefault(strategy, []).append(entry["id"])

        # Create edges for shared strategies (weight=0.5).
        # seen_pairs is shared with symbol loop below — strategy weight (0.5)
        # takes precedence over symbol weight (0.3) when both apply.
        seen_pairs: set[tuple[str, str]] = set()
        for _strategy, ids in by_strategy.items():
            if len(ids) < 2:
                continue
            for i, id_a in enumerate(ids):
                for id_b in ids[i + 1:]:
                    pair = (min(id_a, id_b), max(id_a, id_b))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        self.add_edge(GraphEdge(
                            source=id_a, target=id_b,
                            relation="relates_to", weight=0.5,
                        ))

        # Group entries by symbol
        by_symbol: dict[str, list[str]] = {}
        for entry in entries:
            symbols_str = entry.get("symbols", "")
            if not symbols_str:
                continue
            for symbol in symbols_str.split(","):
                symbol = symbol.strip()
                if symbol:
                    by_symbol.setdefault(symbol, []).append(entry["id"])

        # Create edges for shared symbols (weight=0.3)
        for _symbol, ids in by_symbol.items():
            if len(ids) < 2:
                continue
            for i, id_a in enumerate(ids):
                for id_b in ids[i + 1:]:
                    pair = (min(id_a, id_b), max(id_a, id_b))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        self.add_edge(GraphEdge(
                            source=id_a, target=id_b,
                            relation="relates_to", weight=0.3,
                        ))

    def get_neighbors(self, entry_ids: list[str], hops: int = 1) -> set[str]:
        """BFS from given entry IDs, return neighbor IDs within hop distance.

        Does NOT follow supersedes edges (to avoid resurfacing superseded entries).
        Returns only the neighbor IDs, not the starting IDs.

        Args:
            entry_ids: Starting node IDs.
            hops: Maximum BFS depth (default 1).

        Returns:
            Set of neighbor node IDs (excluding the starting IDs).
        """
        start_set = set(entry_ids)
        visited: set[str] = set(entry_ids)
        # Queue of (node_id, current_depth)
        queue: deque[tuple[str, int]] = deque()

        for eid in entry_ids:
            queue.append((eid, 0))

        while queue:
            current_id, depth = queue.popleft()
            if depth >= hops:
                continue

            for neighbor_id, edge in self._adjacency.get(current_id, []):
                # Do NOT follow supersedes edges
                if edge.relation == "supersedes":
                    continue
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, depth + 1))

        # Return only neighbors, not the starting IDs
        return visited - start_set

    def to_dict(self) -> dict:
        """Export graph as JSON-serializable dict for dashboard."""
        return {
            "nodes": [
                {
                    "id": n.id,
                    "label": n.label,
                    "type": n.node_type,
                    "confidence": n.confidence,
                    "agent": n.agent,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation,
                    "weight": e.weight,
                }
                for e in self._edges
            ],
            "stats": {
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
            },
        }

    def save(self, path: Path | None = None) -> None:
        """Save precomputed graph for dashboard."""
        path = path or Path("memory/graph.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(self.to_dict(), indent=2))
            logger.info("Knowledge graph saved: %d nodes, %d edges", len(self._nodes), len(self._edges))
        except OSError as e:
            logger.error("Failed to save graph: %s", e)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)
