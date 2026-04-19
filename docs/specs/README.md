# Specs

Design documents approved before implementation. Each spec is the output of the `brainstorming` skill and the input of the `writing-plans` skill.

## What goes here

- **Feature designs** — what we're building, why, trade-offs considered, non-goals
- **Decisions locked** — every spec ends with a "decisions" section the plan can trust

## What does NOT go here

- **Implementation steps** → [`../plans/`](../plans/)
- **Architecture diagrams** → [`../architecture/`](../architecture/)
- **ADRs** (shorter, focused on a single decision) → [`../decisions/`](../decisions/)

## Naming

`YYYY-MM-DD-<topic>-design.md` — dated at creation, never renamed.

## Append-only

Specs are historical records of what was approved at a moment in time. Do NOT edit a merged spec. If the design evolves, write a new dated spec and cross-link via an ADR that captures the delta.

## Index

- [`2026-04-17-benchmarks-design.md`](2026-04-17-benchmarks-design.md) — LongMemEval + Brain-Bench harness design (phase 5a + 5b placeholder)
