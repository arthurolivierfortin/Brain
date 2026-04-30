"""Brain MCP server — drop-in memory service.

MCP SSE on BRAIN_MCP_PORT (default 8610).
HTTP API on BRAIN_HTTP_PORT (default 8611).

Env config:
- BRAIN_MCP_PORT, BRAIN_HTTP_PORT, BRAIN_HOST (default 0.0.0.0)
- BRAIN_PERSIST_DIR (ChromaDB location)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from brain.events import EventLog
from brain.pending_queue import PendingQueue
from brain.store import BrainStore

logger = logging.getLogger(__name__)

mcp = FastMCP("money-brain")

# Global store instance -- initialized on startup
_store: BrainStore | None = None
_events: EventLog | None = None
_queue: PendingQueue | None = None
_extractor: Any = None
_raw_buffer: Any = None


def _get_extractor() -> Any:
    """Lazy singleton for the Extractor. Reads GOOGLE_API_KEY from env."""
    global _extractor
    if _extractor is None:
        from brain.hook import GeminiFlashExtractor
        _extractor = GeminiFlashExtractor()
    return _extractor


def get_store() -> BrainStore:
    global _store, _events
    if _store is None:
        import os
        _events = EventLog()
        _store = BrainStore(
            persist_dir=os.environ.get("BRAIN_PERSIST_DIR"),
            event_log=_events,
        )
    return _store


def get_events() -> EventLog:
    global _events
    if _events is None:
        _events = EventLog()
    return _events


def get_queue() -> PendingQueue:
    global _queue
    if _queue is None:
        _queue = PendingQueue()
    return _queue


def get_raw_buffer() -> Any:
    """Lazy singleton for the L1 RawBuffer. Path via BRAIN_RAW_BUFFER_DIR env."""
    global _raw_buffer
    if _raw_buffer is None:
        import os

        from brain.raw_buffer import RawBuffer
        default = "/data/raw_buffer" if Path("/data").exists() else "data/raw_buffer"
        root = Path(os.environ.get("BRAIN_RAW_BUFFER_DIR", default))
        _raw_buffer = RawBuffer(root)
    return _raw_buffer


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def brain_store(
    content: str,
    agent: str = "dev-cycle",
    memory_type: str = "context",
    links: str = "",
    context: str = "",
) -> str:
    """Store a memory in the brain. Goes through gate (filter) and enrichment (entity extraction).

    Args:
        content: The memory content to store.
        agent: Which agent is storing this (e.g., dev-cycle, self-improver, staging).
        memory_type: Type: architecture, strategy, bug, context, decision.
        links: Comma-separated links to other entries or concepts.
        context: Optional context about when/why this is being stored.
    """
    store = get_store()
    full_content = f"{content}\n\nContext: {context}" if context else content
    link_list = [lk.strip() for lk in links.split(",") if lk.strip()] if links else None
    metadata = {"event_type": memory_type}

    try:
        result = store.store(
            content=full_content,
            agent=agent,
            memory_type=memory_type,
            metadata=metadata,
            links=link_list,
        )
    except Exception as e:
        logger.error("ChromaDB store failed, queuing for replay: %s", e)
        queue = get_queue()
        queued = queue.enqueue({
            "content": full_content,
            "agent": agent,
            "memory_type": memory_type,
            "metadata": metadata,
            "links": link_list,
        })
        return json.dumps({
            "stored": False,
            "queued": queued,
            "reason": f"ChromaDB unavailable, queued for replay: {e}",
            "queue_size": queue.pending_count(),
        })

    if result is None:
        return json.dumps({"stored": False, "reason": "Rejected by gate (noise or duplicate)"})

    return json.dumps({"stored": True, **result}, indent=2)


@mcp.tool()
def brain_search(
    query: str,
    agent: str = "",
    memory_type: str = "",
    top_k: int = 5,
) -> str:
    """Search the brain for relevant memories using semantic search.

    Finds conceptually similar content, not just keyword matches.
    "position sizing" will find "Kelly criterion" because they are
    semantically related.

    Args:
        query: Natural language search query.
        agent: Filter by agent name (empty = search all agents).
        memory_type: Filter by type (empty = all types).
        top_k: Maximum results to return.
    """
    store = get_store()
    results = store.search(
        query=query,
        agent=agent or None,
        memory_type=memory_type or None,
        top_k=top_k,
    )
    return json.dumps({"results": results, "count": len(results)}, indent=2)


@mcp.tool()
def brain_related(entry_id: str) -> str:
    """Find memories related to a given entry.

    Uses three types of connections:
    1. Explicit links (manually linked entries)
    2. Semantic similarity (conceptually close content)
    3. Shared metadata (same symbols, strategies)

    Args:
        entry_id: The memory entry ID to find relations for.
    """
    store = get_store()
    related = store.related(entry_id)
    return json.dumps({"entry_id": entry_id, "related": related, "count": len(related)}, indent=2)


@mcp.tool()
def brain_forget(entry_id: str) -> str:
    """Remove a memory from the brain.

    Args:
        entry_id: The memory entry ID to remove.
    """
    store = get_store()
    success = store.forget(entry_id)
    return json.dumps({"forgotten": success, "id": entry_id})


@mcp.tool()
def brain_stats() -> str:
    """Get brain statistics -- total memories, per-agent counts, types, top accessed."""
    store = get_store()
    stats = store.stats()
    events = get_events()
    stats["recent_events"] = events.recent(limit=20)
    stats["activity"] = events.stats_over_time(buckets=24)
    return json.dumps(stats, indent=2)


# ---------------------------------------------------------------------------
# HTTP endpoints (for trading bot and dashboard)
# ---------------------------------------------------------------------------

def create_http_app():
    """Create a simple HTTP API for non-MCP clients (trading bot, dashboard)."""
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class BrainHTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/stats":
                store = get_store()
                data = store.stats()
                self._json_response(data)
            elif parsed.path == "/search":
                query = params.get("query", [""])[0]
                agent = params.get("agent", [""])[0]
                top_k = int(params.get("top_k", ["5"])[0])
                store = get_store()
                results = store.search(query, agent=agent or None, top_k=top_k)
                self._json_response({"results": results})
            elif parsed.path == "/graph":
                store = get_store()
                entries = store.get_all_for_graph()
                self._json_response({"entries": entries})
            elif parsed.path == "/events":
                limit = int(params.get("limit", ["50"])[0])
                events = get_events()
                self._json_response({"events": events.recent(limit=limit)})
            elif parsed.path == "/events/timeline":
                events = get_events()
                self._json_response({"timeline": events.stats_over_time()})
            elif parsed.path == "/queue/status":
                queue = get_queue()
                self._json_response({
                    "pending": queue.pending_count(),
                    "queue_path": str(queue.path),
                })
            elif parsed.path == "/health":
                self._json_response({"status": "ok", "total": get_store()._collection.count()})
            elif parsed.path == "/monitor":
                _html_path = Path(__file__).parent / "static" / "brain.html"
                try:
                    _html_bytes = _html_path.read_bytes()
                except FileNotFoundError:
                    self._json_response({"error": "monitor template missing"}, status=500)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(_html_bytes)
            else:
                self._json_response({"error": "not found"}, status=404)

        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response({"error": "invalid JSON"}, status=400)
                return

            if self.path == "/store":
                store = get_store()
                try:
                    result = store.store(
                        content=data.get("content", ""),
                        agent=data.get("agent", "unknown"),
                        memory_type=data.get("memory_type", "context"),
                        metadata=data.get("metadata"),
                        links=data.get("links"),
                        skip_gate=data.get("skip_gate", False),
                    )
                except Exception as e:
                    logger.error("HTTP /store ChromaDB failed, queuing: %s", e)
                    queue = get_queue()
                    queued = queue.enqueue({
                        "content": data.get("content", ""),
                        "agent": data.get("agent", "unknown"),
                        "memory_type": data.get("memory_type", "context"),
                        "metadata": data.get("metadata"),
                        "links": data.get("links"),
                        "skip_gate": data.get("skip_gate", False),
                    })
                    self._json_response({
                        "stored": False,
                        "queued": queued,
                        "reason": f"ChromaDB unavailable: {e}",
                        "queue_size": queue.pending_count(),
                    }, status=503)
                    return
                if result:
                    self._json_response({"stored": True, **result})
                else:
                    self._json_response({"stored": False, "reason": "rejected by gate"})
            elif self.path == "/queue":
                queue = get_queue()
                queued = queue.enqueue({
                    "content": data.get("content", ""),
                    "agent": data.get("agent", "unknown"),
                    "memory_type": data.get("memory_type", "context"),
                    "metadata": data.get("metadata"),
                    "links": data.get("links"),
                    "skip_gate": data.get("skip_gate", False),
                })
                self._json_response({
                    "queued": queued,
                    "queue_size": queue.pending_count(),
                })
            elif self.path == "/consolidate":
                try:
                    store = get_store()
                    result = store.consolidate()
                    self._json_response(result)
                except Exception as e:
                    logger.error("Consolidation failed: %s", e)
                    self._json_response({"error": str(e)}, status=500)
            elif self.path == "/hook/wake_up":
                import os

                from brain.hook import HookRequest, WakeUpHandler
                agent = data.get("agent", "")
                if not agent:
                    self._json_response({"error": "missing 'agent'"}, status=400)
                    return
                store = get_store()
                events = get_events()
                req = HookRequest(
                    agent=agent,
                    project=data.get("project", ""),
                    session_id=data.get("session_id", ""),
                    git_recent_commits=data.get("git_recent_commits", ""),
                    git_branch=data.get("git_branch", ""),
                    claude_md_excerpt=data.get("claude_md_excerpt", ""),
                )
                handler = WakeUpHandler(store, events)
                r = handler.handle(req)
                threshold = float(os.environ.get("BRAIN_L2_THRESHOLD", "0.45"))
                cosine_scores = [
                    round(1.0 - m["distance"] / 2.0, 4) for m in r.topic
                ]
                events.log(
                    event_type="hook_wake_up",
                    agent=req.agent,
                    metadata={
                        "tokens_approx": r.tokens_approx,
                        "layers_loaded": r.layers_loaded,
                        "duration_ms": r.duration_ms,
                        "memory_ids": {
                            "L0": [m["id"] for m in r.identity],
                            "L1": [m["id"] for m in r.prefs],
                            "L2": [m["id"] for m in r.topic],
                        },
                        "cosine_scores": cosine_scores,
                        "threshold_applied": threshold,
                        "tokens_per_layer": {
                            "L0": sum(len(m["content"]) // 4 for m in r.identity),
                            "L1": sum(len(m["content"]) // 4 for m in r.prefs),
                            "L2": sum(len(m["content"]) // 4 for m in r.topic),
                        },
                    },
                )
                self._json_response({
                    "context": r.context,
                    "layers_loaded": r.layers_loaded,
                    "tokens_approx": r.tokens_approx,
                    "duration_ms": r.duration_ms,
                })
            elif self.path == "/hook/post_turn":
                from brain.hook import HookRequest, PostTurnHandler, Turn
                agent = data.get("agent", "")
                if not agent:
                    self._json_response({"error": "missing 'agent'"}, status=400)
                    return
                try:
                    extractor = _get_extractor()
                except ValueError as e:
                    self._json_response({"error": str(e)}, status=503)
                    return
                store = get_store()
                events = get_events()
                req = HookRequest(
                    agent=agent,
                    project=data.get("project", ""),
                    session_id=data.get("session_id", ""),
                )
                turn_data = data.get("turn", {})
                turn = Turn(
                    user=turn_data.get("user", ""),
                    assistant=turn_data.get("assistant", ""),
                    tool_calls=turn_data.get("tool_calls", []),
                )

                # Dual-write: L1 raw assistant_message before extraction.
                try:
                    from datetime import UTC, datetime

                    from brain.raw_buffer import RawEvent
                    rb = get_raw_buffer()
                    rb.append(RawEvent(
                        timestamp=datetime.now(UTC),
                        kind="assistant_message",
                        agent=agent,
                        session_id=req.session_id,
                        project=req.project,
                        content=turn.assistant,
                        metadata={"tool_calls": turn.tool_calls} if turn.tool_calls else {},
                    ))
                except Exception as e:
                    logger.warning("Raw buffer dual-write failed (non-fatal): %s", e)

                handler = PostTurnHandler(store, extractor, events)
                r = handler.handle(req, turn)
                self._json_response({
                    "extracted": r.extracted,
                    "rejected_by_gate": r.rejected_by_gate,
                    "extraction_cost_usd": r.extraction_cost_usd,
                    "extraction_ms": r.extraction_ms,
                })
            elif self.path == "/raw_event":
                from datetime import UTC, datetime

                from pydantic import ValidationError

                from brain.raw_buffer import RawEvent
                payload = dict(data)
                payload.setdefault("timestamp", datetime.now(UTC).isoformat())
                try:
                    event = RawEvent.model_validate(payload)
                except ValidationError as e:
                    self._json_response({"error": "invalid_payload", "details": e.errors()}, status=400)
                    return
                rb = get_raw_buffer()
                try:
                    rb.append(event)
                except Exception as e:
                    logger.warning("/raw_event append failed: %s", e)
                    self._json_response({"stored": False, "reason": str(e)})
                    return
                self._json_response({
                    "stored": True,
                    "event_id": event.event_id,
                    "timestamp": event.timestamp.isoformat(),
                })
            elif self.path == "/reset":
                store = get_store()
                agent = data.get("agent")
                deleted = store.reset(agent=agent)
                self._json_response({"deleted": deleted, "agent": agent or "ALL"})
            else:
                self._json_response({"error": "not found"}, status=404)

        def _json_response(self, data: dict, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        def log_message(self, fmt, *args):
            logger.debug("HTTP: %s", fmt % args)

    return HTTPServer, BrainHTTPHandler


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _drain_loop(interval: int = 60) -> None:
    """Background thread that periodically drains the pending queue."""
    import time

    while True:
        time.sleep(interval)
        try:
            queue = get_queue()
            if queue.pending_count() > 0:
                store = get_store()
                result = queue.drain(store.store)
                if result["stored"] > 0 or result["discarded"] > 0:
                    logger.info("Background drain: %s", result)
        except Exception as e:
            logger.warning("Background drain failed: %s", e)


def main():
    """Start the brain server (MCP SSE + HTTP API)."""
    import threading

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    # Initialize store eagerly
    store = get_store()
    logger.info("Brain store initialized: %d entries", store._collection.count())

    # Drain any pending entries from previous crash/restart
    queue = get_queue()
    pending = queue.pending_count()
    if pending > 0:
        logger.info("Found %d pending brain_store entries, draining...", pending)
        drain_result = queue.drain(store.store)
        logger.info("Startup drain result: %s", drain_result)

    # Start background drain thread (runs every 60s)
    drain_thread = threading.Thread(target=_drain_loop, daemon=True)
    drain_thread.start()
    logger.info("Background drain thread started (interval=60s)")

    # Ports and bind host via env (drop-in, no config file)
    import os
    http_port = int(os.environ.get("BRAIN_HTTP_PORT", "8611"))
    mcp_port = int(os.environ.get("BRAIN_MCP_PORT", "8610"))
    bind_host = os.environ.get("BRAIN_HOST", "0.0.0.0")  # noqa: S104 — service must be reachable cross-container

    http_server_cls, handler_cls = create_http_app()
    http_server = http_server_cls((bind_host, http_port), handler_cls)  # noqa: S104 — intentional
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    logger.info("HTTP API started on %s:%d", bind_host, http_port)

    logger.info("Starting MCP SSE server on %s:%d", bind_host, mcp_port)
    mcp.settings.host = bind_host
    mcp.settings.port = mcp_port

    service_host = os.environ.get("BRAIN_SERVICE_HOST", "brain")
    mcp.settings.transport_security.allowed_hosts = [
        f"{service_host}:*", "localhost:*", "127.0.0.1:*", "[::1]:*",
    ]
    mcp.settings.transport_security.allowed_origins = [
        f"http://{service_host}:*", "http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*",
    ]

    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
