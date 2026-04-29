# L2-B Adapter Implementation Plan

**Linked spec:** [2026-04-28-l2-b-adapter-design.md](../specs/2026-04-28-l2-b-adapter-design.md)
**Linked checklist:** [2026-04-28-l2-b-adapter-checklist.md](../specs/2026-04-28-l2-b-adapter-checklist.md)
**Goal:** Enrich `scripts/brain_wake_up.py` payload with `git_recent_commits`, `git_branch`, `claude_md_excerpt` so L2 semantic retrieval fires at session start.
**Branch:** `feat/26-l2-b-adapter`

---

### Task 1 — [SPEC-1] + [TEST-1] + [TEST-2]: Add `_run_git` subprocess helper

**Files:**
- Modify: `scripts/brain_wake_up.py`
- Create: `scripts/tests/test_brain_wake_up_l2.py`

- [ ] **Step 1.1: Create the test file with failing tests for `_run_git`**

```python
# scripts/tests/test_brain_wake_up_l2.py
"""Tests for L2-B enrichment helpers in brain_wake_up.py."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import brain_wake_up as hook


# ---------------------------------------------------------------------------
# [TEST-1] _run_git returns None when git binary missing
# ---------------------------------------------------------------------------
def test_run_git_returns_none_when_git_missing():
    with patch.object(hook.subprocess, "run", side_effect=FileNotFoundError("git not found")):
        result = hook._run_git(["status"])
    assert result is None


# ---------------------------------------------------------------------------
# [TEST-2] _run_git returns None on non-zero exit code
# ---------------------------------------------------------------------------
def test_run_git_returns_none_on_nonzero_exit():
    fake = subprocess.CompletedProcess(
        args=["git", "bogus"], returncode=128, stdout="", stderr="fatal: not a git repo"
    )
    with patch.object(hook.subprocess, "run", return_value=fake):
        result = hook._run_git(["bogus"])
    assert result is None
```

- [ ] **Step 1.2: Run tests, watch them fail (AttributeError — `_run_git` does not exist yet)**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py -q
```

Expected: `AttributeError: module 'brain_wake_up' has no attribute '_run_git'`

- [ ] **Step 1.3: Add `import subprocess` and `_run_git` to `scripts/brain_wake_up.py`**

Add `import subprocess` to the imports block (after `import os`, before `import sys`):

```python
import subprocess
```

Add the helper after the `_GENERIC_BASENAMES` line, before `derive_agent`:

```python
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

- [ ] **Step 1.4: Run tests, watch them pass**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py -q
```

Expected: `2 passed`

- [ ] **Step 1.5: Tick [SPEC-1], [TEST-1], [TEST-2] in checklist**

```bash
git add scripts/brain_wake_up.py scripts/tests/test_brain_wake_up_l2.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧠 Feature: SPEC-1 add _run_git subprocess helper (#26)"
```

---

### Task 2 — [SPEC-2] + [TEST-3]: Add `_collect_git_branch`

**Files:**
- Modify: `scripts/brain_wake_up.py`
- Modify: `scripts/tests/test_brain_wake_up_l2.py`

- [ ] **Step 2.1: Add failing test for `_collect_git_branch`**

Append to `scripts/tests/test_brain_wake_up_l2.py`:

```python
# ---------------------------------------------------------------------------
# [TEST-3] _collect_git_branch handles detached HEAD and happy path
# ---------------------------------------------------------------------------
def test_collect_git_branch_handles_detached_head():
    # Detached HEAD — literal "HEAD" returned by git rev-parse --abbrev-ref HEAD
    with patch.object(hook, "_run_git", return_value="HEAD"):
        result = hook._collect_git_branch("/x")
    assert result is None

    # Happy path — normal branch name
    with patch.object(hook, "_run_git", return_value="feature/foo"):
        result = hook._collect_git_branch("/x")
    assert result == "feature/foo"

    # _run_git failure
    with patch.object(hook, "_run_git", return_value=None):
        result = hook._collect_git_branch("/x")
    assert result is None
```

- [ ] **Step 2.2: Run test, watch it fail**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_collect_git_branch_handles_detached_head -q
```

Expected: `AttributeError: module 'brain_wake_up' has no attribute '_collect_git_branch'`

- [ ] **Step 2.3: Add `_collect_git_branch` to `scripts/brain_wake_up.py`**

Add after `_run_git`:

```python
def _collect_git_branch(git_root: str) -> str | None:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    if result == "HEAD":
        return None
    return result
```

- [ ] **Step 2.4: Run test, watch it pass**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_collect_git_branch_handles_detached_head -q
```

Expected: `1 passed`

- [ ] **Step 2.5: Tick [SPEC-2], [TEST-3] in checklist**

```bash
git add scripts/brain_wake_up.py scripts/tests/test_brain_wake_up_l2.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧠 Feature: SPEC-2 add _collect_git_branch with detached-HEAD guard (#26)"
```

---

### Task 3 — [SPEC-3] + [TEST-4]: Add `_collect_git_log`

**Files:**
- Modify: `scripts/brain_wake_up.py`
- Modify: `scripts/tests/test_brain_wake_up_l2.py`

- [ ] **Step 3.1: Add failing test for `_collect_git_log`**

Append to `scripts/tests/test_brain_wake_up_l2.py`:

```python
# ---------------------------------------------------------------------------
# [TEST-4] _collect_git_log truncates at line boundary when over 600 bytes
# ---------------------------------------------------------------------------
def test_collect_git_log_truncates_at_line_boundary():
    # Over-budget: 25 lines × 30 chars each = 750 chars → must truncate to ≤600 bytes
    # Use a deterministic line so every line is exactly 30 bytes in UTF-8
    line_30 = "a" * 28 + "bc"  # 30 chars, 30 bytes
    over_budget = "\n".join([line_30] * 25)  # 25 lines = 750 bytes + 24 newlines = 774 bytes total

    with patch.object(hook, "_run_git", return_value=over_budget):
        result = hook._collect_git_log("/x")

    assert result is not None
    assert len(result.encode("utf-8")) <= 600
    # Must not end with a partial line — last char must be end of a complete line
    # (either no newline at tail, meaning only one line remains, OR the string ends
    # at a line boundary). Verify by re-splitting: each part must be exactly 30 chars.
    for part in result.split("\n"):
        assert len(part) == 30

    # Under-budget: 200-byte string — returned unchanged
    short = "a" * 200
    with patch.object(hook, "_run_git", return_value=short):
        result_short = hook._collect_git_log("/x")
    assert result_short == short

    # _run_git returns None → result is None
    with patch.object(hook, "_run_git", return_value=None):
        assert hook._collect_git_log("/x") is None
```

- [ ] **Step 3.2: Run test, watch it fail**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_collect_git_log_truncates_at_line_boundary -q
```

Expected: `AttributeError: module 'brain_wake_up' has no attribute '_collect_git_log'`

- [ ] **Step 3.3: Add `_collect_git_log` to `scripts/brain_wake_up.py`**

Add after `_collect_git_branch`:

```python
def _collect_git_log(git_root: str) -> str | None:
    result = _run_git(["log", "--oneline", "-10"], cwd=git_root)
    if result is None:
        return None
    encoded = result.encode("utf-8")
    if len(encoded) <= 600:
        return result
    truncated = encoded[:600].decode("utf-8", errors="ignore")
    return truncated.rsplit("\n", 1)[0]
```

- [ ] **Step 3.4: Run test, watch it pass**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_collect_git_log_truncates_at_line_boundary -q
```

Expected: `1 passed`

- [ ] **Step 3.5: Tick [SPEC-3], [TEST-4] in checklist**

```bash
git add scripts/brain_wake_up.py scripts/tests/test_brain_wake_up_l2.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧠 Feature: SPEC-3 add _collect_git_log with 600-byte line-boundary truncation (#26)"
```

---

### Task 4 — [SPEC-4] + [TEST-5]: Add `_collect_claude_md`

**Files:**
- Modify: `scripts/brain_wake_up.py`
- Modify: `scripts/tests/test_brain_wake_up_l2.py`

- [ ] **Step 4.1: Add failing test for `_collect_claude_md`**

Append to `scripts/tests/test_brain_wake_up_l2.py`:

```python
# ---------------------------------------------------------------------------
# [TEST-5] _collect_claude_md reads, truncates, falls back to git_root
# ---------------------------------------------------------------------------
def test_collect_claude_md_reads_truncates_and_falls_back(tmp_path):
    # (a) Truncation: CLAUDE.md with 1500 chars → returns exactly 1000
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("a" * 1500, encoding="utf-8")
    result_a = hook._collect_claude_md(str(tmp_path), git_root=None)
    assert result_a is not None
    assert len(result_a) == 1000

    # (b) Fallback: cwd is a subdir with no CLAUDE.md, git_root has CLAUDE.md
    subdir = tmp_path / "sub"
    subdir.mkdir()
    result_b = hook._collect_claude_md(str(subdir), git_root=str(tmp_path))
    assert result_b is not None
    assert len(result_b) == 1000

    # (c) Missing both: neither cwd nor git_root has CLAUDE.md
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    result_c = hook._collect_claude_md(str(empty_dir), git_root=str(empty_dir))
    assert result_c is None
```

- [ ] **Step 4.2: Run test, watch it fail**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_collect_claude_md_reads_truncates_and_falls_back -q
```

Expected: `AttributeError: module 'brain_wake_up' has no attribute '_collect_claude_md'`

- [ ] **Step 4.3: Add `_collect_claude_md` to `scripts/brain_wake_up.py`**

Add after `_collect_git_log`:

```python
def _collect_claude_md(cwd: str, git_root: str | None) -> str | None:
    candidates = [Path(cwd) / "CLAUDE.md"]
    if git_root is not None and git_root != cwd:
        candidates.append(Path(git_root) / "CLAUDE.md")
    for candidate in candidates:
        try:
            with candidate.open("rb") as f:
                raw = f.read(16384)
            text = raw.decode("utf-8", errors="replace")[:1000]
            if text:
                return text
        except (OSError, UnicodeDecodeError, FileNotFoundError):
            continue
    return None
```

- [ ] **Step 4.4: Run test, watch it pass**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_collect_claude_md_reads_truncates_and_falls_back -q
```

Expected: `1 passed`

- [ ] **Step 4.5: Tick [SPEC-4], [TEST-5] in checklist**

```bash
git add scripts/brain_wake_up.py scripts/tests/test_brain_wake_up_l2.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧠 Feature: SPEC-4 add _collect_claude_md with 16KB cap and git_root fallback (#26)"
```

---

### Task 5 — [SPEC-5]: Add `_collect_topic_enrichment` orchestrator and wire into `main()`

**Files:**
- Modify: `scripts/brain_wake_up.py`

- [ ] **Step 5.1: Add `_collect_topic_enrichment` to `scripts/brain_wake_up.py`**

Add after `_collect_claude_md`:

```python
def _collect_topic_enrichment(cwd: str) -> dict[str, str]:
    enrichment: dict[str, str] = {}

    git_root: str | None = None
    try:
        git_root = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    except Exception:
        pass

    if git_root is not None:
        try:
            branch = _collect_git_branch(git_root)
            if branch:
                enrichment["git_branch"] = branch
        except Exception:
            pass

        try:
            log = _collect_git_log(git_root)
            if log:
                enrichment["git_recent_commits"] = log
        except Exception:
            pass

    try:
        excerpt = _collect_claude_md(cwd, git_root)
        if excerpt:
            enrichment["claude_md_excerpt"] = excerpt
    except Exception:
        pass

    return enrichment
```

- [ ] **Step 5.2: Wire `_collect_topic_enrichment` into `main()` — replace the `httpx.post` `json=` literal**

Current line 47–50 in `scripts/brain_wake_up.py`:

```python
        try:
            resp = httpx.post(
                f"{BRAIN_URL}/hook/wake_up",
                json={"agent": agent, "project": cwd, "session_id": session_id},
                timeout=TIMEOUT_SECONDS,
            )
```

Replace with:

```python
        try:
            resp = httpx.post(
                f"{BRAIN_URL}/hook/wake_up",
                json={"agent": agent, "project": cwd, "session_id": session_id,
                      **_collect_topic_enrichment(cwd)},
                timeout=TIMEOUT_SECONDS,
            )
```

- [ ] **Step 5.3: Run the full scripts test suite to confirm no regression**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/ -q
```

Expected: all previously passing tests still pass; `test_brain_wake_up_l2.py` passes 5 tests so far.

- [ ] **Step 5.4: Tick [SPEC-5] in checklist**

```bash
git add scripts/brain_wake_up.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧠 Feature: SPEC-5 add _collect_topic_enrichment orchestrator and wire into main (#26)"
```

---

### Task 6 — [TEST-6]: Integration test — subprocess sends enriched payload with git repo + CLAUDE.md

**Files:**
- Modify: `scripts/tests/test_brain_wake_up_l2.py`

- [ ] **Step 6.1: Add subprocess integration test**

Append to `scripts/tests/test_brain_wake_up_l2.py`:

```python
# ---------------------------------------------------------------------------
# [TEST-6] Integration: subprocess sends enriched payload when git repo + CLAUDE.md present
# ---------------------------------------------------------------------------
import http.server
import json
import os
import socket
import subprocess as _subprocess
import sys
import threading


class _CaptorHandler(http.server.BaseHTTPRequestHandler):
    captured: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _CaptorHandler.captured.append(json.loads(body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"context": ""}')

    def log_message(self, *args):
        pass  # suppress server noise in test output


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_subprocess_sends_enriched_payload_when_git_and_claudemd_present(tmp_path):
    # Build a minimal git repo
    git_dir = tmp_path / "repo"
    git_dir.mkdir()
    readme = git_dir / "README.md"
    readme.write_text("hello", encoding="utf-8")
    (git_dir / "CLAUDE.md").write_text("x" * 1500, encoding="utf-8")

    _subprocess.run(["git", "init"], cwd=str(git_dir), check=True,
                    capture_output=True)
    _subprocess.run(["git", "config", "user.email", "t@test.com"], cwd=str(git_dir),
                    check=True, capture_output=True)
    _subprocess.run(["git", "config", "user.name", "T"], cwd=str(git_dir),
                    check=True, capture_output=True)
    _subprocess.run(["git", "add", "."], cwd=str(git_dir), check=True,
                    capture_output=True)
    _subprocess.run(["git", "commit", "-m", "init"], cwd=str(git_dir), check=True,
                    capture_output=True)

    # Start captor HTTP server
    port = _free_port()
    _CaptorHandler.captured = []
    server = http.server.HTTPServer(("127.0.0.1", port), _CaptorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        env = {**os.environ, "BRAIN_URL": f"http://127.0.0.1:{port}"}
        stdin_payload = json.dumps({"cwd": str(git_dir), "session_id": "s1"})
        script_path = str((git_dir.parent.parent / "scripts" / "brain_wake_up.py").resolve())
        # Resolve relative to conftest: scripts/ is one level above scripts/tests/
        scripts_dir = str((git_dir.parent.parent).resolve())
        script_path = os.path.join(scripts_dir, "scripts", "brain_wake_up.py")

        proc = _subprocess.run(
            [sys.executable, script_path],
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    finally:
        server.shutdown()

    assert len(_CaptorHandler.captured) == 1
    body = _CaptorHandler.captured[0]

    assert "git_branch" in body, f"git_branch missing from payload: {body}"
    assert isinstance(body["git_branch"], str)

    assert "git_recent_commits" in body, f"git_recent_commits missing from payload: {body}"
    assert len(body["git_recent_commits"].encode("utf-8")) <= 600

    assert "claude_md_excerpt" in body, f"claude_md_excerpt missing from payload: {body}"
    assert len(body["claude_md_excerpt"]) == 1000
```

- [ ] **Step 6.2: Run test, confirm it passes**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_subprocess_sends_enriched_payload_when_git_and_claudemd_present -q
```

Expected: `1 passed`

- [ ] **Step 6.3: Tick [TEST-6] in checklist**

```bash
git add scripts/tests/test_brain_wake_up_l2.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧪 Test: TEST-6 subprocess integration — enriched payload with git+CLAUDE.md (#26)"
```

---

### Task 7 — [TEST-7]: Integration test — subprocess omits enrichment when sources absent

**Files:**
- Modify: `scripts/tests/test_brain_wake_up_l2.py`

- [ ] **Step 7.1: Add second subprocess integration test**

Append to `scripts/tests/test_brain_wake_up_l2.py`:

```python
# ---------------------------------------------------------------------------
# [TEST-7] Integration: subprocess omits enrichment fields when no git repo + no CLAUDE.md
# ---------------------------------------------------------------------------
def test_subprocess_omits_enrichment_fields_when_sources_absent(tmp_path):
    # Empty dir — no .git, no CLAUDE.md
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    port = _free_port()
    _CaptorHandler.captured = []
    server = http.server.HTTPServer(("127.0.0.1", port), _CaptorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    scripts_dir = str((empty_dir.parent.parent).resolve())
    script_path = os.path.join(scripts_dir, "scripts", "brain_wake_up.py")

    try:
        env = {**os.environ, "BRAIN_URL": f"http://127.0.0.1:{port}"}
        stdin_payload = json.dumps({"cwd": str(empty_dir), "session_id": "s2"})

        proc = _subprocess.run(
            [sys.executable, script_path],
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    finally:
        server.shutdown()

    # Stdout must be valid JSON matching SessionStart contract
    stdout_parsed = json.loads(proc.stdout)
    assert stdout_parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert stdout_parsed["hookSpecificOutput"]["additionalContext"] == ""

    assert len(_CaptorHandler.captured) == 1
    body = _CaptorHandler.captured[0]

    # Core fields present
    assert "agent" in body
    assert "project" in body
    assert "session_id" in body

    # Enrichment fields absent
    assert "git_branch" not in body
    assert "git_recent_commits" not in body
    assert "claude_md_excerpt" not in body
```

- [ ] **Step 7.2: Run test, confirm it passes**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/test_brain_wake_up_l2.py::test_subprocess_omits_enrichment_fields_when_sources_absent -q
```

Expected: `1 passed`

- [ ] **Step 7.3: Tick [TEST-7] in checklist**

```bash
git add scripts/tests/test_brain_wake_up_l2.py docs/specs/2026-04-28-l2-b-adapter-checklist.md
git commit -m "🧪 Test: TEST-7 subprocess integration — enrichment absent when no git repo (#26)"
```

---

### Final Task — Verification gates

- [ ] **Step F.1: [GATE-1] ruff on scripts/**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m ruff check scripts/
```

Expected: no errors. Note: S603/S607 are ignored in `backend/pyproject.toml` — `subprocess.run(["git", ...])` is safe. If ruff does not pick up the backend config when run from repo root, pass it explicitly: `backend/.venv/Scripts/python -m ruff check scripts/ --config backend/pyproject.toml`.

- [ ] **Step F.2: [GATE-2a] Backend pytest no-regression**

```bash
cd /c/Brain/backend && python -m pytest -q
```

Expected: same count as before L2-B (L2-B does not touch backend).

- [ ] **Step F.3: [GATE-2b] Scripts pytest — all 7 new tests green**

```bash
cd /c/Brain && backend/.venv/Scripts/python -m pytest scripts/tests/ -q
```

Expected: at minimum 7 new tests pass; existing `test_brain_wake_up.py` (5 tests) and `test_brain_post_turn.py` tests still pass.

- [ ] **Step F.4: Tick all [GATE-N] in checklist, push, open PR**

```bash
git push -u origin feat/26-l2-b-adapter
gh pr create --title "feat: L2-B adapter — brain_wake_up.py sends git + CLAUDE.md context (#26)" \
  --body "$(cat <<'EOF'
## Summary
- Adds `_run_git`, `_collect_git_branch`, `_collect_git_log`, `_collect_claude_md`, `_collect_topic_enrichment` private helpers to `scripts/brain_wake_up.py`
- Wires enrichment into `main()` POST payload via `**_collect_topic_enrichment(cwd)`
- All helpers are best-effort/fail-silent; stdin/stdout contract with Claude Code SessionStart hook is unchanged
- 7 new tests: 5 unit (+ monkeypatching) + 2 subprocess integration tests with real git repo and captor HTTP server

## Test plan
- [x] `ruff check scripts/` passes
- [x] `cd backend && pytest -q` no-regression
- [x] `pytest scripts/tests/ -q` — 7 new tests pass, existing tests pass
- [ ] Manual: open new CC session in Brain repo, check `events.jsonl` for hook_wake_up event with `git_branch` / `git_recent_commits` / `claude_md_excerpt` populated

Closes #26

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Implementation notes for the builder

### Script path resolution in integration tests (Task 6 & 7)

The `tmp_path` fixture from pytest creates directories under the system temp dir (e.g. `C:\Users\arthu\AppData\Local\Temp\pytest-xxx\test_xxx\`). The `scripts/brain_wake_up.py` path must be resolved relative to the repo root, not relative to `tmp_path`. Both integration tests resolve it as:

```python
scripts_dir = str((empty_dir.parent.parent).resolve())  # reaches tmp root
script_path = os.path.join(scripts_dir, "scripts", "brain_wake_up.py")
```

This is fragile if `tmp_path` nesting changes. A safer alternative: use `pathlib.Path(__file__).parent.parent` inside the test to locate `scripts/`:

```python
from pathlib import Path
SCRIPTS_DIR = Path(__file__).parent.parent  # scripts/tests/ → scripts/
SCRIPT = str(SCRIPTS_DIR / "brain_wake_up.py")
```

The builder should use the `Path(__file__)` approach — it's independent of `tmp_path` depth. The plan above shows `tmp_path`-relative for clarity; replace with `Path(__file__)` in the actual code.

### CLAUDE.md path in TEST-6

The `tmp_path` is created by pytest somewhere in the system temp dir. `brain_wake_up.py` lives at `C:/Brain/scripts/brain_wake_up.py`. The subprocess invocation must pass the absolute path to the script, resolved independently of `tmp_path`.

### Ruff config pickup

Running `backend/.venv/Scripts/python -m ruff check scripts/` from repo root may or may not auto-discover `backend/pyproject.toml` (ruff walks up from the target files looking for `pyproject.toml`; since `scripts/` is a sibling of `backend/`, it will walk up to `C:/Brain/` and find any root-level config there). If `C:/Brain/pyproject.toml` does not exist, ruff will use defaults — S603/S607 would NOT be ignored. The builder must verify by running the gate and checking if subprocess warnings appear. If they do, add `--config backend/pyproject.toml` to the gate command.

### Windows-specific: ruff invocation

On Windows, `backend/.venv/Scripts/python -m ruff` is the correct invocation (not `ruff` directly, which may not be on PATH). The checklist gate command is already written correctly for Windows.
