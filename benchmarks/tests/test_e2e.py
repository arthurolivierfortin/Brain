"""End-to-end test: run the pipeline on the mini fixture with mocked LLMs.

Does NOT require Brain running or Ollama installed — wires ChromaDBRawAdapter
(real ChromaDB on tmp path) with fake LLMs to prove the full pipeline
produces a valid report.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain_bench.adapters.chromadb_raw import ChromaDBRawAdapter
from brain_bench.datasets.longmemeval import load_longmemeval_s
from brain_bench.llm.base import LLMCall
from brain_bench.metrics import aggregate
from brain_bench.report import append_csv_row, write_markdown_report
from brain_bench.runners.longmemeval import run_longmemeval

FIXTURE = Path(__file__).parent / "fixtures" / "longmemeval_mini.json"


def _reader():
    r = MagicMock()
    r.complete.return_value = LLMCall(
        text="my answer", input_tokens=50, output_tokens=5, cost_usd=0.001,
    )
    return r


def _judge():
    j = MagicMock()
    j.complete.return_value = LLMCall(
        text="CORRECT", input_tokens=20, output_tokens=2, cost_usd=0.0005,
    )
    return j


def test_e2e_pipeline_produces_report(tmp_path: Path):
    entries = load_longmemeval_s(FIXTURE)
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chroma")
    log_path = tmp_path / "run.jsonl"

    results = run_longmemeval(
        entries=entries, adapter=adapter,
        reader=_reader(), judge=_judge(),
        log_path=log_path, k=5,
    )
    assert len(results) == 5

    summary = aggregate(results)
    assert summary.n == 5
    # All judges returned CORRECT → accuracy = 1.0
    assert summary.accuracy == pytest.approx(1.0)

    # Writing the report should not crash
    md = tmp_path / "report.md"
    write_markdown_report(
        out_path=md, summary=summary,
        benchmark="longmemeval_s", adapter="chromadb_raw",
        reader="mock", judge="mock",
        date="2026-04-20", commit="test", duration_s=10,
    )
    assert "1.000" in md.read_text()

    csv = tmp_path / "results.csv"
    append_csv_row(
        csv_path=csv, date="2026-04-20", commit="test",
        benchmark="longmemeval_s", adapter="chromadb_raw",
        reader="mock", judge="mock", summary=summary, duration_s=10,
    )
    assert csv.exists()
    assert len(csv.read_text().strip().splitlines()) == 2  # header + 1 row


def test_e2e_resume_skips_done(tmp_path: Path):
    entries = load_longmemeval_s(FIXTURE, subset=3, seed=42)
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chroma")
    log_path = tmp_path / "run.jsonl"

    run_longmemeval(
        entries=entries, adapter=adapter,
        reader=_reader(), judge=_judge(),
        log_path=log_path, k=5,
    )

    # Second invocation: log exists, should skip all
    spy_reader = _reader()
    run_longmemeval(
        entries=entries, adapter=adapter,
        reader=spy_reader, judge=_judge(),
        log_path=log_path, k=5,
    )
    # Reader should not be called on resume (all 3 entries were done)
    assert spy_reader.complete.call_count == 0
