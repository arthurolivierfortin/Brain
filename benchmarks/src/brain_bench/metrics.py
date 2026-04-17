from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from brain_bench.runners.longmemeval import QuestionResult


@dataclass
class Summary:
    n: int
    accuracy: float
    recall_at_k: float
    per_category: dict[str, dict[str, float]]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


def aggregate(results: list[QuestionResult]) -> Summary:
    n = len(results)
    if n == 0:
        return Summary(
            n=0, accuracy=0.0, recall_at_k=0.0,
            per_category={}, total_cost_usd=0.0,
            total_input_tokens=0, total_output_tokens=0,
        )

    acc = sum(1 for r in results if r.accuracy) / n
    recall = sum(1 for r in results if r.recall_at_k) / n

    by_cat: dict[str, list[QuestionResult]] = defaultdict(list)
    for r in results:
        by_cat[r.question_type].append(r)

    per_category: dict[str, dict[str, float]] = {}
    for cat, group in by_cat.items():
        per_category[cat] = {
            "n": len(group),
            "accuracy": sum(1 for r in group if r.accuracy) / len(group),
            "recall_at_k": sum(1 for r in group if r.recall_at_k) / len(group),
        }

    return Summary(
        n=n, accuracy=acc, recall_at_k=recall,
        per_category=per_category,
        total_cost_usd=sum(r.cost_usd for r in results),
        total_input_tokens=sum(r.input_tokens for r in results),
        total_output_tokens=sum(r.output_tokens for r in results),
    )
