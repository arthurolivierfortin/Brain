"""LLMClient protocol. Two implementations: ollama (dev), anthropic (release)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMCall:
    """Single LLM completion result with usage stats."""
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMClient(Protocol):
    """Chat-completion style LLM."""

    def complete(self, system: str, user: str) -> LLMCall:
        """Return the assistant text + token usage + cost estimate."""
        ...
