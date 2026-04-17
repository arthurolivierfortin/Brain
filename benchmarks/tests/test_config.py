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
    assert isinstance(cfg, Config)
    assert isinstance(cfg.reader, LLMConfig)


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
    assert isinstance(cfg, Config)


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
