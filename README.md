# Launchpad

🚀 **Community-driven product launch and discovery platform** with moderation, ranking, voting, discovery, and founder analytics.

Founders submit products and schedule a launch day; members vote, comment, and follow topics/makers; reviewers and admins moderate submissions and reports to keep the feed high-signal.

## Repository structure

```text
launchpad/
├── backend/     # FastAPI + PostgreSQL + Redis (modular monolith)
├── frontend/    # reserved for the future frontend app
└── context/     # project specs, standards, and feature specs
```

- **Backend** — FastAPI app under `backend/app/` (API-first, `/api/v1`), with SQLAlchemy + Alembic migrations, PostgreSQL, and Redis.
- **Frontend** — not implemented yet; the directory is reserved for the dedicated frontend app.

## Tech stack

| Area       | Choice                              |
| ---------- | ----------------------------------- |
| Backend    | FastAPI, Python 3.10.12              |
| Database   | PostgreSQL                           |
| Caching    | Redis                                |
| ORM/Migrate| SQLAlchemy + Alembic                 |
| Auth       | JWT (social sign-in later)           |
| Validation | Pydantic                             |
| Frontend   | TBD (separate `frontend/` app)       |

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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is served at `http://localhost:8000` (routes under `/api/v1`).

## Common commands

Run these from `backend/` with the virtualenv active.

| Task      | Command                                   |
| --------- | ----------------------------------------- |
| Dev server| `uvicorn app.main:app --reload`           |
| Tests     | `python3 -m pytest`                       |
| Lint      | `python3 -m ruff check .`                 |
| Format    | `python3 -m black .`                      |
| Migrate   | `alembic upgrade head`                    |
| New migration | `alembic revision --autogenerate -m "..."` |

## Project documentation

- [Project overview](context/project-overview.md) — specs, data model, and directory structure
- [Coding standards](context/coding-standards.md)
- [Backend architecture playbook](context/backend-architecture-playbook.md)
- [Implementation phases](context/phases.md)

## Status

- ✅ Phase 1 — Domain model & migration foundation (SQLAlchemy models + Alembic baseline)
- ⏳ Later phases — auth, product moderation, launches/voting/comments, ranking/search, notifications

See `context/phases.md` for the full roadmap.
