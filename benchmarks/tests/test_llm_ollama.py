from __future__ import annotations

from unittest.mock import MagicMock

from brain_bench.llm.ollama import OllamaClient


def test_complete_returns_llmcall_with_zero_cost():
    fake = MagicMock()
    fake.chat.return_value = {
        "message": {"content": "the answer"},
        "prompt_eval_count": 100,
        "eval_count": 20,
    }
    client = OllamaClient(model="llama3.1:70b", _client=fake)
    result = client.complete(system="you are helpful", user="what is 2+2?")
    assert result.text == "the answer"
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.cost_usd == 0.0  # local inference


def test_complete_sends_correct_messages():
    fake = MagicMock()
    fake.chat.return_value = {
        "message": {"content": "ok"},
        "prompt_eval_count": 1,
        "eval_count": 1,
    }
    client = OllamaClient(model="qwen2.5:7b", _client=fake)
    client.complete(system="SYSTEM", user="USER")
    fake.chat.assert_called_once()
    args = fake.chat.call_args
    assert args.kwargs["model"] == "qwen2.5:7b"
    msgs = args.kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "SYSTEM"}
    assert msgs[1] == {"role": "user", "content": "USER"}
