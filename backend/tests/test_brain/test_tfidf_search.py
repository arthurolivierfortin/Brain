"""Tests for TF-IDF semantic search in brain memory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from brain.memory import (
    MemoryEntry,
    MemoryStore,
    MemoryType,
    _build_tfidf_index,
    _cosine_similarity,
    _tokenize,
)


class TestTokenize:

    def test_basic_tokenization(self):
        tokens = _tokenize("RSI strategy works well on ETH")
        assert "rsi" in tokens
        assert "strategy" in tokens
        assert "eth" in tokens
        # Stop words removed
        assert "on" not in tokens

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_stop_words_only(self):
        assert _tokenize("the is a an") == []

    def test_mixed_case_and_punctuation(self):
        tokens = _tokenize("Hello, World! Test-case 123.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "case" in tokens
        assert "123" in tokens


class TestTfidfIndex:

    def test_single_doc(self):
        docs = [["rsi", "strategy", "momentum"]]
        vectors, idf = _build_tfidf_index(docs)
        assert len(vectors) == 1
        assert "rsi" in vectors[0]
        assert "strategy" in vectors[0]

    def test_idf_differentiation(self):
        # Word in all docs has lower IDF than word in one doc
        docs = [["rsi", "crypto"], ["momentum", "crypto"], ["ema", "crypto"]]
        vectors, idf = _build_tfidf_index(docs)
        assert idf["crypto"] < idf["rsi"]

    def test_empty_corpus(self):
        vectors, idf = _build_tfidf_index([])
        assert vectors == []
        assert idf == {}


class TestCosineSimilarity:

    def test_identical_vectors(self):
        vec = {"a": 1.0, "b": 2.0}
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        vec_a = {"a": 1.0}
        vec_b = {"b": 1.0}
        assert _cosine_similarity(vec_a, vec_b) == 0.0

    def test_empty_vector(self):
        assert _cosine_similarity({}, {"a": 1.0}) == 0.0

    def test_partial_overlap(self):
        vec_a = {"a": 1.0, "b": 1.0}
        vec_b = {"a": 1.0, "c": 1.0}
        sim = _cosine_similarity(vec_a, vec_b)
        assert 0 < sim < 1


class TestTfidfSearch:

    def test_semantic_ranking(self, tmp_path: Path):
        """TF-IDF should rank semantically relevant results higher."""
        store = MemoryStore("test", base_dir=tmp_path)
        store.store("RSI strategy performs well on ETH with overbought signals", MemoryType.STRATEGY, tags=["rsi"])
        store.store("momentum volume filter improves win rate significantly", MemoryType.STRATEGY, tags=["momentum"])
        store.store("architecture decision to use Decimal for money values", MemoryType.ARCHITECTURE)
        store.store("RSI divergence pattern detected on BTC hourly chart", MemoryType.BUG, tags=["rsi", "btc"])

        results = store.search("RSI strategy performance")
        assert len(results) >= 1
        # RSI strategy entry should rank first
        assert "RSI" in results[0].content

    def test_tag_boost(self, tmp_path: Path):
        """Tags should contribute to search relevance."""
        store = MemoryStore("test", base_dir=tmp_path)
        store.store("general trading note", MemoryType.CONTEXT, tags=["momentum", "crypto"])
        store.store("unrelated architecture note", MemoryType.ARCHITECTURE)

        results = store.search("momentum crypto trading")
        assert len(results) >= 1
        assert results[0].tags == ["momentum", "crypto"]

    def test_confidence_weighting(self, tmp_path: Path):
        """Higher confidence entries should rank higher for equal relevance."""
        store = MemoryStore("test", base_dir=tmp_path)

        # Fresh entry (high confidence)
        store.store("ema crossover strategy insight", MemoryType.STRATEGY)

        # Old entry (decayed confidence) — same topic
        old_entry = MemoryEntry(
            id="old1", content="ema crossover strategy old note", memory_type="context", agent="test",
            created_at=(datetime.now(UTC) - timedelta(days=100)).isoformat(),
        )
        store._entries.append(old_entry)
        store._save()

        results = store.search("ema crossover strategy")
        assert len(results) >= 2
        # Fresh entry should rank first due to higher confidence
        assert results[0].compute_confidence() > results[1].compute_confidence()

    def test_fallback_for_short_query(self, tmp_path: Path):
        """Single stop-word queries should fall back to substring match."""
        store = MemoryStore("test", base_dir=tmp_path)
        store.store("the quick brown fox", MemoryType.CONTEXT)
        # "the" is a stop word, so TF-IDF tokenizer produces empty tokens
        # Falls back to substring match
        results = store.search("the")
        assert len(results) >= 1

    def test_no_results(self, tmp_path: Path):
        store = MemoryStore("test", base_dir=tmp_path)
        store.store("something about crypto", MemoryType.CONTEXT)
        results = store.search("completely unrelated quantum physics")
        assert len(results) == 0

    def test_empty_store(self, tmp_path: Path):
        store = MemoryStore("test", base_dir=tmp_path)
        results = store.search("anything")
        assert results == []


class TestConsolidate:

    def test_consolidate_cli_compatible(self, tmp_path: Path):
        """Consolidation should work as expected for CLI command."""
        store = MemoryStore("test-agent", base_dir=tmp_path)
        store.store("fresh architecture note", MemoryType.ARCHITECTURE)
        store.store("fresh strategy note", MemoryType.STRATEGY)

        # Add very old context that should be archived
        old_entry = MemoryEntry(
            id="ancient", content="ancient context", memory_type="context", agent="test",
            created_at=(datetime.now(UTC) - timedelta(days=365)).isoformat(),
        )
        store._entries.append(old_entry)
        store._save()

        stats = store.consolidate()
        assert stats["archived"] >= 1
        assert stats["active"] >= 2  # architecture + strategy survive
