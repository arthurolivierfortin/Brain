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
