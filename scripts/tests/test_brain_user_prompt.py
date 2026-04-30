"""Subprocess tests for scripts/brain_user_prompt.py (UserPromptSubmit CC hook)."""
from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent
SCRIPT_PATH = str(SCRIPTS_DIR / "brain_user_prompt.py")


class _CaptorHandler(http.server.BaseHTTPRequestHandler):
    captured: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CaptorHandler.captured.append({
            "path": self.path,
            "body": json.loads(body),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"stored": true, "event_id": "x"}')

    def log_message(self, *args):
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_subprocess_posts_user_message(tmp_path):
    port = _free_port()
    _CaptorHandler.captured = []
    server = http.server.HTTPServer(("127.0.0.1", port), _CaptorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        env = {**os.environ, "BRAIN_URL": f"http://127.0.0.1:{port}"}
        stdin_payload = json.dumps({
            "prompt": "hello brain", "session_id": "s1", "cwd": str(tmp_path),
        })

        proc = subprocess.run(
            [sys.executable, SCRIPT_PATH],
            input=stdin_payload,
            capture_output=True, text=True, env=env, timeout=10,
        )
    finally:
        server.shutdown()

    assert proc.returncode == 0
    assert proc.stdout.strip() == "{}"
    assert len(_CaptorHandler.captured) == 1
    captured = _CaptorHandler.captured[0]
    assert captured["path"] == "/raw_event"
    body = captured["body"]
    assert body["kind"] == "user_message"
    assert body["content"] == "hello brain"
    assert body["session_id"] == "s1"
    assert "agent" in body
    assert "project" in body


def test_subprocess_silent_on_brain_down(tmp_path):
    """Brain unreachable must NEVER block user input — exit 0, stdout '{}'."""
    env = {**os.environ, "BRAIN_URL": "http://127.0.0.1:1"}
    stdin_payload = json.dumps({
        "prompt": "hello", "session_id": "s1", "cwd": str(tmp_path),
    })
    proc = subprocess.run(
        [sys.executable, SCRIPT_PATH],
        input=stdin_payload,
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "{}"


def test_subprocess_silent_on_malformed_stdin(tmp_path):
    proc = subprocess.run(
        [sys.executable, SCRIPT_PATH],
        input="{not json",
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "{}"
