"""Hook architecture — Extractor Protocol, dataclasses, handlers.

See docs/specs/2026-04-19-hook-architecture-design.md.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass
class Turn:
    user: str
    assistant: str
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class HookRequest:
    agent: str
    project: str
    session_id: str


@dataclass
class WakeUpResponse:
    context: str
    layers_loaded: dict[str, int]
    tokens_approx: int
    duration_ms: int


@dataclass
class ExtractedMemory:
    content: str
    type: str
    tags: list[str]
    confidence: float


@dataclass
class PostTurnResponse:
    extracted: list[dict]
    rejected_by_gate: int
    extraction_cost_usd: float
    extraction_ms: int


class Extractor(Protocol):
    def extract(self, turn: Turn) -> list[ExtractedMemory]: ...


class GeminiFlashExtractor:
    """Default Extractor — uses Google's Gemini Flash 2.5 free tier.

    Requires GOOGLE_API_KEY env var. Returns [] on any failure; caller
    (PostTurnHandler) handles fallback to raw-blob storage.
    """

    SYSTEM_PROMPT = (
        "Extract structured memories from a development conversation turn. "
        "Output ONLY a JSON object with shape: "
        '{"memories": [{"content": "...", "type": "...", "tags": [...], "confidence": 0.0}, ...]}. '
        "Each memory must be ATOMIC (one fact, decision, or preference — not a summary blob). "
        "Types are open strings (fact, decision, preference, bug, lesson, code-change, tool-use, etc.). "
        "Use tag 'identity' for persona/role/communication-style memories. "
        "Use tag 'preference' for durable user rules. "
        "Other tags describe the topic domain (backend, testing, docker, etc.). "
        "Confidence is 0.0-1.0. Skip memories with confidence < 0.5 rather than emitting noise."
    )

    _API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        timeout: float = 30.0,
        _client: Any = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError("GOOGLE_API_KEY not set — cannot initialize GeminiFlashExtractor")
        self._api_key = key
        self._model = model
        self._client = _client if _client is not None else httpx.Client(timeout=timeout)

    def extract(self, turn: Turn) -> list[ExtractedMemory]:
        prompt = self._build_prompt(turn)
        url = f"{self._API_URL}/{self._model}:generateContent?key={self._api_key}"
        try:
            resp = self._client.post(url, json={
                "systemInstruction": {"parts": [{"text": self.SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 2048,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
            })
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except Exception:
            return []
        out: list[ExtractedMemory] = []
        for mem in parsed.get("memories", []):
            if not isinstance(mem, dict):
                continue
            try:
                out.append(ExtractedMemory(
                    content=mem["content"],
                    type=mem.get("type", "context"),
                    tags=list(mem.get("tags", [])),
                    confidence=float(mem.get("confidence", 1.0)),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def _build_prompt(self, turn: Turn) -> str:
        parts = [f"USER: {turn.user}", f"ASSISTANT: {turn.assistant}"]
        for tc in turn.tool_calls or []:
            name = tc.get("name", "")
            tool_input = json.dumps(tc.get("input", ""))[:200]
            parts.append(f"TOOL: {name} input={tool_input}")
        return "\n\n".join(parts)
