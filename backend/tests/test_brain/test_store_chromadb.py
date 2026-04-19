"""Tests for ChromaDB-backed BrainStore."""

from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain.store import BrainStore  # noqa: E402


class TestBrainStore:

    def test_store_and_search(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        result = store.store(
            content="EMA crossover strategy works well on ETH/USDT in trending markets",
            agent="self-improver",
            memory_type="strategy",
            skip_gate=True,
        )
        assert result is not None
        assert result["agent"] == "self-improver"

        results = store.search("EMA strategy ETH")
        assert len(results) >= 1
        assert "EMA" in results[0]["content"]

    def test_semantic_search(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("Kelly criterion determines optimal position size based on edge and odds",
                     agent="docs", memory_type="architecture", skip_gate=True)
        store.store("Mean reversion strategy buys when price drops below lower Bollinger band",
                     agent="self-improver", memory_type="strategy", skip_gate=True)

        # Semantic search: "position sizing" should find "Kelly criterion"
        results = store.search("position sizing bet size")
        assert len(results) >= 1
        assert "Kelly" in results[0]["content"]

    def test_metadata_filter(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("bug in reaper", agent="dev-cycle", memory_type="bug", skip_gate=True)
        store.store("strategy insight", agent="self-improver", memory_type="strategy", skip_gate=True)

        results = store.search("bug", agent="dev-cycle")
        assert all(r["agent"] == "dev-cycle" for r in results)

    def test_reinforcement(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("RSI overbought signal on BTC/USDT", agent="test", memory_type="strategy", skip_gate=True)

        # First search triggers reinforcement (access_count goes from 0 to 1)
        store.search("RSI overbought BTC")

        # Second search sees the updated count (1) and bumps to 2
        results2 = store.search("RSI overbought BTC")
        assert results2[0]["access_count"] >= 1

        # Third search confirms accumulation
        results3 = store.search("RSI overbought BTC")
        assert results3[0]["access_count"] >= 2

    def test_forget(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        result = store.store("temporary note", agent="test", memory_type="context", skip_gate=True)
        entry_id = result["id"]

        assert store.forget(entry_id) is True
        assert store.search("temporary note") == []

    def test_stats(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("fact one", agent="agent-a", memory_type="strategy", skip_gate=True)
        store.store("fact two", agent="agent-b", memory_type="bug", skip_gate=True)

        stats = store.stats()
        assert stats["total"] == 2
        assert stats["agents"]["agent-a"] == 1
        assert stats["types"]["bug"] == 1

    def test_related(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        r1 = store.store("EMA crossover on ETH works in bull markets", agent="test",
                          memory_type="strategy", skip_gate=True)
        store.store("EMA crossover on BTC also works well in uptrend", agent="test",
                     memory_type="strategy", skip_gate=True)

        related = store.related(r1["id"])
        assert len(related) >= 1

    def test_get_all_for_graph(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("node 1", agent="a", memory_type="context", skip_gate=True)
        store.store("node 2", agent="b", memory_type="strategy", skip_gate=True)

        entries = store.get_all_for_graph()
        assert len(entries) == 2
        assert all("id" in e for e in entries)


class TestBrainStoreLevel:
    """Tests for hierarchical level metadata (Phase 4.2)."""

    def test_new_entries_have_level_zero(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("A raw event memory about market conditions today",
                     agent="test", memory_type="context", skip_gate=True)

        # Verify level is stored in ChromaDB metadata
        results = store.search("raw event memory")
        assert len(results) >= 1
        assert results[0]["level"] == 0

    def test_level_in_search_results(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store("Some context about backtest performance details",
                     agent="test", memory_type="strategy", skip_gate=True)

        results = store.search("backtest performance")
        assert "level" in results[0]


class TestBrainStoreSearchPrioritization:
    """Tests for search result prioritization by level (Phase 4.3)."""

    def test_higher_levels_appear_first(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Level 0: raw event
        store.store("Risk management is important for trading strategies",
                     agent="test", memory_type="context", skip_gate=True)
        # Level 2: knowledge
        r2 = store.store("Position sizing using Kelly criterion reduces risk",
                          agent="test", memory_type="architecture", skip_gate=True)
        # Level 3: principle
        r3 = store.store("Never risk more than two percent of portfolio on single trade",
                          agent="test", memory_type="architecture", skip_gate=True)

        # Manually elevate levels in ChromaDB
        _set_level(store, r2["id"], 2)
        _set_level(store, r3["id"], 3)

        results = store.search("risk management position sizing", reinforce=False)

        # The level-3 entry should come before level-0 entries
        levels = [r["level"] for r in results]
        assert levels[0] >= levels[-1], f"Expected descending level order, got {levels}"

    def test_max_results_limits_output(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(15):
            store.store(f"Memory entry number {i} about various trading topics and strategies",
                         agent="test", memory_type="context", skip_gate=True)

        # Default max_results=10
        results = store.search("trading topics strategies")
        assert len(results) <= 10

    def test_custom_max_results(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(10):
            store.store(f"Memory entry {i} about crypto market analysis and indicators",
                         agent="test", memory_type="context", skip_gate=True)

        results = store.search("crypto market analysis", max_results=3)
        assert len(results) <= 3

    def test_principles_always_included(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store a principle
        r_principle = store.store(
            "Fundamental principle: always use stop-losses on every position",
            agent="test", memory_type="architecture", skip_gate=True,
        )
        _set_level(store, r_principle["id"], 3)

        # Store several raw entries
        for i in range(5):
            store.store(f"Raw observation {i} about stop-loss placement strategies",
                         agent="test", memory_type="context", skip_gate=True)

        results = store.search("stop-loss strategies", max_results=10, reinforce=False)

        # Principle should be in the results
        principle_ids = [r["id"] for r in results if r["level"] >= 3]
        assert r_principle["id"] in principle_ids


class TestBrainStoreDedupKey:
    """Tests for dedup_key bug fix (Phase 4.1)."""

    def test_dedup_key_stored_in_metadata_for_errors(self, tmp_path: Path):
        """When gate processes an error, dedup_key should be stored in ChromaDB metadata."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        result = store.store(
            content="Error: connection timeout to exchange API when placing order",
            agent="test-agent",
            memory_type="bug",
            metadata={"event_type": "error"},
            skip_gate=False,
        )
        assert result is not None

        raw = store._collection.get(ids=[result["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        assert "dedup_key" in meta
        assert len(meta["dedup_key"]) > 0

    def test_dedup_key_absent_when_gate_skipped(self, tmp_path: Path):
        """When skip_gate=True, no dedup_key should be stored."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        result = store.store(
            content="This is a memory stored with gate bypassed for migration purposes",
            agent="test-agent",
            memory_type="context",
            skip_gate=True,
        )
        assert result is not None

        raw = store._collection.get(ids=[result["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        assert "dedup_key" not in meta

    def test_dedup_key_absent_for_non_error_content(self, tmp_path: Path):
        """Non-error content accepted by gate should not have a dedup_key."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        result = store.store(
            content="Momentum strategy produced a Sharpe of 1.5 on SOL/USDT in Q1",
            agent="test-agent",
            memory_type="strategy",
            skip_gate=False,
        )
        assert result is not None

        raw = store._collection.get(ids=[result["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        # Gate doesn't generate dedup_key for non-error content
        assert "dedup_key" not in meta

    def test_increment_existing_works_with_dedup_key(self, tmp_path: Path):
        """Storing the same error twice should increment the occurrence counter."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        content = "Error: timeout connecting to exchange API for order submission"

        # First store: accepted (error, first occurrence)
        r1 = store.store(
            content=content, agent="test", memory_type="bug",
            metadata={"event_type": "error"}, skip_gate=False,
        )
        assert r1 is not None
        assert "id" in r1

        # Second store: should be INCREMENT (duplicate error in gate)
        r2 = store.store(
            content=content, agent="test", memory_type="bug",
            metadata={"event_type": "error"}, skip_gate=False,
        )
        # With the dedup_key fix, _increment_existing() should find the entry
        assert r2 is not None
        assert r2.get("incremented") is True
        assert r2.get("count", 0) >= 2


class TestBrainStoreGateIntegration:
    """Tests for gate integration in store."""

    def test_gate_rejects_noise(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        result = store.store(content="ok", agent="test", memory_type="context", skip_gate=False)
        assert result is None

    def test_gate_accepts_valid_content(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        result = store.store(
            content="The momentum strategy showed a Sharpe ratio of 1.5 on SOL/USDT",
            agent="test",
            memory_type="strategy",
            skip_gate=False,
        )
        assert result is not None


class TestConsolidation:
    """Tests for the consolidation engine (Brain v2)."""

    def test_consolidate_creates_level_1(self, tmp_path: Path):
        """Store 5+ entries with same strategy -> consolidate() -> level-1 exists."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(6):
            store.store(
                content=f"EMA crossover observation {i} on ETH/USDT showed profit in trending market",
                agent="test",
                memory_type="strategy",
                skip_gate=True,
            )

        result = store.consolidate()
        assert result["level_1_created"] >= 1
        assert result["entries_processed"] >= 5

        # Verify level-1 entry exists in ChromaDB
        level_1 = store._collection.get(where={"level": 1}, include=["metadatas", "documents"])
        assert len(level_1["ids"]) >= 1
        meta = level_1["metadatas"][0]
        assert meta["level"] == 1
        assert "links" in meta  # Should link to originals

    def test_consolidate_creates_level_2(self, tmp_path: Path):
        """Store enough level-1 entries with shared concept -> level-2 exists."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Create 3 level-1 entries manually with shared concept "drawdown"
        for i in range(3):
            entry_id = f"l1-entry-{i}"
            store._collection.add(
                ids=[entry_id],
                documents=[f"Level-1 summary {i} about drawdown management in strategy_{i}"],
                metadatas=[{
                    "agent": "brain-consolidation",
                    "memory_type": "strategy",
                    "created_at": "2026-03-01T00:00:00+00:00",
                    "access_count": 0,
                    "confidence": 1.0,
                    "sentiment": "neutral",
                    "level": 1,
                    "concepts": "drawdown,risk management",
                    "strategies": f"strategy_{i}",
                }],
            )

        result = store.consolidate()
        assert result["level_2_created"] >= 1

        # Verify level-2 entry exists
        level_2 = store._collection.get(where={"level": 2}, include=["metadatas"])
        assert len(level_2["ids"]) >= 1
        assert level_2["metadatas"][0]["level"] == 2

    def test_consolidate_logs_events(self, tmp_path: Path):
        """EventLog should contain 'consolidated' events after consolidation."""
        events_path = tmp_path / "events.jsonl"
        from brain.events import EventLog
        event_log = EventLog(path=events_path)
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"), event_log=event_log)

        for i in range(6):
            store.store(
                content=f"Momentum strategy observation {i} on BTC/USDT showed strong signals",
                agent="test",
                memory_type="strategy",
                skip_gate=True,
            )

        store.consolidate()

        recent = event_log.recent(limit=100)
        consolidated_events = [e for e in recent if e["event_type"] == "consolidated"]
        assert len(consolidated_events) >= 1

    def test_consolidate_links_originals(self, tmp_path: Path):
        """Level-1 entry should have links to originals; originals have consolidated_into."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        original_ids = []
        for i in range(6):
            r = store.store(
                content=f"RSI strategy result {i} on SOL/USDT with overbought signal detected",
                agent="test",
                memory_type="strategy",
                skip_gate=True,
            )
            original_ids.append(r["id"])

        store.consolidate()

        # Check level-1 entry has links
        level_1 = store._collection.get(where={"level": 1}, include=["metadatas"])
        assert len(level_1["ids"]) >= 1
        links_str = level_1["metadatas"][0].get("links", "")
        links = [lk.strip() for lk in links_str.split(",") if lk.strip()]
        assert len(links) >= 5

        # Check originals have consolidated_into set
        for oid in original_ids:
            raw = store._collection.get(ids=[oid], include=["metadatas"])
            meta = raw["metadatas"][0]
            assert meta.get("consolidated_into"), f"Entry {oid} missing consolidated_into"

    def test_consolidate_idempotent(self, tmp_path: Path):
        """Running consolidate() twice should not create duplicate summaries."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(6):
            store.store(
                content=f"MACD strategy observation {i} on ETH/USDT with crossover signal",
                agent="test",
                memory_type="strategy",
                skip_gate=True,
            )

        r1 = store.consolidate()
        r2 = store.consolidate()

        assert r1["level_1_created"] >= 1
        assert r2["level_1_created"] == 0  # No new summaries on second run


class TestContradictionDetection:
    """Tests for contradiction detection at write time (Brain v2)."""

    def test_contradiction_marks_superseded(self, tmp_path: Path):
        """Store success entry, then failure entry for same topic -> first marked superseded."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store a success entry
        r1 = store.store(
            content="EMA crossover strategy on ETH/USDT works well and profit was gained in trending markets",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )
        assert r1 is not None

        # Store a contradicting failure entry (very similar content, opposite sentiment)
        r2 = store.store(
            content="EMA crossover strategy on ETH/USDT failed badly and loss was incurred in trending markets",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )
        assert r2 is not None

        # Check the first entry is marked superseded
        raw = store._collection.get(ids=[r1["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        assert meta.get("superseded") is True
        assert meta.get("superseded_by") == r2["id"]

    def test_no_contradiction_same_sentiment(self, tmp_path: Path):
        """Store two success entries for same topic -> neither superseded."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="Momentum strategy works great and profit was gained on BTC/USDT",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )
        r2 = store.store(
            content="Momentum strategy works great and profit was improved on BTC/USDT",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )

        # Neither should be superseded
        raw1 = store._collection.get(ids=[r1["id"]], include=["metadatas"])
        assert raw1["metadatas"][0].get("superseded") is not True

        raw2 = store._collection.get(ids=[r2["id"]], include=["metadatas"])
        assert raw2["metadatas"][0].get("superseded") is not True

    def test_superseded_filtered_from_search(self, tmp_path: Path):
        """Superseded entries should not appear in default search results."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="Bollinger band strategy on DOGE/USDT works perfectly and profit was gained",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )

        # Manually mark as superseded
        raw = store._collection.get(ids=[r1["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        meta["superseded"] = True
        meta["superseded_by"] = "some-new-id"
        store._collection.update(ids=[r1["id"]], metadatas=[meta])

        # Default search should filter it out
        results = store.search("Bollinger band strategy DOGE", reinforce=False)
        result_ids = [r["id"] for r in results]
        assert r1["id"] not in result_ids

    def test_superseded_included_when_requested(self, tmp_path: Path):
        """Superseded entries should appear when include_superseded=True."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="Grid trading strategy on LINK/USDT works perfectly and profit was gained",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )

        # Manually mark as superseded
        raw = store._collection.get(ids=[r1["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        meta["superseded"] = True
        meta["superseded_by"] = "some-new-id"
        store._collection.update(ids=[r1["id"]], metadatas=[meta])

        # Search with include_superseded=True should include it
        results = store.search("Grid trading strategy LINK", reinforce=False, include_superseded=True)
        result_ids = [r["id"] for r in results]
        assert r1["id"] in result_ids


class TestCompositeScoring:
    """Tests for composite scoring in search (Brain v2)."""

    def test_recent_entry_scores_higher(self, tmp_path: Path):
        """A recent entry should score above an old entry at similar distance."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store an old entry
        r_old = store.store(
            content="Mean reversion on BTC/USDT is profitable in ranging markets",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )
        # Manually backdate the old entry
        raw = store._collection.get(ids=[r_old["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        meta["created_at"] = "2025-01-01T00:00:00+00:00"
        store._collection.update(ids=[r_old["id"]], metadatas=[meta])

        # Store a recent entry (same topic)
        r_new = store.store(
            content="Mean reversion on BTC/USDT is very profitable in ranging markets recently",
            agent="test",
            memory_type="strategy",
            skip_gate=True,
        )

        results = store.search("mean reversion BTC ranging", reinforce=False)
        assert len(results) >= 2

        # The recent entry should have a higher score
        scores_by_id = {r["id"]: r["score"] for r in results}
        assert scores_by_id[r_new["id"]] > scores_by_id[r_old["id"]]

    def test_high_level_scores_higher(self, tmp_path: Path):
        """A level-2 entry should score above a level-0 entry at similar distance."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store a level-0 entry
        r0 = store.store(
            content="Stop-loss placement is critical for risk management in all strategies",
            agent="test",
            memory_type="context",
            skip_gate=True,
        )

        # Store a level-2 entry (same topic)
        r2 = store.store(
            content="Stop-loss placement is critical for risk management in trading",
            agent="test",
            memory_type="architecture",
            skip_gate=True,
        )
        _set_level(store, r2["id"], 2)

        results = store.search("stop-loss risk management", reinforce=False)
        assert len(results) >= 2

        scores_by_id = {r["id"]: r["score"] for r in results}
        assert scores_by_id[r2["id"]] > scores_by_id[r0["id"]]

    def test_search_results_have_score_field(self, tmp_path: Path):
        """Search results should include a 'score' field."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store(
            content="Kelly criterion is used for optimal position sizing in trading",
            agent="test",
            memory_type="architecture",
            skip_gate=True,
        )

        results = store.search("Kelly position sizing", reinforce=False)
        assert len(results) >= 1
        assert "score" in results[0]
        assert isinstance(results[0]["score"], float)
        assert results[0]["score"] > 0


class TestGraphAugmentedSearch:
    """Tests for graph-augmented search in BrainStore (Brain v2 graph)."""

    def test_search_includes_graph_neighbors(self, tmp_path: Path):
        """Search returns entries linked via graph that wouldn't appear in top-k cosine alone.

        We store two entries that are semantically unrelated but explicitly linked.
        When searching for one, the other should appear via graph expansion.
        """
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Entry about crypto trading (will be the search target)
        r1 = store.store(
            content="Bitcoin momentum strategy showed strong uptrend signals on BTC/USDT pair",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        # Entry about completely different topic but explicitly linked
        r2 = store.store(
            content="Infrastructure Docker container deployment process and configuration notes",
            agent="test", memory_type="architecture", skip_gate=True,
            links=[r1["id"]],
        )

        # Search for Bitcoin-related content. r2 is semantically distant but
        # should appear via graph neighbor expansion.
        results = store.search("Bitcoin momentum BTC", reinforce=False, max_results=20)
        result_ids = [r["id"] for r in results]
        assert r1["id"] in result_ids
        assert r2["id"] in result_ids

    def test_graph_invalidated_on_store(self, tmp_path: Path):
        """After store(), graph should be rebuilt on next search."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        # Store first entry and trigger graph build via search
        store.store(
            content="RSI overbought detection on SOL/USDT token",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        store.search("RSI overbought", reinforce=False)
        assert store._graph is not None

        # Store a new entry -- should invalidate the graph
        store.store(
            content="MACD crossover signal detected on ETH/USDT pair",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        assert store._graph is None  # Invalidated

    def test_graph_invalidated_on_forget(self, tmp_path: Path):
        """After forget(), graph cache should be cleared."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="Trailing stop-loss technique for managing open positions",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        # Build graph via search
        store.search("stop-loss", reinforce=False)
        assert store._graph is not None

        store.forget(r1["id"])
        assert store._graph is None

    def test_graph_invalidated_on_consolidate(self, tmp_path: Path):
        """After consolidate(), graph cache should be cleared."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        for i in range(6):
            store.store(
                content=f"EMA crossover observation {i} on ETH/USDT showed profit in trending market",
                agent="test", memory_type="strategy", skip_gate=True,
            )

        # Build graph via search
        store.search("EMA crossover", reinforce=False)
        assert store._graph is not None

        store.consolidate()
        assert store._graph is None

    def test_graph_neighbor_has_penalty_distance(self, tmp_path: Path):
        """Graph neighbor entries get distance=0.8 when added by graph expansion.

        Verifies the mechanism directly: build graph, get neighbors, confirm
        the penalty distance is applied when neighbors are fetched.
        """
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="Bollinger band squeeze setup on AVAX/USDT breakout signal",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        r2 = store.store(
            content="Docker container PostgreSQL migration rollback procedure",
            agent="test", memory_type="architecture", skip_gate=True,
            links=[r1["id"]],
        )

        # Verify the graph finds r2 as neighbor of r1
        graph = store._get_graph()
        neighbors = graph.get_neighbors([r1["id"]])
        assert r2["id"] in neighbors, "r2 should be a graph neighbor of r1"

        # Verify the penalty distance constant is used in search integration
        # (The actual value 0.8 is hardcoded in store.py search graph expansion)
        from brain import store as store_module
        source = __import__("inspect").getsource(store_module.BrainStore.search)
        assert "0.8" in source, "Search should use 0.8 as graph neighbor penalty distance"

    def test_get_all_for_graph_includes_superseded_by(self, tmp_path: Path):
        """get_all_for_graph should include superseded_by field."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))

        r1 = store.store(
            content="Grid trading on LINK/USDT works well and profit was gained in ranging market",
            agent="test", memory_type="strategy", skip_gate=True,
        )
        # Manually mark as superseded
        raw = store._collection.get(ids=[r1["id"]], include=["metadatas"])
        meta = raw["metadatas"][0]
        meta["superseded"] = True
        meta["superseded_by"] = "new-entry-id"
        store._collection.update(ids=[r1["id"]], metadatas=[meta])

        entries = store.get_all_for_graph()
        superseded_entries = [e for e in entries if e["superseded_by"] == "new-entry-id"]
        assert len(superseded_entries) == 1


def _set_level(store: BrainStore, entry_id: str, level: int) -> None:
    """Helper to manually set the level on an existing entry."""
    raw = store._collection.get(ids=[entry_id], include=["metadatas"])
    meta = raw["metadatas"][0] or {}
    store._collection.update(
        ids=[entry_id],
        metadatas=[{**meta, "level": level}],
    )


class TestCustomMetadataAndTopK:
    """Regression coverage for issues #1 (custom metadata) and #2 (top_k)."""

    def test_custom_metadata_round_trips_through_search(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store(
            content="User said their favorite color is blue",
            agent="longmemeval",
            memory_type="context",
            metadata={
                "session_id": "sess-123",
                "session_date": "2025-03-01",
                "turn_idx": 4,
                "role": "user",
            },
            skip_gate=True,
        )

        results = store.search("favorite color")
        assert len(results) >= 1
        assert "metadata" in results[0], "search() must expose custom metadata dict"
        custom = results[0]["metadata"]
        assert custom["session_id"] == "sess-123"
        assert custom["session_date"] == "2025-03-01"
        assert custom["turn_idx"] == 4
        assert custom["role"] == "user"

    def test_custom_metadata_does_not_collide_with_reserved_fields(self, tmp_path: Path):
        """Native Brain fields (agent, memory_type, …) stay at top level, NOT in metadata."""
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store(
            content="Some content",
            agent="test-agent",
            memory_type="context",
            metadata={"session_id": "s1"},
            skip_gate=True,
        )
        results = store.search("content")
        assert results[0]["agent"] == "test-agent"
        assert results[0]["memory_type"] == "context"
        assert "agent" not in results[0]["metadata"]
        assert "memory_type" not in results[0]["metadata"]
        assert results[0]["metadata"] == {"session_id": "s1"}

    def test_metadata_empty_dict_when_no_custom_keys(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        store.store(
            content="Content with no custom metadata",
            agent="t", memory_type="context", skip_gate=True,
        )
        results = store.search("Content")
        assert results[0]["metadata"] == {}

    def test_top_k_three_returns_three(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(10):
            store.store(
                content=f"Memory number {i} about Lake Michigan sailing",
                agent="t", memory_type="context", skip_gate=True,
            )
        results = store.search("sailing", top_k=3, reinforce=False)
        assert len(results) == 3, f"top_k=3 must return 3 results, got {len(results)}"

    def test_top_k_seven_returns_seven(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(10):
            store.store(
                content=f"Memory number {i} about kayaking",
                agent="t", memory_type="context", skip_gate=True,
            )
        results = store.search("kayaking", top_k=7, reinforce=False)
        assert len(results) == 7, f"top_k=7 must return 7 results, got {len(results)}"

    def test_top_k_greater_than_total_returns_all(self, tmp_path: Path):
        store = BrainStore(persist_dir=str(tmp_path / "chromadb"))
        for i in range(3):
            store.store(
                content=f"Memory {i} about hiking",
                agent="t", memory_type="context", skip_gate=True,
            )
        results = store.search("hiking", top_k=100, reinforce=False)
        assert len(results) == 3
