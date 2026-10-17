# Phase 5 — Ranking, Search, and Historical Snapshots

## Overview

Phase 5 builds the discovery layer that matches the product vision: a daily
front page ranked by **vote velocity** (not raw totals), immutable historical
day pages, per-topic leaderboards, and responsive search. It consumes the
Phase 3 launch/embargo/visibility rules and the Phase 4 vote + follow
primitives already in place. The `ProductLaunch.snapshot_frozen_at` column
(added in Phase 1) and the `ProductLaunchService.activate()` seam (left
explicitly for this phase) are the integration points for day-activation and
snapshot freezing. This phase introduces a new snapshot/ranking domain module,
concrete background jobs in the owning domain's `jobs.py`, and a forward-only
Alembic migration for the snapshot and search-support schema.

## Requirements

### Daily trending ranking

- Implement a `RankingService` (and supporting `crud.py` queries) in a new
  `backend/src/discovery/` module (or extend `backend/src/products/` — pick one
  and keep it consistent with the `<Model>Service` + `crud.py` convention).
- Rank only **publicly visible** products for the current launch day — reuse
  `products/policy.is_publicly_visible(product, today)` so embargoed,
  unreviewed, unverified-owner, or non-launched products never appear.
- The ranking score must reflect **vote velocity**, not just total votes: a
  product that earned twenty votes in its first hour should outrank one that
  earned thirty across the whole day. Implement a scoring function that
  incorporates votes-per-unit-time since launch (and optionally comment
  momentum) — define the exact formula in the service and keep it in one place
  so it is tunable.
- Expose a public read endpoint for today's front page (visitor-accessible,
  `get_optional_current_user`):
  - `GET /products/today` (or `GET /launches/today`) — ranked list of today's
    launches, best first, paginated.
- Ranking must **keep up during the day**: recompute on read against live vote
  counts (or via a short-TTL Redis cache under the `cache:` prefix) rather than
  relying on a nightly batch. Use `src/integrations/redis.get_redis_client()`
  only through the integration helper; set an explicit TTL.

### Day scheduler & launch activation

- Wire the day scheduler job that activates products whose `launch_date` == today
  by calling the existing `ProductLaunchService.activate(product_id)` (it is
  already idempotent `scheduled` → `live` and flips `Product.status` to `LIVE`).
- Define the concrete job in `backend/src/products/jobs.py` (new file) and
  enqueue it by **string name** via `src/tasks/scheduler.enqueue_job`
  (e.g. `enqueue("products.activate_daily_launches", {})`). Do not import the
  job function cross-domain; the executor resolves the name at runtime.
- The current `tasks` infrastructure is a thin stub (`enqueue_job` returns a
  queued dict, `run_task` runs synchronously). Keep the job self-contained and
  synchronous-safe for now; durable queue/retry is Phase 6 — do not build the
  full retry/backoff executor here.

### Historical day snapshots (immutable)

- Add a snapshot model (e.g. `DayRankingSnapshot` / `DailyLaunchSnapshot`) in
  `backend/src/discovery/models.py` (or `products/models.py`) capturing the
  frozen ranking for a closed day:
  - `launch_date` (Date, unique per snapshot), product entries with final
    rank, vote count, and score, plus `frozen_at` timestamp.
  - Consider a `JSON`/`ARRAY` column for the ordered product list or a child
    `snapshot_items` table — pick one and document the choice.
- At day-close, freeze the day's ranking into the snapshot and stamp
  `ProductLaunch.snapshot_frozen_at` for each product in that day. Once frozen,
  the snapshot rows are **immutable**: expose only read endpoints for past
  days, and never allow updates/deletes from the service layer.
- Expose a public read endpoint for past days:
  - `GET /launches/{date}` — return the frozen order for that day, exactly as
    captured. Visitor-accessible.
- A product that never launched (cancelled, still embargoed) is not part of any
  snapshot.

### Topic leaderboards

- Implement per-topic leaderboard views for `week`, `month`, and `all-time`
  windows over publicly visible products tagged with the topic.
- Expose public endpoints (visitor-accessible):
  - `GET /topics/{slug}/leaderboard?window=week|month|all-time` — ranked
    products for the topic within the window.
- "All-time" and long windows can be computed live but should be cached with a
  Redis TTL under `cache:`; week/month can be live or cached. Keep Redis
  non-authoritative — the DB is the source of truth.

### Search

- Implement search over publicly visible products by **name** and
  **description** ("what a product does"), with optional **topic filter** and
  **sort** by `newest` or `most_voted`.
- Expose a public endpoint:
  - `GET /products/search?q=...&topic=...&sort=newest|most_voted` — paginated,
    visitor-accessible.
- Use PostgreSQL-native search to keep it instant: prefer full-text search
  (`tsvector`/`tsquery`) over `name` + `description` with a supporting index,
  or trigram (`pg_trgm`) similarity as an alternative — choose one and apply it
  via a forward migration. A plain `ILIKE` fallback is acceptable for the
  initial cut but must be flagged in Notes if chosen, since it will not scale.
- Sort options:
  - `newest` → `Product.created_at` desc (existing `products_idx_1` on
    `(status, created_at)` helps; an expression/GIN index supports FTS).
  - `most_voted` → aggregate vote count desc (reuse the vote-count pattern from
    `community/crud.count_votes_for_product` generalized to a ranked set).
- Topic filter joins through `product_topics` → `topics` (by `slug`).

### Authorization, integrity, and migrations

- All discovery/search/leaderboard/historical read endpoints are public
  (visitor-accessible via `get_optional_current_user`); no member auth required.
- Day-activation and snapshot-freeze jobs run with no authenticated actor
  (mirror `ProductLaunchService.activate`, which already records audit with
  `actor_profile_id=None`). Persist `AuditLog` entries for `LAUNCH_ACTIVATED`
  (enum already exists) and add a new audit event type for snapshot freezes if
  audit logging of the freeze is desired.
- Add a **forward-only** Alembic migration for: the snapshot table(s) and
  indexes, the search-support index/expression column, and any leaderboard
  helper indexes. Never modify existing migrations (`1aa8bf86d9fb`,
  `8a14589011c8`, `b1f7c2d4a9e0`, or any Phase 3/4 migration).
- Ranking/snapshot writes must be transaction-safe; freezing must be atomic
  (freeze + stamp `snapshot_frozen_at` in one transaction).
- New enums (e.g. `SnapshotState`, leaderboard window values if modeled as an
  enum) follow the project convention of first-class `enum.Enum` classes in the
  ORM, matching the existing `ProductStatus`/`LaunchState` pattern.

### Tests

- Unit tests for the ranking score function (velocity ordering, tie-breaking,
  empty-day, embargoed-product exclusion).
- Integration tests for:
  - Day scheduler activation: scheduled-today product goes `LIVE`; already-live
    product is a no-op (idempotent); cancelled launch is skipped.
  - Snapshot freeze: closed day produces an immutable snapshot with correct
    order and `snapshot_frozen_at` stamps; re-freeze is rejected/no-op.
  - Historical day read returns the frozen order and does not reflect later
    vote changes.
  - Topic leaderboards: week/month/all-time return correct ranked sets for the
    topic; products without the topic are excluded.
  - Search: name hit, description hit, combined; topic filter; `newest` and
    `most_voted` sort correctness; embargoed/invisible products excluded.
- Cover failure/edge paths: empty results, invalid date, date in the future
  (no snapshot yet → 404 or empty), invalid sort/window query params rejected
  at the schema layer.

### Acceptance criteria

- Daily ranking updates during launch windows: the front page reorders as votes
  arrive during the day, and velocity-based ordering beats raw-vote-total
  ordering (verified by a unit test on the score function and an integration
  test on the ranked list).
- Closed-day rankings are immutable: once a day is frozen into a snapshot,
  the historical day endpoint returns that fixed order regardless of subsequent
  votes, and the service layer exposes no write path to mutate snapshot rows.
- Search and topic views are responsive at expected dataset scale: search uses
  a PostgreSQL-native indexed path (FTS or trigram), and hot leaderboard/read
  paths are cached with explicit Redis TTLs under the `cache:` prefix.
- Day scheduler activates today's scheduled launches via the existing
  `ProductLaunchService.activate()` seam and is enqueued by string name through
  `src/tasks/scheduler`.
- All discovery endpoints respect `products/policy.is_publicly_visible()` —
  unreviewed, embargoed, unverified-owner, or cancelled products never appear
  in rankings, search, or leaderboards.

## References

- Phase source: `context/phases.md` (Phase 5)
- Client brief: `context/docs/plans/01-client-brief.md` (The front page; Search; Voting and comments velocity intent)
- Project overview: `context/project-overview.md` (Discovery, Ranking, and Topic Views)
- Coding standards: `context/coding-standards.md` (Services, Pydantic, SQLAlchemy / Alembic, Redis, File Organization, Background Tasks)
- Architecture playbook: `context/backend-architecture-playbook.md` (Reliability Patterns, Caching & Performance Guardrails, Data Evolution & Migrations)
- Prior phase spec: `context/features/04-phase-4-voting-comments-reporting-feed-foundations-spec.md` (vote + feed primitives this phase builds on)
- Implementation modules:
  - `backend/src/products/models.py` — `ProductLaunch.snapshot_frozen_at` and `LaunchState` (Phase 1 hooks)
  - `backend/src/products/service.py` — `ProductLaunchService.activate()` (documented Phase 5 seam)
  - `backend/src/products/policy.py` — `is_publicly_visible()`, `PUBLICLY_VISIBLE_STATUSES`
  - `backend/src/community/crud.py` — `count_votes_for_product`, feed-retrieval stubs (`list_products_from_followed_members/topics`)
  - `backend/src/topics/models.py` — `Topic`, `ProductTopic` join path for leaderboards/search filter
  - `backend/src/tasks/scheduler.py` + `backend/src/tasks/base.py` — `enqueue_job`/`run_task` stubs to extend
  - `backend/src/integrations/redis.py` — `get_redis_client()` (cache helper)
  - `backend/src/main.py` — router registration pattern (`/api/v1` prefix, per-domain routers)
  - `backend/alembic/versions/` — latest migration `b1f7c2d4a9e0` (forward-only baseline)
- AI interaction/workflow: `context/ai-interaction.md`

## Notes

- This project does not use the `phase-N-complete` git-tag convention
  referenced by the generic spec workflow (no `context/git-conventions.md`
  exists, no phase tags present). Prior-phase completion was verified by
  artifact presence: Phase 1 models + Alembic baseline; Phase 2 auth services
  and `core/dependencies.py` guards; Phase 3 product/moderation services,
  `policy.py`, launch scheduling, audit logging; Phase 4 vote/comment/report/
  follow services and feed-retrieval stubs (commit `232dedf`).
- The agent instruction file is `AGENTS.md`. It contains no "five business
  rules" and no session/order data — that generic workflow requirement does not
  apply to Launchpad. The invariants this phase must preserve are: closed-day
  snapshot immutability, embargo/visibility gating via `is_publicly_visible()`,
  and one-vote-per-member-per-product integrity inherited from Phase 4 (ranking
  reads votes, never mutates them).
- Module placement decision: a dedicated `backend/src/discovery/` module
  (owning ranking, snapshots, leaderboards, and search) is preferred over
  overloading `products/`, since discovery is a distinct bounded context and
  keeps `products/` focused on the submission/launch lifecycle. If added, follow
  the same `router.py`/`service.py`/`crud.py`/`models.py`/`schemas.py` layout
  and register under `/api/v1/discovery` (or mount the public endpoints under
  the existing `/products` and `/topics` routers if a lighter footprint is
  preferred — decide during implementation).
- The day-activation job lives in `backend/src/products/jobs.py` (new) per the
  "concrete jobs live in the owning domain" rule; the snapshot-freeze job lives
  in `backend/src/discovery/jobs.py` if the discovery module is created, or
  `products/jobs.py` otherwise. Both enqueue by string name; the current
  `tasks` layer is synchronous — durable retry/backoff is Phase 6.
- Search implementation choice: prefer PostgreSQL full-text search
  (`tsvector`/`tsquery` + GIN index) for description intent matching; trigram
  (`pg_trgm`) is a viable alternative for fuzzy name matching. If an `ILIKE`
  baseline is shipped first for speed of delivery, it must be noted as a
  known scalability gap and upgraded to FTS/trigram before scale. Do not
  introduce an external search engine (Meilisearch, Elasticsearch, etc.) — the
  project standard is PostgreSQL + Redis only.
- "Real-time" vote-count movement on the front page ("should keep up during the
  day") is satisfied here by short-TTL cached recomputation. True push-based
  live updates (SSE/WebSockets) are a frontend concern and not required by this
  phase; the backend exposes responsive read endpoints that reflect current
  vote state.
- Personalized feed refinement (ranking tuned by follows) is Phase 2 / future
  work — Phase 4 supplied the retrieval stubs; Phase 5 supplies ranking but does
  not implement personalized scoring unless trivially composable on top of the
  followed-entity stubs.
- Notifications for "your product is live" and "top five of the day" rely on the
  day-activation and ranking work delivered here, but full email/in-app delivery
  and preference enforcement is Phase 6 — this phase only needs to ensure the
  events are emittable (the `LAUNCH_ACTIVATED` audit event already exists).
- Rate limiting, abuse detection for vote manipulation, and request correlation
  logging are Phase 7 — not in scope here.
- Expected git workflow: branch `phase-5-ranking-search-and-historical-snapshots`,
  merge to `main`, then mark the phase complete in `context/current-feature.md`.
