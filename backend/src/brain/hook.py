"""Hook architecture — Extractor Protocol, dataclasses, handlers.

See docs/specs/2026-04-19-hook-architecture-design.md.
"""
from __future__ import annotations

import json
import os
import re
import time
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


class WakeUpHandler:
    """Selects L0 + L1 memories and formats them as a system-prompt injection."""

    L0_TAG = "identity"
    L1_TAG = "preference"
    BUDGET_TOKENS = 500

    def __init__(self, store: Any) -> None:
        self._store = store

    def handle(self, req: HookRequest) -> WakeUpResponse:
        t0 = time.monotonic()
        identity = self._store.search_by_tag(self.L0_TAG, agent=req.agent, top_k=5)
        prefs = self._store.search_by_tag(self.L1_TAG, agent=req.agent, top_k=10)

        context = self._format(identity, prefs)
        while self._tokens(context) > self.BUDGET_TOKENS and (identity or prefs):
            if prefs:
                prefs.pop()
            else:
                identity.pop()
            context = self._format(identity, prefs)

        duration_ms = int((time.monotonic() - t0) * 1000)
        return WakeUpResponse(
            context=context,
            layers_loaded={"L0": len(identity), "L1": len(prefs)},
            tokens_approx=self._tokens(context),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _format(identity: list[dict], prefs: list[dict]) -> str:
        lines: list[str] = []
        if identity:
            lines.append("## Identity")
            for m in identity:
                lines.append(f"- {m['content']}")
        if prefs:
            if identity:
                lines.append("")
            lines.append("## Preferences")
            for m in prefs:
                lines.append(f"- {m['content']}")
        return "\n".join(lines)

    @staticmethod
    def _tokens(text: str) -> int:
        return len(text) // 4


class PostTurnHandler:
    """Extracts, gates, stores. Fallback to raw-blob if extractor returns [] or raises."""

    def __init__(self, store: Any, extractor: Extractor, events: Any) -> None:
        self._store = store
        self._extractor = extractor
        self._events = events

    def handle(self, req: HookRequest, turn: Turn) -> PostTurnResponse:
        t0 = time.monotonic()
        try:
            memories = self._extractor.extract(turn)
        except Exception:
            memories = []
        extraction_ms = int((time.monotonic() - t0) * 1000)

        extracted: list[dict] = []
        rejected = 0

        if not memories:
            raw = self._fallback_content(turn)
            if raw:
                result = self._store.store(
                    content=raw,
                    agent=req.agent,
                    memory_type="raw-fallback",
                    metadata={
                        "tags": "",
                        "confidence": 0.3,
                        "session_id": req.session_id,
                        "project": req.project,
                    },
                    skip_gate=False,
                )
                if result:
                    extracted.append({
                        "id": result.get("id", ""),
                        "type": "raw-fallback",
                        "content": raw[:200],
                        "tags": [],
                    })
                else:
                    rejected += 1
        else:
            for em in memories:
                sanitized = [self._sanitize_tag(t) for t in em.tags]
                result = self._store.store(
                    content=em.content,
                    agent=req.agent,
                    memory_type=em.type,
                    metadata={
                        "tags": ",".join(t for t in sanitized if t),
                        "confidence": em.confidence,
                        "session_id": req.session_id,
                        "project": req.project,
                    },
                    skip_gate=False,
                )
                if result:
                    extracted.append({
                        "id": result.get("id", ""),
                        "type": em.type,
                        "content": em.content,
                        "tags": sanitized,
                    })
                else:
                    rejected += 1

        self._events.log(
            event_type="hook_post_turn",
            agent=req.agent,
            metadata={
                "extracted_count": len(extracted),
                "rejected_count": rejected,
                "extraction_ms": extraction_ms,
            },
        )
        return PostTurnResponse(
            extracted=extracted,
            rejected_by_gate=rejected,
            extraction_cost_usd=0.0,
            extraction_ms=extraction_ms,
        )

    @staticmethod
    def _fallback_content(turn: Turn) -> str:
        parts = []
        if turn.user:
            parts.append(f"USER: {turn.user}")
        if turn.assistant:
            parts.append(f"ASSISTANT: {turn.assistant}")
        return "\n".join(parts)[:2000]

    @staticmethod
    def _sanitize_tag(tag: str) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", tag.lower()).strip("-")
