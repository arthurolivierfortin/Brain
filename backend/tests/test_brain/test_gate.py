"""Tests for the brain gate (noise filter)."""

from __future__ import annotations

from brain.gate import BrainGate, GateVerdict


class TestBrainGate:

    def test_reject_short_content(self):
        gate = BrainGate()
        result = gate.evaluate("hi", event_type="context")
        assert result.verdict == GateVerdict.REJECT

    def test_reject_scan_no_signals(self):
        gate = BrainGate()
        result = gate.evaluate(
            "Scanned 3 symbols, no signals",
            event_type="scan",
            metadata={"symbols_scanned": ["BTC/USDT"], "signals_generated": 0},
        )
        assert result.verdict == GateVerdict.REJECT

    def test_accept_trade(self):
        gate = BrainGate()
        result = gate.evaluate(
            "Trade buy BTC/USDT via mean_reversion",
            event_type="decision",
            metadata={"order_submitted": True},
        )
        assert result.verdict == GateVerdict.ACCEPT

    def test_accept_first_error(self):
        gate = BrainGate()
        result = gate.evaluate(
            "Error: binance NOTIONAL filter failure",
            event_type="error",
        )
        assert result.verdict == GateVerdict.ACCEPT
        assert result.priority == 0.8

    def test_increment_duplicate_error(self):
        gate = BrainGate()
        gate.evaluate("Error: binance NOTIONAL filter failure", event_type="error")
        result = gate.evaluate("Error: binance NOTIONAL filter failure", event_type="error")
        assert result.verdict == GateVerdict.INCREMENT

    def test_accept_risk_rejection(self):
        gate = BrainGate()
        result = gate.evaluate(
            "Position size too large for BTC/USDT",
            metadata={"risk": {"approved": False, "reason": "exceeds max"}},
        )
        assert result.verdict == GateVerdict.ACCEPT

    def test_accept_agent_insight(self):
        gate = BrainGate()
        result = gate.evaluate(
            "Lesson: mean_reversion works poorly on SOL during high volatility",
        )
        assert result.verdict == GateVerdict.ACCEPT
        assert result.priority == 0.9

    def test_default_accept(self):
        gate = BrainGate()
        result = gate.evaluate(
            "Some general observation about the market",
            event_type="observation",
        )
        assert result.verdict == GateVerdict.ACCEPT
        assert result.priority == 0.5

    def test_first_error_provides_dedup_key(self):
        """Phase 4.1 fix: first error ACCEPT should include dedup_key
        so it can be stored in ChromaDB for future _increment_existing lookups.
        """
        gate = BrainGate()
        result = gate.evaluate(
            "Error: connection timeout to exchange API endpoint",
            event_type="error",
        )
        assert result.verdict == GateVerdict.ACCEPT
        assert result.dedup_key != "", "First error should provide dedup_key for storage"

    def test_duplicate_error_dedup_key_matches(self):
        """The dedup_key for increment should match what was returned on first accept."""
        gate = BrainGate()
        r1 = gate.evaluate("Error: rate limit exceeded on order endpoint", event_type="error")
        r2 = gate.evaluate("Error: rate limit exceeded on order endpoint", event_type="error")
        assert r1.verdict == GateVerdict.ACCEPT
        assert r2.verdict == GateVerdict.INCREMENT
        assert r1.dedup_key == r2.dedup_key
