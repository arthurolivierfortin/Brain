#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG="${1:-config/dev.yaml}"

BRAIN_URL=$(python -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]))['brain_url'])" "$CONFIG")

echo "[run] Checking Brain at $BRAIN_URL/health..."
if ! curl -sf "$BRAIN_URL/health" > /dev/null; then
    echo "[run] Brain not reachable. Start it: docker compose -f ../docker/compose.yml up -d"
    exit 1
fi

echo "[run] Running benchmark with $CONFIG..."
python -m brain_bench.runners.longmemeval --config "$CONFIG"
