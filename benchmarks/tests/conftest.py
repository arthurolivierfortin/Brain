"""Pytest fixtures shared across brain_bench tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def tmp_persist_dir(tmp_path):
    """Temp ChromaDB persist dir per test."""
    return tmp_path / "chromadb"
