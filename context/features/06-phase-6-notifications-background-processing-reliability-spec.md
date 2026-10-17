# Phase 6 — Notifications & Background Processing Reliability

## Overview

Phase 6 turns the Phase 1 notification models into a working, preference-aware
pipeline and upgrades the thin synchronous `src/tasks` stub into durable
infrastructure with retry/backoff. It wires every client-brief notification
trigger (email verification, password reset, moderation outcomes, day-before
launch reminder, "product is live", comment alerts, daily top-five, weekly
best-of) into email + in-app channels while strictly honoring per-user
preferences, and adds the founder dashboard export job that prepares a
downloadable file asynchronously and notifies on completion. The
`NotificationDelivery` model already carries `attempt_count`, `next_retry_at`,
`status` (`pending`/`retrying`/`sent`/`failed`/`dropped`), and `last_error`, so
durability is a matter of wiring an executor and retry policy onto existing
schema rather than a new migration. This phase also corrects a taste
violation: `Notification.event_type` is currently a plain `String(50)` and is
converted to a first-class `NotificationEventType(str, enum.Enum)` mirroring
the established `AuditEventType` convention.

## Requirements

### Notification event types

- Introduce a first-class `NotificationEventType(str, enum.Enum)` in
  `backend/src/notifications/models.py` (or a dedicated `constants.py`) and
  convert `Notification.event_type` from plain `String(50)` to a typed `Enum`
  column via a forward migration. Use dotted values mirroring
  `backend/src/staff/models.py::AuditEventType` (e.g.
  `email.verification_requested`, `password.reset_requested`,
  `submission.approved`/`rejected`/`changes_requested`,
  `launch.scheduled`/`reminder`/`activated`, `comment.created`,
  `ranking.daily_top_five`, `ranking.weekly_best`, `founder.export_ready`).
- Map every client-brief notification trigger to exactly one event type and one
  `NotificationPreference` flag — the flags already exist on the model:
  `email_verification_enabled`, `password_reset_enabled`,
  `moderation_outcome_enabled`, `launch_reminder_enabled`,
  `product_live_enabled`, `comment_alert_enabled`, `daily_top_five_enabled`,
  `weekly_best_enabled`.

### Notification service, schemas, router, crud

- Implement `NotificationService(db)`, `NotificationPreferenceService(db)`, and
  supporting `notifications/crud.py` per the `<Model>Service` + `crud.py`
  convention (these files are currently empty stubs). Services own the
  transaction boundary (`commit`); routers delegate.
- `NotificationService.emit(recipient_profile_id, actor_profile_id, event_type,
  payload)` is the single entry point domains call. It:
  - Loads (or lazy-creates with all-true defaults) the recipient's
    `NotificationPreference`; if the matching preference flag is `False`, no
    delivery is created on the gated channel (end-to-end enforcement — see
    acceptance criteria).
  - Always creates the `Notification` row (the in-app record the bell reads),
    but only fans out an `EMAIL` `NotificationDelivery` when the email
    preference flag for that event is enabled.
  - Enqueues the delivery job by **string name** via `src/tasks/scheduler`
    (e.g. `enqueue("notifications.dispatch_delivery", {...})`) — never imports
    the dispatch job cross-domain.
- Preference seeding: create the `NotificationPreference` row when a profile is
  created. Currently `_create_account` in `auth/service.py` creates user +
  profile but no preference row — add the default-all-true preference at
  profile creation (and on the "add profile to existing account" path).
- Endpoints (member-authenticated, `/api/v1/notifications`):
  - `GET /notifications` — paginated list for the current member's profile,
    newest first (indexed by `notifications_idx_0` on
    `(recipient_profile_id, created_at)`).
  - `GET /notifications/unread-count` — integer count for the bell badge
    (indexed by `notifications_idx_1` on `(recipient_profile_id, read_at)`).
  - `POST /notifications/{id}/read` — mark one read (`read_at` stamp);
  - `POST /notifications/read-all` — mark all read.
  - `GET /notifications/preferences` and `PATCH /notifications/preferences` —
    read/update the per-event flags via Pydantic `<Entity>Read`/`<Entity>Update`
    schemas.
- Real-time bell updates ("updates while they sit on the page") are satisfied
  by responsive read endpoints + short polling/SSE on the frontend; the backend
  only needs accurate unread-count and list reads. Push transport is out of
  scope here (mirrors the Phase 5 decision on live vote-count movement).

### Rewire existing email call sites

- Replace the direct no-op calls in `auth/service.py`
  (`email_integration.send_verification_email` at the signup path ~line 239,
  `send_password_reset_email` at the reset path ~line 380) with
  `NotificationService.emit(...)` so they flow through preference gating,
  delivery-row tracking, and the durable retry path. Keep
  `integrations/email.py`'s helper signatures stable as the provider seam —
  Phase 6 swaps the transport behind `send_email` for a real provider, not the
  call sites.

### Email provider integration

- Implement a real outbound transport in `integrations/email.py` (SMTP or a
  transactional-email SDK), wired through `src/core/config.Settings`
  env-driven fields (e.g. `email_provider`, `smtp_host`, `smtp_port`,
  `smtp_username`, `smtp_password`, `email_from_address`, `email_enabled`).
  Follow the centralize-settings convention (no explicit env lookups) and the
  no-secrets-in-repo rule — add to `.env.example`/`.env.development` only,
  never commit real credentials.
- `email_enabled=False` must short-circuit to in-app-only without raising.
- The transport is the single place provider failures surface: a failed send
  raises and is caught by the delivery executor, which records `last_error`,
  increments `attempt_count`, sets `status=RETRYING` with `next_retry_at`, and
  re-queues. A mock/in-memory transport is acceptable for tests/dev.

### Durable task infrastructure (`src/tasks/*`)

- Upgrade the synchronous stub (`base.run_task`, `scheduler.enqueue_job`
  returning a queued dict, `scheduler.run_job`) into durable infrastructure:
  - A `TaskQueue` adapter (Redis-backed via
    `integrations/redis.get_redis_client()`, `events:`/`locks:`-prefixed where
    appropriate) that persists enqueued jobs so a process restart does not
    lose them. Keep Redis non-authoritative — the queued job is a unit of work,
    not durable state.
  - An `Executor`/`TaskRunner` that drains the queue, resolves job names via
    the existing `tasks/registry.get_job`, runs them with a fresh DB `Session`,
    and records outcomes.
  - A `RetryPolicy` (explicit backoff, max attempts, dead-letter behavior)
    applied by the executor; on terminal failure mark
    `NotificationDelivery.status=FAILED`/`DROPPED` and surface to failure-
    visibility instrumentation (structured log + status fields).
  - `tasks/scheduler.py::enqueue_job` must actually enqueue (replacing the
    current stub return); keep `run_job` for synchronous/test execution.
- Concrete jobs stay in owning domains (do not move them into `src/tasks`):
  `notifications/jobs.py` (dispatch/digest jobs), `products/jobs.py` (export
  job added this phase). Leave `products.activate_daily_launches` and
  `discovery.freeze_daily_snapshots` registered by string name as-is — they
  already conform.
- Keep the dispatch seam idempotent where retries are expected: a delivery job
  re-running must not double-send — check `NotificationDelivery.status` and
  `provider_message_id` before sending.

### Event emit seams (wire each brief trigger)

- Moderation outcomes — emit from `products/SubmissionService` decision path
  (`submission.approved`/`rejected`/`changes_requested`,
  `moderation_outcome_enabled`).
- Launch reminder — emit from the `ProductLaunchService` scheduling path
  (`launch.reminder`, `launch_reminder_enabled`), day-before launch.
- Product-live — emit from the `products.activate_daily_launches` job (or
  `ProductLaunchService.activate`) (`launch.activated`,
  `product_live_enabled`); the `LAUNCH_ACTIVATED` audit event already exists,
  the notification emit is the new seam.
- Comment alert — emit from `community/CommentService` on create
  (`comment.created`, `comment_alert_enabled`) to the product's founder only,
  never the commenter.
- Daily top-five — scheduled job enqueued at day-open computing the top 5 from
  `discovery` ranking (`ranking.daily_top_five`, `daily_top_five_enabled`);
  mirror the `discovery.freeze_daily_snapshots` scheduling seam.
- Weekly best-of — scheduled job (Monday) emitting the weekly leaderboard
  summary (`ranking.weekly_best`, `weekly_best_enabled`).

### Founder dashboard export job

- `POST /products/{id}/export` (founder-authenticated, ownership-checked via the
  existing `require_founder`/`ProductService` ownership pattern) enqueues
  `products.generate_founder_export` and returns a job/asset handle plus a
  "preparing" status. Add `GET /products/{id}/export/{job_id}` to poll
  readiness and fetch the artifact.
- `products/jobs.py::generate_founder_export(db, product_id,
  requester_profile_id)` aggregates available signals into a downloadable file
  (CSV/JSON): vote totals and vote-over-time (from `community` votes +
  `created_at`), comment count, launch state + date, and historical rank from
  `discovery` snapshots. Store the artifact under a deterministic path/key; on
  completion emit a `founder.export_ready` notification (in-app + email if
  enabled) telling the founder it is ready.
- Scope boundary: view counts and referrer ("where visitors came from")
  analytics are NOT tracked by any prior phase; the export includes what exists
  and Notes flags view/referrer tracking as deferred. Do not invent analytics
  tables in this phase.

### Migrations

- Forward-only Alembic migration(s) for: the `Notification.event_type` enum
  conversion (plain string → `Enum`), and any queue/delivery-helper indexes.
  Never modify existing migrations (`1aa8bf86d9fb`, `8a14589011c8`,
  `b1f7c2d4a9e0`, or Phase 3/4/5 migrations). The `notifications` table has
  no rows yet (no service has emitted any), so the enum conversion is safe;
  if any rows existed, backfill alongside rather than in-place alter.

### Tests

- Unit: preference-gating logic (flag off → no email delivery, in-app record
  still created), retry policy (backoff schedule, max-attempts →
  `FAILED`/`DROPPED`, dead-letter), idempotent dispatch (re-run does not
  double-send), event-type enum mapping.
- Integration: end-to-end `emit` → `NotificationDelivery` row → email
  transport (mocked) with `status=SENT`; provider-failure path → `RETRYING`
  with `next_retry_at` set → eventual `SENT` after retry; terminal failure →
  `FAILED`/`DROPPED` with no silent loss for retriable failures; export job
  runs async, writes artifact, emits completion notification.
- Cover edge paths: missing preference row (lazy-created with defaults),
  unknown event type (enum/schema rejection), unread-count/indexed read
  correctness, mark-read idempotency.

### Acceptance criteria

- No-notify preferences are enforced end-to-end: a member with a given event
  flag off never receives that notification on the gated channel (email),
  verified by a service-level unit test and an integration test on the
  emit→delivery path.
- Temporary provider failures do not drop required notifications: a failing
  email transport results in `RETRYING` deliveries that eventually succeed (or
  reach `FAILED`/`DROPPED` only after the configured max attempts), and no
  required notification is lost during a simulated provider outage.
- Export jobs execute asynchronously and notify on completion: requesting an
  export returns immediately (preparing state), the job runs out-of-band, and
  the founder receives an in-app + email (if enabled) "export ready"
  notification when the artifact is available.
- All brief-required notification triggers are wired: email verification,
  password reset, moderation outcome (approved/rejected/changes-requested),
  day-before launch reminder, product-live, comment-on-your-product, daily
  top-five, weekly best-of — each mapped to an event type and preference flag.
- The `src/tasks` layer is durable: enqueued jobs survive a process restart
  and are drained by an executor with explicit retry/backoff; the in-process
  synchronous stub is replaced, not merely wrapped.

## References

- Phase source: `context/phases.md` (Phase 6)
- Client brief: `context/docs/plans/01-client-brief.md` (Notifications; Founder dashboard export; "if our email provider goes down for an hour, nothing should go missing")
- Project overview: `context/project-overview.md` (F) Notifications & Background Jobs
- Coding standards: `context/coding-standards.md` (Services, Pydantic, SQLAlchemy / Alembic, Redis, File Organization, Background Tasks, Security, Error Handling)
- Architecture playbook: `context/backend-architecture-playbook.md` (Reliability Patterns, Caching & Performance Guardrails, Observability Standards, Data Evolution & Migrations)
- AI interaction/workflow: `context/ai-interaction.md`
- Prior phase spec: `context/features/05-phase-5-ranking-search-and-historical-snapshots-spec.md` (discovery ranking the digest jobs read from; the "durable retry/backoff is Phase 6" deferrals)
- Implementation modules:
  - `backend/src/notifications/models.py` — `Notification`, `NotificationPreference`, `NotificationDelivery`, `NotificationChannel`, `NotificationDeliveryStatus` (Phase 1 models with retry-tracking columns already present)
  - `backend/src/notifications/{service,crud,schemas,router}.py` — empty stubs to implement
  - `backend/src/tasks/{base,scheduler,registry}.py` — synchronous stub to make durable (keep `registry`; upgrade `enqueue_job`/`run_job`)
  - `backend/src/integrations/email.py` — `send_email`/`send_verification_email`/`send_password_reset_email` provider seam to wire a real transport
  - `backend/src/integrations/redis.py`, `backend/src/integrations/cache.py` — Redis client + best-effort JSON cache (queue adapter reuses `get_redis_client`)
  - `backend/src/auth/service.py` — signup (`_create_account`) and password-reset call sites to rewire to `NotificationService.emit` (~lines 239, 380) and preference seeding
  - `backend/src/products/{service,jobs}.py` — `ProductLaunchService` (launch reminder + product-live emit seams), `products.activate_daily_launches` job pattern to mirror; export job + endpoint to add in `jobs.py`/`router.py`
  - `backend/src/products/service.py` — `SubmissionService` decision path (moderation-outcome emit), `require_founder`/ownership pattern for the export endpoint
  - `backend/src/community/service.py` — `CommentService` (comment-alert emit seam)
  - `backend/src/discovery/{service,jobs}.py` — `SnapshotService` ranking the digest jobs read; `discovery.freeze_daily_snapshots` job pattern to mirror for digest scheduling
  - `backend/src/staff/models.py` — `AuditEventType` enum convention to mirror for `NotificationEventType` dotted values
  - `backend/src/core/config.py` — `Settings` to extend with email-provider fields
  - `backend/src/main.py` — router registration pattern (`/api/v1` prefix, per-domain routers)
  - `backend/alembic/versions/` — forward-only baseline; add new migrations, never edit existing

## Notes

- This project does not use the `phase-N-complete` git-tag convention (no
  `context/git-conventions.md` exists; no phase tags present — verified).
  Prior-phase completion verified by artifact presence: Phase 1 notification
  models + Alembic baseline; Phase 2 auth services and `send_*_email` call
  sites; Phase 3 `ProductLaunchService`/`SubmissionService` seams; Phase 4
  `CommentService`; Phase 5 `discovery` ranking/snapshots +
  `products/jobs.py`/`discovery/jobs.py` job patterns + the
  `tasks/registry`+`tasks/scheduler` dispatch seam (commits `686883e`,
  `e39edb2`).
- The agent instruction file is `AGENTS.md`. It contains no "five business
  rules" and no session/order data — that generic workflow requirement does not
  apply to Launchpad. The invariants this phase must preserve are: preference
  enforcement end-to-end (a disabled flag never produces a delivery on the
  gated channel), delivery idempotency under retry (no double-send), and
  durability (no required notification lost to a transient provider outage or
  process restart).
- `Notification.event_type` is currently a plain `String(50)`; the project's
  taste convention (and the existing `AuditEventType`/`NotificationChannel`
  enums) call for a first-class `NotificationEventType(str, enum.Enum)`. Convert
  via a forward migration. The `notifications` table is empty today, so the
  conversion is safe; if a plain-string fallback is shipped first, it must be
  flagged and upgraded before this phase is considered done.
- Real-time push for the in-app bell (SSE/WebSocket) is a frontend concern and
  not required here; the backend exposes accurate, indexed unread-count and
  list endpoints. This mirrors the Phase 5 decision on live vote-count
  movement.
- The founder export aggregates available data only (votes, comments,
  launch/rank/snapshot). View-count and referrer analytics are not tracked by
  any prior phase and are explicitly deferred — do not invent analytics tables
  in this phase. A future phase should add view/referrer capture before the
  export can include them.
- Task durability is Redis-backed (queue adapter under `events:`/`locks:`
  prefixes) to keep the stack PostgreSQL + Redis only; do not introduce an
  external broker (Celery/RabbitMQ) — the project standard is PostgreSQL +
  Redis. The queue holds work-in-flight, not source-of-truth state (Redis stays
  non-authoritative).
- Email provider choice is left to implementation (SMTP or a transactional-
  email SDK); it must be env-configured via `Settings`, secrets kept out of the
  repo, and `email_enabled=False` must short-circuit to in-app-only without
  erroring.
- Rate limiting, abuse detection, request-correlation structured logging, and
  anti-cheat notification hooks are Phase 7 — not in scope here.
- Expected git workflow: branch
  `phase-6-notifications-background-processing-reliability`, merge to `main`,
  then mark the phase complete in `context/current-feature.md`.
