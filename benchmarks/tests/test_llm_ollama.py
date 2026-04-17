from __future__ import annotations

from unittest.mock import MagicMock

from brain_bench.llm.ollama import OllamaClient


def test_complete_returns_llmcall_with_zero_cost():
    fake_resp = MagicMock()
    fake_resp.message.content = "the answer"
    fake_resp.prompt_eval_count = 100
    fake_resp.eval_count = 20
    fake = MagicMock()
    fake.chat.return_value = fake_resp
    client = OllamaClient(model="llama3.1:70b", _client=fake)
    result = client.complete(system="you are helpful", user="what is 2+2?")
    assert result.text == "the answer"
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.cost_usd == 0.0


def test_complete_sends_correct_messages():
    fake_resp = MagicMock()
    fake_resp.message.content = "ok"
    fake_resp.prompt_eval_count = 1
    fake_resp.eval_count = 1
    fake = MagicMock()
    fake.chat.return_value = fake_resp
    client = OllamaClient(model="qwen2.5:7b", _client=fake)
    client.complete(system="SYSTEM", user="USER")
    fake.chat.assert_called_once()
    args = fake.chat.call_args
    assert args.kwargs["model"] == "qwen2.5:7b"
    msgs = args.kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "SYSTEM"}
    assert msgs[1] == {"role": "user", "content": "USER"}
