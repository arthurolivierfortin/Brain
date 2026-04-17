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
