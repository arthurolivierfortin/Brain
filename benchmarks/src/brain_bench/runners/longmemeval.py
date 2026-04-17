"""LongMemEval runner — ingest → retrieve → read → judge → log.

Crash-safe: appends each QuestionResult to a JSONL log immediately.
Re-running reuses the log and skips already-processed questions.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import UTC
from pathlib import Path

from tqdm import tqdm

from brain_bench.adapters.base import Adapter
from brain_bench.llm.base import LLMClient
from brain_bench.types import DatasetEntry

logger = logging.getLogger(__name__)


READER_SYSTEM = (
    "You are a helpful assistant. Answer the user's question based ONLY on "
    "the conversation excerpts provided. If the answer cannot be found in "
    "the excerpts, say so plainly."
)

JUDGE_SYSTEM = (
    "You are an evaluation judge. Compare the candidate answer to the ground "
    "truth. Respond with exactly CORRECT or INCORRECT on the first line, "
    "optionally followed by a one-line reason."
)


@dataclass
class QuestionResult:
    question_id: str
    question_type: str
    recall_at_k: bool
    accuracy: bool
    retrieved_session_ids: list[str]
    reader_text: str
    judge_verdict: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


def _build_reader_prompt(question: str, memories: list) -> str:
    lines = ["Here are conversation excerpts that may be relevant:\n"]
    for i, m in enumerate(memories, 1):
        lines.append(f"[Excerpt {i}] {m.content}")
    lines.append(f"\nQuestion: {question}")
    return "\n".join(lines)


def _build_judge_prompt(question: str, ground_truth: str, candidate: str) -> str:
    return (
        f"Question: {question}\n"
        f"Ground truth: {ground_truth}\n"
        f"Candidate answer: {candidate}\n\n"
        "Verdict:"
    )


def _load_done_ids(log_path: Path) -> dict[str, dict]:
    if not log_path.exists():
        return {}
    done: dict[str, dict] = {}
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done[rec["question_id"]] = rec
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed log line: %s", line[:80])
    return done


def _append_log(log_path: Path, result: QuestionResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result)) + "\n")


def run_longmemeval(
    entries: list[DatasetEntry],
    adapter: Adapter,
    reader: LLMClient,
    judge: LLMClient,
    log_path: Path,
    k: int = 5,
) -> list[QuestionResult]:
    """Run the full pipeline, resume-safe via log_path."""
    done = _load_done_ids(log_path)
    results: list[QuestionResult] = []

    for entry in tqdm(entries, desc="LongMemEval"):
        qid = entry.question.question_id
        if qid in done:
            rec = done[qid]
            results.append(QuestionResult(**rec))
            continue

        adapter.reset()
        for session in entry.sessions:
            adapter.ingest(session)

        memories = adapter.retrieve(entry.question.question, k=k)
        retrieved_session_ids = [m.session_id for m in memories if m.session_id]

        recall_hit = any(
            sid in set(entry.question.answer_session_ids)
            for sid in retrieved_session_ids
        )
        if not entry.question.answer_session_ids:
            recall_hit = True

        reader_call = reader.complete(
            system=READER_SYSTEM,
            user=_build_reader_prompt(entry.question.question, memories),
        )

        judge_call = judge.complete(
            system=JUDGE_SYSTEM,
            user=_build_judge_prompt(
                entry.question.question,
                entry.question.answer,
                reader_call.text,
            ),
        )
        raw = judge_call.text.strip() if judge_call.text else ""
        verdict_line = raw.splitlines()[0].strip().upper() if raw else ""
        accuracy = verdict_line.startswith("CORRECT")

        result = QuestionResult(
            question_id=qid,
            question_type=entry.question.question_type,
            recall_at_k=recall_hit,
            accuracy=accuracy,
            retrieved_session_ids=retrieved_session_ids,
            reader_text=reader_call.text,
            judge_verdict=judge_call.text,
            input_tokens=reader_call.input_tokens + judge_call.input_tokens,
            output_tokens=reader_call.output_tokens + judge_call.output_tokens,
            cost_usd=reader_call.cost_usd + judge_call.cost_usd,
        )
        _append_log(log_path, result)
        results.append(result)

    return results


def _make_adapter(cfg):
    if cfg.adapter == "brain":
        from brain_bench.adapters.brain import BrainAdapter
        return BrainAdapter(brain_url=cfg.brain_url)
    if cfg.adapter == "chromadb_raw":
        from brain_bench.adapters.chromadb_raw import ChromaDBRawAdapter
        return ChromaDBRawAdapter(persist_dir=cfg.chromadb_raw_persist_dir)
    raise ValueError(f"Unknown adapter: {cfg.adapter}")


def _make_llm(llm_cfg):
    if llm_cfg.provider == "ollama":
        from brain_bench.llm.ollama import OllamaClient
        return OllamaClient(model=llm_cfg.model)
    if llm_cfg.provider == "anthropic":
        from brain_bench.llm.anthropic import AnthropicClient
        return AnthropicClient(model=llm_cfg.model)
    raise ValueError(f"Unknown provider: {llm_cfg.provider}")


def main() -> None:
    import argparse
    import subprocess
    import time
    from dataclasses import replace
    from datetime import datetime

    from brain_bench.config import load_config
    from brain_bench.datasets.longmemeval import load_longmemeval_s
    from brain_bench.metrics import aggregate
    from brain_bench.report import append_csv_row, write_markdown_report

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--adapter", default=None,
                        help="Override adapter from config (brain | chromadb_raw)")
    parser.add_argument("--dataset-path", default=None, type=Path,
                        help="Override dataset path (default: benchmarks/external/LongMemEval/...)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run but do not write to output_dir")
    args = parser.parse_args()

    if not args.config.exists():
        parser.error(f"Config file not found: {args.config}")

    cfg = load_config(args.config)
    if args.adapter:
        cfg = replace(cfg, adapter=args.adapter)

    try:
        dataset_path = args.dataset_path or (
            Path("external/LongMemEval/data/longmemeval_s.json")
        )
        entries = load_longmemeval_s(dataset_path, subset=cfg.subset, seed=cfg.seed)

        adapter = _make_adapter(cfg)
        reader = _make_llm(cfg.reader)
        judge = _make_llm(cfg.judge)

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
        runs_dir = Path("runs")
        runs_dir.mkdir(exist_ok=True)
        log_path = runs_dir / f"{timestamp}_{cfg.adapter}.jsonl"

        t0 = time.monotonic()
        results = run_longmemeval(
            entries=entries, adapter=adapter, reader=reader, judge=judge,
            log_path=log_path, k=5,
        )
        duration = time.monotonic() - t0
        summary = aggregate(results)

        print(f"\n=== {cfg.adapter} on {len(entries)} Q ===")
        print(f"Accuracy: {summary.accuracy:.3f}")
        print(f"Recall@5: {summary.recall_at_k:.3f}")
        print(f"Cost: ${summary.total_cost_usd:.2f}")
        print(f"Duration: {duration / 60:.1f} min")

        if args.dry_run or cfg.dry_run:
            print("[dry-run] Not writing report.")
            return

        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False,
        ).stdout.strip() or "unknown"

        out_dir = Path(cfg.output_dir)
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        md_path = out_dir / f"{date}-{cfg.dataset}-{cfg.adapter}.md"
        write_markdown_report(
            out_path=md_path, summary=summary,
            benchmark=cfg.dataset, adapter=cfg.adapter,
            reader=cfg.reader.model, judge=cfg.judge.model,
            date=date, commit=commit, duration_s=duration,
        )
        csv_path = out_dir / "results.csv"
        append_csv_row(
            csv_path=csv_path, date=date, commit=commit,
            benchmark=cfg.dataset, adapter=cfg.adapter,
            reader=cfg.reader.model, judge=cfg.judge.model,
            summary=summary, duration_s=duration,
        )
        print(f"Report: {md_path}")
        print(f"CSV: {csv_path}")
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(130)
    except Exception as exc:
        print(f"[error] Run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
