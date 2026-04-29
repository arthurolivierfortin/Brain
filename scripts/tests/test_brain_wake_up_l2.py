"""Tests for L2-B enrichment helpers in brain_wake_up.py."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import brain_wake_up as hook


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
