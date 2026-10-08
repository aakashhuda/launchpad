# Architecture

- Prefers domain-driven modular monolith architecture for FastAPI backends: each feature/domain owns its own `router.py`, `service.py`, `crud.py`, `models.py`, and `schemas.py`, with clear separation between business logic (service) and data access (crud). Confidence: 0.8
- Prefers `src/` as the Python package root (import paths `src.*`) over `app/` or other naming. Confidence: 0.7
- Prefers decentralizing ORM models into per-domain `models.py` files (with inline domain enums) rather than keeping a centralized `db/models/` package. Confidence: 0.7
- Prefers mounting domain routers directly in `main.py` with explicit `prefix` arguments rather than routing through an `api/v1/` aggregator layer. Confidence: 0.7
- Prefers a hybrid approach for cross-cutting concerns like background tasks: keep the **infrastructure/abstraction layer** (queue adapter, executor, retry/backoff, scheduler, dispatch registry) centralized in `src/tasks/`, but define **concrete business logic** (individual jobs) inside the owning domain's `jobs.py` (e.g. `src/notifications/jobs.py`). Uses string-name dispatch (`enqueue("domain.job_name", payload)`) to avoid cross-domain imports and preserve directional dependency rules. Confidence: 0.8
