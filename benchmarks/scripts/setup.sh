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
