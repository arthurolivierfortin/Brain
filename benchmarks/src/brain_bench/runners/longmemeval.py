"""LongMemEval runner — ingest → retrieve → read → judge → log.

Crash-safe: appends each QuestionResult to a JSONL log immediately.
Re-running reuses the log and skips already-processed questions.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
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
