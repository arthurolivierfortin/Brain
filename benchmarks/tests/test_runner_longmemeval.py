from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from brain_bench.llm.base import LLMCall
from brain_bench.runners.longmemeval import run_longmemeval
from brain_bench.types import DatasetEntry, Memory, Question, Session, Turn


def _fake_entry(qid: str, qtype: str, answer_session_id: str) -> DatasetEntry:
    return DatasetEntry(
        question=Question(
            question_id=qid, question_type=qtype,
            question="?", answer="yes",
            question_date="2025-01-01", answer_session_ids=[answer_session_id],
        ),
        sessions=[Session(
            session_id=answer_session_id, session_date="2025-01-01",
            turns=[Turn(role="user", content="evidence")],
        )],
    )


def _fake_reader():
    r = MagicMock()
    r.complete.return_value = LLMCall(text="yes", input_tokens=10, output_tokens=1, cost_usd=0.01)
    return r


def _fake_judge(verdict: str = "CORRECT"):
    j = MagicMock()
    j.complete.return_value = LLMCall(text=verdict, input_tokens=10, output_tokens=1, cost_usd=0.01)
    return j


def _fake_adapter(returned_session_id: str):
    a = MagicMock()
    a.retrieve.return_value = [Memory(
        id="m1", content="evidence", score=0.9, session_id=returned_session_id,
    )]
    return a


def test_runner_produces_one_result_per_entry(tmp_path: Path):
    entries = [
        _fake_entry("q1", "info-extraction", "s1"),
        _fake_entry("q2", "temporal-reasoning", "s2"),
    ]
    log_path = tmp_path / "run.jsonl"
    results = run_longmemeval(
        entries=entries,
        adapter=_fake_adapter("s1"),
        reader=_fake_reader(),
        judge=_fake_judge("CORRECT"),
        log_path=log_path,
        k=5,
    )
    assert len(results) == 2


def test_recall_at_k_correct_when_answer_session_retrieved(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    adapter = _fake_adapter("s1")  # returns s1, which IS the answer session
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=_fake_reader(),
        judge=_fake_judge("CORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].recall_at_k is True


def test_recall_at_k_false_when_answer_session_missing(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    adapter = _fake_adapter("OTHER")  # does NOT return s1
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=_fake_reader(),
        judge=_fake_judge("INCORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].recall_at_k is False


def test_judge_correct_verdict_sets_accuracy_true(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    results = run_longmemeval(
        entries=entries, adapter=_fake_adapter("s1"), reader=_fake_reader(),
        judge=_fake_judge("CORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].accuracy is True


def test_judge_incorrect_verdict_sets_accuracy_false(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    results = run_longmemeval(
        entries=entries, adapter=_fake_adapter("s1"), reader=_fake_reader(),
        judge=_fake_judge("INCORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].accuracy is False


def test_resume_skips_already_logged_questions(tmp_path: Path):
    log_path = tmp_path / "run.jsonl"
    # Pre-populate the log with q1 so it gets skipped
    log_path.write_text(json.dumps({
        "question_id": "q1", "question_type": "info-extraction",
        "recall_at_k": True, "accuracy": True, "retrieved_session_ids": ["s1"],
        "reader_text": "yes", "judge_verdict": "CORRECT",
        "input_tokens": 10, "output_tokens": 1, "cost_usd": 0.02,
    }) + "\n")

    entries = [
        _fake_entry("q1", "info-extraction", "s1"),
        _fake_entry("q2", "temporal-reasoning", "s2"),
    ]
    adapter = _fake_adapter("s2")
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=_fake_reader(),
        judge=_fake_judge("CORRECT"), log_path=log_path, k=5,
    )
    assert len(results) == 2
    # adapter should have been called only for q2 (not q1)
    assert adapter.retrieve.call_count == 1
