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
- Validate input at route boundary and keep services working with typed objects.
- Centralize environment settings in a `BaseSettings`-based config module.

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

## Background Tasks

- Keep the task *infrastructure* (queue adapter, executor, retry policy, scheduler, dispatch registry) centralized in `src/tasks/`.
- Define *concrete jobs* inside the domain that owns the business logic, e.g. `src/notifications/jobs.py`, `src/products/jobs.py`.
- Domains enqueue jobs by **string name** via `src/tasks/scheduler.py` (e.g. `enqueue("notifications.send_daily_digest", payload)`); the executor resolves names to domain job functions at runtime. This avoids cross-domain imports and preserves directional dependency rules.

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
- Enforce least-privilege authorization for member/founder/reviewer/admin roles.

## Code Quality & Testing

- Formatting/linting: Black, Ruff, Isort, Mypy baseline.
- Tests: Pytest with `unit` and `integration` split.
- Cover core security and auth helpers with unit tests.
- Require passing lint/type/tests before merge.
- Keep dead code, commented code, and unused imports out of main branches.
