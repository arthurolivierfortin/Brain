"""Brain status line for Claude Code.

Displays: git branch | context % | rate limit | brain status | updated.
Receives rich session JSON on stdin from Claude Code statusLine.
ANSI colors indicate severity.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path

HOOK_STATE_DIR = Path("data/brain_hook_state")
PENDING_PATH = Path("data/brain_pending_local.jsonl")
LAST_RUN_PATH = Path("data/.statusline_last_run")

# Show save command hint when unsaved delta exceeds this (bytes)
SAVE_THRESHOLD = 20_000

# ANSI color codes
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"


def _color_pct(value: int, low: int = 50, high: int = 70) -> str:
    """Color a percentage value: green < low, yellow < high, red >= high."""
    if value >= high:
        return f"{RED}{BOLD}{value}%{RESET}"
    if value >= low:
        return f"{YELLOW}{value}%{RESET}"
    return f"{GREEN}{value}%{RESET}"


def _fmt_size(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _git_branch() -> str:
    try:
        return subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip() or "?"
    except Exception:
        return "?"


def _pending_count() -> int:
    if not PENDING_PATH.exists():
        return 0
    try:
        return sum(1 for line in PENDING_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    except Exception:
        return 0


def _unsaved_delta(session_id: str, transcript_path: str) -> int:
    """Calculate bytes of transcript not yet saved by the stop hook."""
    if not session_id or not transcript_path:
        return 0

    tp = Path(transcript_path)
    if not tp.exists():
        return 0

    offset = 0
    offset_file = HOOK_STATE_DIR / f"{session_id}.offset"
    if offset_file.exists():
        with contextlib.suppress(ValueError, OSError):
            offset = int(offset_file.read_text(encoding="utf-8").strip())

    try:
        file_size = tp.stat().st_size
    except OSError:
        return 0

    return max(0, file_size - offset)


def _last_save_ago(session_id: str) -> str:
    """Human-readable time since last brain save for this session."""
    if not session_id:
        return ""
    offset_file = HOOK_STATE_DIR / f"{session_id}.offset"
    if not offset_file.exists():
        return "never"
    try:
        mtime = offset_file.stat().st_mtime
    except OSError:
        return "?"
    delta = int(time.time() - mtime)
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    return f"{delta // 3600}h ago"


def main() -> None:
    # Read stdin JSON from Claude Code
    data: dict = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
    except Exception:  # noqa: S110 — stdin parse failure is non-critical, no action to take
        pass

    parts: list[str] = []

    # 1. Git branch
    branch = _git_branch()
    parts.append(f"{CYAN}{branch}{RESET}")

    # 2. Context window usage
    ctx = data.get("context_window", {})
    used_pct = ctx.get("used_percentage")
    if used_pct is not None:
        parts.append(f"ctx {_color_pct(used_pct, low=50, high=70)}")

    # 3. Rate limit (5h window) — value can be a dict or raw int
    rate = data.get("rate_limits", {}).get("five_hour")
    rate_pct = rate.get("used_percentage") if isinstance(rate, dict) else rate
    if isinstance(rate_pct, (int, float)):
        parts.append(f"rate {_color_pct(int(rate_pct), low=50, high=80)}")

    # 4. Brain status
    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")
    unsaved = _unsaved_delta(session_id, transcript_path)
    pending = _pending_count()
    last_save = _last_save_ago(session_id)

    brain_parts: list[str] = []
    if unsaved > 0:
        size_str = _fmt_size(unsaved)
        if unsaved >= SAVE_THRESHOLD:
            brain_parts.append(f"{YELLOW}{size_str} unsaved{RESET}")
        else:
            brain_parts.append(f"{DIM}{size_str} unsaved{RESET}")
    if pending > 0:
        brain_parts.append(f"{YELLOW}{pending} pending{RESET}")

    if brain_parts:
        brain_str = f"brain: {', '.join(brain_parts)}"
        if last_save:
            brain_str += f" {DIM}(saved {last_save}){RESET}"
        if unsaved >= SAVE_THRESHOLD:
            brain_str += f" {RED}-> /save-brain{RESET}"
        parts.append(brain_str)
    else:
        save_info = f" {DIM}(saved {last_save}){RESET}" if last_save else ""
        parts.append(f"brain: {GREEN}ok{RESET}{save_info}")

    # 5. Updated timestamp — time since last statusline refresh
    try:
        if LAST_RUN_PATH.exists():
            delta = int(time.time() - LAST_RUN_PATH.stat().st_mtime)
            parts.append(f"{DIM}updated {delta}s ago{RESET}")
        LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_RUN_PATH.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass

    print(f" {DIM}|{RESET} ".join(parts))


if __name__ == "__main__":
    main()
