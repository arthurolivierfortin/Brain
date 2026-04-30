"""HTTP /raw_event endpoint tests (Phase 2c.1)."""
from __future__ import annotations

from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import httpx
import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain import server  # noqa: E402


def _start_server(tmp_path: Path) -> tuple[HTTPServer, str]:
    import os
    os.environ["BRAIN_PERSIST_DIR"] = str(tmp_path / "chromadb")
    os.environ["BRAIN_RAW_BUFFER_DIR"] = str(tmp_path / "raw_buffer")
    os.environ["GOOGLE_API_KEY"] = "fake"
    server._store = None
    server._events = None
    server._queue = None
    server._extractor = None
    server._raw_buffer = None
    http_cls, handler_cls = server.create_http_app()
    srv = http_cls(("127.0.0.1", 0), handler_cls)
    port = srv.server_address[1]
    thr = Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    return srv, f"http://127.0.0.1:{port}"


def test_post_raw_event_returns_200_and_writes(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/raw_event", json={
            "kind": "user_message",
            "agent": "brain",
            "session_id": "s1",
            "project": "/x",
            "content": "hello brain user prompt content",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("stored") is True
        assert "event_id" in body and len(body["event_id"]) > 0
        assert "timestamp" in body

        rb = server.get_raw_buffer()
        rb.flush()
        files = list((tmp_path / "raw_buffer").glob("brain_raw_buffer.*.jsonl"))
        assert len(files) == 1
        text = files[0].read_text(encoding="utf-8")
        assert "hello brain user prompt content" in text
        assert "user_message" in text
    finally:
        srv.shutdown()


def test_post_raw_event_swallows_storage_failure(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        from brain.raw_buffer import RawBuffer
        with patch.object(RawBuffer, "append", side_effect=RuntimeError("disk full")):
            resp = httpx.post(f"{url}/raw_event", json={
                "kind": "user_message",
                "agent": "brain",
                "session_id": "s1",
                "project": "/x",
                "content": "this should not crash the endpoint",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("stored") is False
        assert "reason" in body
    finally:
        srv.shutdown()


def test_post_raw_event_rejects_invalid_kind(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.post(f"{url}/raw_event", json={
            "kind": "garbage_kind",
            "agent": "brain",
            "session_id": "s1",
            "project": "/x",
            "content": "x",
        })
        assert resp.status_code == 400
    finally:
        srv.shutdown()
