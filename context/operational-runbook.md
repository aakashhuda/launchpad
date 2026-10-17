# Launchpad Operational Runbook

Operational procedures for running the Launchpad backend in production. Grounded
in the actual stack: FastAPI + PostgreSQL + Redis, Alembic migrations, the
Redis-backed task queue, and the `/api/v1` API surface.

## Architecture at a glance

- **API**: FastAPI app (`backend/src/main.py`), routes under `/api/v1`.
- **Database**: PostgreSQL — the authoritative source of truth.
- **Redis**: cache, background task queue, rate-limit counters, abuse counters.
  Non-authoritative: losing Redis degrades performance/limits but never loses
  source-of-truth data.
- **Background worker**: `python -m src.tasks.worker` drains the durable queue.
- **Config**: environment variables via `pydantic-settings` (`backend/src/core/config.py`);
  templates in `backend/.env.example`. No secrets in the repo.

## Deployment checklist

1. **Config** — set env vars (see `.env.example`): `SECRET_KEY`, `DATABASE_URL`,
   `REDIS_URL`, plus any provider settings (`EMAIL_ENABLED`, `SMTP_*`). Never
   commit real secrets. `APP_ENV=production` selects `.env.production`.
2. **Migrations** — run `alembic upgrade head` **before** serving traffic and
   before starting the worker. Migrations are forward-only; never edit an
   applied migration.
3. **Start API** — `uvicorn src.main:app --host 0.0.0.0 --port 8000` (behind a
   reverse proxy). The proxy should forward `X-Forwarded-For` so client IPs are
   captured in audit logs.
4. **Start worker** — `python -m src.tasks.worker` (one or more processes).
5. **Health checks** —
   - Liveness: `GET /api/v1/health` → `{"status": "ok"}`.
   - Readiness: `GET /api/v1/health/ready` → reports `database` and `redis`
     connectivity. `503` means the DB is unreachable (do not route traffic);
     `{"status":"degraded"}` (HTTP 200) means Redis is down but the DB is fine.
6. **Smoke test** — a signup/login round trip and `GET /api/v1/discovery/today`.

## Observability

- **Structured logs**: JSON on stdout with `time`, `level`, `logger`,
  `message`, and `correlation_id` on every line.
- **Correlation id**: every response carries `X-Request-Id`; the same value is
  written into the log lines and into `audit_logs.correlation_id` for privileged
  actions. Send `X-Request-Id` from clients to stitch a request across services.
- **Audit trail**: `GET /api/v1/staff/audit-logs` (reviewer/admin) exposes the
  immutable lifecycle/audit ledger, including `abuse.signal_raised` monitoring
  entries. Filter by `event_type`, `entity_type`, `entity_id`, `actor_profile_id`.
- **Staff actions**: `GET /api/v1/staff/actions` lists moderation/admin actions
  with actor and timestamp.

## Incident checklist

### Locate the incident

1. Grab the `X-Request-Id` from the failing response (or the client's reported id).
2. Grep the log stream for that `correlation_id` to get the full request trace.
3. Check readiness: `GET /api/v1/health/ready`.
4. Inspect queue health (below) if notifications/exports are stuck.

### Rollback path

- **App rollback**: redeploy the previous commit/artifact. Prefer rolling back
  the app over the database.
- **Database**: migrations are forward-only. **Do not `alembic downgrade` in
  production** unless explicitly required and rehearsed; instead backward-compat
  by design. If a downgrade is unavoidable, it is only supported one revision at
  a time and only for the most recent migration.
- **Feature flags**: rate limiting can be disabled via `RATE_LIMIT_ENABLED=false`
  (Redis limiter is fail-open anyway); email via `EMAIL_ENABLED=false` (falls
  back to in-app only).

### Queue controls (Redis)

Keys (see `backend/src/tasks/base.py`):

- `events:task_queue` — sorted set of due/queued jobs scored by availability.
- `events:task_dead_letter` — list of jobs that exhausted retries.

Inspect depth: `ZCARD events:task_queue` and `LLEN events:task_dead_letter`
(also exposed programmatically as `TaskQueue.size()` / `dead_letter_size()`).
To pause processing, stop the worker process. To requeue after fixing a bug,
move entries from the dead-letter list back into the sorted set with an
availability score of "now". Redis holds work-in-flight only — it is safe to
flush when empty of valuable work, but do so only after confirming the
dead-letter list is triaged.

### Abuse / security signals

- Reviewers read monitoring signals at
  `GET /api/v1/staff/audit-logs?event_type=abuse.signal_raised`.
- Admin governance actions (suspend/reactivate member, takedown/restore product,
  feature/unfeature product) are admin-only, recorded in `staff_actions` +
  `audit_logs`, and enforced (suspended accounts are rejected at the auth
  boundary; taken-down products leave public listings going forward).

## Backup & restore (PostgreSQL)

- **Backup**: `pg_dump "$DATABASE_URL" -Fc -f launchpad_$(date +%F).dump`
  (schedule regularly; verify restores periodically).
- **Restore**: restore into a fresh database, run `alembic upgrade head` to
  confirm the migration head, then cut over.
- **Redis**: best-effort only. It caches discovery reads and buffers task work;
  it is not source-of-truth. A Redis loss during an outage is acceptable —
  queues drain empty and caches repopulate.

## Patch cadence

- Review and apply dependency/security patches on a regular cadence
  (`requirements/base.txt`, `requirements/dev.txt`, `requirements/prod.txt`).
- Run lint/format/tests and a migration-validity check (`alembic upgrade head`
  on a scratch DB) before promoting.
- Keep the no-secrets-in-repo policy: rotate any credential that was ever
  committed.

## Runtime knobs (Phase 7)

| Setting | Purpose |
| --- | --- |
| `CORRELATION_ID_HEADER` | Header used to read/echo the request correlation id (default `X-Request-Id`). |
| `RATE_LIMIT_ENABLED` | Master switch for Redis-backed rate limiting (fail-open). |
| `RATE_LIMIT_*_PER_MINUTE` | Per-endpoint-class limits (auth/vote/comment/report). |
| `ABUSE_WINDOW_SECONDS`, `ABUSE_*_THRESHOLD` | Suspicious-behavior monitoring windows/thresholds. |
