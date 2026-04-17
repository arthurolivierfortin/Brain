"""Anthropic (Claude) LLM wrapper — for release runs, tracks cost per call."""
from __future__ import annotations

import os
from typing import Any

from anthropic import Anthropic

from brain_bench.llm.base import LLMCall


class AnthropicClient:
    """Per-million-token prices in USD. Update when Anthropic changes pricing."""
    PRICING: dict[str, dict[str, float]] = {
        "claude-opus-4-7":     {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-6":   {"input":  3.00, "output": 15.00},
        "claude-haiku-4-5":    {"input":  1.00, "output":  5.00},
    }

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_tokens: int = 1024,
        _client: Any = None,
    ) -> None:
        if model not in self.PRICING:
            raise ValueError(
                f"No pricing for {model!r}. Add it to AnthropicClient.PRICING."
            )
        self._model = model
        self._max_tokens = max_tokens
        if _client is not None:
            self._client = _client
        else:
            self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system: str, user: str) -> LLMCall:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text if resp.content else ""
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        p = self.PRICING[self._model]
        cost = (in_tok * p["input"] + out_tok * p["output"]) / 1_000_000
        return LLMCall(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )
