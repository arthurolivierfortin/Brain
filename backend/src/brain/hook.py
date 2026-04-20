"""Hook architecture — Extractor Protocol, dataclasses, handlers.

See docs/specs/2026-04-19-hook-architecture-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


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
