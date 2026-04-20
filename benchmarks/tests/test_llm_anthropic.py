from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brain_bench.llm.anthropic import AnthropicClient


def _fake_resp(text: str, in_tok: int, out_tok: int):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=in_tok, output_tokens=out_tok)
    return resp


def test_complete_returns_text_and_tokens():
    fake = MagicMock()
    fake.messages.create.return_value = _fake_resp("hello world", 100, 20)
    client = AnthropicClient(model="claude-opus-4-7", _client=fake)
    result = client.complete(system="sys", user="usr")
    assert result.text == "hello world"
    assert result.input_tokens == 100
    assert result.output_tokens == 20


def test_cost_computed_from_pricing():
    """claude-opus-4-7 priced per PRICING dict. Test asserts the formula."""
    fake = MagicMock()
    fake.messages.create.return_value = _fake_resp("out", 1_000_000, 1_000_000)
    client = AnthropicClient(model="claude-opus-4-7", _client=fake)
    result = client.complete(system="s", user="u")
    assert result.cost_usd > 0
    assert result.cost_usd == pytest.approx(
        AnthropicClient.PRICING["claude-opus-4-7"]["input"]
        + AnthropicClient.PRICING["claude-opus-4-7"]["output"]
    )


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="pricing"):
        AnthropicClient(model="claude-future-20", _client=MagicMock())
