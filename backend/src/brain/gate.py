"""Brain gate -- decides what gets stored and what is noise.

Like the human brain's attention mechanism: not everything deserves
to be remembered. The gate filters, deduplicates, and prioritizes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GateVerdict(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    INCREMENT = "increment"  # Same event seen before, just bump counter


@dataclass
class GateResult:
    verdict: GateVerdict
    reason: str
    priority: float = 0.5  # 0.0 = low, 1.0 = critical
    dedup_key: str = ""    # For increment: which existing entry to bump


# Event types that are always noise
_NOISE_TYPES = frozenset({"scan", "heartbeat", "ping"})

# Event types that are always significant
_SIGNIFICANT_TYPES = frozenset({"trade", "error", "lesson", "architecture", "strategy_created"})


class BrainGate:
    """Filter incoming data -- reject noise, accept signal."""

    def __init__(self, seen_errors: dict[str, int] | None = None) -> None:
        # Track seen error signatures to deduplicate
        self._seen_errors: dict[str, int] = seen_errors or {}

    def evaluate(
        self,
        content: str,
        event_type: str = "",
        agent: str = "",
        metadata: dict | None = None,
    ) -> GateResult:
        """Decide if this content should be stored in the brain.

        Returns a GateResult with verdict, reason, and priority.
        """
        metadata = metadata or {}

        # Rule 1: Empty or very short content is noise
        if len(content.strip()) < 10:
            return GateResult(
                verdict=GateVerdict.REJECT,
                reason="Content too short to be meaningful",
            )

        # Rule 2: Known noise event types
        if event_type in _NOISE_TYPES:
            return GateResult(
                verdict=GateVerdict.REJECT,
                reason=f"Noise event type: {event_type}",
            )

        # Rule 3: Routine scan with no signals
        if event_type == "scan" or "symbols_scanned" in metadata:
            signals = metadata.get("signals_generated", 0)
            if not signals:
                return GateResult(
                    verdict=GateVerdict.REJECT,
                    reason="Routine scan with no signals",
                )

        # Rule 4: Duplicate error detection
        if event_type == "error" or "error" in content.lower()[:50]:
            error_sig = _error_signature(content)
            if error_sig in self._seen_errors:
                self._seen_errors[error_sig] += 1
                return GateResult(
                    verdict=GateVerdict.INCREMENT,
                    reason=f"Duplicate error (seen {self._seen_errors[error_sig]}x)",
                    dedup_key=error_sig,
                )
            self._seen_errors[error_sig] = 1
            return GateResult(
                verdict=GateVerdict.ACCEPT,
                reason="First occurrence of this error",
                priority=0.8,
                dedup_key=error_sig,
            )

        # Rule 5: Trade executed -- always significant
        if event_type == "decision" or metadata.get("order_submitted"):
            return GateResult(
                verdict=GateVerdict.ACCEPT,
                reason="Trade executed",
                priority=0.7,
            )

        # Rule 6: Risk rejection -- learn from it
        risk = metadata.get("risk", {})
        if isinstance(risk, dict) and risk.get("approved") is False:
            return GateResult(
                verdict=GateVerdict.ACCEPT,
                reason="Risk rejection -- learn why",
                priority=0.6,
            )

        # Rule 7: Significant event types
        if event_type in _SIGNIFICANT_TYPES:
            return GateResult(
                verdict=GateVerdict.ACCEPT,
                reason=f"Significant event: {event_type}",
                priority=0.8 if event_type in ("lesson", "architecture") else 0.6,
            )

        # Rule 8: Agent-generated insights (strategy, lesson, architecture)
        content_lower = content.lower()
        if any(kw in content_lower for kw in ("lesson:", "hypothesis:", "architecture:")):
            return GateResult(
                verdict=GateVerdict.ACCEPT,
                reason="Agent insight detected",
                priority=0.9,
            )

        # Default: accept with normal priority
        return GateResult(
            verdict=GateVerdict.ACCEPT,
            reason="Default accept",
            priority=0.5,
        )


def _error_signature(content: str) -> str:
    """Extract a dedup key from error content.

    Strips variable parts (timestamps, order IDs, prices) to match
    structurally identical errors.
    """
    import re
    # Remove numbers (prices, IDs, timestamps)
    sig = re.sub(r"\d+\.?\d*", "N", content[:200])
    # Remove extra whitespace
    sig = re.sub(r"\s+", " ", sig).strip()
    return sig[:100]
