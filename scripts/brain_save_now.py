"""Manually trigger brain save for the current Claude Code session.

Discovers the active session by finding the most recently modified
transcript file, then runs brain_hook.main() with the right parameters.

Usage: ! python scripts/brain_save_now.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _project_dir_name(cwd: Path) -> str:
    """Encode cwd the way Claude Code names its project transcript dirs.

    Claude Code replaces drive separators and path separators with dashes,
    so C:\\Brain becomes C--Brain, /home/user/foo becomes -home-user-foo.
    """
    s = str(cwd.resolve())
    return s.replace("\\", "-").replace("/", "-").replace(":", "-")


def find_current_session() -> tuple[str, Path] | None:
    """Find the most recently modified transcript in Claude's project dir."""
    project_dir_name = _project_dir_name(Path.cwd())
    project_dir = Path.home() / ".claude" / "projects" / project_dir_name
    if not project_dir.exists():
        return None

    newest: tuple[float, str, Path] | None = None
    for transcript in project_dir.glob("*.jsonl"):
        try:
            mtime = transcript.stat().st_mtime
        except OSError:
            continue
        session_id = transcript.stem
        if newest is None or mtime > newest[0]:
            newest = (mtime, session_id, transcript)

    if newest is None:
        return None
    return newest[1], newest[2]


def main() -> None:
    result = find_current_session()
    if result is None:
        print("brain-save: no active session found", file=sys.stderr)
        sys.exit(1)

    session_id, transcript_path = result
    print(f"brain-save: session {session_id[:12]}...", file=sys.stderr)

    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    sys.path.insert(0, str(project_root / "scripts"))
    from brain_hook import main as hook_main

    stdin_data = json.dumps({
        "session_id": session_id,
        "transcript_path": str(transcript_path),
    })

    success = hook_main(stdin_data=stdin_data)
    if success:
        print("brain-save: done", file=sys.stderr)
    else:
        print("brain-save: skipped (delta too small)", file=sys.stderr)


if __name__ == "__main__":
    main()
