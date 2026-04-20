from __future__ import annotations

from pathlib import Path

from brain_bench.metrics import Summary
from brain_bench.report import append_csv_row, write_markdown_report


def _summary() -> Summary:
    return Summary(
        n=500, accuracy=0.681, recall_at_k=0.742,
        per_category={
            "info-extraction": {"n": 100, "accuracy": 0.85, "recall_at_k": 0.90},
            "temporal-reasoning": {"n": 100, "accuracy": 0.54, "recall_at_k": 0.60},
        },
        total_cost_usd=43.20, total_input_tokens=1_200_000, total_output_tokens=80_000,
    )


def test_write_markdown_report(tmp_path: Path):
    out = tmp_path / "2026-04-20-longmemeval-s-brain.md"
    write_markdown_report(
        out_path=out,
        summary=_summary(),
        benchmark="longmemeval_s",
        adapter="brain",
        reader="claude-opus-4-7",
        judge="claude-opus-4-7",
        date="2026-04-20",
        commit="abc1234",
        duration_s=8040,
    )
    text = out.read_text()
    assert "2026-04-20" in text
    assert "0.681" in text
    assert "0.742" in text
    assert "info-extraction" in text
    assert "abc1234" in text
    assert "43.20" in text or "$43.20" in text


def test_append_csv_row_creates_with_header(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    append_csv_row(
        csv_path=csv_path,
        date="2026-04-20", commit="abc1234",
        benchmark="longmemeval_s", adapter="brain",
        reader="claude-opus-4-7", judge="claude-opus-4-7",
        summary=_summary(), duration_s=8040,
    )
    content = csv_path.read_text()
    assert "date,commit,benchmark,adapter" in content
    assert "0.681" in content


def test_append_csv_row_appends_without_rewriting_header(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    for _ in range(2):
        append_csv_row(
            csv_path=csv_path,
            date="2026-04-20", commit="abc",
            benchmark="longmemeval_s", adapter="brain",
            reader="r", judge="j", summary=_summary(), duration_s=1,
        )
    lines = csv_path.read_text().strip().splitlines()
    assert len(lines) == 3  # 1 header + 2 data rows
