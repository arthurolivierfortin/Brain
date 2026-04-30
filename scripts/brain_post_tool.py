"""Claude Code PostToolUse hook — captures every tool call to L1 raw buffer.

Fire-and-forget: timeout=0.5s, swallows every exception, prints '{}' on
stdout. NEVER blocks the agent's tool pipeline. Captures tool_name,
tool_input (full), and a 2000-char excerpt of tool_response.
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
MAX_EXCERPT_CHARS = 2000

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

        tool_name = data.get("tool_name", "") or ""
        tool_input = data.get("tool_input", {}) or {}
        tool_response = data.get("tool_response", "")
        session_id = data.get("session_id", "") or ""
        cwd = data.get("cwd", "") or os.getcwd()
        agent = derive_agent(cwd)

        if not isinstance(tool_input, dict):
            tool_input = {"raw": str(tool_input)}

        try:
            content = json.dumps(tool_input)[:MAX_EXCERPT_CHARS]
        except (TypeError, ValueError):
            content = str(tool_input)[:MAX_EXCERPT_CHARS]

        excerpt = (
            tool_response if isinstance(tool_response, str)
            else json.dumps(tool_response, default=str)
        )[:MAX_EXCERPT_CHARS]

        payload = {
            "kind": "tool_use",
            "agent": agent,
            "session_id": session_id,
            "project": cwd,
            "content": content,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output_excerpt": excerpt,
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
