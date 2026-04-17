"""LongMemEval dataset loader.

Upstream format (JSON array of entries):
    {
      "question_id", "question_type", "question", "answer", "question_date",
      "answer_session_ids": [...],
      "haystack_sessions": [
        {"session_id", "session_date", "turns": [{"role","content"}, ...]}
      ]
    }
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from brain_bench.types import DatasetEntry, Question, Session, Turn


def load_longmemeval_s(
    path: Path,
    subset: int | None = None,
    seed: int = 42,
) -> list[DatasetEntry]:
    """Load LongMemEval-s JSON. If subset is set, stratify by question_type."""
    raw = json.loads(Path(path).read_text())
    entries: list[DatasetEntry] = []
    for item in raw:
        q = Question(
            question_id=item["question_id"],
            question_type=item["question_type"],
            question=item["question"],
            answer=item["answer"],
            question_date=item["question_date"],
            answer_session_ids=list(item.get("answer_session_ids", [])),
        )
        sessions = [
            Session(
                session_id=s["session_id"],
                session_date=s["session_date"],
                turns=[Turn(role=t["role"], content=t["content"]) for t in s["turns"]],
            )
            for s in item.get("haystack_sessions", [])
        ]
        entries.append(DatasetEntry(question=q, sessions=sessions))

    if subset is None or subset >= len(entries):
        return entries

    by_type: dict[str, list[DatasetEntry]] = defaultdict(list)
    for e in entries:
        by_type[e.question.question_type].append(e)

    rng = random.Random(seed)
    n_types = len(by_type)
    per_type = max(1, subset // n_types)
    sampled: list[DatasetEntry] = []
    leftovers: list[DatasetEntry] = []
    for group in by_type.values():
        rng.shuffle(group)
        sampled.extend(group[:per_type])
        leftovers.extend(group[per_type:])

    # Top up if short (happens when subset % n_types != 0)
    if len(sampled) < subset:
        rng.shuffle(leftovers)
        sampled.extend(leftovers[: subset - len(sampled)])

    rng.shuffle(sampled)
    return sampled[:subset]
