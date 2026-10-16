# Phase 4 — Voting, Comments, Reporting & Feed Foundations

## Overview

Phase 4 adds the community interaction layer on top of the product/moderation workflow built in Phase 3. Members vote on products, leave threaded comments and replies, report comments or products for moderator review, and follow other members and topics to build a personalized feed. The `Vote`, `Comment`, `Report`, `MemberFollow`, and `TopicFollow` models already exist from Phase 1; the `community/` module scaffolds (`router.py`, `service.py`, `crud.py`, `schemas.py`) and the `topics/` module scaffolds (`router.py`, `service.py`, `schemas.py`) are currently empty — this phase fills them following the established `<Model>Service`, `Create`/`Update`/`Read`, and `policy.py` conventions. The phase also introduces a report-status transition policy layer (mirroring `products/policy.py`) and writes `StaffAction` + `AuditLog` records for report triage and resolution actions.

## Requirements

### Voting

- Implement `VoteService` in `backend/src/community/service.py` with raw queries in `backend/src/community/crud.py`.
- Expose vote endpoints under the already-mounted `/api/v1/community` router:
  - `POST /products/{product_id}/vote` — cast a vote (member-only, verified email).
  - `DELETE /products/{product_id}/vote` — unvote (take a vote back).
- Enforce **one vote per member per product**: the `UniqueConstraint("product_id", "profile_id")` (`uq_votes_product_profile`) already exists at the DB level; handle `IntegrityError` on concurrent duplicate inserts using `begin_nested()` + recovery (return existing vote or raise `HTTPException(409)` as appropriate for the endpoint semantics).
- Enforce **no self-voting**: reject if the voting member's profile owns the target product (`HTTPException` 403/422).
- Only allow voting on **publicly visible products** — reuse `products/policy.is_publicly_visible()` so embargoed, unreviewed, or unverified-owner products cannot be voted on.
- Vote model is a simple upvote (no weight/value column); "unvote" is a hard delete of the `Vote` row.
- Idempotent unvote: deleting a non-existent vote returns success (no error).

### Comments & replies

- Implement `CommentService` in `backend/src/community/service.py` with raw queries in `backend/src/community/crud.py`.
- Expose comment endpoints under `/api/v1/community`:
  - `POST /products/{product_id}/comments` — create a top-level comment or reply (set `parent_comment_id` for replies).
  - `GET /products/{product_id}/comments` — list comments for a product, threaded (top-level comments with their replies).
  - `DELETE /comments/{comment_id}` — delete a comment (owner only).
- Threading is already modeled via self-referential `parent_comment_id`; enforce that a reply's `parent_comment_id` belongs to the same product as the comment being created.
- Only allow commenting on **publicly visible products**.
- Comment deletion is owner-only (`assert_owner` against `comment.profile_id`); deleting a parent comment cascades to replies (`ondelete="CASCADE"` already set on `parent_comment_id`).
- Text validation (non-empty, max length) lives in the Pydantic `CommentCreate` schema.

### Reporting

- Implement `ReportService` in `backend/src/community/service.py` with raw queries in `backend/src/community/crud.py`.
- Expose report endpoints under `/api/v1/community`:
  - `POST /products/{product_id}/reports` — report a product (member-only).
  - `POST /comments/{comment_id}/reports` — report a comment (member-only).
  - `GET /reports` — staff moderation queue: list open/in-review reports, oldest first, paginated (reviewer/admin only).
  - `POST /reports/{report_id}/assign` — assign a report to a reviewer (reviewer/admin).
  - `POST /reports/{report_id}/resolve` — resolve or dismiss a report with a resolution note (reviewer/admin).
- Set `target_type` and the matching `target_*_id` consistently — the DB has an XOR-style `CheckConstraint("ck_reports_target_match")` enforcing that `target_type = 'product'` pairs with a non-null `target_product_id` (and null `target_comment_id`), and vice versa.
- The existing `ReportStatus` enum defines the workflow: `OPEN` → `IN_REVIEW` → `RESOLVED` | `DISMISSED`. Create a report-status transition policy module (e.g. `backend/src/community/policy.py`) declaring allowed transitions as frozen dicts, mirroring the `products/policy.py` pattern.
- Reject illegal report-status transitions with `HTTPException` (409).
- Prevent duplicate reports: a member should not file multiple open reports for the same target — enforce at the service level (check for existing open report by same reporter and target before creating).
- Persist `StaffAction` + `AuditLog` records for report assignment and resolution actions (actor, action_type, target_type, target_id, reason/note, before/after state), using the same composition pattern as `ProductService` (instantiate `StaffActionService` and `AuditLogService`, call `.record()` within the `ReportService` transaction, commit once).
- Extend the `StaffActionType`, `StaffTargetType`, `AuditEventType`, and `AuditEntityType` enums in `backend/src/staff/models.py` with new members for report actions (e.g. `ASSIGN_REPORT`, `RESOLVE_REPORT`, `DISMISS_REPORT` for action types; `REPORT` for target/entity types; `"report.created"`, `"report.resolved"`, `"report.dismissed"` for audit event types — follow the existing dot-notation convention for `AuditEventType`).

### Follows & feed scaffolding

- `MemberFollowService` in `backend/src/users/service.py` is already implemented (follow/unfollow/is_following with idempotency). Expose endpoints under `/api/v1/users`:
  - `POST /profiles/{slug}/follow` — follow a member.
  - `DELETE /profiles/{slug}/follow` — unfollow a member.
  - `GET /me/following` — list members the current user follows.
- Implement `TopicFollowService` in `backend/src/topics/service.py` and `TopicFollow` schemas in `backend/src/topics/schemas.py` following the same pattern as `MemberFollowService`. Expose endpoints under `/api/v1/topics`:
  - `POST /{slug}/follow` — follow a topic.
  - `DELETE /{slug}/follow` — unfollow a topic.
  - `GET /me/topic-follows` — list topics the current user follows (or nest under `/api/v1/users/me/topic-follows`).
- Follow idempotency is service-layer for both `MemberFollow` and `TopicFollow` (no DB unique constraint exists on the follower/followed pair — check before insert, return existing if present).
- Prevent self-follow (enforced at service level for `MemberFollow`; `TopicFollow` has no self-follow risk since profile and topic are different entities).
- **Feed scaffolding**: provide initial query methods that retrieve products launched by followed members or tagged with followed topics. These are retrieval-path stubs that Phase 5's ranking/discovery layer will build on — do not implement ranking, personalization scoring, or snapshot logic here.

### Authorization, integrity, and migrations

- Reuse `require_verified_role("member")` for all voting, commenting, reporting, and follow actions (verified email required for every authenticated actor — established in Phase 3).
- Reuse `require_verified_role("reviewer", "admin")` for report queue, assignment, and resolution endpoints.
- Use `get_optional_current_user` for public read paths (e.g., viewing comments on a product as a visitor).
- Enforce ownership checks for comment deletion (`assert_owner` against `comment.profile_id`).
- Vote concurrency: use `begin_nested()` + `IntegrityError` recovery for race-safe vote writes; the DB unique constraint is the last line of defense.
- Add a **forward-only** Alembic migration only if schema changes are needed (e.g., adding a soft-delete column to comments if that design is chosen, or new indexes). Never modify existing applied migrations (`1aa8bf86d9fb`, `8a14589011c8`, `b1f7c2d4a9e0`, or any Phase 3 migration).
- Rate limiting and abuse controls for voting/commenting/reporting endpoints are Phase 7 — provide the endpoints and guards now, hardening comes later.

### Tests

- Unit tests for the report-status transition policy (valid vs. illegal transitions).
- Integration/API tests for:
  - Voting: cast vote, unvote, duplicate vote rejection, self-vote rejection, voting on embargoed/invisible product rejection.
  - Comments: create top-level comment, create reply, reply-to-reply-from-different-product rejection, list threaded comments, delete own comment, delete another's comment rejection.
  - Reports: report product, report comment, duplicate open report rejection, staff queue ordering (oldest first), assignment, resolve/dismiss transitions, illegal transition rejection.
  - Follows: follow/unfollow member, follow/unfollow topic, idempotent follow, self-follow rejection, list followed entities.
  - Feed: retrieval of products by followed members/topics (stub query returns expected results).
- Cover failure paths: unauthorized role, unverified email, ownership violation, voting on invisible product, illegal report transition.
- Audit: verify `StaffAction` and `AuditLog` records are persisted for report assignment and resolution.

### Acceptance criteria

- Vote integrity is transaction-safe under concurrent writes: the DB unique constraint and service-level `begin_nested()`/`IntegrityError` recovery ensure one vote per member per product, and self-voting is rejected.
- Comments support threaded replies with same-product enforcement on reply parent, and owner-only deletion.
- Reports appear in staff moderation surfaces: the report queue lists open/in-review reports oldest first, and reviewer/admin can assign and resolve/dismiss them with audit records persisted.
- Report lifecycle transitions are policy-safe and test-covered: the transition policy in `community/policy.py` is the single source of truth, and illegal transitions are rejected and tested.
- Follows (members and topics) are idempotent at the service level, and followed-entity feed retrieval paths are stable for later ranking expansion (Phase 5).
- All member interaction endpoints require a verified email; all staff moderation endpoints require reviewer/admin role with verified email.
- Interaction endpoints and services are delivered under the existing module boundaries (`src/community/`, `src/topics/`, `src/users/`).

## References

- Phase source: `context/phases.md` (Phase 4)
- Client brief: `context/docs/plans/01-client-brief.md` (Voting and comments; Notifications; The front page)
- Project overview: `context/project-overview.md` (Voting, Comments, and Reporting; Discovery, Ranking, and Topic Views)
- Coding standards: `context/coding-standards.md` (Services, Pydantic, SQLAlchemy / Alembic, Security, Error Handling)
- Architecture playbook: `context/backend-architecture-playbook.md`
- Prior phase spec: `context/features/03-phase-3-product-submission-moderation-workflow-spec.md`
- Implementation modules: `backend/src/community/` (models exist, rest empty), `backend/src/topics/` (models + crud exist, rest empty), `backend/src/users/` (fully implemented including `MemberFollowService`), `backend/src/products/policy.py` (transition policy pattern to mirror), `backend/src/staff/` (models exist — enums to extend), `backend/src/core/dependencies.py` (auth guards), `backend/src/shared/base_model.py` (mixins), `backend/src/main.py` (router registration)
- AI interaction/workflow: `context/ai-interaction.md`

## Notes

- This project does not use the `phase-N-complete` git-tag convention referenced by the generic spec workflow (there is no `context/git-conventions.md` and no phase tags exist). Prior-phase completion was verified by artifact presence: Phase 1 models + Alembic baseline; Phase 2 auth service and guards in `src/core/dependencies.py`; Phase 3 product/moderation services, `policy.py`, launch scheduling, and audit logging (commits `baa29e6`, `55dd055`).
- The agent instruction file is `AGENTS.md`. It contains no "five business rules" and no session/order data — that generic workflow requirement does not apply to Launchpad. The equivalent invariants preserved by this phase are: one vote per member per product, no self-voting, and the report target-match XOR constraint (exactly one of `target_product_id`/`target_comment_id` set per `target_type`).
- The `Vote` model has no value/weight column — it is a pure upvote. "Unvote" is a hard delete of the row; there is no toggle-from-upvote-to-downvote concept. If downvotes are ever needed, that would be a schema change in a future phase.
- The `Comment` model has no soft-delete column (`is_deleted`). This spec defaults to hard delete with cascade to replies. If soft-delete is preferred (to preserve threaded context after a parent is removed), that requires a forward migration adding a boolean column and service-level filtering — decide during implementation.
- `MemberFollow` and `TopicFollow` have no DB unique constraint on the (follower, followed) pair — idempotency is service-layer (check existing before insert). This matches the existing `MemberFollowService` pattern. If race conditions become a concern, a unique constraint + `IntegrityError` recovery can be added in a forward migration.
- Vote/comment/report events can trigger notifications (e.g., founder notified on comment, reporter notified on report resolution). `Notification.event_type` is a free `String(50)` (not an enum), and `NotificationPreference.comment_alert_enabled` already exists. Emit the notification event stub/hook here; full email/in-app delivery and preference enforcement is Phase 6.
- `StaffAction.metadata` is the Python attribute `metadata_json` (the column is named `metadata`) — keep this mapping consistent when writing audit records.
- Public listings, trending ranking, search, historical snapshot freezing, and personalized feed refinement are Phase 5 — Phase 4 supplies only the interaction endpoints, report moderation flow, follow relationships, and feed retrieval-path stubs.
- Staff admin tools (suspend member, takedown product, feature product) and full abuse detection/rate limiting are Phase 7 — Phase 4 delivers the report pipeline that feeds into moderation but not the broader admin surface.
- Expected git workflow: branch `phase-4-voting-comments-reporting-feed-foundations`, merge to `main`, then mark the phase complete in `context/current-feature.md`.
