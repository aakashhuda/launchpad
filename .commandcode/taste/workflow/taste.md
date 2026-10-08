# Workflow

- Prefers project tooling (e.g., Alembic) configured to run directly from the project directory without extra environment setup — so commands like `alembic upgrade head` work out of the box rather than requiring a manual `PYTHONPATH`. Confidence: 0.7
- Prefers performing Postgres admin operations (e.g., dropping/recreating a database) inside an interactive `psql` session rather than via shell utilities like `dropdb`/`createdb`. Confidence: 0.6
- Never add "Co-authored-by" (or any co-author) trailers to git commit messages. Confidence: 0.9
- Keeps a root `README.md` and `context/project-overview.md` as living docs for the whole repo (backend + frontend), including the directory structure and an entity-relationship/data-model diagram. Confidence: 0.7
- Prefers writing implementation plans as serial-prefixed markdown documents in `context/docs/plans/` (e.g., `01-…`, `02-…`, `03-…`) so they form an ordered sequence. Confidence: 0.8
- Treats `context/coding-standards.md` as the canonical home for architectural conventions (e.g., file organization rules, background-task split) and wants plan docs (`phases.md`, `plan 02`) kept in sync when a convention is established or changed. Confidence: 0.7
- When the database migration state is out of sync with the repo (e.g., stale alembic version stamp), prefers a clean schema reset (drop & recreate) over patching/stamping the version — provided data loss is acceptable (e.g., empty dev DB). Still open to preserving existing migration files when they are correct rather than regenerating. Confidence: 0.7
- Does not delete local branches after merging into `main`; prefers to keep them around even when fully merged and safe to remove. Confidence: 0.7
- Does not want automatic pushes to `origin` after a local merge; prefers to control when commits go upstream. Confidence: 0.7
