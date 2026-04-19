# Plans

Implementation plans derived from approved specs. Each plan is the output of the `writing-plans` skill and the input of `subagent-driven-development` or `executing-plans`.

## What goes here

- **Task-by-task breakdown** with exact file paths, code blocks, TDD steps, commit messages
- **Dependency graphs** and parallelizable batches
- **Acceptance criteria** per task

## What does NOT go here

- **Design rationale** → [`../specs/`](../specs/)
- **Ongoing status** — use GitHub issues and `git log`, plans are snapshots

## Naming

`YYYY-MM-DD-<topic>-implementation.md` — dated at creation, never renamed. Placeholder plans use `-placeholder` suffix.

## Append-only

Plans are historical records of what was intended. Do NOT edit a merged plan when scope changes. Open an issue, open a new plan dated to the change, reference the superseded plan.

## Index

- [`2026-04-17-benchmarks-implementation.md`](2026-04-17-benchmarks-implementation.md) — phase 5a LongMemEval MVP (17 tasks, 8 batches)
- [`2026-04-17-brain-bench-placeholder.md`](2026-04-17-brain-bench-placeholder.md) — phase 5b Brain-Bench custom placeholder
