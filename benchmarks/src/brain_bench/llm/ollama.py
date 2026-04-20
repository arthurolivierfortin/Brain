"""Ollama LLM wrapper — local, free, for the dev loop."""
from __future__ import annotations

from typing import Any

import ollama

from brain_bench.llm.base import LLMCall


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        _client: Any = None,
    ) -> None:
        self._model = model
        self._client = _client if _client is not None else ollama.Client(host=host)

    def complete(self, system: str, user: str) -> LLMCall:
        resp = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return LLMCall(
            text=resp.message.content or "",
            input_tokens=resp.prompt_eval_count or 0,
            output_tokens=resp.eval_count or 0,
            cost_usd=0.0,
        )
