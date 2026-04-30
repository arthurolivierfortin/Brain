"""Hook architecture — Extractor Protocol, dataclasses, handlers.

See docs/specs/2026-04-19-hook-architecture-design.md.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
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
    git_recent_commits: str = ""
    git_branch: str = ""
    claude_md_excerpt: str = ""


@dataclass
class WakeUpResponse:
    context: str
    layers_loaded: dict[str, int]
    tokens_approx: int
    duration_ms: int
    identity: list[dict] = field(default_factory=list)
    prefs: list[dict] = field(default_factory=list)
    topic: list[dict] = field(default_factory=list)


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


BRAIN_L2_TIMEOUT_S: float = 2.0


def _build_topic_query(req: HookRequest) -> str:
    parts: list[str] = []
    if req.git_branch:
        parts.append(f"branch: {req.git_branch}")
    if req.git_recent_commits:
        parts.append(f"recent commits:\n{req.git_recent_commits}")
    if req.claude_md_excerpt:
        parts.append(req.claude_md_excerpt)
    return "\n\n".join(parts).strip()


def _apply_threshold(candidates: list[dict], threshold: float) -> list[dict]:
    return [c for c in candidates if (1.0 - c["distance"] / 2.0) > threshold]


def _age_days(iso_ts: str, now: float) -> float:
    try:
        dt = datetime.fromisoformat(iso_ts)
        return max((now - dt.timestamp()) / 86400, 0.0)
    except (ValueError, TypeError):
        return 0.0


def _rerank_candidates(candidates: list[dict]) -> list[dict]:
    now = time.time()
    for c in candidates:
        cosine = 1.0 - c["distance"] / 2.0
        access = int(c.get("access_count", 0))
        age = _age_days(c.get("created_at", ""), now)
        c["_rerank_score"] = (
            cosine * (1.0 + math.log(access + 1) * 0.05) * math.exp(-age * 0.01)
        )
    return sorted(candidates, key=lambda x: x["_rerank_score"], reverse=True)


def _fit_to_budget(memories: list[dict], cap: int) -> list[dict]:
    out: list[dict] = []
    total = 0
    for m in memories:
        cost = len(m["content"]) // 4
        if total + cost > cap:
            break
        out.append(m)
        total += cost
    return out


def _log_degraded(
    events: Any,
    req: HookRequest,
    reason: str,
    layer_affected: str,
    fallback_used: str = "",
) -> None:
    events.log(
        event_type="degraded_wake_up",
        agent=req.agent,
        metadata={
            "reason": reason,
            "layer_affected": layer_affected,
            "fallback_used": fallback_used,
            "agent": req.agent,
            "session_id": req.session_id,
        },
    )


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
        url = f"{self._API_URL}/{self._model}:generateContent"
        try:
            resp = self._client.post(url, json={
                "systemInstruction": {"parts": [{"text": self.SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 2048,
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
            }, headers={"x-goog-api-key": self._api_key})
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
    """Selects L0 + L1 + L2 memories and formats them as a system-prompt injection.

    L0 = identity tag (cross-agent, cap 100 tokens)
    L1 = preference tag (cross-agent, cap 300 tokens)
    L2 = topic-triggered semantic search (cross-agent, cap 500 tokens)

    See docs/specs/2026-04-28-l2-a-backend-design.md and ADR 0003.
    """

    L0_TAG = "identity"
    L1_TAG = "preference"
    L0_CAP = 100
    L1_CAP = 300
    L2_CAP = 500
    BUDGET_TOKENS = 500

    def __init__(self, store: Any, events: Any = None) -> None:
        self._store = store
        self._events = events
        self._threshold = float(os.environ.get("BRAIN_L2_THRESHOLD", "0.45"))
        self._topk_raw = int(os.environ.get("BRAIN_L2_TOPK_RAW", "20"))

    def handle(self, req: HookRequest) -> WakeUpResponse:
        t0 = time.monotonic()

        try:
            identity = self._store.search_by_tag(self.L0_TAG, agent=None, top_k=5)
            identity = _fit_to_budget(identity, self.L0_CAP)
        except Exception:
            identity = []
            if self._events is not None:
                _log_degraded(self._events, req, reason="l0_failed", layer_affected="L0")

        try:
            prefs = self._store.search_by_tag(self.L1_TAG, agent=None, top_k=10)
            prefs = _fit_to_budget(prefs, self.L1_CAP)
        except Exception:
            prefs = []
            if self._events is not None:
                _log_degraded(self._events, req, reason="l1_failed", layer_affected="L1")

        topic: list[dict] = []
        topic_query = _build_topic_query(req)
        if topic_query:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(
                        lambda: self._store.search(
                            topic_query, agent=None, top_k=self._topk_raw,
                        )
                    )
                    try:
                        candidates = future.result(timeout=BRAIN_L2_TIMEOUT_S)
                    except concurrent.futures.TimeoutError:
                        if self._events is not None:
                            _log_degraded(
                                self._events, req,
                                reason="db_timeout", layer_affected="L2",
                            )
                        candidates = None
                if candidates is not None:
                    filtered = _apply_threshold(candidates, self._threshold)
                    reranked = _rerank_candidates(filtered)
                    topic = _fit_to_budget(reranked, self.L2_CAP)
            except Exception:
                if self._events is not None:
                    _log_degraded(
                        self._events, req,
                        reason="embedding_failed", layer_affected="L2",
                    )

        context = self._format(identity, prefs, topic)
        duration_ms = int((time.monotonic() - t0) * 1000)
        layers_loaded = {
            "L0": len(identity),
            "L1": len(prefs),
            "L2": len(topic),
        }
        return WakeUpResponse(
            context=context,
            layers_loaded=layers_loaded,
            tokens_approx=self._tokens(context),
            duration_ms=duration_ms,
            identity=identity,
            prefs=prefs,
            topic=topic,
        )

    @staticmethod
    def _format(
        identity: list[dict],
        prefs: list[dict],
        topic: list[dict] | None = None,
    ) -> str:
        topic = topic or []
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
        if topic:
            if identity or prefs:
                lines.append("")
            lines.append("## Topic")
            for m in topic:
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
