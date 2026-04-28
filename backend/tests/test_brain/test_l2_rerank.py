"""Unit tests for _rerank_candidates and _age_days."""
from __future__ import annotations

import math

from brain.hook import _rerank_candidates


def _candidate(distance: float, access_count: int, created_at: str) -> dict:
    return {
        "id": "x",
        "content": "test",
        "distance": distance,
        "access_count": access_count,
        "created_at": created_at,
    }


def test_rerank_orders_by_composite_score() -> None:
    now_iso = "2026-04-28T00:00:00+00:00"
    top = _candidate(distance=0.1, access_count=10, created_at=now_iso)
    old_iso = "2025-01-01T00:00:00+00:00"
    bottom = _candidate(distance=0.9, access_count=0, created_at=old_iso)
    mid = _candidate(distance=0.5, access_count=2, created_at=now_iso)

    result = _rerank_candidates([bottom, mid, top])
    assert result[0] is top
    assert result[-1] is bottom


def test_rerank_sets_rerank_score_key() -> None:
    c = _candidate(distance=0.2, access_count=0, created_at="2026-04-28T00:00:00+00:00")
    result = _rerank_candidates([c])
    assert "_rerank_score" in result[0]
    assert result[0]["_rerank_score"] > 0


def test_rerank_bad_created_at_uses_zero_age() -> None:
    """Parse failure on created_at -> age=0 -> no age penalty, does not crash."""
    c = _candidate(distance=0.3, access_count=0, created_at="not-a-date")
    result = _rerank_candidates([c])
    cosine = 1.0 - 0.3 / 2.0
    expected = cosine * (1.0 + math.log(1) * 0.05) * math.exp(0)
    assert abs(result[0]["_rerank_score"] - expected) < 1e-6


def test_rerank_empty_list() -> None:
    assert _rerank_candidates([]) == []
