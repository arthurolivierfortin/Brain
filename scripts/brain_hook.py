"""Brain Hook — Claude Code Stop hook.

Reads the conversation JSONL transcript, summarizes via Gemini Flash API,
and POSTs the summary to the Brain HTTP API. If Brain is offline, entries
go to a local pending queue for retry.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

HOOK_STATE_DIR = Path("data/brain_hook_state")
PENDING_PATH = Path("data/brain_pending_local.jsonl")
BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8611")
BRAIN_TIMEOUT = 2.0
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY and sys.platform == "win32":
    import subprocess
    try:
        GOOGLE_API_KEY = subprocess.run(
            ["powershell", "-Command",
             "[System.Environment]::GetEnvironmentVariable('GOOGLE_API_KEY', 'User')"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        pass
GEMINI_MODEL = os.environ.get("BRAIN_HOOK_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
SYSTEM_PROMPT = (
    "Extract ALL important information from this development conversation. "
    "Include: every decision made and WHY, every problem encountered and how it was solved, "
    "every file created or modified and what changed, every architectural choice, "
    "every rejected alternative and why, every configuration change, "
    "every insight or lesson learned. "
    "Be thorough — keep details, names, numbers, and reasoning. "
    "Do NOT over-summarize. More detail is better than less. "
    "Respond in the same language as the conversation."
)
MAX_INPUT_CHARS = 40_000
MIN_DELTA_CHARS = 100
MAX_PENDING_ATTEMPTS = 50


# ---------------------------------------------------------------------------
# Task 1 — Pending queue helpers
# ---------------------------------------------------------------------------


def append_pending(path: Path, entry: dict) -> None:
    """Append a JSONL entry to the pending queue with timestamp and attempts=0."""
    enriched = {
        **entry,
        "queued_at": datetime.now(tz=UTC).isoformat(),
        "attempts": 0,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(enriched) + "\n")


def read_pending(path: Path) -> list[dict]:
    """Read all pending entries. Returns [] if file does not exist."""
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            entries.append(json.loads(line))
    return entries


def write_pending(path: Path, entries: list[dict]) -> None:
    """Overwrite the pending queue file with the given entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        path.write_text("", encoding="utf-8")
        return
    content = "\n".join(json.dumps(e) for e in entries) + "\n"
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Task 2 — Offset tracking
# ---------------------------------------------------------------------------


def load_offset(state_dir: Path, session_id: str) -> int:
    """Load byte offset for a session. Returns 0 if not found."""
    offset_file = state_dir / f"{session_id}.offset"
    if not offset_file.exists():
        return 0
    try:
        return int(offset_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0


def save_offset(state_dir: Path, session_id: str, offset: int) -> None:
    """Persist byte offset for a session."""
    state_dir.mkdir(parents=True, exist_ok=True)
    offset_file = state_dir / f"{session_id}.offset"
    offset_file.write_text(str(offset), encoding="utf-8")


def read_delta(transcript_path: Path, offset: int) -> tuple[str, int]:
    """Read transcript file from offset to EOF.

    Returns (delta_text, new_offset). delta_text is plain text extracted
    from JSONL lines (assistant/user content). new_offset is the byte
    position after the last read byte.
    """
    if not transcript_path.exists():
        return "", offset

    with transcript_path.open("rb") as fh:
        fh.seek(offset)
        raw = fh.read()
        new_offset = offset + len(raw)

    if not raw:
        return "", offset

    lines: list[str] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            role = obj.get("role", "")
            content = obj.get("content", "")
            if isinstance(content, str) and content:
                lines.append(f"{role}: {content}" if role else content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            lines.append(f"{role}: {text}" if role else text)
        except json.JSONDecodeError:
            if line:
                lines.append(line)

    return "\n".join(lines), new_offset


# ---------------------------------------------------------------------------
# Task 3 — Gemini summarization
# ---------------------------------------------------------------------------


def summarize_delta(delta: str) -> str | None:
    """Summarize delta via Gemini Flash API.

    Returns summary string or None on failure / missing API key.
    Truncates input to MAX_INPUT_CHARS.
    """
    if not GOOGLE_API_KEY:
        return None

    truncated = delta[:MAX_INPUT_CHARS]
    url = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={GOOGLE_API_KEY}"

    try:
        response = httpx.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [
                    {"role": "user", "parts": [{"text": truncated}]},
                ],
                "generationConfig": {
                    "maxOutputTokens": 2048,
                    "temperature": 0.3,
                },
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Task 4 — Brain store + drain
# ---------------------------------------------------------------------------


def store_to_brain(content: str, session_id: str = "") -> bool:
    """POST content to Brain API.

    Falls back to pending queue on any failure. Returns True if stored
    directly to Brain, False if queued.
    """
    payload: dict = {
        "content": content,
        "agent": "local-session",
        "memory_type": "context",
        "metadata": {"session_id": session_id, "source": "hook-stop"} if session_id else None,
    }

    try:
        response = httpx.post(
            f"{BRAIN_URL}/store",
            json=payload,
            timeout=BRAIN_TIMEOUT,
        )
        response.raise_for_status()
        return True
    except Exception:
        append_pending(PENDING_PATH, payload)
        return False


def drain_pending(pending_path: Path | None = None) -> dict[str, int]:
    """Drain the pending queue by replaying entries to Brain API.

    Returns dict with keys: drained, failed, discarded.
    Entries with attempts >= MAX_PENDING_ATTEMPTS are discarded.
    """
    path = pending_path if pending_path is not None else PENDING_PATH
    entries = read_pending(path)
    if not entries:
        return {"drained": 0, "failed": 0, "discarded": 0}

    drained = 0
    failed = 0
    discarded = 0
    remaining: list[dict] = []

    for entry in entries:
        attempts = entry.get("attempts", 0)
        if attempts >= MAX_PENDING_ATTEMPTS:
            discarded += 1
            continue

        content = entry.get("content", "")
        session_id = entry.get("session_id", "")
        payload: dict = {"content": content}
        if session_id:
            payload["session_id"] = session_id

        try:
            response = httpx.post(
                f"{BRAIN_URL}/store",
                json=payload,
                timeout=BRAIN_TIMEOUT,
            )
            response.raise_for_status()
            drained += 1
        except Exception:
            updated = {**entry, "attempts": attempts + 1}
            remaining.append(updated)
            failed += 1

    write_pending(path, remaining)
    return {"drained": drained, "failed": failed, "discarded": discarded}


# ---------------------------------------------------------------------------
# Task 5 — Main entrypoint
# ---------------------------------------------------------------------------


def main(
    stdin_data: str | None = None,
    state_dir: Path | None = None,
    pending_path: Path | None = None,
) -> bool:
    """Main hook entrypoint.

    1. Parse stdin JSON for session_id and transcript_path.
    2. Read delta from last saved offset.
    3. Skip if delta < MIN_DELTA_CHARS (but save offset).
    4. Opportunistically drain pending queue.
    5. Summarize via Gemini Flash.
    6. If summarization fails, store raw delta truncated to 500 chars.
    7. Store to Brain.
    8. Save new offset.

    Returns True on success, False on unrecoverable parse error.
    """
    resolved_state_dir = state_dir if state_dir is not None else HOOK_STATE_DIR
    resolved_pending = pending_path if pending_path is not None else PENDING_PATH

    raw = stdin_data if stdin_data is not None else sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False

    session_id = data.get("session_id", "")
    transcript_str = data.get("transcript_path", "")
    if not transcript_str:
        return False

    transcript_path = Path(transcript_str)

    offset = load_offset(resolved_state_dir, session_id)
    delta, new_offset = read_delta(transcript_path, offset)

    if len(delta) < MIN_DELTA_CHARS:
        save_offset(resolved_state_dir, session_id, new_offset)
        return False

    drain_pending(pending_path=resolved_pending)

    summary = summarize_delta(delta)

    if summary is None:
        summary = f"[raw] {delta[:500]}"

    store_to_brain(summary, session_id=session_id)

    save_offset(resolved_state_dir, session_id, new_offset)

    return True


if __name__ == "__main__":
    main(stdin_data=sys.stdin.read())
    sys.exit(0)
