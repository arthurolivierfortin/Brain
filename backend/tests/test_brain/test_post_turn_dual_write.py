"""POST /hook/post_turn dual-writes to ChromaDB AND raw buffer (Phase 2c.1)."""
from __future__ import annotations

from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import httpx
import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")

from brain import server  # noqa: E402
from brain.hook import ExtractedMemory  # noqa: E402


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


def test_post_turn_writes_to_raw_and_extracted(tmp_path: Path):
    srv, url = _start_server(tmp_path)
    try:
        fake = [
            ExtractedMemory(
                content="raw fact about the backend pipeline",
                type="fact", tags=["backend"], confidence=0.9,
            ),
        ]
        with patch.object(server, "_get_extractor") as mock_get:
            mock_get.return_value.extract.return_value = fake
            resp = httpx.post(f"{url}/hook/post_turn", json={
                "agent": "brain", "project": "/x", "session_id": "s1",
                "turn": {
                    "user": "user prompt text",
                    "assistant": "assistant turn text",
                    "tool_calls": [{"name": "Bash", "input": {"command": "ls"}}],
                },
            })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["extracted"]) == 1

        # ChromaDB has the extracted memory
        store = server.get_store()
        results = store.search("raw fact backend", agent="brain")
        assert len(results) >= 1

        # Raw buffer has the assistant_message line
        rb = server.get_raw_buffer()
        rb.flush()
        files = list((tmp_path / "raw_buffer").glob("brain_raw_buffer.*.jsonl"))
        assert len(files) == 1
        text = files[0].read_text(encoding="utf-8")
        assert "assistant turn text" in text
        assert "assistant_message" in text
    finally:
        srv.shutdown()


def test_post_turn_succeeds_when_raw_buffer_fails(tmp_path: Path):
    """Raw-buffer write must not break the legacy extracted path."""
    srv, url = _start_server(tmp_path)
    try:
        from brain.raw_buffer import RawBuffer
        with patch.object(RawBuffer, "append", side_effect=RuntimeError("disk full")), \
             patch.object(server, "_get_extractor") as mock_get:
            mock_get.return_value.extract.return_value = [
                ExtractedMemory(
                    content="content c1 long enough to pass gate",
                    type="fact", tags=[], confidence=0.9,
                )
            ]
            resp = httpx.post(f"{url}/hook/post_turn", json={
                "agent": "brain", "project": "/x", "session_id": "s1",
                "turn": {"user": "u", "assistant": "a", "tool_calls": []},
            })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["extracted"]) == 1
    finally:
        srv.shutdown()
