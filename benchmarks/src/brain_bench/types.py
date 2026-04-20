"""Shared data types for the benchmark harness."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Turn:
    role: str
    content: str


@dataclass
class Session:
    session_id: str
    session_date: str
    turns: list[Turn]


@dataclass
class Memory:
    id: str
    content: str
    score: float
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Question:
    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    answer_session_ids: list[str]


@dataclass
class DatasetEntry:
    question: Question
    sessions: list[Session]
