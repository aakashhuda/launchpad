# Release Playbook

How Launchpad is released, promoted, and rolled back. For incident response,
queue controls, and backup/restore specifics, see
[operational-runbook.md](./operational-runbook.md) — this document covers
release discipline only.

## Branch & review policy

- Work happens on feature branches (`feature/...`, `phase-N-...`).
- Features merge to `main` via pull request — no direct commits to `main`.
- **All required CI checks must be green before merge** (see the Backend CI
  workflow: ruff, black, isort, mypy, `alembic upgrade head`, `alembic check`,
  OpenAPI compatibility, tests).
- Commits use conventional messages (`feat:`, `fix:`, `chore:`, …). Do not put
  AI authorship lines in commit messages.

## Release checklist

1. Ensure CI is green on the commit to be released.
2. Bump the version in `backend/pyproject.toml`.
3. Update `CHANGELOG.md` (move entries from `[Unreleased]` into the new version).
4. Confirm migrations: run `alembic upgrade head` against the target database
   and `alembic check` (no drift).
5. Confirm the API baseline: `python scripts/export_openapi.py` then
   `python scripts/openapi_compat.py openapi.json openapi.json` (no breaking
   changes for a patch/minor on the same version).
6. Deploy the API (`uvicorn src.main:app`) and the worker
   (`python -m src.tasks.worker`).
7. Smoke test: `GET /api/v1/health` (liveness) and `GET /api/v1/health/ready`
   (DB + Redis).
8. Tag the release: `git tag vX.Y.Z` on `main`.

## Environment promotion flow

`development` → `staging` → `production`.

- Each environment selects its config via `APP_ENV`
  (`backend/src/core/config.py::resolve_env_file`), reading the matching
  `.env.<env>` file. Secrets are supplied by the environment, never committed.
- Promoting to the next environment requires: green CI, a successful
  `alembic upgrade head`, and a passing readiness check.
- Migrations run **before** the new app/worker processes start.

## Rollback

- **App**: redeploy the previous artifact/commit. Prefer rolling back the app
  over the database.
- **Database**: migrations are forward-only. Do **not** run `alembic downgrade`
  in production unless it is an emergency and has been rehearsed; the supported
  path is forward-compatible-by-design. If a downgrade is unavoidable it is
  only valid one revision at a time for the most recent migration.
- **Kill switches** (no redeploy needed): `EMAIL_ENABLED=false` (in-app only),
  `RATE_LIMIT_ENABLED=false` (the limiter is fail-open anyway).
- After any rollback, re-run the readiness check and confirm queue depth via
  the operational runbook's queue controls.

## Versioning & tagging

- Releases are tagged `vX.Y.Z` on `main` after merge.
- The API is versioned independently under `/api/v1`; see
  [api-versioning-policy.md](./api-versioning-policy.md).
