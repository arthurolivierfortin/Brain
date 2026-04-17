from __future__ import annotations

import csv
from pathlib import Path

from brain_bench.metrics import Summary

CSV_HEADER = [
    "date", "commit", "benchmark", "adapter", "reader", "judge", "n",
    "accuracy", "recall_at_k",
    "acc_info_extraction", "acc_multi_session_reasoning",
    "acc_temporal_reasoning", "acc_knowledge_update", "acc_abstention",
    "cost_usd", "duration_s", "mean_latency_q_s",
    "total_input_tokens", "total_output_tokens",
]


def write_markdown_report(
    out_path: Path,
    summary: Summary,
    benchmark: str,
    adapter: str,
    reader: str,
    judge: str,
    date: str,
    commit: str,
    duration_s: float,
) -> None:
    mean_latency = duration_s / summary.n if summary.n else 0.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {benchmark} — {adapter} — {date}",
        "",
        f"**Config**: reader={reader}, judge={judge}, adapter={adapter}, N={summary.n}",
        f"**Commit**: {commit}",
        f"**Duration**: {duration_s / 60:.1f} min — **Cost**: ${summary.total_cost_usd:.2f} — "
        f"**Mean latency/Q**: {mean_latency:.1f}s",
        "",
        "| Metric              | Score   |",
        "|---------------------|---------|",
        f"| Recall@5            | {summary.recall_at_k:.3f}   |",
        f"| Accuracy (global)   | {summary.accuracy:.3f}   |",
        "",
        "| Category               | Accuracy | Recall@5 | N  |",
        "|------------------------|----------|----------|-----|",
    ]
    for cat, stats in sorted(summary.per_category.items()):
        lines.append(
            f"| {cat:<22} | {stats['accuracy']:.3f}    | "
            f"{stats['recall_at_k']:.3f}    | {int(stats['n']):>3} |"
        )
    lines += [
        "",
        f"**Tokens**: {summary.total_input_tokens:,} input, {summary.total_output_tokens:,} output",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def append_csv_row(
    csv_path: Path,
    date: str,
    commit: str,
    benchmark: str,
    adapter: str,
    reader: str,
    judge: str,
    summary: Summary,
    duration_s: float,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    cats = summary.per_category
    mean_latency = duration_s / summary.n if summary.n else 0.0
    row = {
        "date": date, "commit": commit, "benchmark": benchmark, "adapter": adapter,
        "reader": reader, "judge": judge, "n": summary.n,
        "accuracy": f"{summary.accuracy:.4f}",
        "recall_at_k": f"{summary.recall_at_k:.4f}",
        "acc_info_extraction": f"{cats.get('info-extraction', {}).get('accuracy', 0.0):.4f}",
        "acc_multi_session_reasoning": (
            f"{cats.get('multi-session-reasoning', {}).get('accuracy', 0.0):.4f}"
        ),
        "acc_temporal_reasoning": f"{cats.get('temporal-reasoning', {}).get('accuracy', 0.0):.4f}",
        "acc_knowledge_update": f"{cats.get('knowledge-update', {}).get('accuracy', 0.0):.4f}",
        "acc_abstention": f"{cats.get('abstention', {}).get('accuracy', 0.0):.4f}",
        "cost_usd": f"{summary.total_cost_usd:.4f}",
        "duration_s": f"{duration_s:.1f}",
        "mean_latency_q_s": f"{mean_latency:.2f}",
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
    }
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if write_header:
            w.writeheader()
        w.writerow(row)
