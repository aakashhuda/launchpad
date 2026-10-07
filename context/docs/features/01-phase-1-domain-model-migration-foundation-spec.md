# Phase 1 — Domain Model & Migration Foundation

## Overview

Define the Launchpad backend domain model baseline and establish migration-first PostgreSQL evolution with SQLAlchemy + Alembic.

## Requirements

- Create initial SQLAlchemy model set under `backend/app/db/models/` for:
  - users, roles, profiles
  - products, submissions, topics
  - votes, comments, reports
  - notifications, preferences
  - staff actions/audit logs
- Add integrity rules at schema level:
  - primary keys, foreign keys, unique constraints
  - check constraints where policy-critical
  - cascade behaviors explicitly chosen per relationship
- Add operational indexes for hot read/write paths:
  - daily launches and ranking inputs
  - vote lookup and vote uniqueness
  - moderation queue ordering
  - report triage lists
  - search seed columns
- Configure and use Alembic migration workflow in `backend/alembic/versions/`.
- Ensure migration flow is additive and forward-only; never mutate applied migrations.
- Keep model boundaries aligned to modular monolith structure and avoid route-level query logic.

## References

- Phase source: `@context/docs/plans/02-backend-implementation-phases.md`
- Client brief: `@context/docs/plans/01-client-brief.md`
- Initial DB design: `@context/docs/plans/03-initial-db-design.md`
- Project overview: `@context/project-overview.md`
- Coding standards: `@context/coding-standards.md`
- Architecture playbook: `@context/backend-architecture-playbook.md`
- SQLAlchemy docs: https://docs.sqlalchemy.org/
- Alembic docs: https://alembic.sqlalchemy.org/

## Notes

- This phase is foundation only: do not implement feature/business endpoint behavior yet.
- Design for policy enforcement readiness (embargo, launch quota, self-vote prevention), but keep full enforcement logic for service-layer phases.
- Keep PostgreSQL as source of truth and Redis out of authoritative data paths.
- Use migration scripts as the single history of schema evolution.
- Validate clean bootstrap path:
  - empty database -> migrate up to head
  - downgrade step where safe for development checks
  - re-upgrade to head without drift
- Prefer naming and key/index conventions that support long-term maintainability and auditability.
