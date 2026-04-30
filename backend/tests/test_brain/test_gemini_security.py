"""Security regression tests for GeminiFlashExtractor."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from brain.hook import GeminiFlashExtractor, Turn


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({"memories": []})}]}}]
    }
    resp.raise_for_status = MagicMock()
    return resp


def test_extract_uses_header_auth_not_query_param() -> None:
    """SPEC-1: outbound URL must not contain the API key; header must carry it."""
    api_key = "test-key-abc123"
    fake_client = MagicMock()
    fake_client.post.return_value = _ok_response()

    ext = GeminiFlashExtractor(api_key=api_key, _client=fake_client)
    ext.extract(Turn(user="u", assistant="a"))

    assert fake_client.post.called
    call_args = fake_client.post.call_args
    url: str = call_args.args[0] if call_args.args else call_args.kwargs["url"]
    headers: dict = call_args.kwargs.get("headers", {})

    # URL must end with :generateContent — no query string
    assert url.endswith(":generateContent"), f"URL has unexpected suffix: {url}"
    assert "?" not in url, f"URL must not contain query string, got: {url}"
    assert api_key not in url, f"API key must not appear in URL, got: {url}"

    # Key must be in the header instead
    assert headers.get("x-goog-api-key") == api_key, (
        f"Expected header x-goog-api-key={api_key!r}, got headers={headers}"
    )


import logging


def test_httpx_logger_level_is_warning() -> None:
    """SPEC-2: importing brain.hook must suppress httpx INFO URL logs."""
    import brain.hook  # noqa: F401 — side-effect import triggers module-top setLevel
    assert logging.getLogger("httpx").level == logging.WARNING, (
        f"Expected httpx logger level WARNING ({logging.WARNING}), "
        f"got {logging.getLogger('httpx').level}"
    )
