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
