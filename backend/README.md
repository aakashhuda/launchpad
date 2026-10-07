# Launchpad Backend

FastAPI backend scaffold for Launchpad using Python 3.10.12, PostgreSQL, Redis, JWT, and Alembic.

## Setup

1. Create and activate virtualenv with Python 3.10.12.
2. Install dependencies:

```bash
pip install -r requirements/dev.txt
```

3. Configure environment:

```bash
cp .env.example .env.development
```

4. Run development server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Migrations

Initialize migrations after adding first SQLAlchemy models.
