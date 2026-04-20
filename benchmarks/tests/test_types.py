from __future__ import annotations

from brain_bench.types import (
    DatasetEntry,
    Memory,
    Question,
    Session,
    Turn,
)


class TestTurn:
    def test_create(self):
        t = Turn(role="user", content="hello")
        assert t.role == "user"
        assert t.content == "hello"


class TestSession:
    def test_create(self):
        s = Session(
            session_id="s1",
            session_date="2025-01-01",
            turns=[Turn(role="user", content="hi"), Turn(role="assistant", content="hello")],
        )
        assert s.session_id == "s1"
        assert len(s.turns) == 2

    def test_iter_turns(self):
        s = Session(session_id="s1", session_date="2025-01-01", turns=[])
        assert list(s.turns) == []


class TestMemory:
    def test_create_minimal(self):
        m = Memory(id="m1", content="text", score=0.8)
        assert m.session_id is None

    def test_create_full(self):
        m = Memory(id="m1", content="text", score=0.8, session_id="s1", metadata={"k": "v"})
        assert m.session_id == "s1"
        assert m.metadata == {"k": "v"}


class TestQuestion:
    def test_create(self):
        q = Question(
            question_id="q1",
            question_type="temporal-reasoning",
            question="when?",
            answer="yesterday",
            question_date="2025-01-02",
            answer_session_ids=["s1"],
        )
        assert q.question_type == "temporal-reasoning"


class TestDatasetEntry:
    def test_create(self):
        q = Question(
            question_id="q1", question_type="info-extraction",
            question="?", answer=".", question_date="2025-01-01",
            answer_session_ids=[],
        )
        e = DatasetEntry(question=q, sessions=[])
        assert e.question.question_id == "q1"
