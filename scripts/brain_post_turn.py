"""Claude Code Stop hook — posts turn delta to Brain /hook/post_turn.

Replaces the legacy scripts/brain_hook.py. Differences:
- Parses transcript delta into structured Turn (user/assistant/tool_calls)
  instead of flattening
- POSTs to /hook/post_turn instead of /store
- Extraction is done backend-side (no more client Gemini call)

Preserves:
- Byte-offset tracking per session_id in data/brain_hook_state/
- Pending queue at data/brain_pending_local.jsonl with opportunistic drain
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

HOOK_STATE_DIR = Path("data/brain_hook_state")
PENDING_PATH = Path("data/brain_pending_local.jsonl")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
BRAIN_TIMEOUT = 30.0
MIN_DELTA_CHARS = 100
MAX_PENDING_ATTEMPTS = 50

_GENERIC_BASENAMES = frozenset({"docker", "src", "app", "project", "repo", "code"})


def derive_agent(cwd: str) -> str:
    p = Path(cwd)
    basename = p.name.lower() or "default"
    if basename in _GENERIC_BASENAMES:
        parent = p.parent.name.lower() or "root"
        basename = f"{parent}-{basename}"
    return basename


def load_offset(state_dir: Path, session_id: str) -> int:
    f = state_dir / f"{session_id}.offset"
    if not f.exists():
        return 0
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0


def save_offset(state_dir: Path, session_id: str, offset: int) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f"{session_id}.offset").write_text(str(offset), encoding="utf-8")


def parse_delta_to_turn(transcript_path: Path, offset: int) -> dict:
    """Parse transcript JSONL from offset. Returns {user, assistant, tool_calls}
    using the LAST user message and LAST assistant message in the delta."""
    if not transcript_path.exists():
        return {"user": "", "assistant": "", "tool_calls": []}
    with transcript_path.open("rb") as fh:
        fh.seek(offset)
        raw = fh.read()
    user, assistant = "", ""
    tool_calls: list[dict] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = obj.get("role", "")
        content = obj.get("content", "")
        if role == "user" and isinstance(content, str):
            user = content
        elif role == "assistant":
            if isinstance(content, str):
                assistant = content
            elif isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "name": block.get("name", ""),
                                "input": block.get("input", ""),
                            })
                if text_parts:
                    assistant = "\n".join(text_parts)
    return {"user": user, "assistant": assistant, "tool_calls": tool_calls}


def read_delta_size(transcript_path: Path, offset: int) -> int:
    if not transcript_path.exists():
        return 0
    with transcript_path.open("rb") as fh:
        fh.seek(offset)
        return len(fh.read())


def get_new_offset(transcript_path: Path) -> int:
    if not transcript_path.exists():
        return 0
    return transcript_path.stat().st_size


def append_pending(path: Path, entry: dict) -> None:
    enriched = {**entry, "queued_at": datetime.now(tz=UTC).isoformat(), "attempts": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(enriched) + "\n")


def read_pending(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            out.append(json.loads(line))
    return out


def write_pending(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        path.write_text("", encoding="utf-8")
        return
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def drain_pending(pending_path: Path) -> None:
    entries = read_pending(pending_path)
    if not entries:
        return
    remaining: list[dict] = []
    for entry in entries:
        payload = entry.get("payload")
        if payload is None:
            continue
        attempts = entry.get("attempts", 0)
        if attempts >= MAX_PENDING_ATTEMPTS:
            continue
        try:
            resp = httpx.post(
                f"{BRAIN_URL}/hook/post_turn",
                json=payload,
                timeout=BRAIN_TIMEOUT,
            )
            resp.raise_for_status()
        except Exception:
            remaining.append({**entry, "attempts": attempts + 1})
    write_pending(pending_path, remaining)


def main(
    stdin_data: str | None = None,
    state_dir: Path | None = None,
    pending_path: Path | None = None,
) -> int:
    try:
        resolved_state = state_dir or HOOK_STATE_DIR
        resolved_pending = pending_path or PENDING_PATH

        raw = stdin_data if stdin_data is not None else sys.stdin.read()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return 0

        session_id = data.get("session_id", "")
        transcript_str = data.get("transcript_path", "")
        cwd = data.get("cwd", "") or os.getcwd()
        if not transcript_str:
            return 0
        transcript_path = Path(transcript_str)

        offset = load_offset(resolved_state, session_id)
        delta_size = read_delta_size(transcript_path, offset)
        if delta_size < MIN_DELTA_CHARS:
            save_offset(resolved_state, session_id, get_new_offset(transcript_path))
            return 0

        turn = parse_delta_to_turn(transcript_path, offset)
        agent = derive_agent(cwd)
        payload = {"agent": agent, "project": cwd, "session_id": session_id, "turn": turn}

        drain_pending(resolved_pending)

        try:
            resp = httpx.post(f"{BRAIN_URL}/hook/post_turn", json=payload, timeout=BRAIN_TIMEOUT)
            resp.raise_for_status()
        except Exception:
            append_pending(resolved_pending, {"payload": payload})

        save_offset(resolved_state, session_id, get_new_offset(transcript_path))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
