"""Claude Code SessionStart hook — fetches wake-up context from Brain.

Reads CC's stdin JSON (cwd, session_id, etc.), POSTs to Brain's
/hook/wake_up endpoint, and writes Claude Code's SessionStart
contract to stdout. On any failure (Brain unreachable, timeout,
bad stdin), writes empty additionalContext so the session proceeds
unblocked.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
TIMEOUT_SECONDS = 0.5

_GENERIC_BASENAMES = frozenset({"docker", "src", "app", "project", "repo", "code"})


def _run_git(args: list[str], cwd: str | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _collect_git_branch(git_root: str) -> str | None:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    if result == "HEAD":
        return None
    return result


def _collect_git_log(git_root: str) -> str | None:
    result = _run_git(["log", "--oneline", "-10"], cwd=git_root)
    if result is None:
        return None
    encoded = result.encode("utf-8")
    if len(encoded) <= 600:
        return result
    truncated = encoded[:600].decode("utf-8", errors="ignore")
    return truncated.rsplit("\n", 1)[0]


def derive_agent(cwd: str) -> str:
    p = Path(cwd)
    basename = p.name.lower() or "default"
    if basename in _GENERIC_BASENAMES:
        parent = p.parent.name.lower() or "root"
        basename = f"{parent}-{basename}"
    return basename


def main(stdin_data: str | None = None) -> int:
    try:
        raw = stdin_data if stdin_data is not None else sys.stdin.read()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            _write_empty()
            return 0

        cwd = data.get("cwd", "") or os.getcwd()
        session_id = data.get("session_id", "")
        agent = derive_agent(cwd)

        try:
            resp = httpx.post(
                f"{BRAIN_URL}/hook/wake_up",
                json={"agent": agent, "project": cwd, "session_id": session_id},
                timeout=TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception:
            _write_empty()
            return 0

        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": body.get("context", ""),
            },
        }))
        return 0
    except Exception:
        return 0


def _write_empty() -> None:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "",
        },
    }))


if __name__ == "__main__":
    sys.exit(main())
