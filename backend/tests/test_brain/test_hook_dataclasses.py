"""Tests for hook dataclasses + Extractor protocol."""
from __future__ import annotations


def test_turn_defaults_empty_tool_calls() -> None:
    from brain.hook import Turn
    t = Turn(user="hi", assistant="hey")
    assert t.user == "hi"
    assert t.assistant == "hey"
    assert t.tool_calls == []


def test_hook_request_has_expected_fields() -> None:
    from brain.hook import HookRequest
    r = HookRequest(agent="a", project="/p", session_id="s")
    assert (r.agent, r.project, r.session_id) == ("a", "/p", "s")


def test_wake_up_response_has_expected_fields() -> None:
    from brain.hook import WakeUpResponse
    r = WakeUpResponse(context="x", layers_loaded={"L0": 1}, tokens_approx=42, duration_ms=7)
    assert r.context == "x"
    assert r.layers_loaded == {"L0": 1}
    assert r.tokens_approx == 42
    assert r.duration_ms == 7


def test_extracted_memory_has_expected_fields() -> None:
    from brain.hook import ExtractedMemory
    m = ExtractedMemory(content="c", type="fact", tags=["a", "b"], confidence=0.9)
    assert m.content == "c"
    assert m.type == "fact"
    assert m.tags == ["a", "b"]
    assert m.confidence == 0.9


def test_post_turn_response_has_expected_fields() -> None:
    from brain.hook import PostTurnResponse
    r = PostTurnResponse(extracted=[], rejected_by_gate=0, extraction_cost_usd=0.0, extraction_ms=5)
    assert r.extracted == []
    assert r.rejected_by_gate == 0
    assert r.extraction_cost_usd == 0.0
    assert r.extraction_ms == 5


def test_extractor_protocol_structurally_typed() -> None:
    from brain.hook import ExtractedMemory, Extractor, Turn

    class _MiniExtractor:
        def extract(self, turn: Turn) -> list[ExtractedMemory]:
            return []

    ext: Extractor = _MiniExtractor()
    assert ext.extract(Turn(user="", assistant="")) == []
