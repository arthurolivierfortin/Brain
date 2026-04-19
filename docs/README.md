# Brain — Documentation Index

Every doc file lives under a subfolder. Nothing at this root except this index.

## Layout

| Folder | Purpose | Naming |
|--------|---------|--------|
| [`architecture/`](architecture/) | Durable design — system shape, modules, data flow, port map | `<topic>.md` |
| [`research/`](research/) | Competitive analysis, external benchmark studies, literature | `<topic>.md` |
| [`specs/`](specs/) | Brainstorming outputs — design specs approved before implementation | `YYYY-MM-DD-<topic>-design.md` |
| [`plans/`](plans/) | Implementation plans derived from specs | `YYYY-MM-DD-<topic>-implementation.md` |
| [`runbooks/`](runbooks/) | Operational — "how to start Brain", "how to run a bench", troubleshooting | `<action>.md` |
| [`benchmarks/`](benchmarks/) | Published run reports + `results.csv` | `YYYY-MM-DD-<benchmark>-<adapter>.md` |
| [`improvements/`](improvements/) | Tracked technical debt, one file per item when it grows | `<slug>.md` or inline in `README.md` |
| [`decisions/`](decisions/) | ADRs — why we chose X over Y | `NNNN-<slug>.md` |

## Rules (mirrored from CLAUDE.md)

- **Issue-first**: every non-trivial change has a GitHub issue before code. PRs reference `Closes #N` / `Refs #N`.
- **Doc-freshness**: every PR that changes observable behavior MUST update the relevant doc(s). Reviewer blocks the merge otherwise.
- **Specs and plans are append-only**. Don't edit merged specs — write a new dated spec. Issues/ADRs link the delta.
- **ADRs** are numbered (`0001`, `0002`, …) and never renumbered. Supersede by writing a new ADR.
- **No docs at this root** except this `README.md`.

## Where to look first

- **New to the project?** → start at repo `README.md`, then `CLAUDE.md`, then [`research/memory-systems.md`](research/memory-systems.md)
- **Want to understand a decision?** → [`decisions/`](decisions/)
- **Want to run a bench?** → [`runbooks/`](runbooks/) (TBD) then `benchmarks/README.md` at repo root
- **Want to see known issues / debt?** → [`improvements/`](improvements/)
