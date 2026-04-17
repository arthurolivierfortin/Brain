"""Tests for brain enrichment (entity extraction)."""

from __future__ import annotations

from brain.enrichment import enrich


class TestEnrichment:

    def test_extract_symbols(self):
        result = enrich("Trade buy BTC/USDT via mean_reversion, also watching ETH/USDT")
        assert "BTC/USDT" in result.symbols
        assert "ETH/USDT" in result.symbols

    def test_extract_strategies(self):
        result = enrich("The ema_crossover strategy works well in trending markets")
        assert "ema_crossover" in result.strategies

    def test_extract_strategy_with_spaces(self):
        result = enrich("Mean reversion performed poorly on SOL")
        assert "mean_reversion" in result.strategies

    def test_extract_concepts(self):
        result = enrich("The Sharpe ratio improved after adjusting the stop-loss")
        assert "sharpe" in result.concepts
        assert "stop-loss" in result.concepts

    def test_sentiment_success(self):
        result = enrich("Strategy deployed successfully, tests passed, profit increased")
        assert result.sentiment == "success"

    def test_sentiment_failure(self):
        result = enrich("The strategy failed, error occurred, loss detected")
        assert result.sentiment == "failure"

    def test_sentiment_neutral(self):
        result = enrich("Market is moving sideways, no clear direction")
        assert result.sentiment == "neutral"

    def test_chromadb_metadata_format(self):
        result = enrich("Trade BTC/USDT via ema_crossover, good Sharpe ratio")
        meta = result.to_chromadb_metadata()
        assert isinstance(meta["symbols"], str)
        assert "BTC/USDT" in meta["symbols"]
        assert isinstance(meta["sentiment"], str)

    def test_merge_existing_metadata(self):
        result = enrich(
            "Some analysis content",
            existing_metadata={"symbol": "SOL/USDT", "strategy": "momentum"},
        )
        assert "SOL/USDT" in result.symbols
        assert "momentum" in result.strategies

