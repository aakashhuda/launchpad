# Phase 3 — Product Submission & Moderation Workflow

## Overview

Phase 3 implements Launchpad's core founder-to-reviewer publishing workflow: founders draft and submit products, reviewers approve/reject/request changes, and approved products get a founder-chosen launch day governed by a per-founder/day cap, a pre-launch embargo, and a post-launch edit lock. The `Product`, `Submission`, `ProductLaunch`, and `ProductTopic` models already exist from Phase 1, and the `products` and `staff` module scaffolds (`crud.py`, `service.py`, `schemas.py`, `router.py`) are currently empty — this phase fills them following the established `<Model>Service` and `Create`/`Update`/`Read` conventions. The phase also introduces a single-source-of-truth state-transition policy layer and writes `StaffAction` + `AuditLog` records for every moderation action.

## Requirements

### Domain services, schemas, and controllers

- Implement the empty scaffolds under `backend/src/products/` and `backend/src/staff/` using the project conventions: one `<Model>Service` class per model constructed with a `Session` (e.g. `ProductService`, `SubmissionService`, `ProductLaunchService`, `ProductTopicService` in `src/products/service.py`; `StaffActionService`, `AuditLogService` in `src/staff/service.py`), raw queries in `crud.py`, and split `Create`/`Update`/`Read` Pydantic schemas per entity.
- Expose endpoints under the already-mounted `/api/v1/products` and `/api/v1/staff` routers; use `status.HTTP_*` constants and `HTTPException`; no query logic in routers.
- Product draft create/update: `name`, `one_line_pitch`, `description`, `logo_url`, `screenshot_urls`, `website_url`, and up to **three** topics (via `product_topics`); a product starts with `status = draft`.
- Submissions: model the founder's submission record against a product, using the existing `SubmissionStatus` (`draft`, `in_review`, `approved`, `rejected`, `changes_requested`) and recording `reviewed_by_profile_id`, `review_note`, `reviewed_at` on decisions.

### State transition policy layer

- Create a single source of truth for lifecycle rules (e.g. a policy module/object in the `products` domain) declaring the allowed transitions for `SubmissionStatus` and `ProductStatus`.
- Enforce transitions in the service layer; reject illegal transitions with an appropriate `HTTPException` (409/422) and never mutate state outside the policy.
- Keep review-outcome → product-status effects explicit: approval moves the product to `approved`; rejection and `changes_requested` keep it out of any public visibility.

### Moderation workflow

- Founder can submit a draft for review (`draft` → `in_review`).
- Reviewer queue: list `in_review` submissions **oldest first** (order by `created_at` ascending), paginated.
- Reviewer decisions: approve, reject, or request changes — persisting reviewer identity, note, and timestamp; gated by `require_role("reviewer", "admin")`.
- Ownership: only the owning founder profile may create/update/submit its own products and submissions (enforced via `assert_owner`/profile-ownership checks); only reviewers/admin may decide.

### Launch scheduling & visibility

- After approval, the founder schedules a launch day: create a `ProductLaunch` with `launch_date` and `state = scheduled`, moving the product to `scheduled`.
- The founder may change `launch_date` while still `scheduled`; the date freezes once launched.
- Enforce a **per-founder/day cap** (client brief: two to start) at the service level; model the value as a named constant/config rather than a magic literal.
- Pre-launch embargo: define a visibility predicate (e.g. a `Product`-level "publicly visible" rule) that excludes `draft`/`in_review`/`rejected`/`changes_requested` products and any product whose launch day has not arrived — later listing/search phases must consume this predicate so unreviewed or embargoed products never leak.
- Provide an idempotent service method for `scheduled` → `live` (setting `launched_at` and `state = live`); the automated day scheduler/materialization is Phase 5, so only the seam is delivered now.

### Post-launch edit policy

- After launch (`state = live`), only `description` and links (`website_url`, `screenshot_urls`) remain editable; `name`, `one_line_pitch`, `logo_url`, and topics are locked. Enforce in the service and reject locked-field edits.

### Staff action & audit logging hooks

- Persist a `StaffAction` (actor, `action_type`, `target_type`, `target_id`, reason, metadata) and an `AuditLog` record for every moderation and launch-policy action, including before/after state where applicable.
- Keep logging writes in the same transaction as the action they record; `metadata` maps to the `metadata_json` attribute on `StaffAction`.
- Model action/event types as Python `enum.Enum` classes and reuse existing enums rather than raw strings.

### Authorization, config, and migrations

- Reuse `get_current_user`, `require_role(...)`, `require_verified_email`, and `assert_owner` from `src/core/dependencies.py`; add founder-scoped and reviewer-scoped guards at both dependency and service level.
- Require a **confirmed email for every authenticated actor** (not only voting): all founder actions (create/update/submit/schedule) and reviewer decisions go through a verified-role guard (`require_verified_role`). Visitors (anonymous) are unaffected. A product is publicly visible only when its owner's email is verified, so an unverified owner's product is never enlisted.
- Add any new settings (e.g. launches-per-founder-per-day, launch-window values) to `src/core/config.py` via environment variables; extend `.env.example` only — never commit secrets.
- Add a **forward-only** Alembic migration for any new columns/tables required; never modify `1aa8bf86d9fb_initial_schema`, `8a14589011c8_add_refresh_tokens`, or `b1f7c2d4a9e0_allow_multiple_profiles_per_user`.

### Tests

- Unit tests for the transition policy (valid vs. illegal transitions), the per-day cap, the embargo/visibility predicate, and the post-launch edit policy.
- Integration/API tests for draft create/update, submit-for-review, queue ordering (oldest first), each reviewer decision, schedule + day change before launch, cap enforcement, and `staff_actions`/`audit_logs` persistence.
- Cover failure paths: unauthorized role, ownership violation, cap exceeded, locked-field edit after launch, and illegal state transition.

### Acceptance criteria

- Unreviewed products never appear in public listings: the visibility/embargo predicate excludes `draft`/`in_review`/`rejected`/`changes_requested`, pre-launch products, and products whose owner has not verified their email; it is the enforced path later listing phases use.
- Every non-visitor action requires a verified email: an unverified founder or reviewer is rejected (403) on product and moderation endpoints.
- Lifecycle transitions are policy-safe and test-covered: the transition policy is the single source of truth, and illegal transitions are rejected and tested.
- Launch constraints and edit constraints are enforced at the service level: the per-founder/day cap and the post-launch edit lock are enforced in services with tests.
- Product and moderation domain services and API endpoints are delivered under the module boundaries.
- Reviewer/admin action logs are persisted with actor and timestamp (`staff_actions` + `audit_logs`).

## References

- Phase source: `context/phases.md` (Phase 3)
- Client brief: `context/docs/plans/01-client-brief.md` (Posting a product; Staff tools)
- Initial DB design: `context/docs/plans/03-initial-db-design.md`
- Project overview: `context/project-overview.md` (Product Submission & Moderation; Launch Scheduling & Visibility Rules; Staff actions and audit logs)
- Coding standards: `context/coding-standards.md` (Services, Pydantic, SQLAlchemy / Alembic, Error Handling)
- Architecture playbook: `context/backend-architecture-playbook.md`
- Prior phase spec: `context/features/02-phase-2-authentication-authorization-account-lifecycle-spec.md`
- Implementation modules: `backend/src/products/`, `backend/src/staff/`, `backend/src/users/`, `backend/src/core/dependencies.py`, `backend/src/core/config.py`, `backend/src/main.py`
- AI interaction/workflow: `context/ai-interaction.md`

## Notes

- This project does not use the `phase-N-complete` git-tag convention referenced by the generic spec workflow (there is no `context/git-conventions.md` and no phase tags exist). Prior-phase completion was verified by artifact presence: Phase 1 models + Alembic baseline `1aa8bf86d9fb`; Phase 2 auth service and guards in `src/core/dependencies.py`, refresh-token migration `8a14589011c8`, and the multiple-profiles migration `b1f7c2d4a9e0`.
- The agent instruction file is `AGENTS.md`. It contains no "five business rules" and no session/order data — that generic workflow requirement does not apply to Launchpad. The equivalent invariants preserved by this phase are: pre-launch embargo (nobody sees a product before its launch day), launch quota (two per founder per day to start), and the post-launch edit lock. No-self-voting is Phase 4; rate limiting and abuse controls for these writes are Phase 7.
- Scope boundaries: reporting/comment-report handling is Phase 4; suspend/takedown/feature staff tooling and full admin surfaces are Phase 7. Public listings, trending ranking, search, and historical snapshot freezing are Phase 5 — Phase 3 supplies only the visibility predicate and the launch-activation seam they depend on.
- **Verified email is enforced for every authenticated actor**, not only voting (decided during Phase 3 review). `require_verified_role` composes the existing `require_role` guard with the `email_verified` check and is applied to all product and staff endpoints; identity-only endpoints (e.g. `GET /users/me`) still use `get_current_user` so an unverified user can observe their own status. The visibility predicate additionally hides an unverified owner's product.
- Founder notifications for moderation outcomes (approved/rejected/needs changes) and launch reminders are Phase 6; emit the domain hook/stub here but do not implement the email transport.
- `StaffAction.metadata` is the Python attribute `metadata_json` (the column is named `metadata`); keep this mapping consistent when writing audit records.
- Confirm and centralize the day-cap value (client brief: two to start) as config/constant so it can change without code edits.
- Expected git workflow: branch `phase-3-product-submission-moderation-workflow`, merge to `main`, then mark the phase complete in `context/current-feature.md`.
