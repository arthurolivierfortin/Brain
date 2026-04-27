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


def test_monitor_route_serves_html(tmp_path: Path) -> None:
    srv, url = _start_server(tmp_path)
    try:
        resp = httpx.get(f"{url}/monitor")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert b"<title>brain \xc2\xb7 live monitor</title>" in resp.content
        assert b'<div id="root"></div>' in resp.content
    finally:
        srv.shutdown()
