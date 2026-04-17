"""Brain enrichment -- extract structured metadata from content.

At write time, the enrichment layer parses content to extract:
- Symbols (BTC/USDT, ETH/USDT)
- Strategies (ema_crossover, mean_reversion, momentum)
- Concepts (drawdown, Sharpe, stop-loss, Kelly)
- Sentiment (success/failure/neutral)

These become ChromaDB metadata for filtered semantic search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Known entities
# ---------------------------------------------------------------------------

# TODO(phase-5): These hardcoded frozensets should be config-driven, loaded
# from config/brain_entities.yaml or similar. This would let operators add
# new symbols, strategies, and concepts without code changes. For now the
# sets cover the common entities used by the Money trading system.

_SYMBOL_RE = re.compile(r"\b([A-Z]{2,10}/[A-Z]{2,10})\b")

KNOWN_STRATEGIES = frozenset({
    "ema_crossover", "mean_reversion", "momentum", "rsi",
    "bollinger", "macd", "breakout", "pairs_trading",
    "trend_following", "scalping", "grid_trading",
})

KNOWN_CONCEPTS = frozenset({
    "drawdown", "sharpe", "sortino", "stop-loss", "stop_loss",
    "take-profit", "take_profit", "kelly", "position sizing",
    "position_sizing", "risk management", "risk_management",
    "backtest", "paper trading", "paper_trading", "live trading",
    "slippage", "volatility", "correlation", "diversification",
    "rebalance", "regime", "bull", "bear", "consolidation",
    "breakout", "support", "resistance", "volume", "liquidity",
    "half-kelly", "half_kelly", "circuit breaker", "kill switch",
})

_SUCCESS_WORDS = frozenset({
    "success", "passed", "approved", "profit", "gained", "improved",
    "works", "solved", "fixed", "merged", "deployed",
})

_FAILURE_WORDS = frozenset({
    "failure", "failed", "rejected", "loss", "crashed", "error",
    "bug", "broke", "reverted", "abandoned", "timeout",
})


@dataclass
class EnrichedMetadata:
    """Structured metadata extracted from content."""

    symbols: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    sentiment: str = "neutral"  # success, failure, neutral

    def to_chromadb_metadata(self) -> dict[str, str]:
        """Convert to flat dict for ChromaDB metadata (strings only)."""
        meta: dict[str, str] = {}
        if self.symbols:
            meta["symbols"] = ",".join(self.symbols)
        if self.strategies:
            meta["strategies"] = ",".join(self.strategies)
        if self.concepts:
            meta["concepts"] = ",".join(self.concepts[:10])
        meta["sentiment"] = self.sentiment
        return meta


def enrich(content: str, existing_metadata: dict | None = None) -> EnrichedMetadata:
    """Extract structured metadata from content text.

    Args:
        content: The text to analyze.
        existing_metadata: Optional pre-existing metadata to merge.

    Returns:
        EnrichedMetadata with extracted entities.
    """
    content_lower = content.lower()
    result = EnrichedMetadata()

    # Symbols
    result.symbols = list(set(_SYMBOL_RE.findall(content)))

    # Strategies
    result.strategies = [
        s for s in KNOWN_STRATEGIES
        if s in content_lower or s.replace("_", " ") in content_lower
    ]

    # Concepts
    result.concepts = [
        c for c in KNOWN_CONCEPTS
        if c in content_lower or c.replace("_", " ") in content_lower or c.replace("-", " ") in content_lower
    ]

    # Sentiment
    words = set(re.findall(r"[a-z]+", content_lower))
    success_count = len(words & _SUCCESS_WORDS)
    failure_count = len(words & _FAILURE_WORDS)
    if success_count > failure_count:
        result.sentiment = "success"
    elif failure_count > success_count:
        result.sentiment = "failure"

    # Merge existing metadata if provided
    if existing_metadata:
        if "symbol" in existing_metadata and existing_metadata["symbol"] not in result.symbols:
            result.symbols.append(existing_metadata["symbol"])
        if "strategy" in existing_metadata and existing_metadata["strategy"] not in result.strategies:
            result.strategies.append(existing_metadata["strategy"])

    return result
