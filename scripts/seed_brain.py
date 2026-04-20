"""One-off bootstrap — store initial identity/preference memories for dogfood.

Run once after the hook endpoints are live and before the first dogfood session.

**Not idempotent** — the current gate only dedupes `event_type="error"` memories,
so re-running this script duplicates every seed. Before re-running (e.g. after a
schema change or a Brain wipe), first clear the agent scope:

    curl -X POST http://localhost:8621/reset \\
         -H 'Content-Type: application/json' \\
         -d '{"agent":"brain"}'

Content-hash dedup for context memories is tracked as a follow-up improvement.
"""
from __future__ import annotations

import os
import sys

import httpx

BRAIN_URL = os.environ.get("BRAIN_URL", "http://localhost:8621")
AGENT = os.environ.get("BRAIN_SEED_AGENT", "brain")

SEEDS: list[dict] = [
    # Identity
    {"content": "User is Arthur (arthurolivier.fortin@gmail.com), building Brain as a drop-in memory system for LLM agents.",
     "type": "context", "tags": ["identity", "persona"]},
    {"content": "Communicate in French by default. Technical terms stay English when clearer.",
     "type": "context", "tags": ["identity", "communication"]},
    {"content": "Blunt, no glazing, no trailing summaries. This is infrastructure — ambiguity costs time.",
     "type": "context", "tags": ["identity", "communication"]},

    # Preferences
    {"content": "Commit emoji convention: 🧠 Feature / 🩹 Fix / 📓 Docs / 🧹 Chore / 🧪 Test / 🧬 Refactor. Always include Co-Authored-By trailer.",
     "type": "context", "tags": ["preference", "git"]},
    {"content": "Docker safety: never --remove-orphans without audit, always explicit `name:` in compose.yml. Incident 2026-04-17 deleted Money containers.",
     "type": "context", "tags": ["preference", "docker", "safety"]},
    {"content": "Issue-first workflow: every non-trivial change gets a GitHub issue before code. PRs reference Closes #N.",
     "type": "context", "tags": ["preference", "workflow"]},
    {"content": "No `--no-verify` on git operations without explicit user approval.",
     "type": "context", "tags": ["preference", "git", "safety"]},
    {"content": "Doc structure: every doc lives under docs/ in a disciplined subfolder (architecture, research, specs, plans, runbooks, benchmarks, improvements, decisions). Specs and plans are append-only.",
     "type": "context", "tags": ["preference", "docs"]},
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    seeded = 0
    for seed in SEEDS:
        payload = {
            "content": seed["content"],
            "agent": AGENT,
            "memory_type": seed["type"],
            "metadata": {"tags": ",".join(seed["tags"])},
            "skip_gate": False,
        }
        try:
            resp = httpx.post(f"{BRAIN_URL}/store", json=payload, timeout=30.0)
            resp.raise_for_status()
            body = resp.json()
            if body.get("stored"):
                seeded += 1
                print(f"[seeded] {seed['tags']} — {seed['content'][:60]}...")
            else:
                print(f"[skipped] {seed['content'][:60]}... reason={body.get('reason', 'unknown')}")
        except Exception as e:
            print(f"[error] {e}")
    print(f"\nTotal seeded: {seeded}/{len(SEEDS)}")


if __name__ == "__main__":
    main()
