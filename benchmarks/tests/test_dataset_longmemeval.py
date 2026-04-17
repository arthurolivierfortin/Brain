from __future__ import annotations

from pathlib import Path

from brain_bench.datasets.longmemeval import load_longmemeval_s

FIXTURE = Path(__file__).parent / "fixtures" / "longmemeval_mini.json"


def test_loads_all_entries():
    entries = load_longmemeval_s(FIXTURE)
    assert len(entries) == 5


def test_question_parsed_correctly():
    entries = load_longmemeval_s(FIXTURE)
    e1 = entries[0]
    assert e1.question.question_id == "q1"
    assert e1.question.question_type == "single-session-assistant"
    assert e1.question.answer == "blue"


def test_sessions_parsed_correctly():
    entries = load_longmemeval_s(FIXTURE)
    e1 = entries[0]
    assert len(e1.sessions) == 1
    assert e1.sessions[0].session_id == "s1"
    assert len(e1.sessions[0].turns) == 2
    assert e1.sessions[0].turns[0].role == "user"


def test_subset_stratified():
    """subset=5 with seed=42 should yield 1 per category (5 categories)."""
    entries = load_longmemeval_s(FIXTURE, subset=5, seed=42)
    types = [e.question.question_type for e in entries]
    assert len(set(types)) == 5


def test_subset_larger_than_dataset_returns_all():
    entries = load_longmemeval_s(FIXTURE, subset=1000, seed=42)
    assert len(entries) == 5


def test_abstention_entries_have_no_haystack():
    entries = load_longmemeval_s(FIXTURE)
    abstention = next(e for e in entries if e.question.question_type == "abstention")
    assert abstention.sessions == []
