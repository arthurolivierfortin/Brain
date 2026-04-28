# L2-B Adapter — SessionStart hook enrichment — Design

**Goal:** Enrich the `scripts/brain_wake_up.py` payload with `git_recent_commits`, `git_branch`, `claude_md_excerpt` so the L2-A backend can compute topic-triggered semantic retrieval (L2 layer).
**Roadmap phase:** R:phase-2b (extends Phase 2b hook architecture work)
**Blocked-by:** L2-A backend PR (`docs/specs/2026-04-28-l2-a-backend-design.md`). L2-A ships first; backend is backward-compatible — when L2-B lands, L2 begins firing in practice.

**Scope (in):**
- Modify `scripts/brain_wake_up.py` to detect a git repo, collect git metadata, read CLAUDE.md, and POST these 3 new optional fields alongside the existing `agent`/`project`/`session_id`.
- Each collection step is best-effort and silent on failure (the SessionStart stdout contract is preserved unchanged — script exits 0 with empty `additionalContext` on full failure path, exactly as today).
- Adapter unit + integration tests in `scripts/tests/test_brain_wake_up_l2.py` (subprocess-driven integration tests with a temp git repo fixture, plus mocked-httpx unit tests for payload shape).

**Scope (out — explicit YAGNI):**
- Backend changes (owned by L2-A; this PR depends on L2-A having shipped the new optional fields).
- Adapter behavior on non-Claude-Code IDEs (Cursor, Codex) — Phase 2b out-of-scope.
- Caching of git output between sessions (wake_up fires once per session, not worth the cache).
- Multi-language CLAUDE.md handling (UTF-8 only assumption per brainstorm).
- Cross-platform git-binary nuances — relies on `git` in PATH (already required by Brain dev workflow).
- Pre-`git rev-parse` shortcut to skip subprocess if `.git` directory absent — `git rev-parse --show-toplevel` itself returns non-zero quickly enough; no premature optimization.

**Constraints:**
- **stdin/stdout contract is sacred.** The script reads CC's SessionStart JSON from stdin and writes CC's `hookSpecificOutput` JSON to stdout. The L2-B changes only enrich the POST body sent to Brain — they MUST NOT change stdin parsing, stdout shape, or the script exit code (always 0, fail-silent).
- **Failure is silent.** Any of: git not in PATH, cwd not a git repo, CLAUDE.md absent, file unreadable, subprocess timeout — the corresponding field is omitted from the payload. The script still completes its existing duty (calls `/hook/wake_up`, writes additionalContext to stdout).
- **Cascade per Q5 of brainstorm:** if all 3 enrichment fields are absent, backend logs `degraded_wake_up` with `reason: empty_topic_query` (already the L2-A handler's responsibility — adapter just sends fewer/no enrichment fields).
- **Performance:** total wake_up budget stays <500ms. Existing `httpx.post` timeout is 0.5s. New subprocess + filesystem work must not push the script past ~200ms wall-clock. Each `git` subprocess gets a 1.0s timeout (defensive — typically <50ms locally; if `git` hangs we want to drop the field, not block CC startup).
- **Truncation limits (locked in brainstorm Q2):** `git_recent_commits` truncated to 600 chars (UTF-8 byte-safe truncation — drop trailing partial lines), `claude_md_excerpt` truncated to 1000 chars (read first 1000 chars of file, no scanning past).
- **No backwards-compat shim:** the only adapter change is additive. Old behavior (before L2-A backend ships) means new fields are sent and ignored by old backend (HTTP norm — backend `data.get(...)` already shapes this). After L2-A ships, fields are consumed.

## Architecture

### Components and data flow

```
Claude Code SessionStart hook fires
│
└─ scripts/brain_wake_up.py.main(stdin_data=<CC JSON>)
   ├─ existing: parse stdin, derive agent, get cwd/session_id
   ├─ NEW: enrichment = _collect_topic_enrichment(cwd)
   │       returns {git_recent_commits?, git_branch?, claude_md_excerpt?}
   │       — every field optional; missing fields simply omitted from dict
   │       — total wall-clock budget ~150ms; each subprocess call 1s timeout
   ├─ POST /hook/wake_up with body = {agent, project, session_id, **enrichment}
   ├─ existing: parse response.context, write CC SessionStart contract to stdout
   └─ existing: any unhandled exception → _write_empty() + return 0
```

### New helpers (private, in same module)

All helpers live inside `scripts/brain_wake_up.py` to avoid creating a `scripts/brain_lib/` package for a single consumer. They are private (`_` prefix) and unit-testable.

- `_collect_topic_enrichment(cwd: str) -> dict[str, str]` — orchestrator. Calls each `_collect_*` helper, includes only non-empty results in returned dict. Catches all exceptions per call site so a single failure doesn't poison the others.
- `_git_root(cwd: str) -> str | None` — runs `git -C <cwd> rev-parse --show-toplevel`, returns stdout stripped, or `None` on any non-zero exit / timeout / `FileNotFoundError`.
- `_collect_git_branch(git_root: str) -> str | None` — runs `git -C <git_root> rev-parse --abbrev-ref HEAD`. Strips. Returns `None` on detached HEAD (`HEAD` literal output is treated as a valid branch name only if non-empty; we treat the literal `"HEAD"` as no-branch and return `None`). Returns `None` on any failure.
- `_collect_git_log(git_root: str) -> str | None` — runs `git -C <git_root> log --oneline -10`. Captures stdout. If the result exceeds 600 bytes (UTF-8), truncates at the last newline boundary that keeps the result ≤600 bytes (no partial line at the tail). Returns `None` on failure or empty output (empty repo with no commits).
- `_collect_claude_md(cwd: str, git_root: str | None) -> str | None` — looks for `<cwd>/CLAUDE.md` first; if absent and `git_root` differs from cwd, looks at `<git_root>/CLAUDE.md`. Reads first 1000 chars (`Path.read_text(encoding="utf-8")[:1000]`). Returns the substring, or `None` on missing file / read error / empty file.

### Subprocess hardening

```python
import subprocess
def _run_git(args: list[str], cwd: str | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
```

`check=False` because we handle non-zero ourselves (silent fallback). `text=True` handles encoding via the platform default — adequate for git output (ASCII commit subjects on this project; non-ASCII tolerated via Python 3 utf-8 default decode).

### Where this lives

Single file: `scripts/brain_wake_up.py`. New tests in `scripts/tests/test_brain_wake_up_l2.py` (separate file from existing `test_brain_wake_up.py` to keep concern isolation; existing tests stay untouched and must still pass).

## Affected systems

- **HTTP API:** sends 3 new optional body fields (`git_recent_commits`, `git_branch`, `claude_md_excerpt`) on POST `/hook/wake_up`. No new endpoints. Backend route already accepts these per L2-A.
- **MCP tools:** unchanged.
- **Storage:** unchanged.
- **Frontend:** unchanged.
- **Installer (`npx brain`):** unchanged. The script is bundled as-is.
- **Scripts (Claude Code hooks):** `brain_wake_up.py` modified; `brain_post_turn.py`, `brain_statusline.py`, `brain_save_now.py` unchanged.
- **Benchmarks:** no direct impact. Once both L2-A and L2-B are merged, LongMemEval session-aware questions may improve via topic-triggered retrieval — measured separately in a future bench cycle.
- **Tests:** new `scripts/tests/test_brain_wake_up_l2.py`. Run via `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/ -q` (existing convention — see `docs/runbooks/phase2b-dogfood.md` line 21 and `docs/plans/2026-04-19-hook-architecture-implementation.md` line 1408+).

## Open question resolution (from brainstorm)

**Brainstorm Q4: "Adapter PR (L2-B) test infrastructure — `scripts/tests/` exists but uses different test runner than `backend/tests/`?"**

Resolved by reading `scripts/tests/conftest.py` and existing tests:
- `scripts/tests/conftest.py` simply prepends `scripts/` to `sys.path` so test files can `import brain_wake_up`. No separate pytest config, no new venv.
- Tests are run with the **backend's pytest installation** invoked from the repo root: `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/ -q`. This is documented in `docs/runbooks/phase2b-dogfood.md` and used throughout `docs/plans/2026-04-19-hook-architecture-implementation.md`.
- `backend/pyproject.toml` has `[tool.pytest.ini_options].testpaths = ["tests"]` — meaning if you run `pytest` from `backend/`, scripts tests are NOT picked up. They are run as a separate explicit invocation. **This is intentional** — backend tests run hot in CI (or via `cd backend && pytest`), scripts tests are a parallel suite gated separately.

**Implication for [GATE-2]:** We add an EXPLICIT scripts-pytest gate alongside the backend-pytest gate. The builder/judge run BOTH:
1. `cd backend && python -m pytest -q` (must keep passing — no regressions, even though L2-B doesn't touch backend)
2. `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/ -q` (the new tests live here)

**Implication for [GATE-1]:** `backend/pyproject.toml` `[tool.ruff].src = ["src", "tests"]` — running `cd backend && ruff check .` lints only backend Python. `scripts/` is NOT covered by that gate. The L2-B PR explicitly invokes `cd C:/Brain && backend/.venv/Scripts/python -m ruff check scripts/` to lint the changed adapter. Scripts use the same ruff version (the dev extra in `backend/pyproject.toml` is what gets installed). If the existing `scripts/brain_wake_up.py` has any latent lint warnings, surface them in the PR but don't fix as drive-by (CLAUDE.md rule 3: "no features outside the task").

**Brainstorm Q2 (formatting): "Exact `_build_topic_query` concatenation format"** — that question lives in L2-A spec, not L2-B. L2-B simply ships fields as raw strings.

## Risks

1. **`git` not in PATH on a user's machine.** Cascade handles it (subprocess raises `FileNotFoundError`, helper returns `None`, field omitted, payload still sent). No regression because previous adapter never depended on git either. Backend logs `degraded_wake_up` with `reason: empty_topic_query` if all fields end up missing — surfaces in the monitor.
2. **CLAUDE.md doesn't exist** in some projects. By design — fallback to git-only. No event because Q5 cascade explicitly says "this is the silent path; degraded only when ALL signals absent."
3. **CLAUDE.md is huge** (e.g. 50KB). The `read_text` reads the entire file. Mitigation: truncate to 1000 chars in memory after read. For a sane upper bound on file size (avoid pathological multi-MB CLAUDE.md), we open with `Path.open()` and read only `read(1024 * 16)` bytes (16KB cap), then decode and slice to 1000 chars. If decode fails (binary blob mistakenly named CLAUDE.md), return `None`.
4. **Subprocess hang.** 1s timeout per git call. Worst case: 2s wasted (branch + log) before falling back. Acceptable — CC SessionStart already tolerates Brain being unreachable for 0.5s.
5. **stdout contract regression.** Tests cover this — at least one integration test runs the full subprocess pipeline and asserts the exact stdout JSON shape is unchanged.
6. **Detached HEAD in git_branch.** `git rev-parse --abbrev-ref HEAD` returns the literal string `"HEAD"` when in detached state. We treat that as no-branch (return `None`). Builder must verify this in test [TEST-3].
7. **CRLF on Windows.** `subprocess.run(..., text=True)` does universal newline conversion in Python 3 — git output ends up with `\n` regardless of platform. `.strip()` handles trailing whitespace. No special handling needed.

## Consumer impact

- **Money:** unchanged. Money's legacy Brain at `localhost:8611` is a separate codebase; this adapter calls `localhost:8621` (Brain standalone).
- **Marcel:** not yet a consumer.
- **Future consumers:** the new payload fields are optional. Any downstream replay/rerun of wake_up logs will see them as additional context, ignored if unrecognized.
- **Backend (L2-A):** consumes the new fields. If L2-B ships before L2-A (shouldn't, per phasing), backend silently drops the unknown keys — `data.get("git_recent_commits", "")` semantics. So order isn't strictly required, but sequence L2-A → L2-B is the planned path and yields zero "fields-sent-but-not-yet-used" sessions.
