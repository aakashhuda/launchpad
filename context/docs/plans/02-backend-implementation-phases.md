# Launchpad Backend Implementation Phases

A phase-by-phase execution guide for the Launchpad backend, aligned with our modular monolith architecture, current directory structure, and project standards.

## Phase 1 — Domain Model & Migration Foundation

### Objectives

- Translate client brief rules into concrete PostgreSQL schema design.
- Establish first stable Alembic migration baseline.
- Preserve modular boundaries (`src/<domain>/*`) while defining shared core entities.

### Scope

- Define entities and relationships for:
  - users, roles, profiles
  - products, submissions, topics
  - votes, comments, reports
  - notifications, preferences
  - staff actions/audit logs
- Add DB constraints and indexes for integrity/performance.
- Configure migration workflow in Alembic for team-safe iteration.

### Deliverables

- SQLAlchemy models in `backend/src/<domain>/models.py`.
- Initial migration series in `backend/alembic/versions/`.
- Entity conventions doc update in `context/` if needed.

### Exit Criteria

- Fresh database can migrate up/down cleanly.
- Core uniqueness and FK constraints are enforced.
- Indexes exist for expected hot paths (feeds, votes, moderation queues, search seeds).

---

## Phase 2 — Authentication, Authorization & Account Lifecycle

### Objectives

- Deliver production-grade auth baseline with JWT and role-aware access control.
- Implement account lifecycle essentials from client brief.

### Scope

- Module completion for `src/auth` and identity dependencies.
- Implement:
  - email/password signup/login
  - JWT access/refresh issuance and refresh flow
  - email verification workflow
  - forgot/reset/change password
  - Google sign-in integration seam
- Role and ownership guards in `src/core/dependencies.py` and service-level checks.

### Deliverables

- Auth routes, schemas, services.
- Security utilities hardened in `src/core/security.py`.
- Token/session revocation strategy (blacklist or rotation policy) documented.

### Exit Criteria

- Auth flows tested for success and failure paths.
- Privileged endpoints reject unauthorized/forbidden actors correctly.
- Security checks cover token validation, password hashing, reset flows.

---

## Phase 3 — Product Submission & Moderation Workflow

### Objectives

- Implement the core founder-to-reviewer publishing workflow.

### Scope

- Build `products` + moderation lifecycle:
  - draft submission create/update
  - reviewer queue (oldest first)
  - approve/reject/request changes transitions
  - launch day scheduling with per-user/day cap
  - pre-launch embargo and post-launch editable-field policy
- Staff and audit action logging hooks.

### Deliverables

- Product/moderation domain services and API endpoints.
- State transition policy layer (single source of truth for lifecycle rules).
- Reviewer/admin action logs persisted with actor and timestamp.

### Exit Criteria

- Unreviewed products never appear in public listings.
- Lifecycle transitions are policy-safe and test-covered.
- Launch constraints and edit constraints are enforced at service level.

---

## Phase 4 — Voting, Comments, Reporting & Feed Foundations

### Objectives

- Add community interaction primitives with abuse-aware rules.

### Scope

- Voting:
  - one vote per user/product
  - unvote
  - no self-voting
- Comments and replies (threaded model).
- Reporting system for comments/products into moderation flow.
- Follow members/topics and feed scaffolding.

### Deliverables

- Interaction endpoints and services under module boundaries.
- Integrity constraints and anti-abuse checkpoints.
- Initial feed query strategy for followed entities.

### Exit Criteria

- Vote integrity is transaction-safe under concurrent writes.
- Reports appear in staff moderation surfaces.
- Feed data model and retrieval paths are stable for later ranking expansion.

---

## Phase 5 — Ranking, Search, and Historical Snapshots

### Objectives

- Implement discovery logic that matches product vision: quality velocity ranking and immutable history.

### Scope

- Dynamic daily trending/ranking algorithm implementation seam.
- Historical day snapshot freeze process.
- Topic leaderboards for week/month/all-time.
- Search by product name + intent-like description with topic filtering and sort options.

### Deliverables

- Ranking service and data materialization jobs.
- Snapshot persistence strategy for day-close immutability.
- Search endpoints with latency-oriented indexes/caching support.

### Exit Criteria

- Daily ranking updates during launch windows.
- Closed-day rankings are immutable.
- Search and topic views are responsive at expected dataset scale.

---

## Phase 6 — Notifications & Background Processing Reliability

### Objectives

- Build resilient async processing for user notifications and long-running jobs.

### Scope

- Implement notification events for all brief-required triggers.
- Honor per-user notification preferences strictly.
- Introduce durable retry strategy for provider downtime.
- Implement export-generation background jobs with completion notification.

### Deliverables

- Background execution integration from `src/tasks/*` abstraction. Keep the task infrastructure (queue/executor/retry/scheduler) centralized in `src/tasks/`; define concrete jobs in the owning domain's `jobs.py` (e.g. `src/notifications/jobs.py`, `src/products/jobs.py`) and enqueue by string name to avoid cross-domain imports.
- Email/in-app notification pipelines and status tracking.
- Retry/backoff/failure visibility instrumentation.

### Exit Criteria

- No-notify preferences are enforced end-to-end.
- Temporary provider failures do not drop required notifications.
- Export jobs execute asynchronously and notify on completion.

---

## Phase 7 — Staff Tools, Security Hardening & Operational Readiness

### Objectives

- Finish governance tooling and prepare backend for production operation.

### Scope

- Admin capabilities: suspend member, takedown product, feature product.
- Complete audit views and moderation tooling APIs.
- Add hardening controls:
  - rate limiting
  - suspicious behavior monitoring hooks
  - request correlation and structured logging
- Validate backup, migration, and rollback procedures.

### Deliverables

- Staff/admin endpoint suite.
- Operational runbook and incident response checklist updates.
- Security and observability baseline fully wired.

### Exit Criteria

- Staff actions are fully traceable.
- Core abuse vectors have mitigation controls.
- Service is deployment-ready with confidence checks.

---

## Phase 8 — Quality Gates, CI, and Release Discipline

### Objectives

- Make quality reproducible and enforceable before feature acceleration.

### Scope

- CI pipeline for:
  - lint (ruff/black/isort)
  - type checks (mypy)
  - tests (unit + integration)
  - migration validity checks
- Define release checklist and environment promotion flow.
- Add API compatibility/versioning validation policy.

### Deliverables

- CI workflow config and documented branch/review policy.
- Stable pre-merge quality gates.
- Release and rollback playbook.

### Exit Criteria

- Every merge is quality-gated.
- Migration/API breakage is caught before deployment.
- Release process is deterministic and documented.

---

## Cross-Phase Guardrails

- Keep all backend code under `backend/` and preserve modular boundaries.
- Keep API routes versioned under `/api/v1`.
- Treat `context/coding-standards.md` and `context/backend-architecture-playbook.md` as governing documents.
- Maintain strict no-secrets-in-repo policy.
- Prefer additive evolution: migrations, versioned APIs, explicit deprecations.
