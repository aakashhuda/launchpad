# Phase 7 — Staff Tools, Security Hardening & Operational Readiness

## Overview

Phase 7 finishes the governance surface and prepares the backend for
production operation. It wires the admin capabilities the client brief
requires (suspend a member, takedown a product, feature a product on the
front page) onto the existing `StaffAction`/`AuditLog` ledger, completes the
audit-read and moderation-tooling APIs, and adds the hardening controls every
prior phase has explicitly deferred: rate limiting, suspicious-behavior
monitoring hooks, and request-correlation-backed structured logging. Finally
it documents the operational runbook (deployment, incident/rollback, queue
controls, backup/restore) so the service is deployment-ready with confidence
checks. Most schema seams already exist — `AuditLog.correlation_id`/
`ip_address`/`user_agent` columns, the admin `permissions` JSONB, the
`INACTIVE` product state — this phase is primarily wiring, enforcement, and a
small set of additive migrations.

## Requirements

### Suspend / reactivate member

- Add a `UserStatus(str, enum.Enum)` (`active`, `suspended`) — first-class
  enum per the project's taste convention (mirrors `StaffActionType`/etc.) —
  and a `status` column on `users` (default `active`) plus `suspended_at`
  and `suspension_reason: str | None`, via a forward Alembic migration. Do
  not add a separate `is_active` boolean; one enum is the source of truth.
- Extend `StaffActionType` with `SUSPEND_MEMBER` and `REACTIVATE_MEMBER`,
  and `StaffTargetType` to accept `MEMBER`/`USER` (or reuse `PROFILE` —
  choose one and be consistent; the `target_id` should reference
  `profiles.id` to match the actor-profile id convention used by every other
  staff action). Because enums use `native_enum=False` (VARCHAR-backed),
  adding members is a type-only change — no DDL needed for the enum columns,
  but the migration still adds the new `users` columns.
- `UserService.suspend(user, target_user_id, reason)` and
  `UserService.reactivate(user, target_user_id)`: admin-only (enforced at
  the router via `require_verified_role("admin")`), sets status/
  `suspended_at`/`suspension_reason`, records a `StaffAction` and an
  `AuditLog` (`user.suspended` / `user.reactivated` — add these
  `AuditEventType`/`AuditEntityType` members), and emits an in-app
  notification to the affected member. Guard: a suspended user cannot be
  re-suspended; an active user cannot be reactivated. Admins cannot suspend
  themselves or other admins (least-privilege self-protection).
- Enforce suspension at the auth boundary: `get_current_user` (and
  `get_optional_current_user`) in `core/dependencies.py` must reject a
  suspended user's tokens with `401`/`403` and a clear `account_suspended`
  error so suspended members cannot act on protected endpoints. Issued
  access tokens remain structurally valid; the status check is the gate.
  Document this as the chosen revocation strategy (token blacklist is NOT
  introduced this phase — suspension is).
- Endpoints under `/api/v1/staff`:
  - `POST /staff/users/{user_id}/suspend` — body `SuspendMemberRequest{reason: str}`.
  - `POST /staff/users/{user_id}/reactivate` — no body.

### Takedown / restore product

- Reuse the existing `ProductStatus.INACTIVE` as the taken-down state rather
  than adding a new status — extend `PRODUCT_TRANSITIONS` in
  `products/policy.py` to allow an admin-driven `* → INACTIVE` transition
  (and `INACTIVE → LIVE`/`SCHEDULED` restore) gated behind an `admin` actor.
  Keep the founder-driven `LIVE → INACTIVE` path as-is; the admin path is a
  distinct actor on the same target state.
- Extend `StaffActionType` with `TAKE_DOWN_PRODUCT` and
  `RESTORE_PRODUCT` (target_type `PRODUCT`, `target_id` = `products.id`).
- `ProductService.takedown(user, product_id, reason)` and
  `ProductService.restore(user, product_id)`: admin-only, transitions status
  to/from `INACTIVE`, records `StaffAction` + `AuditLog`
  (`product.taken_down` / `product.restored`), and updates the product's
  launch state if needed (a `LIVE` product taken down must also move its
  `ProductLaunch` out of `LIVE` so it stops appearing in today's feed —
  coordinate with `ProductLaunchService`; a clean approach is to set the
  launch to `ARCHIVED`/`CANCELLED` on takedown and not auto-restore the
  launch on product restore, requiring the founder to reschedule).
- Update `products/policy.py::is_publicly_visible` to exclude `INACTIVE`
  products so taken-down products vanish from discovery/search/snapshots.
  Already-immutable historical snapshots are not rewritten (consistent with
  Phase 5 immutability) — a takedown hides the product going forward, not
  retroactively.
- Endpoints:
  - `POST /staff/products/{product_id}/takedown` — body `TakedownProductRequest{reason: str}`.
  - `POST /staff/products/{product_id}/restore`.

### Feature product on the front page

- Add a feature mechanism. Prefer a small `featured_products` table
  (`id`, `product_id` FK unique, `featured_by_profile_id` FK, `reason`,
  `featured_at`, `ends_at: datetime | None`) over a boolean column — it
  preserves who featured it and when (auditability) and allows scheduled
  expiry without row churn. Add an index on `product_id` and on
  `featured_at`.
- `ProductService` (or a dedicated `FeatureService` in `products/`) exposes
  `feature(user, product_id, reason, ends_at=None)` and
  `unfeature(user, product_id)`: admin-only; only publicly-visible
  (`SCHEDULED`/`LIVE`) products can be featured; records `StaffAction`
  (`FEATURE_PRODUCT` / `UNFEATURE_PRODUCT`, target_type `PRODUCT`) +
  `AuditLog` (`product.featured` / `product.unfeatured`).
- Discovery inclusion: the front-page/daily ranking in
  `src/discovery` must factor in active features (e.g. a featured boost or a
  pinned slot). The exact ranking math is owned by the discovery service —
  this phase adds a `is_featured(product_id, at=now)` read (honoring
  `ends_at`) that discovery consults. Do not hardcode feature logic into
  every endpoint; one read path.
- Endpoints:
  - `POST /staff/products/{product_id}/feature` — body `FeatureProductRequest{reason: str, ends_at: datetime | None}`.
  - `POST /staff/products/{product_id}/unfeature`.
  - Optionally `GET /products/featured` (public) listing currently-featured
    products for the front page.

### Audit views and moderation-tooling APIs

- Add `list_audit_logs(db, *, entity_type=None, entity_id=None,
  event_type=None, actor_profile_id=None, limit, offset) -> list[AuditLog]`
  to `staff/crud.py` and a corresponding `AuditLogService.list(...)` that
  passes the request-scoped `correlation_id`/`ip_address`/`user_agent` into
  `record(...)` (see Request correlation below). Add an `AuditLogRead`
  Pydantic schema.
- Endpoint: `GET /staff/audit-logs` (reviewer/admin) with filters
  (`entity_type`, `entity_id`, `event_type`, `actor_profile_id`,
  pagination). This is the "complete audit views" deliverable.
- Consolidate staff moderation surfaces under `/staff` without breaking
  existing consumers: add `GET /staff/reports` mirroring the existing
  `community/ReportService.list_queue` (or keep the report queue at
  `/community/reports` and document the split — choose one and keep it
  consistent). Do not duplicate the report lifecycle logic; reuse
  `ReportService`.
- Surface admin permission flags: the `Role.permissions` JSONB
  (`takedown_products`, `feature_products`, `manage_users`) is seeded but
  never read. Either (a) introduce a `require_permission(flag)` guard that
  reads the acting profile's role permissions, or (b) keep the slug-based
  `require_verified_role("admin")` convention and document that permissions
  are advisory. Prefer (a) only if it is consistent with existing patterns;
  the slug convention is acceptable and the spec should not over-engineer
  a permission engine this phase. State the chosen approach in Notes.

### Rate limiting & abuse controls

- Add a Redis-backed rate limiter backed by
  `integrations/redis.get_redis_client()` (Redis is already available;
  keep it non-authoritative — a limiter miss is a safety control, not
  source-of-truth). Use a sliding-window or fixed-window counter per key
  under a `limits:` prefix per the coding-standards key convention.
- Apply limits to the endpoints prior phases flagged as abuse-prone and
  that the client brief calls out for anti-cheat:
  - Auth: `POST /auth/login`, `POST /auth/signup`,
    `POST /auth/password-reset` (and the resend-verification path) —
    per-IP and per-email lockout-style limits. On repeated failure, return
    `429` with `Retry-After`.
  - Voting: `POST /products/{id}/vote` and unvote — per-member and
    per-IP limits to blunt scripted vote manipulation.
  - Reporting: `POST /community/reports/*` — per-member limits to blunt
    report-flooding.
  - Comments: `POST /products/{id}/comments` — per-member throttling.
- Implement a reusable dependency or middleware decorator (e.g.
  `rate_limit(key_fn, limit, window)`) applied at the router level so the
  policy lives with the endpoint, not in a global catch-all. Keep the
  limit/window values env-configured in `Settings` (e.g.
  `rate_limit_auth_per_minute`, `rate_limit_vote_per_minute`).
- "People will try to cheat the votes" — beyond per-request rate limits, add
  **suspicious-behavior monitoring hooks**: when a vote/comment/report
  crosses a threshold (e.g. N votes from one IP range in a window, rapid
  account creation from one IP), enqueue an abuse-review job by string name
  via the existing `src/tasks` scheduler (e.g.
  `enqueue("staff.evaluate_abuse_signal", {...})`). Add `staff/jobs.py`
  with the job, and the side-effect import in `main.py` alongside
  `notifications.jobs`/`products.jobs`. The job records a `StaffAction`
  (`AuditEventType` abuse-signal) or opens a report for reviewer attention —
  it does not auto-act. This is monitoring, not automated punishment.
- Keep the rate limiter out of the test path's critical correctness checks:
  a way to disable/bypass limits in tests (env flag or dependency override)
  must exist so existing unit/integration tests are not flaky.

### Request correlation & structured logging

- Add a `CorrelationIdMiddleware` (or equivalent) in `src/core` that reads
  `X-Request-Id` from the incoming request (or generates a UUID) and stores
  it in `request.state.correlation_id`, returning it on the response as
  `X-Request-Id`. Register it in `main.py::create_app` via
  `app.add_middleware(...)`.
- Thread the correlation id into audit writes: `AuditLogService.record`
  must read `correlation_id` (and `ip_address`/`user_agent`) from the
  request context (e.g. a small request-scoped context object or a
  dependency-injected `Request` passed from the router) and pass them to
  `crud.create_audit_log`, which already accepts these params. This closes
  the gap where those three columns are always `NULL` today.
- Upgrade `src/core/logging.py` from the 6-line `basicConfig` to structured
  logging: a JSON (or structured) formatter that emits timestamp, level,
  logger, message, and `correlation_id` on every line. Use `structlog` or a
  stdlib `logging.Formatter` subclass — keep the dependency minimal and
  add to `requirements/base.txt` if a new lib is introduced. Bind the
  correlation id to the log context per request so service-layer logs are
  traceable to the originating request.
- Fix the global exception handler in `src/shared/exceptions.py`:
  - Stop leaking internals: return a generic `{"detail": "Internal server
    error"}` for unexpected `Exception` (server failures), and actionable
    messages only for known client errors.
  - Re-raise / pass through `HTTPException` so its status code and detail
    are preserved (do not collapse to 500).
  - Log the unhandled exception with the correlation id and stack trace
    (server-side), per coding-standards Error Handling.
  - Include `X-Request-Id` (correlation id) in error responses so clients
    can reference it.

### Operational runbook & deployment readiness

- Create `context/operational-runbook.md` (or `context/docs/operational-runbook.md`)
  documenting, grounded in what actually exists in the codebase:
  - **Deployment checklist:** env config via `Settings`/`.env.*`,
    `alembic upgrade head` before serving, health check at
    `GET /api/v1/health`, worker start (`python -m src.tasks.worker`).
  - **Incident checklist:** rollback path (forward-only migrations →
    deploy previous commit + do NOT downgrade the DB; document a
    `downgrade` only for emergency and only for the last migration),
    locate logs by `correlation_id`/`X-Request-Id`, queue controls
    (inspect `TaskQueue.size()` / `dead_letter_size()` under
    `events:task_queue` / `events:task_dead_letter`, pause the worker,
    requeue dead-letter).
  - **Backup & restore:** PostgreSQL `pg_dump`/`pg_restore` procedure for
    the database; Redis is non-authoritative (cache/queue only) so its
    backup is best-effort.
  - **Patch cadence:** dependency update and security-patch rhythm.
- Add a richer health endpoint or a readiness check that reports DB +
  Redis connectivity (current `/health` returns a static `{"status":"ok"}`).
  A `/health/ready` that pings `SELECT 1` and `redis.ping()` is acceptable;
  keep the lightweight `/health` liveness as-is.

### Migrations

- Forward-only Alembic migration(s) — never edit `1aa8bf86d9fb`,
  `8a14589011c8`, `b1f7c2d4a9e0`, or any Phase 3–6 migration. Add:
  - `users.status` (`active`/`suspended` enum), `users.suspended_at`,
    `users.suspension_reason`.
  - The `featured_products` table + indexes.
  - Any index supporting audit-log queries (e.g. on
    `(actor_profile_id, created_at)` already exists; add only what the new
    filter params need, e.g. `(entity_type, entity_id, created_at)` if not
    already covered — verify before adding).
- Enum-member additions (`StaffActionType`, `AuditEventType`,
  `AuditEntityType`, `StaffTargetType`) are type-only because columns use
  `native_enum=False`; no DDL is needed for those columns, but if any
  CHECK constraint guards allowed values, update it in the migration. Check
  existing migrations for such constraints before assuming none exist.

### Tests

- Unit: suspension enforcement (suspended token rejected at
  `get_current_user`, active token passes), takedown/restore transitions
  and `is_publicly_visible` exclusion, feature read honoring `ends_at`,
  rate-limit window math (limit hit → 429 with `Retry-After`, under-limit
  passes), abuse-signal threshold triggers an enqueue, correlation-id is
  generated when absent and reused when present.
- Integration: end-to-end admin suspend → affected user can no longer call
  protected endpoints; admin takedown → product disappears from
  discovery/search (but historical snapshot unchanged); feature → discovery
  surfaces it; audit-log read returns entries with populated
  `correlation_id`/`ip_address`; unhandled exception returns generic 500 +
  logs with correlation id + does not leak `str(exc)`; `HTTPException`
  preserves its status code through the global handler; rate-limited
  endpoint returns 429 after N rapid calls and recovers after the window.
- Cover edge paths: admin self-suspend/self-feature rejection, featuring a
  non-public product, restoring a product whose launch was archived,
  rate-limit disabled in test config, correlation id on a request that
  raises mid-flight (still on the response + log).

### Acceptance criteria

- Staff actions are fully traceable: every admin action (suspend/reactivate
  member, takedown/restore product, feature/unfeature product) writes a
  `StaffAction` and an `AuditLog` with the acting profile, timestamp,
  reason, and request `correlation_id`; the new `GET /staff/audit-logs`
  endpoint returns filterable audit records.
- Admin capabilities from the client brief are implemented and
  enforced: a reviewer cannot suspend/takedown/feature (403); only admins
  can; a suspended member is blocked from protected API access; a
  taken-down product is hidden from public discovery/search going forward;
  a featured product surfaces on the front page.
- Core abuse vectors have mitigation controls: auth, voting, reporting, and
  commenting endpoints are rate-limited (429 on excess) backed by Redis;
  suspicious-behavior thresholds enqueue an abuse-review job rather than
  silently passing.
- Service is deployment-ready with confidence checks: request correlation
  ids are present on every response and every log line and audit row;
  structured logging replaces the basic-config stub; the global exception
  handler no longer leaks internals and logs with correlation metadata; a
  readiness check reports DB + Redis connectivity; and an operational
  runbook documents deployment, incident/rollback, queue, and backup
  procedures.

## References

- Phase source: `context/phases.md` (Phase 7)
- Client brief: `context/docs/plans/01-client-brief.md` (Staff tools — suspend/takedown/feature; "a record of every action our staff took"; "People will try to cheat the votes… We need to catch that"; "Must work on a phone"; trust/leaking ends the company)
- Project overview: `context/project-overview.md` (E Discovery, F Notifications/Background; staff actions and audit logs entity)
- Coding standards: `context/coding-standards.md` (Security — rate limiting/abuse controls for auth, voting, reporting; Error Handling — log with correlation metadata, generic server errors; Redis — prefixed keys + TTLs, non-authoritative; Services; Pydantic; SQLAlchemy/Alembic)
- Architecture playbook: `context/backend-architecture-playbook.md` (§4 Security Baseline — abuse controls: rate limit/lockout/anomaly monitoring; §8 Observability — structured logs with correlation IDs, metrics, centralized error tracking, audit logs for privileged actions; §11 Operational Runbook Baseline)
- AI interaction/workflow: `context/ai-interaction.md`
- Prior phase specs:
  - `context/features/06-phase-6-notifications-background-processing-reliability-spec.md` (the "rate limiting/abuse/correlation/structured-logging is Phase 7" deferral; `src/tasks` durable queue + `enqueue` by string name; `NotificationService.emit` seam for staff-action notifications)
  - `context/features/03-phase-3-product-submission-moderation-workflow-spec.md` (`StaffAction`/`AuditLog` recording pattern; reviewer queue)
  - `context/features/04-phase-4-voting-comments-reporting-feed-foundations-spec.md` (vote/comment/report abuse-prone endpoints flagged for Phase 7 rate limiting; `ReportService` queue flow)
  - `context/features/05-phase-5-ranking-search-and-historical-snapshots-spec.md` (snapshot immutability — takedown must not rewrite history; discovery ranking the feature-read consults)
- Implementation modules:
  - `backend/src/staff/models.py` — `StaffAction`, `AuditLog`, `StaffActionType`, `StaffTargetType`, `AuditEventType`, `AuditEntityType` (enum members to extend; `correlation_id`/`ip_address`/`user_agent` columns to populate)
  - `backend/src/staff/{service,crud,router,schemas}.py` — `StaffActionService`/`AuditLogService` (wire correlation/ip/ua into `record`; add `list` for audit logs), add `AuditLogRead` + action request schemas, extend router with admin + audit-log endpoints
  - `backend/src/core/dependencies.py` — `get_current_user`/`get_optional_current_user` (suspension gate), `require_verified_role`/`require_role` (admin guards), `assert_owner`
  - `backend/src/core/logging.py` — basic-config stub to upgrade to structured/JSON with correlation id
  - `backend/src/core/config.py` — `Settings` to extend with rate-limit + correlation + structured-log + suspension fields
  - `backend/src/shared/exceptions.py` — global exception handler to harden (no leak, log with correlation, preserve `HTTPException` status)
  - `backend/src/main.py` — `create_app` (add correlation-id middleware, rate-limit wiring, `staff.jobs` side-effect import)
  - `backend/src/users/models.py` — `User` (add `status`/`suspended_at`/`suspension_reason`); `users/service.py` (suspend/reactivate)
  - `backend/src/products/{models,policy,service}.py` — `ProductStatus.INACTIVE`, `PRODUCT_TRANSITIONS`, `is_publicly_visible`, takedown/restore + feature service methods
  - `backend/src/products/router.py` — feature read endpoint (public) if added
  - `backend/src/community/service.py` — `ReportService` queue reuse for staff moderation surface
  - `backend/src/discovery/{service,jobs}.py` — consult feature read in front-page ranking; keep snapshot immutability
  - `backend/src/integrations/redis.py` — `get_redis_client()` reused for the rate limiter (`limits:` prefix)
  - `backend/src/tasks/{scheduler,registry}.py` — `enqueue_job` by string name for abuse-signal jobs; existing durable queue
  - `backend/src/staff/jobs.py` — new file: `evaluate_abuse_signal` job registered by string name
  - `backend/scripts/seed_roles.sql` — admin `permissions` JSONB (`takedown_products`, `feature_products`, `manage_users`) seeded but unused
  - `backend/alembic/versions/` — forward-only baseline; add Phase 7 migrations, never edit existing
- `context/backend-architecture-playbook.md` §11 — runbook baseline to expand into `context/operational-runbook.md`

## Notes

- This project does not use the `phase-N-complete` git-tag convention (no
  `context/git-conventions.md` exists; no phase tags present — verified, and
  the user confirmed the tag system is unused). Prior-phase completion is
  verified by artifact presence: Phases 1–6 models/services/tests (recent
  commits `97299e3`, `ab045be`). The expected git workflow is branch
  `phase-7-staff-tools-security-hardening-operational-readiness`, merge to
  `main`, then mark the phase complete in `context/current-feature.md`.
- The agent instruction file is `AGENTS.md`. It contains no "five business
  rules" and no session/order data — that generic requirement does not
  apply to Launchpad. The invariants this phase must preserve are: snapshot
  immutability (a takedown hides a product going forward but never rewrites
  a frozen historical day), least-privilege role enforcement (only admins
  suspend/takedown/feature; reviewers do not), audit completeness (every
  privileged action is recorded with actor, reason, timestamp, and
  correlation id), and no-secrets-in-repo (rate-limit/logging config via
  `Settings` + `.env.*`, never committed credentials).
- Revocation strategy choice: suspension is enforced at the auth boundary
  (`get_current_user` rejects suspended users' tokens). A JWT blacklist or
  refresh-token revocation list is explicitly out of scope this phase —
  document it as a Phase 2/7 follow-up if stricter revocation is later
  required. Existing issued access tokens for a newly-suspended user remain
  structurally valid until they expire; the status check is the gate. If
  this is unacceptable, a future phase adds a token blacklist backed by
  Redis.
- Featured slots as a revenue stream is explicitly out of scope per the
  client brief ("We make money later from featured slots… Not in this
  version"). The feature mechanism here is the staff/admin "feature a
  product on the front page" capability only — no paid placement, no
  jobs-board. The `featured_products.ends_at` supports temporary feature
  slots without implying payment.
- View-count and referrer analytics are not tracked by any prior phase
  (flagged in the Phase 6 spec) and remain deferred here. The Phase 7
  runbook documents what is observable (correlation-id logs, queue depth,
  audit trail) but does not add product-view/referrer capture.
- Permission-flag enforcement: the seeded `Role.permissions` JSONB is dead
  data today. This phase may keep the slug-based `require_verified_role`
  convention and treat permissions as advisory, OR introduce a
  `require_permission(flag)` guard — the simpler slug convention is
  acceptable and preferred to avoid over-engineering a permission engine.
  Whichever is chosen, state it in the implementation; do not leave the
  flags both seeded and silently unused without a note.
- Rate limiter must be bypassable in tests (env flag or FastAPI dependency
  override) so existing unit/integration suites do not become flaky under
  default limits. Redis must remain non-authoritative: a limiter outage
  degrades to allowing (fail-open) for availability, not to blocking all
  traffic — document this choice, since fail-open is the conventional
  tradeoff for a non-authoritative rate limiter.
- Structured logging library choice is left to implementation (`structlog`
  or a stdlib `logging.Formatter` JSON subclass); keep the new dependency
  minimal and add to `requirements/base.txt` if external. The correlation id
  is the contract that ties logs ↔ audit rows ↔ error responses, so it
  must be on every response header and every log line regardless of the
  formatter.
- Real-time push for the in-app bell and live vote-count movement remain
  frontend concerns (per Phase 5/6 decisions); this phase adds no
  WebSocket/SSE transport.
