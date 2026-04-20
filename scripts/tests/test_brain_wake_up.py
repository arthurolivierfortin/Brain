"""Unit tests for brain_wake_up.py (SessionStart CC hook adapter)."""
from __future__ import annotations

import io
import json
from unittest.mock import patch

import brain_wake_up as hook


def _capture(fn):
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        rc = fn()
    return buf.getvalue(), rc


def test_derive_agent_uses_cwd_basename():
    assert hook.derive_agent("C:/Brain") == "brain"
    assert hook.derive_agent("/home/user/Money") == "money"


def test_derive_agent_handles_generic_basename():
    assert hook.derive_agent("C:/someproject/src") == "someproject-src"
    assert hook.derive_agent("/a/Marcel/docker") == "marcel-docker"


def test_successful_wake_up_returns_cc_contract(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResp(200, {
            "context": "## Identity\n- Arthur",
            "layers_loaded": {"L0": 1, "L1": 0},
            "tokens_approx": 10,
            "duration_ms": 5,
        })
    monkeypatch.setattr(hook.httpx, "post", fake_post)
    out, rc = _capture(lambda: hook.main(
        stdin_data=json.dumps({"cwd": "C:/Brain", "session_id": "s1"})
    ))
    parsed = json.loads(out)
    assert rc == 0
    assert parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Arthur" in parsed["hookSpecificOutput"]["additionalContext"]


def test_brain_unreachable_yields_empty_context(monkeypatch):
    def _raise(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(hook.httpx, "post", _raise)
    out, rc = _capture(lambda: hook.main(
        stdin_data=json.dumps({"cwd": "C:/Brain", "session_id": "s1"})
    ))
    parsed = json.loads(out)
    assert rc == 0
    assert parsed["hookSpecificOutput"]["additionalContext"] == ""


def test_malformed_stdin_yields_empty_context(monkeypatch):
    out, rc = _capture(lambda: hook.main(stdin_data="{not json"))
    parsed = json.loads(out)
    assert rc == 0
    assert parsed["hookSpecificOutput"]["additionalContext"] == ""


def test_http_500_yields_empty_context(monkeypatch):
    monkeypatch.setattr(hook.httpx, "post",
                        lambda *a, **kw: _FakeResp(500, {"error": "boom"}))
    out, rc = _capture(lambda: hook.main(
        stdin_data=json.dumps({"cwd": "/x", "session_id": "s"})
    ))
    parsed = json.loads(out)
    assert rc == 0
    assert parsed["hookSpecificOutput"]["additionalContext"] == ""


class _FakeResp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
