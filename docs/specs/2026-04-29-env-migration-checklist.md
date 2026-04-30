# Checklist — Env Migration

**Linked spec:** [2026-04-29-env-migration-design.md](2026-04-29-env-migration-design.md)

> **Manual smoke (no automated tests — config/docs change only):**
> After SPEC-1 lands, create `docker/.env` from the template and verify:
> 1. `docker compose -f docker/compose.yml config` shows `GOOGLE_API_KEY` resolved to your key value
> 2. `docker compose -f docker/compose.yml down && docker compose -f docker/compose.yml up -d` succeeds
> 3. `docker exec brain printenv GOOGLE_API_KEY` returns the `.env` value (not empty)
> 4. `curl -s http://localhost:8621/health` returns 200
> 5. One `hook_post_turn` extraction completes (verifies the key works end-to-end)

## Code
- [x] [SPEC-1] Create `docker/.env.example` with header comment, `GOOGLE_API_KEY=` empty value, and AI Studio URL — `docker/.env.example`
- [ ] [SPEC-2] Create `docs/runbooks/secrets-management.md` covering: where Brain reads secrets, how to add a new secret (4-step procedure), one-time migration from Windows User env vars (6-step procedure including key rotation and Windows var deletion), and rotation procedure — `docs/runbooks/secrets-management.md`
- [ ] [SPEC-3] Add one-line pointer to `docs/runbooks/secrets-management.md` in the `## Repo dependencies for a fresh agent` section of `README.md` — `README.md`

## Tests
_(none — config/docs only, manual smoke documented in preamble above)_

## Storage / Migrations
- [ ] [DB-0] None

## Verification gates
- [ ] [GATE-1] `cd backend && python -m ruff check .` passes (no Python touched — expected trivially green; run as no-regression confirmation)
- [ ] [GATE-2] `cd backend && python -m pytest -q` passes — 215 tests green, no regression

> [GATE-3] frontend skipped — no frontend code touched.

## Commit guidance (non-binding, for builder)
- SPEC-1 (`docker/.env.example`): `🧹 Chore: add docker/.env.example secrets template`
- SPEC-2 (`docs/runbooks/secrets-management.md`) + SPEC-3 (`README.md` pointer): `📓 Docs: add secrets-management runbook + README pointer`
