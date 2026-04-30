"""Claude Code UserPromptSubmit hook — captures the user prompt to L1 raw buffer.

Fire-and-forget by design: timeout=0.5s, swallows every exception, prints
'{}' on stdout (UserPromptSubmit contract: no additional context injected).
NEVER blocks user input even if Brain is down or slow.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
TIMEOUT_SECONDS = 0.5

_GENERIC_BASENAMES = frozenset({"docker", "src", "app", "project", "repo", "code"})


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
            sys.stdout.write("{}")
            return 0

        prompt = data.get("prompt", "") or ""
        session_id = data.get("session_id", "") or ""
        cwd = data.get("cwd", "") or os.getcwd()
        agent = derive_agent(cwd)

        if not prompt:
            sys.stdout.write("{}")
            return 0

        payload = {
            "kind": "user_message",
            "agent": agent,
            "session_id": session_id,
            "project": cwd,
            "content": prompt,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            httpx.post(
                f"{BRAIN_URL}/raw_event", json=payload, timeout=TIMEOUT_SECONDS,
            )
        except Exception:
            pass

        sys.stdout.write("{}")
        return 0
    except Exception:
        sys.stdout.write("{}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
