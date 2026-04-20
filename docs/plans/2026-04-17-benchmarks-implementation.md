# Brain Benchmarks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement phase 5a of `docs/specs/2026-04-17-benchmarks-design.md` — LongMemEval-s runner with Brain full vs ChromaDB raw ablation, Ollama dev loop, Claude release capability. Phase 5b (Brain-Bench custom) gets a placeholder task to be detailed after 5a lands.

**Architecture:** Standalone `benchmarks/` directory at repo root with its own `pyproject.toml`, never shipped with the `brain` package. Protocol-based adapter + LLM client design allows swapping Brain/ChromaDB and Ollama/Claude via YAML config. Runner streams each Q's result to a JSONL log for crash-safe resume.

**Tech Stack:** Python 3.12+, uv, pytest, httpx, chromadb, ollama-python, anthropic, datasets (HuggingFace optional — primary path is git clone), pandas, pyyaml, tqdm.

---

## File structure

```
benchmarks/
├── pyproject.toml
├── README.md
├── config/
│   ├── dev.yaml
│   └── release.yaml
├── src/
│   └── brain_bench/
│       ├── __init__.py
│       ├── types.py             # Session, Turn, Memory, Question, DatasetEntry
│       ├── config.py            # Config loader (yaml → dataclass)
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py          # Adapter Protocol
│       │   ├── brain.py         # BrainAdapter (HTTP to localhost:8621)
│       │   └── chromadb_raw.py  # ChromaDBRawAdapter (direct ChromaDB)
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py          # LLMClient Protocol
│       │   ├── ollama.py        # OllamaClient
│       │   └── anthropic.py     # AnthropicClient
│       ├── datasets/
│       │   ├── __init__.py
│       │   └── longmemeval.py   # load_longmemeval_s
│       ├── metrics.py           # Recall@k, per-category accuracy, aggregator
│       ├── report.py            # Markdown + CSV writer
│       └── runners/
│           ├── __init__.py
│           └── longmemeval.py   # Orchestrator
├── scripts/
│   ├── setup.sh                 # clone LongMemEval, ollama pull
│   └── run.sh                   # wrapper: healthcheck Brain, run, publish
├── external/                    # gitignored: cloned LongMemEval
└── tests/
    ├── conftest.py
    ├── test_types.py
    ├── test_config.py
    ├── test_adapter_brain.py
    ├── test_adapter_chromadb_raw.py
    ├── test_llm_ollama.py
    ├── test_llm_anthropic.py
    ├── test_dataset_longmemeval.py
    ├── test_metrics.py
    ├── test_report.py
    └── test_runner_longmemeval.py

docs/
└── benchmarks/
    ├── README.md                          # index, how to read
    └── results.csv                        # append-only, header pre-written
```

## Task dependency graph

```
Task 1 (scaffold) ──┬──→ Task 2 (types) ──┬──→ Task 3 (adapter base)   ──→ Task 5 (brain)       ──┐
                    │                     ├──→ Task 6 (adapter chromadb)                          ├──→ Task 11 (runner)
                    │                     ├──→ Task 7 (llm base)       ──→ Task 8 (ollama)        │
                    │                     │                            ──→ Task 9 (anthropic)     │
                    │                     ├──→ Task 10 (dataset loader)                           │
                    │                     ├──→ Task 12 (metrics)                                  │
                    │                     ├──→ Task 13 (report writer)                            │
                    │                     └──→ Task 4 (config loader) ────────────────────────────┘
                    │
                    └──→ Task 14 (scripts) ──→ Task 15 (integration test)

Task 16 (docs) ──→ independent, last
Task 17 (brain-bench placeholder) ──→ independent, last
```

**Parallel batches (for subagent dispatch):**
- Batch A (seq): Task 1
- Batch B (seq after 1): Task 2
- Batch C (parallel after 2): Tasks 3, 4, 7, 10, 12, 13
- Batch D (parallel after 3): Tasks 5, 6
- Batch E (parallel after 7): Tasks 8, 9
- Batch F (seq, depends on B-E): Task 11
- Batch G (parallel): Tasks 14, 15
- Batch H (parallel, final): Tasks 16, 17

---

### Task 1: Scaffold benchmarks/

**Files:**
- Create: `benchmarks/pyproject.toml`
- Create: `benchmarks/README.md`
- Create: `benchmarks/src/brain_bench/__init__.py`
- Create: `benchmarks/tests/__init__.py`
- Create: `benchmarks/tests/conftest.py`
- Create: `benchmarks/.gitignore`
- Create: `benchmarks/config/dev.yaml`
- Create: `benchmarks/config/release.yaml`
- Modify: `.gitignore` (add `benchmarks/external/`, `benchmarks/runs/`, `benchmarks/.venv/`)

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "brain-bench"
version = "0.1.0"
description = "Benchmarks harness for Brain (LongMemEval, Brain-Bench)"
requires-python = ">=3.12"
dependencies = [
    "chromadb>=0.5.0",
    "httpx>=0.27",
    "ollama>=0.3",
    "anthropic>=0.42",
    "pandas>=2.2",
    "pyyaml>=6.0",
    "tqdm>=4.66",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "mypy>=1.10",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/brain_bench"]

[tool.ruff]
src = ["src", "tests"]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
pythonpath = ["src"]
```

- [ ] **Step 2: Create README**

```markdown
# Brain Benchmarks

Harness for running Brain against LongMemEval-s (phase 5a) and a custom Brain-Bench (phase 5b).

## Setup
```bash
cd benchmarks
uv venv && uv pip install -e ".[dev]"
bash scripts/setup.sh     # clones LongMemEval, pulls Ollama model
```

## Dev run (free, Ollama, 50 Q)
```bash
# Ensure Brain is up: docker compose -f ../docker/compose.yml up -d
python -m brain_bench.runners.longmemeval --config config/dev.yaml
```

## Release run (Claude, full 500 Q)
```bash
python -m brain_bench.runners.longmemeval --config config/release.yaml --adapter brain
python -m brain_bench.runners.longmemeval --config config/release.yaml --adapter chromadb_raw
```

See `docs/specs/2026-04-17-benchmarks-design.md` for the full spec.
```

- [ ] **Step 3: Create __init__.py files**

`benchmarks/src/brain_bench/__init__.py`:
```python
"""Brain benchmarks harness."""
```

`benchmarks/tests/__init__.py`:
```python
```

`benchmarks/tests/conftest.py`:
```python
"""Pytest fixtures shared across brain_bench tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def tmp_persist_dir(tmp_path):
    """Temp ChromaDB persist dir per test."""
    return tmp_path / "chromadb"
```

- [ ] **Step 4: Create .gitignore**

`benchmarks/.gitignore`:
```
.venv/
external/
runs/
*.egg-info/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

- [ ] **Step 5: Update root .gitignore**

Append to `.gitignore`:
```
benchmarks/external/
benchmarks/runs/
benchmarks/.venv/
```

- [ ] **Step 6: Create config/dev.yaml**

```yaml
dataset: longmemeval_s
subset: 50
adapter: brain
reader:
  provider: ollama
  model: llama3.1:70b
judge:
  provider: ollama
  model: llama3.1:70b
brain_url: http://localhost:8621
chromadb_raw_persist_dir: ./runs/chromadb_raw
output_dir: ./runs
dry_run: false
seed: 42
```

- [ ] **Step 7: Create config/release.yaml**

```yaml
dataset: longmemeval_s
subset: null
adapter: brain
reader:
  provider: anthropic
  model: claude-opus-4-7
judge:
  provider: anthropic
  model: claude-opus-4-7
brain_url: http://localhost:8621
chromadb_raw_persist_dir: ./runs/chromadb_raw
output_dir: ../docs/benchmarks
dry_run: false
seed: 42
```

- [ ] **Step 8: Verify install works**

```bash
cd benchmarks
uv venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -c "import brain_bench; print('ok')"
```
Expected: `ok`

- [ ] **Step 9: Commit**

```bash
git add benchmarks/ .gitignore
git commit -m "🧠 Feature: scaffold benchmarks/ harness (phase 5a bootstrap)"
```

---

### Task 2: Core types

**Files:**
- Create: `benchmarks/src/brain_bench/types.py`
- Create: `benchmarks/tests/test_types.py`

- [ ] **Step 1: Write the failing test**

`benchmarks/tests/test_types.py`:
```python
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
```

- [ ] **Step 2: Run — expect failure**

```bash
cd benchmarks
.venv/Scripts/pytest tests/test_types.py -v
```
Expected: ImportError (brain_bench.types does not exist yet)

- [ ] **Step 3: Implement types.py**

`benchmarks/src/brain_bench/types.py`:
```python
"""Shared data types for the benchmark harness."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Turn:
    role: str
    content: str


@dataclass
class Session:
    session_id: str
    session_date: str
    turns: list[Turn]


@dataclass
class Memory:
    id: str
    content: str
    score: float
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Question:
    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    answer_session_ids: list[str]


@dataclass
class DatasetEntry:
    question: Question
    sessions: list[Session]
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_types.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/types.py benchmarks/tests/test_types.py
git commit -m "🧠 Feature: benchmarks core types (Session, Memory, Question, DatasetEntry)"
```

---

### Task 3: Adapter base protocol

**Files:**
- Create: `benchmarks/src/brain_bench/adapters/__init__.py`
- Create: `benchmarks/src/brain_bench/adapters/base.py`

- [ ] **Step 1: Create __init__.py**

```python
"""Memory adapter protocol and implementations."""
```

- [ ] **Step 2: Define Adapter protocol**

`benchmarks/src/brain_bench/adapters/base.py`:
```python
"""Adapter protocol: what every memory backend must implement."""
from __future__ import annotations

from typing import Protocol

from brain_bench.types import Memory, Session


class Adapter(Protocol):
    """Memory backend contract.

    An adapter ingests conversation sessions and retrieves the top-k most
    relevant memories for a query. Implementations exist for Brain (HTTP
    API) and ChromaDB raw (direct, used as ablation baseline).
    """

    def reset(self) -> None:
        """Clear all stored memories. Called once per dataset entry."""
        ...

    def ingest(self, session: Session) -> None:
        """Store all turns of a session as retrievable memories."""
        ...

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        """Return top-k memories ranked by relevance to query."""
        ...
```

- [ ] **Step 3: Commit**

```bash
git add benchmarks/src/brain_bench/adapters/
git commit -m "🧠 Feature: adapter base protocol"
```

---

### Task 4: Config loader

**Files:**
- Create: `benchmarks/src/brain_bench/config.py`
- Create: `benchmarks/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`benchmarks/tests/test_config.py`:
```python
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from brain_bench.config import Config, LLMConfig, load_config


def test_load_dev_config(tmp_path: Path):
    p = tmp_path / "dev.yaml"
    p.write_text(dedent("""
        dataset: longmemeval_s
        subset: 50
        adapter: brain
        reader: { provider: ollama, model: "llama3.1:70b" }
        judge: { provider: ollama, model: "llama3.1:70b" }
        brain_url: http://localhost:8621
        chromadb_raw_persist_dir: ./runs/chromadb_raw
        output_dir: ./runs
        dry_run: false
        seed: 42
    """))
    cfg = load_config(p)
    assert cfg.dataset == "longmemeval_s"
    assert cfg.subset == 50
    assert cfg.adapter == "brain"
    assert cfg.reader.provider == "ollama"
    assert cfg.reader.model == "llama3.1:70b"
    assert cfg.brain_url == "http://localhost:8621"
    assert cfg.seed == 42


def test_subset_null_means_full(tmp_path: Path):
    p = tmp_path / "release.yaml"
    p.write_text(dedent("""
        dataset: longmemeval_s
        subset: null
        adapter: brain
        reader: { provider: anthropic, model: "claude-opus-4-7" }
        judge: { provider: anthropic, model: "claude-opus-4-7" }
        brain_url: http://localhost:8621
        chromadb_raw_persist_dir: ./runs/chromadb_raw
        output_dir: ../docs/benchmarks
        dry_run: false
        seed: 42
    """))
    cfg = load_config(p)
    assert cfg.subset is None


def test_invalid_adapter_raises(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text(dedent("""
        dataset: longmemeval_s
        subset: 10
        adapter: not_a_real_adapter
        reader: { provider: ollama, model: "x" }
        judge: { provider: ollama, model: "x" }
        brain_url: http://localhost:8621
        chromadb_raw_persist_dir: ./runs/chromadb_raw
        output_dir: ./runs
        dry_run: false
        seed: 42
    """))
    with pytest.raises(ValueError, match="adapter"):
        load_config(p)
```

- [ ] **Step 2: Run — expect failure**

Expected: ImportError.

- [ ] **Step 3: Implement config.py**

```python
"""YAML config loader for benchmark runs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

VALID_ADAPTERS = {"brain", "chromadb_raw"}
VALID_PROVIDERS = {"ollama", "anthropic"}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str

    def __post_init__(self) -> None:
        if self.provider not in VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {VALID_PROVIDERS}, got {self.provider!r}")


@dataclass(frozen=True)
class Config:
    dataset: str
    subset: int | None
    adapter: str
    reader: LLMConfig
    judge: LLMConfig
    brain_url: str
    chromadb_raw_persist_dir: str
    output_dir: str
    dry_run: bool
    seed: int

    def __post_init__(self) -> None:
        if self.adapter not in VALID_ADAPTERS:
            raise ValueError(f"adapter must be one of {VALID_ADAPTERS}, got {self.adapter!r}")


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    return Config(
        dataset=raw["dataset"],
        subset=raw.get("subset"),
        adapter=raw["adapter"],
        reader=LLMConfig(**raw["reader"]),
        judge=LLMConfig(**raw["judge"]),
        brain_url=raw["brain_url"],
        chromadb_raw_persist_dir=raw["chromadb_raw_persist_dir"],
        output_dir=raw["output_dir"],
        dry_run=raw.get("dry_run", False),
        seed=raw.get("seed", 42),
    )
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/config.py benchmarks/tests/test_config.py
git commit -m "🧠 Feature: yaml config loader (Config, LLMConfig, validation)"
```

---

### Task 5: Brain adapter (HTTP)

**Files:**
- Create: `benchmarks/src/brain_bench/adapters/brain.py`
- Create: `benchmarks/tests/test_adapter_brain.py`

- [ ] **Step 1: Write the failing tests**

`benchmarks/tests/test_adapter_brain.py`:
```python
from __future__ import annotations

import pytest
import respx
from httpx import Response

from brain_bench.adapters.brain import BrainAdapter
from brain_bench.types import Session, Turn


@respx.mock
def test_ingest_posts_each_turn():
    respx.post("http://brain:8611/store").mock(
        return_value=Response(200, json={"stored": True, "id": "m1"})
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="hi"), Turn(role="assistant", content="hey")],
    ))
    assert respx.calls.call_count == 2


@respx.mock
def test_retrieve_returns_memories():
    respx.get("http://brain:8611/search").mock(
        return_value=Response(200, json={
            "results": [
                {"id": "m1", "content": "hi", "score": 0.9,
                 "metadata": {"session_id": "s1"}},
                {"id": "m2", "content": "hello", "score": 0.7,
                 "metadata": {"session_id": "s1"}},
            ],
            "count": 2,
        })
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    memories = adapter.retrieve("greetings", k=5)
    assert len(memories) == 2
    assert memories[0].id == "m1"
    assert memories[0].score == pytest.approx(0.9)
    assert memories[0].session_id == "s1"


@respx.mock
def test_reset_calls_forget_all():
    # Spec: reset clears Brain's collection via a (to-be-added) endpoint.
    # For v1 we call /stats and forget each entry one by one (slow, OK for 500 Q).
    respx.get("http://brain:8611/stats").mock(
        return_value=Response(200, json={"ids": ["m1", "m2"]})
    )
    respx.post("http://brain:8611/forget").mock(
        return_value=Response(200, json={"forgotten": True})
    )
    adapter = BrainAdapter(brain_url="http://brain:8611")
    adapter.reset()
    assert respx.calls.call_count >= 1
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement BrainAdapter**

`benchmarks/src/brain_bench/adapters/brain.py`:
```python
"""Brain HTTP adapter — wires LongMemEval sessions into Brain's /store and /search."""
from __future__ import annotations

import httpx

from brain_bench.types import Memory, Session


class BrainAdapter:
    """Uses Brain's HTTP API (localhost:8621 in docker compose setup)."""

    def __init__(self, brain_url: str, timeout: float = 30.0) -> None:
        self._url = brain_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def reset(self) -> None:
        """Forget every memory currently stored.

        For phase 5a we iterate and forget per entry. A bulk /reset
        endpoint on Brain is a future improvement.
        """
        stats = self._client.get(f"{self._url}/stats").json()
        ids = stats.get("ids", [])
        for mid in ids:
            self._client.post(f"{self._url}/forget", json={"id": mid})

    def ingest(self, session: Session) -> None:
        for i, turn in enumerate(session.turns):
            content = f"[{turn.role}] {turn.content}"
            payload = {
                "content": content,
                "agent": "longmemeval",
                "memory_type": "context",
                "metadata": {
                    "session_id": session.session_id,
                    "session_date": session.session_date,
                    "turn_idx": i,
                    "role": turn.role,
                },
                "skip_gate": True,
            }
            resp = self._client.post(f"{self._url}/store", json=payload)
            resp.raise_for_status()

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        resp = self._client.get(
            f"{self._url}/search",
            params={"query": query, "top_k": k},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            Memory(
                id=r["id"],
                content=r["content"],
                score=r.get("score", 0.0),
                session_id=(r.get("metadata") or {}).get("session_id"),
                metadata=r.get("metadata") or {},
            )
            for r in data.get("results", [])
        ]
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_adapter_brain.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/adapters/brain.py benchmarks/tests/test_adapter_brain.py
git commit -m "🧠 Feature: BrainAdapter (HTTP) with ingest/retrieve/reset + mocked tests"
```

---

### Task 6: ChromaDB raw adapter

**Files:**
- Create: `benchmarks/src/brain_bench/adapters/chromadb_raw.py`
- Create: `benchmarks/tests/test_adapter_chromadb_raw.py`

- [ ] **Step 1: Write the failing tests**

`benchmarks/tests/test_adapter_chromadb_raw.py`:
```python
from __future__ import annotations

from pathlib import Path

from brain_bench.adapters.chromadb_raw import ChromaDBRawAdapter
from brain_bench.types import Session, Turn


def test_ingest_and_retrieve_roundtrip(tmp_path: Path):
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chromadb")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[
            Turn(role="user", content="I love sailing on Lake Michigan"),
            Turn(role="assistant", content="Great hobby."),
        ],
    ))
    mems = adapter.retrieve("sailing", k=5)
    assert len(mems) >= 1
    assert any("sailing" in m.content.lower() for m in mems)


def test_reset_clears_collection(tmp_path: Path):
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chromadb")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="some content")],
    ))
    assert len(adapter.retrieve("content", k=5)) >= 1
    adapter.reset()
    assert adapter.retrieve("content", k=5) == []


def test_score_is_similarity_not_distance(tmp_path: Path):
    """ChromaDB returns distances by default; adapter converts to similarity."""
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chromadb")
    adapter.ingest(Session(
        session_id="s1", session_date="2025-01-01",
        turns=[Turn(role="user", content="The sky is blue")],
    ))
    mems = adapter.retrieve("sky is blue", k=1)
    assert 0.0 <= mems[0].score <= 1.0
    assert mems[0].score > 0.5  # close match → high similarity
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement ChromaDBRawAdapter**

`benchmarks/src/brain_bench/adapters/chromadb_raw.py`:
```python
"""Raw ChromaDB adapter — ablation baseline with no Brain logic."""
from __future__ import annotations

from pathlib import Path

import chromadb

from brain_bench.types import Memory, Session


class ChromaDBRawAdapter:
    """Baseline: bare ChromaDB with default embeddings.

    This is what an app gets with just `chromadb.PersistentClient`. If Brain
    does not outperform this on LongMemEval, then Brain's structure (gate,
    graph, decay, consolidation) is not contributing — the embedding model is.
    """

    def __init__(self, persist_dir: str | Path, collection_name: str = "longmemeval_raw") -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._name = collection_name
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        self._client.delete_collection(self._name)
        self._collection = self._client.get_or_create_collection(
            name=self._name,
            metadata={"hnsw:space": "cosine"},
        )

    def ingest(self, session: Session) -> None:
        if not session.turns:
            return
        ids, docs, metas = [], [], []
        for i, turn in enumerate(session.turns):
            ids.append(f"{session.session_id}_{i}")
            docs.append(f"[{turn.role}] {turn.content}")
            metas.append({
                "session_id": session.session_id,
                "session_date": session.session_date,
                "turn_idx": i,
                "role": turn.role,
            })
        self._collection.upsert(ids=ids, documents=docs, metadatas=metas)

    def retrieve(self, query: str, k: int = 5) -> list[Memory]:
        count = self._collection.count()
        if count == 0:
            return []
        res = self._collection.query(query_texts=[query], n_results=min(k, count))
        memories: list[Memory] = []
        for i in range(len(res["ids"][0])):
            distance = res["distances"][0][i]
            similarity = max(0.0, 1.0 - distance)
            meta = res["metadatas"][0][i] or {}
            memories.append(Memory(
                id=res["ids"][0][i],
                content=res["documents"][0][i],
                score=similarity,
                session_id=meta.get("session_id"),
                metadata=dict(meta),
            ))
        return memories
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_adapter_chromadb_raw.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/adapters/chromadb_raw.py benchmarks/tests/test_adapter_chromadb_raw.py
git commit -m "🧠 Feature: ChromaDBRawAdapter baseline (ablation for MemPalace trap)"
```

---

### Task 7: LLM base protocol

**Files:**
- Create: `benchmarks/src/brain_bench/llm/__init__.py`
- Create: `benchmarks/src/brain_bench/llm/base.py`

- [ ] **Step 1: Create __init__.py**

```python
"""LLM clients (Ollama, Anthropic)."""
```

- [ ] **Step 2: Define LLMClient protocol**

`benchmarks/src/brain_bench/llm/base.py`:
```python
"""LLMClient protocol. Two implementations: ollama (dev), anthropic (release)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMCall:
    """Single LLM completion result with usage stats."""
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMClient(Protocol):
    """Chat-completion style LLM."""

    def complete(self, system: str, user: str) -> LLMCall:
        """Return the assistant text + token usage + cost estimate."""
        ...
```

- [ ] **Step 3: Commit**

```bash
git add benchmarks/src/brain_bench/llm/
git commit -m "🧠 Feature: LLMClient protocol with LLMCall (text + token + cost)"
```

---

### Task 8: Ollama LLM wrapper

**Files:**
- Create: `benchmarks/src/brain_bench/llm/ollama.py`
- Create: `benchmarks/tests/test_llm_ollama.py`

- [ ] **Step 1: Write the failing tests**

`benchmarks/tests/test_llm_ollama.py`:
```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

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
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement OllamaClient**

`benchmarks/src/brain_bench/llm/ollama.py`:
```python
"""Ollama LLM wrapper — local, free, for the dev loop."""
from __future__ import annotations

from typing import Any

import ollama

from brain_bench.llm.base import LLMCall


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        _client: Any = None,
    ) -> None:
        self._model = model
        self._client = _client if _client is not None else ollama.Client(host=host)

    def complete(self, system: str, user: str) -> LLMCall:
        resp = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return LLMCall(
            text=resp["message"]["content"],
            input_tokens=resp.get("prompt_eval_count", 0),
            output_tokens=resp.get("eval_count", 0),
            cost_usd=0.0,
        )
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_llm_ollama.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/llm/ollama.py benchmarks/tests/test_llm_ollama.py
git commit -m "🧠 Feature: OllamaClient (local, free, dev loop)"
```

---

### Task 9: Anthropic LLM wrapper

**Files:**
- Create: `benchmarks/src/brain_bench/llm/anthropic.py`
- Create: `benchmarks/tests/test_llm_anthropic.py`

- [ ] **Step 1: Write the failing tests**

`benchmarks/tests/test_llm_anthropic.py`:
```python
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
    """claude-opus-4-7 is $15/M input, $75/M output (illustrative rates).

    Engineer: confirm current Opus 4.7 prices at release time; the test
    asserts the formula, not the literal rate.
    """
    fake = MagicMock()
    fake.messages.create.return_value = _fake_resp("out", 1_000_000, 1_000_000)
    client = AnthropicClient(model="claude-opus-4-7", _client=fake)
    result = client.complete(system="s", user="u")
    # 1M input + 1M output at Opus rates (rates come from PRICING dict)
    assert result.cost_usd > 0
    assert result.cost_usd == pytest.approx(
        AnthropicClient.PRICING["claude-opus-4-7"]["input"]
        + AnthropicClient.PRICING["claude-opus-4-7"]["output"]
    )


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="pricing"):
        AnthropicClient(model="claude-future-20", _client=MagicMock())
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement AnthropicClient**

`benchmarks/src/brain_bench/llm/anthropic.py`:
```python
"""Anthropic (Claude) LLM wrapper — for release runs, tracks cost per call."""
from __future__ import annotations

import os
from typing import Any

from anthropic import Anthropic

from brain_bench.llm.base import LLMCall


class AnthropicClient:
    """Per-million-token prices in USD. Update when Anthropic changes pricing."""
    PRICING: dict[str, dict[str, float]] = {
        "claude-opus-4-7":     {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-6":   {"input":  3.00, "output": 15.00},
        "claude-haiku-4-5":    {"input":  1.00, "output":  5.00},
    }

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_tokens: int = 1024,
        _client: Any = None,
    ) -> None:
        if model not in self.PRICING:
            raise ValueError(
                f"No pricing for {model!r}. Add it to AnthropicClient.PRICING."
            )
        self._model = model
        self._max_tokens = max_tokens
        if _client is not None:
            self._client = _client
        else:
            self._client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system: str, user: str) -> LLMCall:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text if resp.content else ""
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        p = self.PRICING[self._model]
        cost = (in_tok * p["input"] + out_tok * p["output"]) / 1_000_000
        return LLMCall(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_llm_anthropic.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/llm/anthropic.py benchmarks/tests/test_llm_anthropic.py
git commit -m "🧠 Feature: AnthropicClient with per-call cost tracking (PRICING table)"
```

---

### Task 10: LongMemEval dataset loader

**Files:**
- Create: `benchmarks/src/brain_bench/datasets/__init__.py`
- Create: `benchmarks/src/brain_bench/datasets/longmemeval.py`
- Create: `benchmarks/tests/test_dataset_longmemeval.py`
- Create: `benchmarks/tests/fixtures/longmemeval_mini.json` (5 entries, hand-crafted)

- [ ] **Step 1: Create test fixture**

`benchmarks/tests/fixtures/longmemeval_mini.json`:
```json
[
  {
    "question_id": "q1",
    "question_type": "single-session-assistant",
    "question": "What is my favorite color?",
    "answer": "blue",
    "question_date": "2025-01-10",
    "answer_session_ids": ["s1"],
    "haystack_sessions": [
      {
        "session_id": "s1",
        "session_date": "2025-01-05",
        "turns": [
          {"role": "user", "content": "My favorite color is blue."},
          {"role": "assistant", "content": "Noted."}
        ]
      }
    ]
  },
  {
    "question_id": "q2",
    "question_type": "temporal-reasoning",
    "question": "When did I change jobs?",
    "answer": "2024-11-01",
    "question_date": "2025-02-01",
    "answer_session_ids": ["s2"],
    "haystack_sessions": [
      {
        "session_id": "s2",
        "session_date": "2024-11-02",
        "turns": [
          {"role": "user", "content": "I started my new job yesterday, November 1st 2024."},
          {"role": "assistant", "content": "Congrats."}
        ]
      }
    ]
  },
  {
    "question_id": "q3",
    "question_type": "multi-session-reasoning",
    "question": "What do I usually drink?",
    "answer": "coffee",
    "question_date": "2025-03-01",
    "answer_session_ids": ["s3"],
    "haystack_sessions": [
      {"session_id": "s3", "session_date": "2025-02-01",
       "turns": [{"role": "user", "content": "I had coffee this morning."},
                 {"role": "assistant", "content": "Ok."}]}
    ]
  },
  {
    "question_id": "q4",
    "question_type": "knowledge-update",
    "question": "What city do I live in?",
    "answer": "Montreal",
    "question_date": "2025-04-01",
    "answer_session_ids": ["s4"],
    "haystack_sessions": [
      {"session_id": "s4", "session_date": "2025-03-15",
       "turns": [{"role": "user", "content": "I moved from Toronto to Montreal last week."},
                 {"role": "assistant", "content": "Nice city."}]}
    ]
  },
  {
    "question_id": "q5",
    "question_type": "abstention",
    "question": "What is my middle name?",
    "answer": "I don't have that information.",
    "question_date": "2025-05-01",
    "answer_session_ids": [],
    "haystack_sessions": []
  }
]
```

- [ ] **Step 2: Create __init__.py**

`benchmarks/src/brain_bench/datasets/__init__.py`:
```python
"""Dataset loaders (LongMemEval + custom)."""
```

- [ ] **Step 3: Write failing tests**

`benchmarks/tests/test_dataset_longmemeval.py`:
```python
from __future__ import annotations

from pathlib import Path

from brain_bench.datasets.longmemeval import load_longmemeval_s


FIXTURE = Path(__file__).parent / "fixtures" / "longmemeval_mini.json"


def test_loads_all_entries():
    entries = load_longmemeval_s(FIXTURE)
    assert len(entries) == 5


def test_question_parsed_correctly():
    entries = load_longmemeval_s(FIXTURE)
    e1 = entries[0]
    assert e1.question.question_id == "q1"
    assert e1.question.question_type == "single-session-assistant"
    assert e1.question.answer == "blue"


def test_sessions_parsed_correctly():
    entries = load_longmemeval_s(FIXTURE)
    e1 = entries[0]
    assert len(e1.sessions) == 1
    assert e1.sessions[0].session_id == "s1"
    assert len(e1.sessions[0].turns) == 2
    assert e1.sessions[0].turns[0].role == "user"


def test_subset_stratified():
    """subset=5 with seed=42 should yield 1 per category (5 categories)."""
    entries = load_longmemeval_s(FIXTURE, subset=5, seed=42)
    types = [e.question.question_type for e in entries]
    assert len(set(types)) == 5


def test_subset_larger_than_dataset_returns_all():
    entries = load_longmemeval_s(FIXTURE, subset=1000, seed=42)
    assert len(entries) == 5


def test_abstention_entries_have_no_haystack():
    entries = load_longmemeval_s(FIXTURE)
    abstention = next(e for e in entries if e.question.question_type == "abstention")
    assert abstention.sessions == []
```

- [ ] **Step 4: Run — expect ImportError**

- [ ] **Step 5: Implement loader**

`benchmarks/src/brain_bench/datasets/longmemeval.py`:
```python
"""LongMemEval dataset loader.

Upstream format (JSON array of entries):
    {
      "question_id", "question_type", "question", "answer", "question_date",
      "answer_session_ids": [...],
      "haystack_sessions": [
        {"session_id", "session_date", "turns": [{"role","content"}, ...]}
      ]
    }
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from brain_bench.types import DatasetEntry, Question, Session, Turn


def load_longmemeval_s(
    path: Path,
    subset: int | None = None,
    seed: int = 42,
) -> list[DatasetEntry]:
    """Load LongMemEval-s JSON. If subset is set, stratify by question_type."""
    raw = json.loads(Path(path).read_text())
    entries: list[DatasetEntry] = []
    for item in raw:
        q = Question(
            question_id=item["question_id"],
            question_type=item["question_type"],
            question=item["question"],
            answer=item["answer"],
            question_date=item["question_date"],
            answer_session_ids=list(item.get("answer_session_ids", [])),
        )
        sessions = [
            Session(
                session_id=s["session_id"],
                session_date=s["session_date"],
                turns=[Turn(role=t["role"], content=t["content"]) for t in s["turns"]],
            )
            for s in item.get("haystack_sessions", [])
        ]
        entries.append(DatasetEntry(question=q, sessions=sessions))

    if subset is None or subset >= len(entries):
        return entries

    # Stratified sampling by question_type
    by_type: dict[str, list[DatasetEntry]] = defaultdict(list)
    for e in entries:
        by_type[e.question.question_type].append(e)

    rng = random.Random(seed)
    n_types = len(by_type)
    per_type = max(1, subset // n_types)
    sampled: list[DatasetEntry] = []
    for t, group in by_type.items():
        rng.shuffle(group)
        sampled.extend(group[:per_type])
    rng.shuffle(sampled)
    return sampled[:subset]
```

- [ ] **Step 6: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_dataset_longmemeval.py -v
```

- [ ] **Step 7: Commit**

```bash
git add benchmarks/src/brain_bench/datasets/ benchmarks/tests/test_dataset_longmemeval.py benchmarks/tests/fixtures/
git commit -m "🧠 Feature: LongMemEval dataset loader with stratified subset sampling"
```

---

### Task 11: Runner orchestrator

**Files:**
- Create: `benchmarks/src/brain_bench/runners/__init__.py`
- Create: `benchmarks/src/brain_bench/runners/longmemeval.py`
- Create: `benchmarks/tests/test_runner_longmemeval.py`

- [ ] **Step 1: Create __init__.py**

```python
"""Benchmark runners."""
```

- [ ] **Step 2: Write failing tests**

`benchmarks/tests/test_runner_longmemeval.py`:
```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from brain_bench.llm.base import LLMCall
from brain_bench.runners.longmemeval import QuestionResult, run_longmemeval
from brain_bench.types import DatasetEntry, Memory, Question, Session, Turn


def _fake_entry(qid: str, qtype: str, answer_session_id: str) -> DatasetEntry:
    return DatasetEntry(
        question=Question(
            question_id=qid, question_type=qtype,
            question="?", answer="yes",
            question_date="2025-01-01", answer_session_ids=[answer_session_id],
        ),
        sessions=[Session(
            session_id=answer_session_id, session_date="2025-01-01",
            turns=[Turn(role="user", content="evidence")],
        )],
    )


def _fake_reader():
    r = MagicMock()
    r.complete.return_value = LLMCall(text="yes", input_tokens=10, output_tokens=1, cost_usd=0.01)
    return r


def _fake_judge(verdict: str = "CORRECT"):
    j = MagicMock()
    j.complete.return_value = LLMCall(text=verdict, input_tokens=10, output_tokens=1, cost_usd=0.01)
    return j


def _fake_adapter(returned_session_id: str):
    a = MagicMock()
    a.retrieve.return_value = [Memory(
        id="m1", content="evidence", score=0.9, session_id=returned_session_id,
    )]
    return a


def test_runner_produces_one_result_per_entry(tmp_path: Path):
    entries = [
        _fake_entry("q1", "info-extraction", "s1"),
        _fake_entry("q2", "temporal-reasoning", "s2"),
    ]
    log_path = tmp_path / "run.jsonl"
    results = run_longmemeval(
        entries=entries,
        adapter=_fake_adapter("s1"),
        reader=_fake_reader(),
        judge=_fake_judge("CORRECT"),
        log_path=log_path,
        k=5,
    )
    assert len(results) == 2


def test_recall_at_k_correct_when_answer_session_retrieved(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    adapter = _fake_adapter("s1")  # returns s1, which IS the answer session
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=_fake_reader(),
        judge=_fake_judge("CORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].recall_at_k is True


def test_recall_at_k_false_when_answer_session_missing(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    adapter = _fake_adapter("OTHER")  # does NOT return s1
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=_fake_reader(),
        judge=_fake_judge("INCORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].recall_at_k is False


def test_judge_correct_verdict_sets_accuracy_true(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    results = run_longmemeval(
        entries=entries, adapter=_fake_adapter("s1"), reader=_fake_reader(),
        judge=_fake_judge("CORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].accuracy is True


def test_judge_incorrect_verdict_sets_accuracy_false(tmp_path: Path):
    entries = [_fake_entry("q1", "info-extraction", "s1")]
    results = run_longmemeval(
        entries=entries, adapter=_fake_adapter("s1"), reader=_fake_reader(),
        judge=_fake_judge("INCORRECT"), log_path=tmp_path / "log.jsonl", k=5,
    )
    assert results[0].accuracy is False


def test_resume_skips_already_logged_questions(tmp_path: Path):
    log_path = tmp_path / "run.jsonl"
    # Pre-populate the log with q1 so it gets skipped
    log_path.write_text(json.dumps({
        "question_id": "q1", "question_type": "info-extraction",
        "recall_at_k": True, "accuracy": True, "retrieved_session_ids": ["s1"],
        "reader_text": "yes", "judge_verdict": "CORRECT",
        "input_tokens": 10, "output_tokens": 1, "cost_usd": 0.02,
    }) + "\n")

    entries = [_fake_entry("q1", "info-extraction", "s1"), _fake_entry("q2", "temporal-reasoning", "s2")]
    adapter = _fake_adapter("s2")
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=_fake_reader(),
        judge=_fake_judge("CORRECT"), log_path=log_path, k=5,
    )
    assert len(results) == 2
    # adapter should have been called only for q2 (not q1)
    assert adapter.retrieve.call_count == 1
```

- [ ] **Step 3: Run — expect ImportError**

- [ ] **Step 4: Implement runner**

`benchmarks/src/brain_bench/runners/longmemeval.py`:
```python
"""LongMemEval runner — ingest → retrieve → read → judge → log.

Crash-safe: appends each QuestionResult to a JSONL log immediately.
Re-running reuses the log and skips already-processed questions.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from tqdm import tqdm

from brain_bench.adapters.base import Adapter
from brain_bench.llm.base import LLMClient
from brain_bench.types import DatasetEntry

logger = logging.getLogger(__name__)


READER_SYSTEM = (
    "You are a helpful assistant. Answer the user's question based ONLY on "
    "the conversation excerpts provided. If the answer cannot be found in "
    "the excerpts, say so plainly."
)

JUDGE_SYSTEM = (
    "You are an evaluation judge. Compare the candidate answer to the ground "
    "truth. Respond with exactly CORRECT or INCORRECT on the first line, "
    "optionally followed by a one-line reason."
)


@dataclass
class QuestionResult:
    question_id: str
    question_type: str
    recall_at_k: bool
    accuracy: bool
    retrieved_session_ids: list[str]
    reader_text: str
    judge_verdict: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


def _build_reader_prompt(question: str, memories: list) -> str:
    lines = ["Here are conversation excerpts that may be relevant:\n"]
    for i, m in enumerate(memories, 1):
        lines.append(f"[Excerpt {i}] {m.content}")
    lines.append(f"\nQuestion: {question}")
    return "\n".join(lines)


def _build_judge_prompt(question: str, ground_truth: str, candidate: str) -> str:
    return (
        f"Question: {question}\n"
        f"Ground truth: {ground_truth}\n"
        f"Candidate answer: {candidate}\n\n"
        "Verdict:"
    )


def _load_done_ids(log_path: Path) -> dict[str, dict]:
    if not log_path.exists():
        return {}
    done: dict[str, dict] = {}
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                done[rec["question_id"]] = rec
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed log line: %s", line[:80])
    return done


def _append_log(log_path: Path, result: QuestionResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result)) + "\n")


def run_longmemeval(
    entries: list[DatasetEntry],
    adapter: Adapter,
    reader: LLMClient,
    judge: LLMClient,
    log_path: Path,
    k: int = 5,
) -> list[QuestionResult]:
    """Run the full pipeline, resume-safe via log_path."""
    done = _load_done_ids(log_path)
    results: list[QuestionResult] = []

    for entry in tqdm(entries, desc="LongMemEval"):
        qid = entry.question.question_id
        if qid in done:
            rec = done[qid]
            results.append(QuestionResult(**rec))
            continue

        # Fresh adapter state per question (LongMemEval treats each as isolated)
        adapter.reset()
        for session in entry.sessions:
            adapter.ingest(session)

        # Retrieve
        memories = adapter.retrieve(entry.question.question, k=k)
        retrieved_session_ids = [m.session_id for m in memories if m.session_id]

        # Recall@k: did the answer session make it into the top-k?
        recall_hit = any(
            sid in set(entry.question.answer_session_ids)
            for sid in retrieved_session_ids
        )
        # Abstention questions have no answer session — recall is trivially true
        if not entry.question.answer_session_ids:
            recall_hit = True

        # Read
        reader_call = reader.complete(
            system=READER_SYSTEM,
            user=_build_reader_prompt(entry.question.question, memories),
        )

        # Judge
        judge_call = judge.complete(
            system=JUDGE_SYSTEM,
            user=_build_judge_prompt(
                entry.question.question,
                entry.question.answer,
                reader_call.text,
            ),
        )
        verdict_line = judge_call.text.strip().splitlines()[0].strip().upper() if judge_call.text else ""
        accuracy = verdict_line.startswith("CORRECT")

        result = QuestionResult(
            question_id=qid,
            question_type=entry.question.question_type,
            recall_at_k=recall_hit,
            accuracy=accuracy,
            retrieved_session_ids=retrieved_session_ids,
            reader_text=reader_call.text,
            judge_verdict=judge_call.text,
            input_tokens=reader_call.input_tokens + judge_call.input_tokens,
            output_tokens=reader_call.output_tokens + judge_call.output_tokens,
            cost_usd=reader_call.cost_usd + judge_call.cost_usd,
        )
        _append_log(log_path, result)
        results.append(result)

    return results
```

- [ ] **Step 5: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_runner_longmemeval.py -v
```

- [ ] **Step 6: Commit**

```bash
git add benchmarks/src/brain_bench/runners/ benchmarks/tests/test_runner_longmemeval.py
git commit -m "🧠 Feature: LongMemEval runner (ingest→retrieve→read→judge, resume-safe JSONL log)"
```

---

### Task 12: Metrics aggregator

**Files:**
- Create: `benchmarks/src/brain_bench/metrics.py`
- Create: `benchmarks/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

`benchmarks/tests/test_metrics.py`:
```python
from __future__ import annotations

import pytest

from brain_bench.metrics import aggregate, Summary
from brain_bench.runners.longmemeval import QuestionResult


def _r(qid: str, qtype: str, recall: bool, acc: bool, cost: float = 0.01) -> QuestionResult:
    return QuestionResult(
        question_id=qid, question_type=qtype,
        recall_at_k=recall, accuracy=acc,
        retrieved_session_ids=[], reader_text="", judge_verdict="",
        input_tokens=10, output_tokens=5, cost_usd=cost,
    )


def test_global_accuracy_and_recall():
    results = [
        _r("q1", "info-extraction", True, True),
        _r("q2", "info-extraction", True, False),
        _r("q3", "temporal-reasoning", False, False),
        _r("q4", "temporal-reasoning", True, True),
    ]
    s = aggregate(results)
    assert s.n == 4
    assert s.accuracy == pytest.approx(0.5)
    assert s.recall_at_k == pytest.approx(0.75)


def test_per_category_accuracy():
    results = [
        _r("q1", "info-extraction", True, True),
        _r("q2", "info-extraction", True, True),
        _r("q3", "temporal-reasoning", True, False),
    ]
    s = aggregate(results)
    assert s.per_category["info-extraction"]["accuracy"] == pytest.approx(1.0)
    assert s.per_category["info-extraction"]["n"] == 2
    assert s.per_category["temporal-reasoning"]["accuracy"] == pytest.approx(0.0)


def test_total_cost_sum():
    results = [
        _r("q1", "info-extraction", True, True, cost=0.05),
        _r("q2", "info-extraction", True, True, cost=0.03),
    ]
    s = aggregate(results)
    assert s.total_cost_usd == pytest.approx(0.08)


def test_empty_results_handled():
    s = aggregate([])
    assert s.n == 0
    assert s.accuracy == 0.0
    assert s.recall_at_k == 0.0
    assert s.per_category == {}
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement metrics.py**

`benchmarks/src/brain_bench/metrics.py`:
```python
"""Aggregate per-question results into a Summary."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from brain_bench.runners.longmemeval import QuestionResult


@dataclass
class Summary:
    n: int
    accuracy: float
    recall_at_k: float
    per_category: dict[str, dict[str, float]]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


def aggregate(results: list[QuestionResult]) -> Summary:
    n = len(results)
    if n == 0:
        return Summary(
            n=0, accuracy=0.0, recall_at_k=0.0,
            per_category={}, total_cost_usd=0.0,
            total_input_tokens=0, total_output_tokens=0,
        )

    acc = sum(1 for r in results if r.accuracy) / n
    recall = sum(1 for r in results if r.recall_at_k) / n

    by_cat: dict[str, list[QuestionResult]] = defaultdict(list)
    for r in results:
        by_cat[r.question_type].append(r)

    per_category: dict[str, dict[str, float]] = {}
    for cat, group in by_cat.items():
        per_category[cat] = {
            "n": len(group),
            "accuracy": sum(1 for r in group if r.accuracy) / len(group),
            "recall_at_k": sum(1 for r in group if r.recall_at_k) / len(group),
        }

    return Summary(
        n=n, accuracy=acc, recall_at_k=recall,
        per_category=per_category,
        total_cost_usd=sum(r.cost_usd for r in results),
        total_input_tokens=sum(r.input_tokens for r in results),
        total_output_tokens=sum(r.output_tokens for r in results),
    )
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_metrics.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/metrics.py benchmarks/tests/test_metrics.py
git commit -m "🧠 Feature: metrics aggregator (Summary with per-category breakdown)"
```

---

### Task 13: Report writer

**Files:**
- Create: `benchmarks/src/brain_bench/report.py`
- Create: `benchmarks/tests/test_report.py`

- [ ] **Step 1: Write failing tests**

`benchmarks/tests/test_report.py`:
```python
from __future__ import annotations

from pathlib import Path

from brain_bench.metrics import Summary
from brain_bench.report import append_csv_row, write_markdown_report


def _summary() -> Summary:
    return Summary(
        n=500, accuracy=0.681, recall_at_k=0.742,
        per_category={
            "info-extraction": {"n": 100, "accuracy": 0.85, "recall_at_k": 0.90},
            "temporal-reasoning": {"n": 100, "accuracy": 0.54, "recall_at_k": 0.60},
        },
        total_cost_usd=43.20, total_input_tokens=1_200_000, total_output_tokens=80_000,
    )


def test_write_markdown_report(tmp_path: Path):
    out = tmp_path / "2026-04-20-longmemeval-s-brain.md"
    write_markdown_report(
        out_path=out,
        summary=_summary(),
        benchmark="longmemeval_s",
        adapter="brain",
        reader="claude-opus-4-7",
        judge="claude-opus-4-7",
        commit="abc1234",
        duration_s=8040,
    )
    text = out.read_text()
    assert "LongMemEval-s" in text or "longmemeval_s" in text
    assert "0.681" in text
    assert "0.742" in text
    assert "info-extraction" in text
    assert "abc1234" in text
    assert "43.20" in text or "$43.20" in text


def test_append_csv_row_creates_with_header(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    append_csv_row(
        csv_path=csv_path,
        date="2026-04-20", commit="abc1234",
        benchmark="longmemeval_s", adapter="brain",
        reader="claude-opus-4-7", judge="claude-opus-4-7",
        summary=_summary(), duration_s=8040,
    )
    content = csv_path.read_text()
    assert "date,commit,benchmark,adapter" in content  # header
    assert "0.681" in content


def test_append_csv_row_appends_without_rewriting_header(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    for _ in range(2):
        append_csv_row(
            csv_path=csv_path,
            date="2026-04-20", commit="abc",
            benchmark="longmemeval_s", adapter="brain",
            reader="r", judge="j", summary=_summary(), duration_s=1,
        )
    lines = csv_path.read_text().strip().splitlines()
    assert len(lines) == 3  # 1 header + 2 data rows
```

- [ ] **Step 2: Run — expect ImportError**

- [ ] **Step 3: Implement report.py**

`benchmarks/src/brain_bench/report.py`:
```python
"""Markdown + CSV writers for benchmark results."""
from __future__ import annotations

import csv
from pathlib import Path

from brain_bench.metrics import Summary


CSV_HEADER = [
    "date", "commit", "benchmark", "adapter", "reader", "judge", "n",
    "accuracy", "recall_at_k",
    "acc_info_extraction", "acc_multi_session_reasoning",
    "acc_temporal_reasoning", "acc_knowledge_update", "acc_abstention",
    "cost_usd", "duration_s", "mean_latency_q_s",
    "total_input_tokens", "total_output_tokens",
]


def write_markdown_report(
    out_path: Path,
    summary: Summary,
    benchmark: str,
    adapter: str,
    reader: str,
    judge: str,
    commit: str,
    duration_s: float,
) -> None:
    mean_latency = duration_s / summary.n if summary.n else 0.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {benchmark} — {adapter} — {out_path.stem[:10]}",
        "",
        f"**Config**: reader={reader}, judge={judge}, adapter={adapter}, N={summary.n}",
        f"**Commit**: {commit}",
        f"**Duration**: {duration_s / 60:.1f} min — **Cost**: ${summary.total_cost_usd:.2f} — "
        f"**Mean latency/Q**: {mean_latency:.1f}s",
        "",
        "| Metric              | Score   |",
        "|---------------------|---------|",
        f"| Recall@5            | {summary.recall_at_k:.3f}   |",
        f"| Accuracy (global)   | {summary.accuracy:.3f}   |",
        "",
        "| Category               | Accuracy | Recall@5 | N  |",
        "|------------------------|----------|----------|-----|",
    ]
    for cat, stats in sorted(summary.per_category.items()):
        lines.append(
            f"| {cat:<22} | {stats['accuracy']:.3f}    | "
            f"{stats['recall_at_k']:.3f}    | {int(stats['n']):>3} |"
        )
    lines += [
        "",
        f"**Tokens**: {summary.total_input_tokens:,} input, {summary.total_output_tokens:,} output",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def append_csv_row(
    csv_path: Path,
    date: str,
    commit: str,
    benchmark: str,
    adapter: str,
    reader: str,
    judge: str,
    summary: Summary,
    duration_s: float,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    cats = summary.per_category
    mean_latency = duration_s / summary.n if summary.n else 0.0
    row = {
        "date": date, "commit": commit, "benchmark": benchmark, "adapter": adapter,
        "reader": reader, "judge": judge, "n": summary.n,
        "accuracy": f"{summary.accuracy:.4f}",
        "recall_at_k": f"{summary.recall_at_k:.4f}",
        "acc_info_extraction": f"{cats.get('info-extraction', {}).get('accuracy', 0.0):.4f}",
        "acc_multi_session_reasoning": f"{cats.get('multi-session-reasoning', {}).get('accuracy', 0.0):.4f}",
        "acc_temporal_reasoning": f"{cats.get('temporal-reasoning', {}).get('accuracy', 0.0):.4f}",
        "acc_knowledge_update": f"{cats.get('knowledge-update', {}).get('accuracy', 0.0):.4f}",
        "acc_abstention": f"{cats.get('abstention', {}).get('accuracy', 0.0):.4f}",
        "cost_usd": f"{summary.total_cost_usd:.4f}",
        "duration_s": f"{duration_s:.1f}",
        "mean_latency_q_s": f"{mean_latency:.2f}",
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
    }
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if write_header:
            w.writeheader()
        w.writerow(row)
```

- [ ] **Step 4: Run — expect pass**

```bash
.venv/Scripts/pytest tests/test_report.py -v
```

- [ ] **Step 5: Commit**

```bash
git add benchmarks/src/brain_bench/report.py benchmarks/tests/test_report.py
git commit -m "🧠 Feature: markdown + CSV report writers"
```

---

### Task 14: Setup + run scripts, CLI entry point

**Files:**
- Create: `benchmarks/scripts/setup.sh`
- Create: `benchmarks/scripts/run.sh`
- Modify: `benchmarks/src/brain_bench/runners/longmemeval.py` (add `main()` CLI)

- [ ] **Step 1: Create setup.sh**

`benchmarks/scripts/setup.sh`:
```bash
#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p external

if [ ! -d external/LongMemEval ]; then
    echo "[setup] Cloning LongMemEval..."
    git clone --depth 1 https://github.com/xiaowu0162/LongMemEval external/LongMemEval
else
    echo "[setup] LongMemEval already cloned"
fi

if command -v ollama >/dev/null 2>&1; then
    echo "[setup] Pulling Ollama model (llama3.1:70b — takes time, ~40 GB)..."
    ollama pull llama3.1:70b || echo "[setup] Ollama pull failed — you may want a smaller model"
else
    echo "[setup] Ollama not installed. For dev loop, install from https://ollama.com"
fi

echo "[setup] Done. Next: python -m brain_bench.runners.longmemeval --config config/dev.yaml"
```

- [ ] **Step 2: Create run.sh**

`benchmarks/scripts/run.sh`:
```bash
#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG="${1:-config/dev.yaml}"

BRAIN_URL=$(python -c "
import yaml, sys
print(yaml.safe_load(open('$CONFIG'))['brain_url'])
")

echo "[run] Checking Brain at $BRAIN_URL/health..."
if ! curl -sf "$BRAIN_URL/health" > /dev/null; then
    echo "[run] Brain not reachable. Start it: docker compose -f ../docker/compose.yml up -d"
    exit 1
fi

echo "[run] Running benchmark with $CONFIG..."
python -m brain_bench.runners.longmemeval --config "$CONFIG"
```

- [ ] **Step 3: Add `main()` CLI to runner**

Append to `benchmarks/src/brain_bench/runners/longmemeval.py`:
```python


def _make_adapter(cfg):
    if cfg.adapter == "brain":
        from brain_bench.adapters.brain import BrainAdapter
        return BrainAdapter(brain_url=cfg.brain_url)
    if cfg.adapter == "chromadb_raw":
        from brain_bench.adapters.chromadb_raw import ChromaDBRawAdapter
        return ChromaDBRawAdapter(persist_dir=cfg.chromadb_raw_persist_dir)
    raise ValueError(f"Unknown adapter: {cfg.adapter}")


def _make_llm(llm_cfg):
    if llm_cfg.provider == "ollama":
        from brain_bench.llm.ollama import OllamaClient
        return OllamaClient(model=llm_cfg.model)
    if llm_cfg.provider == "anthropic":
        from brain_bench.llm.anthropic import AnthropicClient
        return AnthropicClient(model=llm_cfg.model)
    raise ValueError(f"Unknown provider: {llm_cfg.provider}")


def main() -> None:
    import argparse
    import subprocess
    import time
    from datetime import datetime, timezone

    from brain_bench.config import load_config
    from brain_bench.datasets.longmemeval import load_longmemeval_s
    from brain_bench.metrics import aggregate
    from brain_bench.report import append_csv_row, write_markdown_report

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--adapter", default=None,
                        help="Override adapter from config (brain | chromadb_raw)")
    parser.add_argument("--dataset-path", default=None, type=Path,
                        help="Override dataset path (default: benchmarks/external/LongMemEval/...)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run but do not write to output_dir")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.adapter:
        # override at runtime
        from dataclasses import replace
        cfg = replace(cfg, adapter=args.adapter)

    dataset_path = args.dataset_path or (
        Path("external/LongMemEval/data/longmemeval_s.json")
    )
    entries = load_longmemeval_s(dataset_path, subset=cfg.subset, seed=cfg.seed)

    adapter = _make_adapter(cfg)
    reader = _make_llm(cfg.reader)
    judge = _make_llm(cfg.judge)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    log_path = runs_dir / f"{timestamp}_{cfg.adapter}.jsonl"

    t0 = time.monotonic()
    results = run_longmemeval(
        entries=entries, adapter=adapter, reader=reader, judge=judge,
        log_path=log_path, k=5,
    )
    duration = time.monotonic() - t0
    summary = aggregate(results)

    print(f"\n=== {cfg.adapter} on {len(entries)} Q ===")
    print(f"Accuracy: {summary.accuracy:.3f}")
    print(f"Recall@5: {summary.recall_at_k:.3f}")
    print(f"Cost: ${summary.total_cost_usd:.2f}")
    print(f"Duration: {duration / 60:.1f} min")

    if args.dry_run or cfg.dry_run:
        print("[dry-run] Not writing report.")
        return

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=False,
    ).stdout.strip() or "unknown"

    out_dir = Path(cfg.output_dir)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_path = out_dir / f"{date}-{cfg.dataset}-{cfg.adapter}.md"
    write_markdown_report(
        out_path=md_path, summary=summary,
        benchmark=cfg.dataset, adapter=cfg.adapter,
        reader=cfg.reader.model, judge=cfg.judge.model,
        commit=commit, duration_s=duration,
    )
    csv_path = out_dir / "results.csv"
    append_csv_row(
        csv_path=csv_path, date=date, commit=commit,
        benchmark=cfg.dataset, adapter=cfg.adapter,
        reader=cfg.reader.model, judge=cfg.judge.model,
        summary=summary, duration_s=duration,
    )
    print(f"Report: {md_path}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: chmod +x scripts**

```bash
chmod +x benchmarks/scripts/setup.sh benchmarks/scripts/run.sh
```

- [ ] **Step 5: Run existing tests to make sure nothing broke**

```bash
cd benchmarks
.venv/Scripts/pytest -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add benchmarks/scripts/ benchmarks/src/brain_bench/runners/longmemeval.py
git commit -m "🧠 Feature: scripts (setup, run) + CLI entry point for runner"
```

---

### Task 15: End-to-end integration test (3 Q, mocked LLMs)

**Files:**
- Create: `benchmarks/tests/test_e2e.py`

- [ ] **Step 1: Write the test**

`benchmarks/tests/test_e2e.py`:
```python
"""End-to-end test: run the pipeline on the mini fixture with mocked LLMs.

This does NOT require Brain running or Ollama installed — it wires the real
adapter (ChromaDBRawAdapter with a tmp persist dir) with fake LLMs, to prove
the full pipeline produces a valid report.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brain_bench.adapters.chromadb_raw import ChromaDBRawAdapter
from brain_bench.datasets.longmemeval import load_longmemeval_s
from brain_bench.llm.base import LLMCall
from brain_bench.metrics import aggregate
from brain_bench.report import append_csv_row, write_markdown_report
from brain_bench.runners.longmemeval import run_longmemeval


FIXTURE = Path(__file__).parent / "fixtures" / "longmemeval_mini.json"


def _reader():
    r = MagicMock()
    r.complete.return_value = LLMCall(text="my answer", input_tokens=50, output_tokens=5, cost_usd=0.001)
    return r


def _judge():
    j = MagicMock()
    j.complete.return_value = LLMCall(text="CORRECT", input_tokens=20, output_tokens=2, cost_usd=0.0005)
    return j


def test_e2e_pipeline_produces_report(tmp_path: Path):
    entries = load_longmemeval_s(FIXTURE)
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chroma")
    log_path = tmp_path / "run.jsonl"

    results = run_longmemeval(
        entries=entries, adapter=adapter,
        reader=_reader(), judge=_judge(),
        log_path=log_path, k=5,
    )
    assert len(results) == 5

    summary = aggregate(results)
    assert summary.n == 5
    # All judges returned CORRECT → accuracy = 1.0
    assert summary.accuracy == pytest.approx(1.0)

    # Writing the report should not crash
    md = tmp_path / "report.md"
    write_markdown_report(
        out_path=md, summary=summary,
        benchmark="longmemeval_s", adapter="chromadb_raw",
        reader="mock", judge="mock", commit="test", duration_s=10,
    )
    assert "1.000" in md.read_text()

    csv = tmp_path / "results.csv"
    append_csv_row(
        csv_path=csv, date="2026-04-20", commit="test",
        benchmark="longmemeval_s", adapter="chromadb_raw",
        reader="mock", judge="mock", summary=summary, duration_s=10,
    )
    assert csv.exists()
    assert len(csv.read_text().strip().splitlines()) == 2  # header + 1 row


def test_e2e_resume_skips_done(tmp_path: Path):
    entries = load_longmemeval_s(FIXTURE, subset=3, seed=42)
    adapter = ChromaDBRawAdapter(persist_dir=tmp_path / "chroma")
    log_path = tmp_path / "run.jsonl"

    run_longmemeval(
        entries=entries, adapter=adapter,
        reader=_reader(), judge=_judge(),
        log_path=log_path, k=5,
    )
    call_count_after_first = _reader().complete.call_count  # new mock, 0

    # Second invocation: log exists, should skip all
    spy_reader = _reader()
    run_longmemeval(
        entries=entries, adapter=adapter,
        reader=spy_reader, judge=_judge(),
        log_path=log_path, k=5,
    )
    # Reader should not be called on resume
    assert spy_reader.complete.call_count == 0
```

- [ ] **Step 2: Run — expect pass**

```bash
cd benchmarks
.venv/Scripts/pytest tests/test_e2e.py -v
```

- [ ] **Step 3: Run full suite to confirm nothing broke**

```bash
.venv/Scripts/pytest -v
```
Expected: all pass (including the original 143 backend tests when run from `backend/`).

- [ ] **Step 4: Commit**

```bash
git add benchmarks/tests/test_e2e.py
git commit -m "🧪 Test: E2E pipeline (fixture → runner → aggregate → report)"
```

---

### Task 16: Docs — benchmarks/README + docs/benchmarks/README

**Files:**
- Modify: `benchmarks/README.md` (expand with full command reference)
- Create: `docs/benchmarks/README.md`

- [ ] **Step 1: Expand benchmarks/README.md**

Replace the content of `benchmarks/README.md` (from Task 1) with:
```markdown
# Brain Benchmarks

Harness for running Brain against LongMemEval-s (phase 5a) and a custom
Brain-Bench (phase 5b, TBD). See
[`docs/specs/2026-04-17-benchmarks-design.md`](../docs/specs/2026-04-17-benchmarks-design.md)
for the full design.

## One-time setup

```bash
cd benchmarks
uv venv
.venv/Scripts/pip install -e ".[dev]"
bash scripts/setup.sh            # clones LongMemEval into external/, pulls Ollama model
```

## Dev run (free, Ollama, 50 Q)

Ensure Brain is running:
```bash
docker compose -f ../docker/compose.yml up -d
curl http://localhost:8621/health   # should be {"status":"ok",...}
```

Then:
```bash
python -m brain_bench.runners.longmemeval --config config/dev.yaml
```
Output goes to `runs/YYYY-MM-DD_HH-MM_brain.jsonl` (NOT committed).

## Release run (Claude, full 500 Q, ~$20-50)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m brain_bench.runners.longmemeval --config config/release.yaml --adapter brain
python -m brain_bench.runners.longmemeval --config config/release.yaml --adapter chromadb_raw
```
Output goes to `../docs/benchmarks/<date>-longmemeval_s-<adapter>.md` and
appends a row to `../docs/benchmarks/results.csv`.

## Resume after crash

If a run dies mid-way, just re-run the same command. The JSONL log in `runs/`
holds the already-processed Q's; they'll be skipped.

## Tests

```bash
.venv/Scripts/pytest -v
```

## Layout

See [`docs/specs/2026-04-17-benchmarks-design.md §3`](../docs/specs/2026-04-17-benchmarks-design.md).
```

- [ ] **Step 2: Create docs/benchmarks/README.md**

`docs/benchmarks/README.md`:
```markdown
# Brain Benchmark Results

Each published run lives in a dated `YYYY-MM-DD-<benchmark>-<adapter>.md`
file. `results.csv` is the append-only machine-readable log (one row per
run). To produce a run, see `benchmarks/README.md`.

## Latest scores

_(populated automatically by release runs — see CSV for the authoritative history)_

## Interpreting the ablation

Every release publishes **two runs**: `brain` (full) and `chromadb_raw`
(bare ChromaDB baseline). The delta between them is what Brain's structure
adds on top of the embedding model.

- If `brain` ≫ `chromadb_raw`: the gate, graph, and composite scoring help.
- If `brain` ≈ `chromadb_raw`: the embedding is doing all the work. Signal
  to revisit the design — **not** to hide the score.

## Reader/judge note

Scores are produced with Claude Opus 4.7 as both reader and judge.
Published-literature scores for mem0 (49%), Zep (63.8%) and MemPalace (96.6%)
use GPT-4o. Absolute numbers are NOT directly comparable across judges. When
we want to compare, we re-run the comparator with our Claude config.

## Files

- `results.csv` — append-only, machine-readable
- `YYYY-MM-DD-<benchmark>-<adapter>.md` — human-readable report per run
```

- [ ] **Step 3: Commit**

```bash
git add benchmarks/README.md docs/benchmarks/README.md
git commit -m "📓 Docs: benchmarks README (dev + release instructions, how to read results)"
```

---

### Task 17: Phase 5b placeholder task

**Files:**
- Create: `docs/plans/2026-04-17-brain-bench-placeholder.md`

- [ ] **Step 1: Write placeholder plan**

`docs/plans/2026-04-17-brain-bench-placeholder.md`:
```markdown
# Brain-Bench (phase 5b) — placeholder

> **Status**: not scheduled. Unblocks after phase 5a lands and produces a
> credible LongMemEval-s score. Detailed plan will be written then via
> `superpowers:writing-plans`.

## Pre-requisites before detailing

- [ ] Phase 5a published: at least one release run with Brain full + ChromaDB
      raw ablation in `docs/benchmarks/`
- [ ] Decision: which Money sessions to use (30-day window, specific branches)
- [ ] Decision: QA authoring workflow — who writes, how we prevent bias
      (user writes the QA AND runs Brain → review needed)

## What it will contain (sketch only)

- Dataset curation workflow: transcripts → JSONL with `{question, ground_truth, expected_sources, category}`
- `benchmarks/src/brain_bench/runners/brain_bench.py` — same shape as LongMemEval runner, different dataset loader and metrics
- 30-50 hand-authored QA in `benchmarks/datasets/brain_bench_v1.jsonl` (committed to the repo)
- A separate `config/brain_bench_dev.yaml` + `config/brain_bench_release.yaml`
- Published report in `docs/benchmarks/YYYY-MM-DD-brain_bench-<adapter>.md`

## Non-goals (carried forward)

- No Marcel data yet (phase 5c)
- No synthetic QA generation (phase 5c)
- No auto-extraction of QA from transcripts

## Reference

See `docs/specs/2026-04-17-benchmarks-design.md §6`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-04-17-brain-bench-placeholder.md
git commit -m "📓 Docs: Brain-Bench (phase 5b) placeholder plan"
```

---

## Self-review checklist

- [x] Spec §1 (context) → covered by README + plan goal
- [x] Spec §2 (decisions 1-10) → all 10 locked in config YAMLs + code
- [x] Spec §3 (architecture) → file structure matches spec §3 exactly
- [x] Spec §4 (pipeline) → Task 11 implements ingest→retrieve→read→judge with resume
- [x] Spec §5.1 (markdown report) → Task 13 + test asserts metrics render
- [x] Spec §5.2 (CSV) → Task 13 `append_csv_row`, header written once, appended rows
- [x] Spec §5.3 (README table) → Task 16 `docs/benchmarks/README.md`
- [x] Spec §6 (Brain-Bench) → Task 17 placeholder plan
- [x] Spec §7 (non-goals) → respected (no CI, no frontend, no auto-QA)
- [x] Spec §8 (success criteria 1-7) → tasks 1-16 map 1:1 to criteria 1-5; criteria 6-7 are runtime outcomes
- [x] Spec §9 (risks) → mitigations wired: gitignored external/, scripts/setup.sh, dry_run flag, resume-safe log, PRICING table in AnthropicClient

**Type consistency check:**
- `Adapter.reset / ingest / retrieve` — consistent across brain.py, chromadb_raw.py, tests
- `LLMClient.complete(system, user) -> LLMCall` — consistent across ollama.py, anthropic.py
- `QuestionResult` fields — same in runner, metrics, report
- `Summary` fields — same in metrics, report
- Config field names — same across dev.yaml, release.yaml, Config dataclass

**Placeholder scan:**
- No TBD / TODO / "implement later" in code steps
- Template markdown in Task 13 test uses illustrative values (0.681, 0.742) — explicitly labelled in the test, not in code
- Task 17 is a *deliberate* placeholder (the spec marks phase 5b as deferred)

**No leftover ambiguity.**
