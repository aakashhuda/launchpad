# Phase 8 — Quality Gates, CI, and Release Discipline

## Overview

Phase 8 makes quality reproducible and enforceable so the backend can
accelerate features safely. It introduces a GitHub Actions CI pipeline that
runs lint, type checks, tests, and migration-validity checks on every pull
request and on `main`; fixes the pre-existing mypy and `alembic check` drift
flagged in Phase 7 (pydantic plugin, missing stubs, the raw `products_search_idx`
not declared in metadata); adds an API compatibility/versioning validation
gate via an OpenAPI baseline diff; and documents the release checklist,
environment promotion flow, and rollback playbook. The codebase is already
no-Docker and GitHub-hosted, so CI uses GitHub Actions service containers for
PostgreSQL + Redis and the exact commands already documented in `AGENTS.md`.

## Requirements

### CI pipeline (GitHub Actions)

- Add `.github/workflows/backend-ci.yml` triggered on push to `main` and on
  pull requests targeting `main` (and, optionally, on feature branches).
  Single job on Python **3.10.12** (matches `pyproject.toml` /
  `AGENTS.md`).
- Provision **PostgreSQL** and **Redis** as GitHub Actions service containers
  — the test suite is integration-style against a real Postgres
  (`tests/conftest.py` uses `engine`/`SessionLocal` bound to
  `DATABASE_URL`) and Redis (rate limiter, task queue, discovery cache). Do
  **not** introduce Docker Compose for CI; the project is no-Docker per the
  architecture playbook §3.
- Job steps, run from `backend/` to match the documented commands:
  - `pip install -r requirements/dev.txt`
  - `ruff check .`
  - `black --check .`
  - `isort --check-only .`
  - `mypy src`
  - `alembic upgrade head` (against the CI Postgres) — migration applies
    cleanly head-to-head.
  - `alembic check` — ORM metadata matches the migrated DB (no drift).
  - `pytest -q` — unit + integration suite, green.
- Environment for CI: throwaway `SECRET_KEY`, `DATABASE_URL` pointing at the
  Postgres service container, `REDIS_URL` pointing at the Redis service
  container, `EMAIL_ENABLED=false`, `RATE_LIMIT_ENABLED=false` (or true with
  generous limits — the suite disables it via `conftest`). No real secrets in
  CI; never commit credentials.
- Mark the workflow's checks as **required** for merge to `main` (documented
  in the branch/review policy).

### Pre-merge quality gates & type-check baseline

- Add a `[tool.mypy]` section to `backend/pyproject.toml` so `mypy src` is
  green and enforceable:
  - `plugins = ["pydantic.mypy"]` — makes mypy pydantic-aware and resolves
    the `Settings()` "missing named argument" errors for the env-driven
    `secret_key`/`database_url`/`redis_url` fields on `BaseSettings`
    (`src/core/config.py`).
  - `ignore_missing_imports = true` overrides for `jose.*` and `passlib.*`
    (no shipped stubs), **or** add `types-python-jose` and `types-passlib`
    to `requirements/dev.txt`. Prefer stub packages if they install cleanly;
    fall back to the override. Either way `mypy src` must exit 0.
  - Keep the baseline pragmatic (do not flip on `strict` mid-phase and break
    the build); the gate is "mypy passes on `src`", not "fully strict".
- Resolve the pre-existing `alembic check` drift: the Phase 5 `products_search_idx`
  was created with raw SQL (`op.execute("CREATE INDEX ... USING gin (to_tsvector(...))")`)
  and is not declared on the `Product` model, so `alembic check` reports a
  spurious "removed index". Declare it in `Product.__table_args__` using a
  functional GIN index (e.g.
  `Index("products_search_idx", text("to_tsvector('english'::regconfig, name || ' ' || description)"), postgresql_using="gin")`)
  so metadata and DB agree and `alembic check` is clean. Do not edit the
  applied Phase 5 migration — this is a metadata-only correction.
- Coverage: run with `pytest-cov` (already in `dev.txt`) and emit a report.
  Start **report-only** (or a conservative `--cov-fail-under` set just below
  the current baseline) so the gate is green on day one; a stricter threshold
  can be raised later once a baseline is measured. Do not block merges on an
  unmeasured threshold.

### API compatibility / versioning validation policy

- APIs are versioned under `/api/v1` (`src/core/constants.py::API_V1_PREFIX`).
  Document a compatibility policy in `context/api-versioning-policy.md`:
  - **Additive** changes (new optional response fields, new endpoints, new
    optional query params) are allowed on `/api/v1`.
  - **Breaking** changes (removing/renaming a field, changing a field type,
    changing a status code's semantics, removing an endpoint) require either
    a new version segment (e.g. `/api/v2`) introduced alongside the old one,
    or an explicit deprecation window. Breaking changes must not land silently.
- Enforce it with an **OpenAPI baseline diff**: commit a generated
  `backend/openapi.json` (exported from `FastAPI().openapi()` via a small
  script, e.g. `backend/scripts/export_openapi.py`). In CI, regenerate the
  spec and fail if it differs from the committed baseline in a breaking way
  (field removal/rename/type change). Additive diffs are accepted by
  regenerating and committing the updated baseline. This is the concrete
  "API compatibility validation" gate.
- Keep response contracts explicit and stable per coding-standards §API
  Design; schema changes stay Pydantic-driven and additive where possible.

### Release & rollback playbook

- Document release discipline in `context/release-playbook.md` (cross-reference
  the Phase 7 `context/operational-runbook.md` for incident/queue/backup
  specifics — do not duplicate them):
  - **Release checklist**: version bump in `pyproject.toml`, update
    `CHANGELOG.md`, confirm CI green on `main`, run `alembic upgrade head`
    against the target environment, smoke test `/api/v1/health` and
    `/api/v1/health/ready`, then serve.
  - **Environment promotion flow**: `development` → `staging` → `production`,
    each gated by green CI and a successful `alembic upgrade head` + readiness
    check; promote via the env-specific `.env.*` selected by `APP_ENV`
    (`src/core/config.py::resolve_env_file`).
  - **Rollback**: redeploy the previous artifact; migrations are forward-only
    — do **not** `alembic downgrade` in production unless rehearsed and
    explicitly required (one revision at a time, emergency only). Forward-
    compatible-by-design is the default. (Matches the runbook's incident
    checklist.)
  - **Tagging**: tag releases (`vX.Y.Z`) on `main` after merge.
- Introduce a `CHANGELOG.md` at the repo root (Keep a Changelog format) so
  releases are deterministic and auditable.
- Branch/review policy (documented, e.g. in the release playbook or
  `AGENTS.md`): feature branches (`feature/...`, `phase-N-...`) merge to
  `main` via PR; merges require all required CI checks green; no direct
  commits to `main` for features.

### Tests

- Add a lightweight test that the OpenAPI export is stable and round-trips
  (the export script produces a spec without error, and `/api/v1` is the
  prefix) so the baseline-diff gate has a backing assertion.
- No new application-behavior tests are required — this phase's gates are
  enforced by CI configuration and the existing 148-test suite, which must
  remain green.

### Acceptance criteria

- Every merge is quality-gated: the GitHub Actions workflow runs ruff, black,
  isort, mypy, `alembic upgrade head`, `alembic check`, and pytest on every
  PR and on `main`, and those checks are required to merge.
- Migration/API breakage is caught before deployment: a PR that breaks the
  migration chain or the committed OpenAPI baseline (breaking field
  removal/rename/type change) fails CI before it reaches `main`.
- Release process is deterministic and documented: a release checklist,
  environment promotion flow, rollback procedure, and tagging convention are
  documented in `context/release-playbook.md` (+ `CHANGELOG.md`), and the
  API versioning policy is documented in `context/api-versioning-policy.md`.

## References

- Phase source: `context/phases.md` (Phase 8)
- Coding standards: `context/coding-standards.md` (Code Quality & Testing — Black/Ruff/Isort/Mypy/Pytest unit+integration split; API Design — `/api/v1`, stable response contracts; Error Handling)
- Architecture playbook: `context/backend-architecture-playbook.md` (§3 No-Docker environment; §6 Data Evolution & Migrations — forward-only, validate migration chains in CI; §10 API Governance — version from day one, explicit deprecation windows; §11 Operational Runbook Baseline)
- AI interaction/workflow: `context/ai-interaction.md` (commits — conventional, no Claude; branching — feature branches merge to main; build must pass before commit)
- Operational runbook: `context/operational-runbook.md` (Phase 7 — deployment checklist, incident/rollback, queue controls, backup/restore; extend with release/promotion here)
- Prior phase spec: `context/features/07-phase-7-staff-tools-security-hardening-operational-readiness-spec.md` (flagged the pre-existing mypy `Settings()`/jose-passlib stub errors and the `alembic check` `products_search_idx` drift — resolved in this phase)
- `backend/pyproject.toml` — existing `[tool.black]`/`[tool.isort]`/`[tool.ruff]`/`[tool.pytest.ini_options]`; **no `[tool.mypy]` yet** (to add)
- `backend/requirements/{base,dev,prod}.txt` — pinned tooling (ruff 0.5.1, black 24.4.2, isort 5.13.2, mypy 1.10.1, pytest 8.2.2, pytest-cov 5.0.0); dev/prod split to preserve
- `backend/alembic/env.py`, `backend/alembic/versions/*` — migration chain head `f7a1b2c3d4e5`; `alembic check` target
- `backend/src/core/constants.py` (`API_V1_PREFIX = "/api/v1"`), `backend/src/core/config.py` (`Settings` — mypy call-arg source; `resolve_env_file` — env promotion seam), `backend/src/core/security.py` (jose/passlib imports — stub source)
- `backend/src/products/models.py` — `Product.__table_args__` (where `products_search_idx` must be declared to clear `alembic check`)
- `backend/tests/conftest.py` — Postgres+Redis integration test wiring (DATABASE_URL/REDIS_URL; rate-limit disabled via fixture)
- `AGENTS.md` — documented commands (`cd backend && python3 -m ruff check .` / `black .` / `pytest`), branching, and the no-Claude-in-commits rule

## Notes

- This project does **not** use the `phase-N-complete` git-tag convention (no
  `context/git-conventions.md`; no phase tags — verified in Phase 7, and the
  user confirmed the tag system is unused). Prior-phase completion is verified
  by artifact presence: Phases 1–7 merged to `main` (HEAD `90d593c` after the
  Phase 7 merge). Expected git workflow: branch
  `phase-8-quality-gates-ci-and-release-discipline`, merge to `main`, then
  mark the phase complete in `context/current-feature.md`.
- The agent instruction file is `AGENTS.md`. It contains no "five business
  rules" and no session/order data — that generic requirement does not apply
  to Launchpad. The invariants this phase must preserve: forward-only
  migrations (never edit an applied migration), `/api/v1` additive-only
  evolution with explicit deprecation, no-secrets-in-repo (CI uses throwaway
  env), and the no-Docker constraint (GitHub Actions service containers, not
  Docker Compose).
- This phase is the natural home for the three pre-existing tooling items
  flagged at the end of Phase 7: the mypy `Settings()` call-arg errors
  (resolved via the pydantic mypy plugin), the `jose`/`passlib` missing-stub
  errors (resolved via stub packages or `ignore_missing_imports` overrides),
  and the `alembic check` `products_search_idx` drift (resolved by declaring
  the functional GIN index in the `Product` model metadata). None are runtime
  bugs; all block a clean `mypy src` / `alembic check` gate and are resolved
  here so CI can be green from day one.
- CI must provision real PostgreSQL and Redis because the suite is
  integration-style against Postgres and uses Redis for rate-limit/queue/cache.
  Document the service-container env vars (`DATABASE_URL`, `REDIS_URL`) in the
  workflow. The conftest already disables rate limiting and clears Redis keys
  per test, so the suite is non-flaky under those settings.
- Coverage: start report-only or with a conservative `--cov-fail-under` just
  below the measured baseline; do not impose an unmeasured hard threshold that
  would block merges. Raise the threshold deliberately afterward.
- OpenAPI baseline diff is the enforceable API-compatibility gate. Additive
  schema changes are accepted by regenerating and committing the updated
  `backend/openapi.json`; breaking changes (field removal/rename/type change)
  fail CI unless introduced under a new version segment with a deprecation
  window. Keep the diff logic simple and committed alongside the spec.
- Do not introduce new application/runtime dependencies — only dev tooling
  (optional type stubs) and CI config. `requirements/base.txt` and
  `requirements/prod.txt` stay unchanged.
- Pre-commit hooks are optional and out of scope unless desired; the
  enforceable gate is CI. Local formatting commands remain those documented in
  `AGENTS.md`.
- Real-time push, mobile clients, payments, and jobs board remain out of
  scope (per the client brief) and are unaffected by this phase.
