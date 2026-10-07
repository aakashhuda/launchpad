# Current Feature: Phase 1 — Domain Model & Migration Foundation

## Status

Completed

## Goals

- Create initial SQLAlchemy model set under `backend/app/db/models/` for:
  - users, roles, profiles
  - products, submissions, topics
  - votes, comments, reports
  - notifications, preferences
  - staff actions/audit logs
- Add schema-level integrity rules: primary keys, foreign keys, unique constraints, policy-critical check constraints, explicit cascade behaviors per relationship.
- Add operational indexes for hot read/write paths: daily launches/ranking, vote lookup and uniqueness, moderation queue ordering, report triage, search seed columns.
- Configure and use the Alembic migration workflow in `backend/alembic/versions/`.
- Keep migrations additive and forward-only; never mutate applied migrations.
- Keep model boundaries aligned to the modular monolith; avoid route-level query logic.

## Notes

- Foundation only — do not implement feature/business endpoint behavior yet.
- Design for policy-enforcement readiness (embargo, launch quota, self-vote prevention), but defer full enforcement logic to service-layer phases.
- PostgreSQL is source of truth; keep Redis out of authoritative data paths.
- Migration scripts are the single history of schema evolution.
- Validate clean bootstrap path: empty DB -> migrate to head -> downgrade step (where safe) -> re-upgrade without drift.
- Prefer naming and key/index conventions that support long-term maintainability and auditability.

## History
