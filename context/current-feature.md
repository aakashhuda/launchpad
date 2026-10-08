# Current Feature

<!-- Feature Name -->

## Status

<!-- Not Started|In Progress|Completed -->

Not Started

## Goals

<!-- Goals & requirements -->

## Notes

<!-- Any extra notes -->

## History

<!-- Keep this updated. Earliest to latest -->

- Phase 1 — Domain Model & Migration Foundation: SQLAlchemy models for users/roles/profiles, products/submissions/topics, votes/comments/reports, notifications/preferences, and staff actions/audit logs; schema-level constraints and hot-path indexes; Alembic migration baseline (1aa8bf86d9fb).
- Phase 2 — Authentication, Authorization & Account Lifecycle: JWT access/refresh auth with typed tokens; email/password account lifecycle (signup, email verification, forgot/reset/change password); Google sign-in seam; role-aware guards (get_current_user, require_role, require_verified_email, assert_owner); identity CRUD/service in src/users with /users/me and /users/{slug}; persisted refresh-token rotation (migration 8a14589011c8) with revocation; email seam for verification/reset (transport in Phase 6); model registry (src/shared/registry.py) for cross-module mapper resolution; 33 tests passing.
