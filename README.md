# Launchpad

🚀 **Community-driven product launch and discovery platform** with moderation, ranking, voting, discovery, and founder analytics.

Founders submit products and schedule a launch day; members vote, comment, and follow topics/makers; reviewers and admins moderate submissions and reports to keep the feed high-signal.

## Repository structure

```text
launchpad/
├── backend/     # FastAPI + PostgreSQL + Redis (modular monolith)
├── frontend/    # reserved for the future frontend app
├── restfox/     # API client collections for manual/exploratory testing
├── context/     # project specs, standards, runbooks, and feature docs
└── .github/     # CI workflows
```

- **Backend** — FastAPI app under `backend/src/` (API-first, `/api/v1`), with SQLAlchemy + Alembic migrations, PostgreSQL, and Redis.
- **Frontend** — not implemented yet; the directory is reserved for the dedicated frontend app.

## Tech stack

| Area         | Choice                                          |
| ------------ | ----------------------------------------------- |
| Backend      | FastAPI, Python 3.10.12                          |
| Database     | PostgreSQL                                       |
| Caching/Jobs | Redis (cache, durable task queue, rate limiting) |
| ORM/Migrate  | SQLAlchemy + Alembic                             |
| Auth         | JWT access/refresh (+ Google sign-in seam)       |
| Validation   | Pydantic v2                                      |
| Background   | Redis-backed worker (`python -m src.tasks.worker`) |
| Quality      | ruff, black, isort, mypy, pytest (unit + integration) |
| Frontend     | TBD (separate `frontend/` app)                   |

## Prerequisites

- Python 3.10.12
- PostgreSQL (running locally)
- Redis (running locally)

## Getting started (backend)

```bash
cd backend

# 1. Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements/dev.txt

# 3. Configure environment
cp .env.example .env.development   # then fill in SECRET_KEY / DATABASE_URL / REDIS_URL

# 4. Create the database and apply migrations
sudo -u postgres psql -c "CREATE DATABASE launchpad_dev;"   # or use your DB role/name
alembic upgrade head

# 5. Run the dev server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 6. (separate terminal) Run the background worker
python -m src.tasks.worker
```

The API is served at `http://localhost:8000` (routes under `/api/v1`).

### Interactive API docs

FastAPI serves the OpenAPI schema and interactive docs at:

- **Swagger UI** — <http://localhost:8000/docs>
- **ReDoc** — <http://localhost:8000/redoc>
- **OpenAPI JSON** — <http://localhost:8000/openapi.json>

A committed snapshot of the schema lives at `backend/openapi.json` (kept in sync
by `backend/scripts/export_openapi.py`; guarded in CI by `scripts/openapi_compat.py`).

## Common commands

Run these from `backend/` with the virtualenv active.

| Task           | Command                                              |
| -------------- | --------------------------------------------------- |
| Dev server     | `uvicorn src.main:app --reload`                     |
| Worker         | `python -m src.tasks.worker`                        |
| Tests          | `python3 -m pytest`                                 |
| Lint           | `python3 -m ruff check .`                           |
| Format         | `python3 -m black .`                                |
| Import order   | `python3 -m isort .`                                |
| Type check     | `python3 -m mypy src`                               |
| Migrate        | `alembic upgrade head`                              |
| Migration drift| `alembic check`                                     |
| New migration  | `alembic revision --autogenerate -m "..."`          |

CI (`.github/workflows/backend-ci.yml`) runs all of the above — plus the API
compatibility check — on every pull request and on `main`.

## Project documentation

- [Project overview](context/project-overview.md) — specs, data model, and directory structure
- [Implementation phases](context/phases.md) — the phased build plan
- [Coding standards](context/coding-standards.md)
- [Backend architecture playbook](context/backend-architecture-playbook.md)
- [API versioning policy](context/api-versioning-policy.md)
- [Operational runbook](context/operational-runbook.md)
- [Release playbook](context/release-playbook.md)
- [API testing with Restfox](context/docs/plans/06-api-testing-with-restfox.md)

## Status

Backend phases complete (see `context/phases.md` and the history in
`context/current-feature.md`):

- ✅ Phase 1 — Domain model & migration foundation
- ✅ Phase 2 — Authentication, authorization & account lifecycle
- ✅ Phase 3 — Product submission & moderation workflow
- ✅ Phase 4 — Voting, comments, reporting & feed foundations
- ✅ Phase 5 — Ranking, search & historical snapshots
- ✅ Phase 6 — Notifications & background processing reliability
- ✅ Phase 7 — Staff tools, security hardening & operational readiness
- ✅ Phase 8 — Quality gates, CI & release discipline

The frontend app (`frontend/`) is not implemented yet.
