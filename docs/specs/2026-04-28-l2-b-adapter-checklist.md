# Checklist — L2-B Adapter (SessionStart hook enrichment)

**Linked spec:** [2026-04-28-l2-b-adapter-design.md](2026-04-28-l2-b-adapter-design.md)

**Budget:** 0.5 day. **Roadmap phase:** R:phase-2b. **Blocked-by:** L2-A backend PR merged.

**Commit emoji convention** (per CLAUDE.md): `🧠 Feature` for [SPEC-1] through [SPEC-5] (new code), `🧪 Test` for [TEST-1] through [TEST-7] (test-only commits if they land separately; usually grouped by [SPEC-N] in a single commit).

## Code

- [x] [SPEC-1] Add `import subprocess` and a private helper `_run_git(args: list[str], cwd: str | None = None) -> str | None` in `scripts/brain_wake_up.py`. Calls `subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=1.0, check=False)`. Catches `FileNotFoundError`, `subprocess.TimeoutExpired`, `OSError` and returns `None`. Returns `None` if `result.returncode != 0`. Returns `result.stdout.strip() or None` on success. — `scripts/brain_wake_up.py`
- [x] [SPEC-2] Add private helper `_collect_git_branch(git_root: str) -> str | None` that calls `_run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)`. If the result is exactly `"HEAD"` (detached HEAD), returns `None`. Otherwise returns the result (or `None` from `_run_git`). — `scripts/brain_wake_up.py`
- [x] [SPEC-3] Add private helper `_collect_git_log(git_root: str) -> str | None` that calls `_run_git(["log", "--oneline", "-10"], cwd=git_root)`. If non-None and the UTF-8 byte length exceeds 600: encode to bytes, slice `[:600]`, decode with `errors="ignore"`, then `truncated.rsplit("\n", 1)[0]` to drop any partial trailing line (this also drops the final newline so the result has no trailing whitespace). If the encoded length is ≤600, return the input unchanged. Returns `None` if `_run_git` returned `None`. — `scripts/brain_wake_up.py`
- [x] [SPEC-4] Add private helper `_collect_claude_md(cwd: str, git_root: str | None) -> str | None`. Looks for `Path(cwd) / "CLAUDE.md"`; if not exists and `git_root` differs from cwd, looks at `Path(git_root) / "CLAUDE.md"`. Opens with `Path.open("rb")`, reads at most 16384 bytes (`f.read(16384)`), decodes as UTF-8 with `errors="replace"`, slices `[:1000]`. Returns the slice if non-empty, else `None`. Catches `OSError` / `UnicodeDecodeError` / `FileNotFoundError` and returns `None`. — `scripts/brain_wake_up.py`
- [x] [SPEC-5] Add orchestrator `_collect_topic_enrichment(cwd: str) -> dict[str, str]` that:
  1. Calls `git_root = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)`.
  2. Builds a result dict, including a key only when its value is non-`None` and non-empty.
  3. If `git_root` is not None: keys `git_branch` (from `_collect_git_branch(git_root)`), `git_recent_commits` (from `_collect_git_log(git_root)`).
  4. Always: key `claude_md_excerpt` (from `_collect_claude_md(cwd, git_root)` — works without git_root too; `_collect_claude_md` falls back to cwd alone).
  5. Each helper call wrapped in `try/except Exception: pass` so a single helper failure cannot poison the others.
  6. Returns the dict (possibly empty).

  Modify `main()` (around current line 47): replace the existing `json={"agent": agent, "project": cwd, "session_id": session_id}` literal with `json={"agent": agent, "project": cwd, "session_id": session_id, **_collect_topic_enrichment(cwd)}`. The `**` spread inserts only the non-empty fields. — `scripts/brain_wake_up.py`

## Tests

- [x] [TEST-1] Unit test for [SPEC-1] `_run_git` returns `None` when git binary missing. Monkeypatch `brain_wake_up.subprocess.run` (the module is imported as `brain_wake_up` per `scripts/tests/conftest.py` sys.path shim) to raise `FileNotFoundError`. Assert `_run_git(["status"])` returns `None`. — `scripts/tests/test_brain_wake_up_l2.py::test_run_git_returns_none_when_git_missing`
- [x] [TEST-2] Unit test for [SPEC-1] `_run_git` returns `None` on non-zero exit. Monkeypatch to return a `CompletedProcess` with `returncode=128`. Assert `_run_git(["bogus"])` returns `None`. — `scripts/tests/test_brain_wake_up_l2.py::test_run_git_returns_none_on_nonzero_exit`
- [x] [TEST-3] Unit test for [SPEC-2] detached HEAD path. Monkeypatch `_run_git` to return `"HEAD"`. Assert `_collect_git_branch("/x")` returns `None`. Also covers happy path (returns `"feature/foo"` when `_run_git` returns `"feature/foo"`). — `scripts/tests/test_brain_wake_up_l2.py::test_collect_git_branch_handles_detached_head`
- [x] [TEST-4] Unit test for [SPEC-3] truncation. Monkeypatch `_run_git` to return a string of 25 lines × 30 chars each (~775 bytes). Assert the result of `_collect_git_log("/x")` has byte length ≤ 600 AND ends without a partial line (no chars after the last `\n`). Also covers under-budget: when `_run_git` returns 200 bytes, `_collect_git_log` returns the input unchanged. — `scripts/tests/test_brain_wake_up_l2.py::test_collect_git_log_truncates_at_line_boundary`
- [x] [TEST-5] Unit test for [SPEC-4] CLAUDE.md reading. Three scenarios in one test using `tmp_path`:
  (a) **Truncation:** write `<tmp>/CLAUDE.md` containing 1500 chars of `"a"`. Assert `_collect_claude_md(str(tmp_path), git_root=None)` returns a string of length exactly 1000.
  (b) **Fallback to git_root:** create subdir `<tmp>/sub` (no CLAUDE.md inside it), keep the `<tmp>/CLAUDE.md` from (a). Call `_collect_claude_md(str(tmp_path / "sub"), git_root=str(tmp_path))` and assert it returns a 1000-char string (falls back to `<tmp>/CLAUDE.md`).
  (c) **Missing both:** create `<tmp>/empty` subdir with no CLAUDE.md anywhere on the path. Call `_collect_claude_md(str(tmp_path / "empty"), git_root=str(tmp_path / "empty"))` and assert it returns `None`.
  — `scripts/tests/test_brain_wake_up_l2.py::test_collect_claude_md_reads_truncates_and_falls_back`
- [ ] [TEST-6] Integration test: subprocess + tempdir fixture WITH git repo and CLAUDE.md. Build a temp git repo (`git init`, `git config user.email`/`user.name`, write README, `git add .`, `git commit -m "init"`), write a CLAUDE.md with 1500 chars, then invoke `scripts/brain_wake_up.py` as a subprocess (using `sys.executable`) with stdin = `{"cwd": "<tmp>", "session_id": "s1"}`. Spawn a tiny background HTTP server on an ephemeral port (`http.server.HTTPServer` + a captor handler that records the request body and returns `{"context": ""}` with status 200) for the duration of the test, set `BRAIN_URL=http://127.0.0.1:<port>` in the subprocess env. Run the subprocess, parse the captured request body and assert it contains keys `git_branch` (string), `git_recent_commits` (string with byte length ≤ 600), and `claude_md_excerpt` (string of length 1000). — `scripts/tests/test_brain_wake_up_l2.py::test_subprocess_sends_enriched_payload_when_git_and_claudemd_present`
- [ ] [TEST-7] Integration test: subprocess + tempdir fixture with NO git repo (just an empty dir, no `.git`, no CLAUDE.md). Same captor-server pattern as [TEST-6]. Assert the captured request body contains `agent`, `project`, `session_id` and does NOT contain `git_branch` / `git_recent_commits` / `claude_md_excerpt`. Verify the subprocess stdout is valid JSON matching the SessionStart contract (`hookSpecificOutput.hookEventName == "SessionStart"`, `additionalContext == ""`). — `scripts/tests/test_brain_wake_up_l2.py::test_subprocess_omits_enrichment_fields_when_sources_absent`

## Storage / Migrations

- [ ] [DB-0] None.

## Verification gates

- [ ] [GATE-1] `cd C:/Brain && backend/.venv/Scripts/python -m ruff check scripts/` passes (Python touched: `scripts/brain_wake_up.py`, `scripts/tests/test_brain_wake_up_l2.py`).
  - **Note:** `cd backend && ruff check .` does NOT cover `scripts/` — `[tool.ruff].src = ["src", "tests"]` in `backend/pyproject.toml`. The explicit `ruff check scripts/` invocation above is the actual lint gate for L2-B.
- [ ] [GATE-2a] `cd backend && python -m pytest -q` passes (no regression — L2-B does not touch backend, baseline must remain green).
- [ ] [GATE-2b] `cd C:/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/ -q` passes (new file `test_brain_wake_up_l2.py` adds 7 tests; existing `test_brain_wake_up.py` and `test_brain_post_turn.py` must keep passing).
- [skipped] [GATE-3] frontend gates — no frontend touched; `frontend/` package does not exist yet (lands in Phase 4).

**Note:** mypy is NOT a hard gate for Brain (99+ pre-existing errors on main as of 2026-04-27, tracked as `docs/improvements/` P2 per CLAUDE.md). Builder/judge MAY run `cd backend && python -m mypy .` and `mypy scripts/brain_wake_up.py` for advisory signal; failures don't block.
