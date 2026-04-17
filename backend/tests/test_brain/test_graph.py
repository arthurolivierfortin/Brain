"""Tests for the knowledge graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.graph import GraphEdge, KnowledgeGraph

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")


class TestKnowledgeGraph:

    def test_build_from_memories(self):
        graph = KnowledgeGraph()
        graph.build_from_memories({
            "dev-cycle": [
                {
                    "id": "m1",
                    "content": "EMA crossover works well, see [[IMP-005]] and [[momentum-strategy]]",
                    "memory_type": "strategy",
                    "confidence": 0.9,
                    "links": [],
                },
                {
                    "id": "m2",
                    "content": "Bug in reaper fixed",
                    "memory_type": "bug",
                    "confidence": 0.7,
                    "links": ["m1"],
                },
            ],
        })

        assert graph.node_count == 2
        # m1 has 2 wikilinks + m2 has 1 explicit link = 3 edges
        assert graph.edge_count == 3

    def test_wikilink_parsing(self):
        graph = KnowledgeGraph()
        graph.build_from_memories({
            "test": [{
                "id": "w1",
                "content": "Related to [[feature-232]] and [[IMP-031]]",
                "memory_type": "context",
                "confidence": 1.0,
                "links": [],
            }],
        })

        edges = graph.to_dict()["edges"]
        targets = {e["target"] for e in edges}
        assert "feature-232" in targets
        assert "IMP-031" in targets

    def test_export_dict(self):
        graph = KnowledgeGraph()
        graph.build_from_memories({
            "agent1": [{"id": "n1", "content": "test", "memory_type": "context", "confidence": 1.0, "links": []}],
        })

        data = graph.to_dict()
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert data["stats"]["node_count"] == 1

    def test_export_dict_includes_edge_weight(self):
        """Edges exported to dict should include relation and weight."""
        graph = KnowledgeGraph()
        graph.add_edge(GraphEdge(source="a", target="b", relation="supports", weight=0.5))

        data = graph.to_dict()
        assert len(data["edges"]) == 1
        assert data["edges"][0]["relation"] == "supports"
        assert data["edges"][0]["weight"] == 0.5

    def test_save_load(self, tmp_path: Path):
        graph = KnowledgeGraph()
        graph.build_from_memories({
            "dev": [{"id": "s1", "content": "saved", "memory_type": "architecture", "confidence": 1.0, "links": []}],
        })

        path = tmp_path / "graph.json"
        graph.save(path)
        assert path.exists()

        import json
        data = json.loads(path.read_text())
        assert data["stats"]["node_count"] == 1

    def test_empty_graph(self):
        graph = KnowledgeGraph()
        assert graph.node_count == 0
        assert graph.edge_count == 0
        data = graph.to_dict()
        assert data["stats"]["node_count"] == 0


class TestGraphEdgeTypes:
    """Tests for typed edges (relation + weight)."""

    def test_default_edge_values(self):
        edge = GraphEdge(source="a", target="b")
        assert edge.relation == "relates_to"
        assert edge.weight == 1.0

    def test_typed_edge(self):
        edge = GraphEdge(source="old", target="new", relation="supersedes", weight=1.0)
        assert edge.relation == "supersedes"
        assert edge.source == "old"
        assert edge.target == "new"

    def test_weighted_edge(self):
        edge = GraphEdge(source="a", target="b", relation="relates_to", weight=0.5)
        assert edge.weight == 0.5


class TestBuildFromBrainStore:
    """Tests for build_from_brain_store() integration."""

    def test_build_from_brain_store(self, tmp_path: Path):
        """Store entries with shared strategy -> graph has edges."""
        from brain.store import BrainStore
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store two entries about the same EMA strategy on ETH
        store.store(
            content="EMA crossover strategy on ETH/USDT works well in trending markets",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        store.store(
            content="EMA crossover strategy on ETH/USDT also works in volatile conditions",
            agent="test", memory_type="strategy", skip_gate=True,
        )

        graph = KnowledgeGraph()
        graph.build_from_brain_store(store)

        assert graph.node_count == 2
        # Both entries share strategy and symbol, so there should be edges
        assert graph.edge_count >= 1

    def test_typed_edges_supersedes(self, tmp_path: Path):
        """Store contradicting entries -> graph has supersedes edge."""
        from brain.store import BrainStore
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store success entry
        r1 = store.store(
            content="Momentum strategy on BTC/USDT works well and profit was gained",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        # Store contradicting failure entry
        r2 = store.store(
            content="Momentum strategy on BTC/USDT failed badly and loss was incurred",
            agent="test", memory_type="strategy", skip_gate=True,
        )

        graph = KnowledgeGraph()
        graph.build_from_brain_store(store)

        # Find supersedes edges
        edges_dict = graph.to_dict()["edges"]
        supersedes_edges = [e for e in edges_dict if e["relation"] == "supersedes"]
        assert len(supersedes_edges) >= 1
        # The superseded entry (r1) should point to the new entry (r2)
        assert any(
            e["source"] == r1["id"] and e["target"] == r2["id"]
            for e in supersedes_edges
        )

    def test_wikilinks_from_brain_store(self, tmp_path: Path):
        """Wikilinks in content are parsed into relates_to edges."""
        from brain.store import BrainStore
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        store.store(
            content="Related to [[feature-100]] and [[IMP-050]] design decisions",
            agent="test", memory_type="context", skip_gate=True,
        )

        graph = KnowledgeGraph()
        graph.build_from_brain_store(store)

        edges_dict = graph.to_dict()["edges"]
        targets = {e["target"] for e in edges_dict}
        assert "feature-100" in targets
        assert "IMP-050" in targets

    def test_explicit_links_from_metadata(self, tmp_path: Path):
        """Explicit links stored in metadata are parsed into edges."""
        from brain.store import BrainStore
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="First observation about risk limits in trading strategies",
            agent="test", memory_type="context", skip_gate=True,
        )
        # Store second entry with explicit link to first
        store.store(
            content="Follow-up on risk limits after studying portfolio drawdown closely",
            agent="test", memory_type="context", skip_gate=True,
            links=[r1["id"]],
        )

        graph = KnowledgeGraph()
        graph.build_from_brain_store(store)

        edges_dict = graph.to_dict()["edges"]
        link_targets = {e["target"] for e in edges_dict if e["relation"] == "relates_to"}
        assert r1["id"] in link_targets

    def test_graph_weight_by_relation(self, tmp_path: Path):
        """Shared strategy edges have weight 0.5, shared symbol edges weight 0.3."""
        from brain.store import BrainStore
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Two entries sharing strategy "ema" but different symbols
        store.store(
            content="EMA crossover strategy observation on ETH/USDT in bull market",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        store.store(
            content="EMA crossover strategy observation on BTC/USDT in ranging market",
            agent="test", memory_type="strategy", skip_gate=True,
        )

        graph = KnowledgeGraph()
        graph.build_from_brain_store(store)

        edges_dict = graph.to_dict()["edges"]
        weights = {e["weight"] for e in edges_dict}
        # Shared strategy → weight 0.5
        assert 0.5 in weights, f"Expected weight 0.5 for shared strategy edge, got {weights}"


class TestGetNeighbors:
    """Tests for BFS neighbor discovery."""

    def test_get_neighbors_one_hop(self):
        """BFS returns correct 1-hop neighbors."""
        graph = KnowledgeGraph()
        from brain.graph import GraphNode
        graph.add_node(GraphNode(id="a", label="A", node_type="context"))
        graph.add_node(GraphNode(id="b", label="B", node_type="context"))
        graph.add_node(GraphNode(id="c", label="C", node_type="context"))
        graph.add_node(GraphNode(id="d", label="D", node_type="context"))

        graph.add_edge(GraphEdge(source="a", target="b", relation="relates_to"))
        graph.add_edge(GraphEdge(source="b", target="c", relation="relates_to"))
        graph.add_edge(GraphEdge(source="c", target="d", relation="relates_to"))

        # 1-hop from "a" should only return "b"
        neighbors = graph.get_neighbors(["a"], hops=1)
        assert neighbors == {"b"}

    def test_get_neighbors_two_hops(self):
        """BFS with 2 hops returns nodes within 2 hops."""
        graph = KnowledgeGraph()
        from brain.graph import GraphNode
        graph.add_node(GraphNode(id="a", label="A", node_type="context"))
        graph.add_node(GraphNode(id="b", label="B", node_type="context"))
        graph.add_node(GraphNode(id="c", label="C", node_type="context"))
        graph.add_node(GraphNode(id="d", label="D", node_type="context"))

        graph.add_edge(GraphEdge(source="a", target="b"))
        graph.add_edge(GraphEdge(source="b", target="c"))
        graph.add_edge(GraphEdge(source="c", target="d"))

        neighbors = graph.get_neighbors(["a"], hops=2)
        assert "b" in neighbors
        assert "c" in neighbors
        assert "d" not in neighbors

    def test_get_neighbors_excludes_superseded(self):
        """Supersedes edges are NOT followed in BFS."""
        graph = KnowledgeGraph()
        from brain.graph import GraphNode
        graph.add_node(GraphNode(id="old", label="Old", node_type="strategy"))
        graph.add_node(GraphNode(id="new", label="New", node_type="strategy"))
        graph.add_node(GraphNode(id="related", label="Related", node_type="context"))

        # old -> new via supersedes (should NOT be followed)
        graph.add_edge(GraphEdge(source="old", target="new", relation="supersedes"))
        # old -> related via relates_to (should be followed)
        graph.add_edge(GraphEdge(source="old", target="related", relation="relates_to"))

        neighbors = graph.get_neighbors(["old"], hops=1)
        assert "related" in neighbors
        assert "new" not in neighbors

    def test_get_neighbors_excludes_starting_ids(self):
        """Starting IDs should not appear in the returned set."""
        graph = KnowledgeGraph()
        from brain.graph import GraphNode
        graph.add_node(GraphNode(id="x", label="X", node_type="context"))
        graph.add_node(GraphNode(id="y", label="Y", node_type="context"))
        graph.add_edge(GraphEdge(source="x", target="y"))

        neighbors = graph.get_neighbors(["x"], hops=1)
        assert "x" not in neighbors
        assert "y" in neighbors

    def test_get_neighbors_multiple_start(self):
        """BFS from multiple starting nodes returns union of neighbors."""
        graph = KnowledgeGraph()
        from brain.graph import GraphNode
        for nid in ("a", "b", "c", "d"):
            graph.add_node(GraphNode(id=nid, label=nid, node_type="context"))

        graph.add_edge(GraphEdge(source="a", target="c"))
        graph.add_edge(GraphEdge(source="b", target="d"))

        neighbors = graph.get_neighbors(["a", "b"], hops=1)
        assert neighbors == {"c", "d"}

    def test_get_neighbors_empty_graph(self):
        """BFS on empty graph returns empty set."""
        graph = KnowledgeGraph()
        neighbors = graph.get_neighbors(["nonexistent"], hops=1)
        assert neighbors == set()

    def test_get_neighbors_bidirectional(self):
        """BFS traverses edges in both directions."""
        graph = KnowledgeGraph()
        from brain.graph import GraphNode
        graph.add_node(GraphNode(id="a", label="A", node_type="context"))
        graph.add_node(GraphNode(id="b", label="B", node_type="context"))
        graph.add_edge(GraphEdge(source="a", target="b"))

        # Starting from "b", should find "a" (reverse direction)
        neighbors = graph.get_neighbors(["b"], hops=1)
        assert "a" in neighbors
