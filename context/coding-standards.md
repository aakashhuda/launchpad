# Coding Standards

## Python

- Python version is locked to `3.10.12`.
- Use type hints for all public functions, services, and route handlers.
- Keep functions focused and small; split orchestration from pure logic.
- Prefer explicit imports and avoid wildcard imports.

## FastAPI

- Keep API routes under `/api/v1/**`.
- Keep SSR web routes in `app/web` and exclude them from OpenAPI when needed.
- Use dependency injection for settings, DB sessions, and auth contexts.
- Use `status.HTTP_*` constants and `HTTPException` for API error semantics.

## Pydantic

- Use Pydantic schemas for all request/response contracts.
- Keep API schemas separate from persistence models.
- Split schemas per operation for each entity: `<Entity>Create` (write input),
  `<Entity>Update` (partial write input), and `<Entity>Read` (output
  projection). Action-specific DTOs (`<Action>Request` / `<Action>Response`) are
  fine for non-CRUD flows such as login or password reset.
- Put validation (format, ranges, allowed values) in the schemas; services
  receive already-validated, typed objects.
- Centralize environment settings in a `BaseSettings`-based config module.
  `pydantic-settings` maps field names to env vars case-insensitively
  (`secret_key` <- `SECRET_KEY`), so no explicit env lookups are needed.

## SQLAlchemy / Alembic

- Use SQLAlchemy ORM with explicit session handling.
- Keep model definitions in `src/<domain>/models.py` and avoid query logic inside routes.
- All schema changes must be migration-driven with Alembic.
- Never edit existing applied migrations; create new forward migrations.

## Redis

- Use Redis only through integration helpers, not ad hoc direct usage.
- Prefix keys by domain (`cache:`, `locks:`, `events:`) for operability.
- Set TTLs intentionally for cache entries.
- Keep Redis usage non-authoritative for critical source-of-truth data.

## File Organization

- `src/core` for config, database, security, logging, constants, and shared dependencies.
- `src/shared` for cross-cutting base models and global exception handlers.
- `src/<domain>/*` for feature logic: each domain owns `router.py`, `service.py`, `crud.py`, `models.py`, `schemas.py`, and its concrete `jobs.py`.
- `src/integrations` for external systems (Redis, email, etc.).
- `src/tasks` for background task infrastructure only (queue/executor abstraction, retry/backoff, scheduler, dispatch registry). Concrete job definitions live in the owning domain's `jobs.py`, not here.
- `src/web` for template-rendered pages.

## Services

- Each `service.py` exposes one class per model (`<Model>Service`) instead of
  module-level functions, e.g. `UserService`, `RoleService`, `ProfileService`,
  `MemberFollowService` in `src/users/service.py`.
- Construct services with the request's DB `Session` (`UserService(db)`).
  Routers instantiate the service and delegate to it; raw queries stay in
  `crud.py`.
- A service may compose sibling services (e.g. `AuthService` uses `UserService`
  and `ProfileService`) and owns the transaction boundary (`commit`) for its use
  case.
- Keep model-specific business rules in that model's service; keep pure data
  access in `crud.py`.

## Background Tasks

- Keep the task *infrastructure* (queue adapter, executor, retry policy, scheduler, dispatch registry) centralized in `src/tasks/`.
- Define *concrete jobs* inside the domain that owns the business logic, e.g. `src/notifications/jobs.py`, `src/products/jobs.py`.
- Domains enqueue jobs by **string name** via `src/tasks/scheduler.py` (e.g. `enqueue("notifications.send_daily_digest", payload)`); the executor resolves names to domain job functions at runtime. This avoids cross-domain imports and preserves directional dependency rules.
- Suspicious-behavior monitoring lives in `src/staff/monitor.py` and enqueues
  `staff.evaluate_abuse_signal` (records an `abuse.signal_raised` audit entry —
  monitoring only, it never blocks a request).

## Naming

- Modules/files: `snake_case`.
- Classes/schemas: `PascalCase`.
- Functions/variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Route path segments: lowercase, hyphenated only when readability needs it.

## API Design

- Version API from day one (`/api/v1`).
- Keep response shapes stable and explicit.
- Enforce role/ownership checks via dependencies and service-level guards.
- Prefer idempotent semantics for retry-prone write endpoints where applicable.
- Keep evolution **additive** on `/api/v1`; breaking changes require a new
  version segment or an explicit deprecation window (see
  `context/api-versioning-policy.md`).
- The committed `backend/openapi.json` baseline is CI-guarded by
  `scripts/openapi_compat.py`; refresh it with `scripts/export_openapi.py` after
  an intentional additive change.

## Error Handling

- Register global exception handlers for consistent API responses.
- Separate API JSON error behavior from SSR template error rendering.
- Return actionable error messages for client mistakes and generic messages for server failures.
- Log server-side exceptions with correlation metadata when available.

## Security

- Hash passwords with strong password hashing (bcrypt via passlib).
- Use JWT access/refresh strategy with bounded expirations.
- Never commit real secrets to repository; use environment variables.
- Apply rate limiting and abuse controls for auth, voting, and reporting endpoints.
- Apply rate limiting per endpoint with the `rate_limit(bucket, limit_setting=...)`
  dependency (`src/core/rate_limit.py`) on auth/vote/comment/report; it is
  Redis-backed, non-authoritative, and fail-open.
- Enforce least-privilege authorization for member/founder/reviewer/admin roles.
- Governance actions (suspend/reactivate member, takedown/restore/feature
  products) use `require_verified_role("admin")` and record a `StaffAction` +
  `AuditLog`. Suspended users are rejected at the auth boundary
  (`src/core/dependencies.py`). Authorization is by role **slug**; the
  `Role.permissions` JSONB is advisory metadata only.

## Observability & Request Context

- Every request gets a correlation id via `CorrelationIdMiddleware`
  (`src/core/middleware.py`), held in context vars (`src/core/context.py`) and
  echoed on the response as `X-Request-Id`.
- `AuditLogService.record` reads `correlation_id`/`ip_address`/`user_agent` from
  the request context — don't thread them through service signatures manually.
- Logging is structured JSON (`src/core/logging.py`) with the correlation id on
  every line. Let the global exception handler log server-side errors and return
  a generic client message (never leak internals).

## Code Quality & Testing

- Formatting/linting: Black, Ruff, Isort, Mypy baseline.
- Tests: Pytest with `unit` and `integration` split.
- Cover core security and auth helpers with unit tests.
- Require passing lint/type/tests before merge.
- Keep dead code, commented code, and unused imports out of main branches.
- CI (`.github/workflows/backend-ci.yml`) enforces ruff, black, isort, mypy,
  `alembic upgrade head` + `alembic check`, the OpenAPI compatibility check, and
  pytest on every PR and on `main`. Coverage is reported via `pytest-cov`; mypy
  runs on `src` with the pydantic plugin configured in `pyproject.toml`.
