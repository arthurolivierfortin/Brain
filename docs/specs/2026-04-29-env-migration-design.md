# Env Migration — Design

**Goal:** Replace Windows User-scope environment variable usage for `GOOGLE_API_KEY` with a repo-local `docker/.env` file, documented via a runbook and surfaced in README.
**Roadmap phase:** ad-hoc P:normal (security hygiene, follow-up of #34)
**Scope (in):**
- NEW `docker/.env.example` — committed template, empty value, documents the schema
- NEW `docs/runbooks/secrets-management.md` — authoritative runbook for secret management and one-time Windows env var migration
- MODIFY `README.md` — one-line pointer to the runbook in the "Repo dependencies for a fresh agent" section

**Scope (out):**
- No changes to `docker/compose.yml`, `backend/`, or `scripts/` — `${GOOGLE_API_KEY:-}` already works
- Other secrets beyond `GOOGLE_API_KEY` (runbook covers the pattern; no other secrets exist today)
- Auto-detection or scripted migration of pre-existing Windows env vars
- Benchmark harness secrets (separate concern, out of scope)

**Constraints:**
- `docker/.env` must remain gitignored — root `.gitignore` already has `.env` (no leading `/`), which covers subdirectory `.env` files; verified
- docker compose auto-loads `.env` from the compose-file directory — no `--env-file` flag needed, no `compose.yml` change needed
- Runbook must address the docker compose precedence rule: shell env > `.env` file. If a Windows User env var co-exists with `docker/.env`, the Windows one wins. Migration procedure must delete the old var.

## Architecture

The change is purely additive config and documentation. `docker/compose.yml` already contains `GOOGLE_API_KEY: ${GOOGLE_API_KEY:-}`, which reads from the environment at compose invocation time. Docker compose auto-discovers a `.env` file located in the same directory as the compose file (`docker/`), and uses it to populate `${VAR}` substitutions before passing values to the container — no flag or compose change required.

`docker/.env.example` is the committed schema record. It contains no secrets — only the variable name with an empty value and a comment pointing to AI Studio. Developers `cp docker/.env.example docker/.env` and fill in the real key. `docker/.env` is excluded from git by the root `.gitignore` entry `.env` (matches any depth).

`docs/runbooks/secrets-management.md` is the single source of truth for: where Brain reads secrets, how to add a new secret, how to perform the one-time migration from Windows User env vars (rotate key → write `.env` → restart container → verify → delete old Windows var), and the ongoing rotation procedure.

## Affected systems

- HTTP API: none
- MCP tools: none
- Storage: none (no migrations)
- Frontend: none
- Installer (`npx brain`): none — `.env.example` will naturally be included in the installer's file-drop when phase 3 lands; no action needed now
- Scripts (Claude Code hooks): none
- Benchmarks: none
- Tests: none — config/data change only; manual smoke steps documented in checklist preamble

## Risks

- **Precedence ambiguity:** docker compose resolution order is shell env > `.env` file. If a Windows User env var survives alongside `docker/.env`, the Windows one silently wins. Runbook explicitly mandates deletion of the old var as the final migration step.
- **gitignore coverage:** root `.gitignore` has `.env` at line 34 (no leading `/`), which matches `docker/.env`. Confirmed. If a future contributor adds a `docker/.gitignore`, they must not override this. Noted in runbook.
- **Path confusion:** `docker compose -f docker/compose.yml` invoked from repo root still auto-loads `docker/.env` because docker compose uses the compose file's directory as the `.env` search root, not the shell's cwd. Documented in runbook.

## Consumer impact

- Money and Marcel are not consumers of Brain's Docker config. No contract breakage.
- Fresh agents reading README will now find the runbook pointer before touching `GOOGLE_API_KEY` setup.
