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
- Keep model definitions in `app/db/models` and avoid query logic inside routes.
- All schema changes must be migration-driven with Alembic.
- Never edit existing applied migrations; create new forward migrations.

## Redis

- Use Redis only through integration helpers, not ad hoc direct usage.
- Prefix keys by domain (`cache:`, `locks:`, `events:`) for operability.
- Set TTLs intentionally for cache entries.
- Keep Redis usage non-authoritative for critical source-of-truth data.

## File Organization

- `app/api` for API transport concerns.
- `app/web` for template-rendered pages.
- `app/modules/*` for feature logic and module routers.
- `app/core` for config, security, logging, constants, and global handlers.
- `app/db` for DB base/session/models.
- `app/integrations` for external systems (Redis, email, etc.).
- `app/tasks` for background task abstractions and jobs.

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
