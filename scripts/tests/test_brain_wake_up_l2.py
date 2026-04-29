"""Tests for L2-B enrichment helpers in brain_wake_up.py."""
from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import brain_wake_up as hook

SCRIPTS_DIR = Path(__file__).parent.parent
SCRIPT_PATH = str(SCRIPTS_DIR / "brain_wake_up.py")


# ---------------------------------------------------------------------------
# [TEST-1] _run_git returns None when git binary missing
# ---------------------------------------------------------------------------
def test_run_git_returns_none_when_git_missing():
    with patch.object(hook.subprocess, "run", side_effect=FileNotFoundError("git not found")):
        result = hook._run_git(["status"])
    assert result is None


# ---------------------------------------------------------------------------
# [TEST-2] _run_git returns None on non-zero exit code
# ---------------------------------------------------------------------------
def test_run_git_returns_none_on_nonzero_exit():
    fake = subprocess.CompletedProcess(
        args=["git", "bogus"], returncode=128, stdout="", stderr="fatal: not a git repo"
    )
    with patch.object(hook.subprocess, "run", return_value=fake):
        result = hook._run_git(["bogus"])
    assert result is None


# ---------------------------------------------------------------------------
# [TEST-3] _collect_git_branch handles detached HEAD and happy path
# ---------------------------------------------------------------------------
def test_collect_git_branch_handles_detached_head():
    with patch.object(hook, "_run_git", return_value="HEAD"):
        result = hook._collect_git_branch("/x")
    assert result is None

    with patch.object(hook, "_run_git", return_value="feature/foo"):
        result = hook._collect_git_branch("/x")
    assert result == "feature/foo"

    with patch.object(hook, "_run_git", return_value=None):
        result = hook._collect_git_branch("/x")
    assert result is None


# ---------------------------------------------------------------------------
# [TEST-4] _collect_git_log truncates at line boundary when over 600 bytes
# ---------------------------------------------------------------------------
def test_collect_git_log_truncates_at_line_boundary():
    line_30 = "a" * 28 + "bc"
    over_budget = "\n".join([line_30] * 25)

    with patch.object(hook, "_run_git", return_value=over_budget):
        result = hook._collect_git_log("/x")

    assert result is not None
    assert len(result.encode("utf-8")) <= 600
    for part in result.split("\n"):
        assert len(part) == 30

    short = "a" * 200
    with patch.object(hook, "_run_git", return_value=short):
        result_short = hook._collect_git_log("/x")
    assert result_short == short

    with patch.object(hook, "_run_git", return_value=None):
        assert hook._collect_git_log("/x") is None


# ---------------------------------------------------------------------------
# [TEST-5] _collect_claude_md reads, truncates, falls back to git_root
# ---------------------------------------------------------------------------
def test_collect_claude_md_reads_truncates_and_falls_back(tmp_path):
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("a" * 1500, encoding="utf-8")
    result_a = hook._collect_claude_md(str(tmp_path), git_root=None)
    assert result_a is not None
    assert len(result_a) == 1000

    subdir = tmp_path / "sub"
    subdir.mkdir()
    result_b = hook._collect_claude_md(str(subdir), git_root=str(tmp_path))
    assert result_b is not None
    assert len(result_b) == 1000

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result_c = hook._collect_claude_md(str(empty_dir), git_root=str(empty_dir))
    assert result_c is None


# ---------------------------------------------------------------------------
# Captor HTTP server used by integration tests [TEST-6] and [TEST-7]
# ---------------------------------------------------------------------------
class _CaptorHandler(http.server.BaseHTTPRequestHandler):
    captured: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CaptorHandler.captured.append(json.loads(body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"context": ""}')

    def log_message(self, *args):
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _git_subprocess_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@test.com",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@test.com",
    }


# ---------------------------------------------------------------------------
# [TEST-6] Integration: subprocess sends enriched payload when git repo + CLAUDE.md present
# ---------------------------------------------------------------------------
def test_subprocess_sends_enriched_payload_when_git_and_claudemd_present(tmp_path):
    git_dir = tmp_path / "repo"
    git_dir.mkdir()
    (git_dir / "README.md").write_text("hello", encoding="utf-8")
    (git_dir / "CLAUDE.md").write_text("x" * 1500, encoding="utf-8")

    git_env = _git_subprocess_env()
    subprocess.run(["git", "init"], cwd=str(git_dir), check=True,
                   capture_output=True, env=git_env)
    subprocess.run(["git", "config", "user.email", "t@test.com"], cwd=str(git_dir),
                   check=True, capture_output=True, env=git_env)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(git_dir),
                   check=True, capture_output=True, env=git_env)
    subprocess.run(["git", "add", "."], cwd=str(git_dir), check=True,
                   capture_output=True, env=git_env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(git_dir), check=True,
                   capture_output=True, env=git_env)

    port = _free_port()
    _CaptorHandler.captured = []
    server = http.server.HTTPServer(("127.0.0.1", port), _CaptorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        env = {**os.environ, "BRAIN_URL": f"http://127.0.0.1:{port}"}
        stdin_payload = json.dumps({"cwd": str(git_dir), "session_id": "s1"})

        subprocess.run(
            [sys.executable, SCRIPT_PATH],
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    finally:
        server.shutdown()

    assert len(_CaptorHandler.captured) == 1
    body = _CaptorHandler.captured[0]

    assert "git_branch" in body, f"git_branch missing from payload: {body}"
    assert isinstance(body["git_branch"], str)

    assert "git_recent_commits" in body, f"git_recent_commits missing from payload: {body}"
    assert len(body["git_recent_commits"].encode("utf-8")) <= 600

    assert "claude_md_excerpt" in body, f"claude_md_excerpt missing from payload: {body}"
    assert len(body["claude_md_excerpt"]) == 1000
