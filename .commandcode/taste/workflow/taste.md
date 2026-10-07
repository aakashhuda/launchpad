# Workflow

- Prefers project tooling (e.g., Alembic) configured to run directly from the project directory without extra environment setup — so commands like `alembic upgrade head` work out of the box rather than requiring a manual `PYTHONPATH`. Confidence: 0.7
- Prefers performing Postgres admin operations (e.g., dropping/recreating a database) inside an interactive `psql` session rather than via shell utilities like `dropdb`/`createdb`. Confidence: 0.6
- Never add "Co-authored-by" (or any co-author) trailers to git commit messages. Confidence: 0.9
- Keeps a root `README.md` and `context/project-overview.md` as living docs for the whole repo (backend + frontend), including the directory structure and an entity-relationship/data-model diagram. Confidence: 0.7
