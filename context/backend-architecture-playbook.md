# Backend Architecture Playbook (FastAPI Modular Monolith)

This playbook defines a high-level, reusable backend blueprint for this Launchpad project and future FastAPI production systems.

## 1) Architecture Principles

- Use a **modular monolith** before microservices.
- Keep explicit boundaries between transport, application/domain logic, and infrastructure.
- Design modules as independently evolvable units even inside one codebase.
- Prefer explicit contracts (schemas, service interfaces, dependency boundaries).

## 2) Layering Model

- **Transport layer**: FastAPI routers, request parsing, response serialization.
- **Application layer**: use cases, orchestration, policy checks.
- **Domain layer**: core entities, invariants, business rules.
- **Infrastructure layer**: DB adapters, cache clients, queue adapters, provider integrations.

Rule: Transport should not contain business logic; infrastructure should not dictate domain behavior.

## 3) Environment Strategy (No Docker)

- Pin Python runtime (3.10.12).
- Manage dependencies with pip and split requirement sets (`base`, `dev`, `prod`).
- Centralize settings via Pydantic with environment variables.
- Provide `.env.example`, `.env.development`, `.env.production.example` as templates only.
- Use process manager/service unit in production and explicit startup flags.

## 4) Security Baseline

- Password hashing with bcrypt/passlib.
- JWT access and refresh token strategy with explicit expiration and rotation policy.
- Mandatory role- and ownership-based authorization checks.
- Secret management outside source control.
- Input validation at all external boundaries.
- Abuse controls: rate limit, lockout, anomaly monitoring for sensitive actions.

## 5) Reliability Patterns

- Make critical write paths idempotent where retries are expected.
- Use durable background job semantics for outbound notifications.
- Keep retry strategy explicit (backoff, max attempts, dead-letter behavior).
- Track operational events for audit and replay diagnostics.

## 6) Data Evolution & Migrations

- All schema changes are migration-driven (Alembic).
- Never modify historical applied migrations; only add forward migrations.
- Validate migration chains in CI.
- Keep backwards-compatibility plan for API and DB rollouts where needed.

## 7) Caching & Performance Guardrails

- Use Redis as cache/coordination layer, not source of truth.
- Define key naming conventions and TTL strategy before broad usage.
- Cache only measurable hotspots; instrument before and after.
- Protect high-traffic endpoints with query optimization and selective caching.

## 8) Observability Standards

- Structured logs with request correlation IDs.
- Metrics for latency, error rates, queue depth, retry outcomes, and DB health.
- Centralized error tracking for uncaught exceptions.
- Audit logs for privileged staff actions and policy-impacting events.

## 9) Testing Strategy

- Unit tests for pure logic and security primitives.
- Integration tests for DB/cache and module boundaries.
- API tests for contract and permission behavior.
- Smoke checks for startup, health, and migration state.

## 10) API Governance

- Version APIs from first release (`/api/v1`).
- Keep response contracts explicit and stable.
- Introduce deprecation windows for breaking changes.
- Document auth, rate limits, and error semantics consistently.

## 11) Operational Runbook Baseline

- Deployment checklist (config, migrations, health checks).
- Incident checklist (rollback path, logs, metrics, queue controls).
- Backup and restore process for PostgreSQL.
- Dependency and security patch cadence.

## 12) Modular Growth Guidelines

- Add new features as modules with dedicated router/service/schema structure.
- Minimize cross-module coupling; prefer shared abstractions in controlled core packages.
- Split into services only when scaling/ownership boundaries require it and data seams are stable.

---

Use this playbook as the architecture source of truth when introducing new backend features, services, and operational standards.
