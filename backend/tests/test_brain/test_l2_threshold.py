"""Unit tests for _apply_threshold and _fit_to_budget."""
from __future__ import annotations

from brain.hook import _apply_threshold, _fit_to_budget


def _make(distance: float, content: str = "x") -> dict:
    return {"distance": distance, "content": content}


def test_apply_threshold_strict_and_env_override() -> None:
    """Distance 1.1 -> cosine 0.45 exactly -> excluded (strict >). Distance 1.0 -> 0.5 -> included."""
    at_boundary = _make(distance=1.1)
    above = _make(distance=1.0)
    below = _make(distance=1.2)

    result = _apply_threshold([at_boundary, above, below], threshold=0.45)
    assert len(result) == 1
    assert result[0] is above


def test_apply_threshold_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BRAIN_L2_THRESHOLD", "0.60")
    c = _make(distance=0.9)
    result = _apply_threshold([c], threshold=0.60)
    assert result == []


def test_apply_threshold_preserves_order() -> None:
    a = _make(distance=0.2)
    b = _make(distance=0.4)
    c = _make(distance=0.6)
    result = _apply_threshold([a, b, c], threshold=0.45)
    assert result == [a, b, c]


def test_apply_threshold_empty() -> None:
    assert _apply_threshold([], threshold=0.45) == []


def test_fit_to_budget_caps_and_preserves_order() -> None:
    a = {"content": "12345678", "id": "a"}
    b = {"content": "12345678", "id": "b"}
    result = _fit_to_budget([a, b], cap=3)
    assert result == [a]


def test_fit_to_budget_all_fit() -> None:
    items = [{"content": "ab", "id": str(i)} for i in range(3)]
    result = _fit_to_budget(items, cap=10)
    assert result == items


def test_fit_to_budget_empty() -> None:
    assert _fit_to_budget([], cap=100) == []


def test_fit_to_budget_preserves_input_order() -> None:
    a = {"content": "a" * 8, "id": "a"}
    b = {"content": "b" * 8, "id": "b"}
    c = {"content": "c" * 8, "id": "c"}
    result = _fit_to_budget([a, b, c], cap=5)
    assert result == [a, b]
