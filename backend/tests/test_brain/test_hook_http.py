"""HTTP route integration tests — uses the real HTTP handler against mocked backend state."""
from __future__ import annotations

from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import httpx
import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain import server  # noqa: E402


def _start_server(tmp_path: Path, api_key: str = "fake") -> tuple[HTTPServer, str]:
    import os
    os.environ["BRAIN_PERSIST_DIR"] = str(tmp_path / "chromadb")
    os.environ["GOOGLE_API_KEY"] = api_key
    server._store = None
    server._events = None
    server._queue = None
    if hasattr(server, "_extractor"):
        server._extractor = None
    http_cls, handler_cls = server.create_http_app()
    srv = http_cls(("127.0.0.1", 0), handler_cls)
    port = srv.server_address[1]
    thr = Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    return srv, f"http://127.0.0.1:{port}"


def test_wake_up_returns_empty_context_for_fresh_brain(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/wake_up", json={
            "agent": "brain-dev", "project": "/", "session_id": "s"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["context"] == ""
        assert body["layers_loaded"] == {"L0": 0, "L1": 0}
    finally:
        srv.shutdown()


def test_wake_up_missing_agent_returns_400(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/wake_up", json={"project": "/", "session_id": "s"})
        assert resp.status_code == 400
    finally:
        srv.shutdown()


def test_post_turn_stores_extracted_memories(tmp_path: Path):
    from brain.hook import ExtractedMemory

    srv, url = _start_server(tmp_path)
    try:
        fake_memories = [
            ExtractedMemory(
                content="content c1 about backend stuff",
                type="fact",
                tags=["backend"],
                confidence=0.9,
            ),
        ]
        with patch.object(server, "_get_extractor") as mock_get:
            mock_extractor = mock_get.return_value
            mock_extractor.extract.return_value = fake_memories
            resp = httpx.post(f"{url}/hook/post_turn", json={
                "agent": "brain-dev", "project": "/", "session_id": "s",
                "turn": {"user": "u", "assistant": "a", "tool_calls": []},
            })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["extracted"]) == 1
        assert body["extracted"][0]["type"] == "fact"
    finally:
        srv.shutdown()


def test_post_turn_missing_agent_returns_400(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/hook/post_turn", json={
            "project": "/", "session_id": "s",
            "turn": {"user": "u", "assistant": "a"}
        })
        assert resp.status_code == 400
    finally:
        srv.shutdown()


def test_post_turn_without_api_key_returns_503(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    srv, url = _start_server(tmp_path, api_key="")
    # Clear the env after server start
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    try:
        resp = httpx.post(f"{url}/hook/post_turn", json={
            "agent": "t", "project": "/", "session_id": "s",
            "turn": {"user": "u", "assistant": "a"},
        })
        assert resp.status_code == 503
    finally:
        srv.shutdown()
