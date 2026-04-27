"""Schema smoke test for GET /graph — validates fields the JS monitor depends on."""
from __future__ import annotations

from http.server import HTTPServer
from pathlib import Path
from threading import Thread

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


def test_graph_route_returns_expected_schema(tmp_path: Path) -> None:
    srv, url = _start_server(tmp_path)
    try:
        r1 = httpx.post(f"{url}/store", json={
            "content": "alpha memory for graph test",
            "agent": "test",
            "memory_type": "fact",
            "skip_gate": True,
        })
        assert r1.status_code == 200
        entry_id_1 = r1.json().get("id", "")

        r2 = httpx.post(f"{url}/store", json={
            "content": "beta memory for graph test",
            "agent": "test",
            "memory_type": "context",
            "links": entry_id_1,
            "skip_gate": True,
        })
        assert r2.status_code == 200

        resp = httpx.get(f"{url}/graph")
        assert resp.status_code == 200

        body = resp.json()
        assert "entries" in body
        entries = body["entries"]
        assert isinstance(entries, list)
        assert len(entries) >= 2

        for entry in entries:
            assert "id" in entry, f"missing 'id' in {entry}"
            assert "memory_type" in entry, f"missing 'memory_type' in {entry}"
            assert "links" in entry, f"missing 'links' in {entry}"
            assert "access_count" in entry, f"missing 'access_count' in {entry}"
            assert isinstance(entry["links"], str), (
                f"'links' must be str (CSV), got {type(entry['links'])}"
            )
            assert isinstance(entry["access_count"], int), (
                f"'access_count' must be int, got {type(entry['access_count'])}"
            )
    finally:
        srv.shutdown()
