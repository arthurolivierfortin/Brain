from __future__ import annotations

import pytest

from brain_bench.metrics import aggregate
from brain_bench.runners.longmemeval import QuestionResult


def _r(qid: str, qtype: str, recall: bool, acc: bool, cost: float = 0.01) -> QuestionResult:
    return QuestionResult(
        question_id=qid, question_type=qtype,
        recall_at_k=recall, accuracy=acc,
        retrieved_session_ids=[], reader_text="", judge_verdict="",
        input_tokens=10, output_tokens=5, cost_usd=cost,
    )


def test_global_accuracy_and_recall():
    results = [
        _r("q1", "info-extraction", True, True),
        _r("q2", "info-extraction", True, False),
        _r("q3", "temporal-reasoning", False, False),
        _r("q4", "temporal-reasoning", True, True),
    ]
    s = aggregate(results)
    assert s.n == 4
    assert s.accuracy == pytest.approx(0.5)
    assert s.recall_at_k == pytest.approx(0.75)


def test_per_category_accuracy():
    results = [
        _r("q1", "info-extraction", True, True),
        _r("q2", "info-extraction", True, True),
        _r("q3", "temporal-reasoning", True, False),
    ]
    s = aggregate(results)
    assert s.per_category["info-extraction"]["accuracy"] == pytest.approx(1.0)
    assert s.per_category["info-extraction"]["n"] == 2
    assert s.per_category["temporal-reasoning"]["accuracy"] == pytest.approx(0.0)


def test_total_cost_sum():
    results = [
        _r("q1", "info-extraction", True, True, cost=0.05),
        _r("q2", "info-extraction", True, True, cost=0.03),
    ]
    s = aggregate(results)
    assert s.total_cost_usd == pytest.approx(0.08)


def test_empty_results_handled():
    s = aggregate([])
    assert s.n == 0
    assert s.accuracy == 0.0
    assert s.recall_at_k == 0.0
    assert s.per_category == {}
