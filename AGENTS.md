# Launchpad

A product launch and discovery platform where founders schedule launches, members vote and discuss products, and staff moderates quality and trust.

## Context Files

Read the following to get the full context of the project:

- @context/project-overview.md
- @context/coding-standards.md
- @context/ai-interaction.md
- @context/backend-architecture-playbook.md
- @context/docs/plans/01-client-brief.md
- @context/api-versioning-policy.md
- @context/operational-runbook.md
- @context/release-playbook.md
- @context/docs/plans/06-api-testing-with-restfox.md

## Commands

- **Backend dev server**: `cd backend && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`
- **Backend worker**: `cd backend && python -m src.tasks.worker`
- **Backend tests**: `cd backend && python3 -m pytest`
- **Backend lint**: `cd backend && python3 -m ruff check .`
- **Backend format**: `cd backend && python3 -m black .`
- **Backend import order**: `cd backend && python3 -m isort .`
- **Backend type check**: `cd backend && python3 -m mypy src`
- **Apply migrations**: `cd backend && alembic upgrade head`
- **Migration drift check**: `cd backend && alembic check`
- **Export OpenAPI baseline**: `cd backend && python scripts/export_openapi.py`
- **API compatibility check**: `cd backend && python scripts/openapi_compat.py openapi.json /tmp/openapi.json`

## Quality Gates

CI (`.github/workflows/backend-ci.yml`) runs lint (ruff/black/isort), type
checks (mypy), `alembic upgrade head` + `alembic check`, the OpenAPI
compatibility check, and the unit + integration test suite on every pull request
and on `main`. All required checks must be green before merge (see
`context/release-playbook.md`). Docs: Swagger UI at `/docs`, ReDoc at `/redoc`,
schema at `/openapi.json`.

**IMPORTANT:** Do not add Claude to any commit messages
