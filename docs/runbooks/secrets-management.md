# Secrets management

## Where Brain reads secrets

- File: `docker/.env` (gitignored, never committed)
- Loaded by: docker compose automatic `.env` discovery — compose reads `docker/.env`
  because the compose file lives at `docker/compose.yml` and docker compose uses the
  compose file's directory as the `.env` search root, regardless of shell `cwd`.
- Injected into the container via: `docker/compose.yml` `environment:` block using
  `${VAR:-}` substitution (empty default keeps the service startable without the key).

**Precedence rule (docker compose):** shell env > `.env` file > default value.
If a Windows User-scope env var co-exists with `docker/.env`, the Windows one silently
wins. The migration procedure below explicitly deletes the old var for this reason.

## Adding a new secret

1. Add the variable to `docker/.env.example` with an empty value and a comment.
2. Add the variable to your local `docker/.env` with the real value.
3. Reference it in `docker/compose.yml` under the service `environment:` block:
   ```yaml
   MY_SECRET: ${MY_SECRET:-}
   ```
4. Restart the container:
   ```bash
   docker compose -f docker/compose.yml down && docker compose -f docker/compose.yml up -d
   ```

## One-time migration from Windows User-scope env vars

For users who set `GOOGLE_API_KEY` (or any secret) as a Windows User-scope environment
variable before the `docker/.env` pattern landed in Brain:

1. **Rotate the key** — assume the old one is compromised.
   Go to [Google AI Studio](https://aistudio.google.com/app/apikey), revoke the old key,
   and generate a new one.

2. **Copy the template:**
   ```bash
   cp docker/.env.example docker/.env
   ```

3. **Fill in the new value.** Edit `docker/.env`:
   ```
   GOOGLE_API_KEY=AIzaSy_YOUR_NEW_KEY_HERE
   ```

4. **Restart the container:**
   ```bash
   docker compose -f docker/compose.yml down && docker compose -f docker/compose.yml up -d
   ```

5. **Verify the key is live inside the container:**
   ```bash
   docker exec brain printenv GOOGLE_API_KEY
   ```
   The output must match the value you wrote in step 3 (not the old Windows env var value).

6. **Delete the old Windows User-scope env var.** Open PowerShell and run:
   ```powershell
   [Environment]::SetEnvironmentVariable("GOOGLE_API_KEY", $null, "User")
   ```
   Then close **all** running shells, terminals, and IDEs and reopen them so they pick up
   the deletion. Verify with:
   ```powershell
   [System.Environment]::GetEnvironmentVariable("GOOGLE_API_KEY", "User")
   ```
   Expected: empty output.

## Rotation procedure

1. Generate a new key in [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Edit `docker/.env`, replace the old value.
3. Restart:
   ```bash
   docker compose -f docker/compose.yml down && docker compose -f docker/compose.yml up -d
   ```
4. Verify: `docker exec brain printenv GOOGLE_API_KEY`
5. Disable or delete the old key in AI Studio.

## gitignore note

The root `.gitignore` contains `.env` (no leading `/`), which matches `docker/.env` at
any directory depth. If a `docker/.gitignore` is ever added in the future, it must not
override or redefine this rule in a way that makes `docker/.env` committable.
