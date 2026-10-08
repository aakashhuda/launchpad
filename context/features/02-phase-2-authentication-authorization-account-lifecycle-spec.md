# Phase 2 — Authentication, Authorization & Account Lifecycle

## Overview

Phase 2 establishes the production authentication baseline for Launchpad: JWT-based auth with access/refresh tokens, the email/password account lifecycle (signup, email verification, forgot/reset/change password), a Google sign-in integration seam, and role-aware authorization guards. It completes the `src/auth` and `src/users` identity modules, hardens the existing bcrypt/JWT utilities in `src/core/security.py`, and adds authorization dependencies in `src/core/dependencies.py`. Email delivery itself runs through the existing `src/integrations/email.py` stub and is fully wired in Phase 6.

## Requirements

- Implement `src/auth/router.py`, `src/auth/service.py`, `src/auth/schemas.py` exposing endpoints under `/api/v1/auth`:
  - `POST /signup` — email/password registration: hash password (bcrypt), create `User` + `Profile` + default `Role` (member), generate a unique profile `slug`, issue access + refresh tokens, trigger email verification via the email seam.
  - `POST /login` — email/password login: verify credentials, update `User.last_login_role`, issue tokens.
  - `POST /refresh` — validate refresh token, rotate it, issue a new access token.
  - `POST /logout` — revoke the caller's refresh token(s).
  - `POST /verify-email` — validate the email-verification token, set `User.email_verified = True`.
  - `POST /forgot-password` — issue a signed, time-bound reset token; send via the email seam; return a generic response (no account enumeration).
  - `POST /reset-password` — validate the reset token, set the new password hash, invalidate existing refresh tokens.
  - `POST /change-password` — authenticated; email/password users only; requires the current password; rotates tokens.
- Implement a Google sign-in seam: `POST /auth/google` — verify the Google ID token (signature, audience, expiry), resolve or create a `User` with `auth_provider=GOOGLE` and `auth_provider_id` = Google `sub`, and issue tokens. Configure the Google client ID via settings; defer real OAuth client provisioning but keep the handler production-shaped.
- Harden `src/core/security.py`:
  - Add refresh-token creation with bounded expiry (`refresh_token_expire_days`) distinct from access tokens (`access_token_expire_min`).
  - Add token type/claim discrimination (access vs refresh vs reset vs email-verification) so tokens cannot be used across purposes.
  - Add a signed, time-bound reset/verification token issuer + verifier (built on the existing `jose` JWT setup).
  - Keep and reuse the existing `hash_password` / `verify_password` / `create_access_token` / `decode_token`.
- Implement identity CRUD + service in `src/users/` (`crud.py`, `service.py`, `schemas.py`): user/profile/role lookups, profile creation with `slug` uniqueness, and current-user response shaping. Provide a minimal `GET /api/v1/users/me` and a public `GET /api/v1/users/{slug}` profile endpoint.
- Implement authorization dependencies in `src/core/dependencies.py`:
  - `get_current_user` — decode the access token, load the `User`, reject invalid/expired tokens.
  - `get_current_active_user` and an email-verified enforcement helper where required.
  - `require_role(...)` — role-based guard leveraging `LastLoginRole` / `Role.permissions` for member/founder/reviewer/admin.
  - An ownership-check helper for resource-scoped endpoints (used by later phases).
- Token revocation strategy: choose and document blacklist-vs-rotation. Recommended: refresh-token rotation with persisted refresh tokens so logout, password change, and compromise can invalidate them. Add a **forward** Alembic migration for any auth persistence required (e.g., a `refresh_tokens` table) — migration-driven and forward-only; never modify the existing `1aa8bf86d9fb` baseline.
- Enforce auth-specific policies:
  - Passwords are never logged or returned in responses.
  - No account enumeration on `forgot-password` / `verify-email` (constant, generic responses).
  - Google-authenticated users (`auth_provider != EMAIL`) cannot use email/password flows and have no password set; `change-password` is unavailable to them.
  - `email_verified` gating is ready here (the brief requires confirmed emails for voting; enforcement at vote time lands in Phase 4).
- Configuration: add Google OAuth client ID/secret and any token settings to `src/core/config.py` via environment variables; keep secrets out of the repo (extend `.env.example` only).
- Tests: unit tests for security helpers (hash/verify, token create/decode/expiry, token-type discrimination) and API tests for each auth flow covering success and failure paths (bad credentials, expired token, wrong token type, unverified email, forbidden role).

### Acceptance criteria

- Auth flows (signup, login, refresh, logout, verify-email, forgot/reset, change-password, Google seam) work end-to-end and are covered by tests for both success and failure paths.
- Privileged/restricted endpoints reject unauthenticated and forbidden actors correctly via role/ownership guards.
- Security checks cover JWT validation, password hashing, and reset/verification flows.
- Refresh tokens are rotatable and revocable; the chosen revocation strategy is documented.
- Email verification sets `User.email_verified` and the flow is usable (email transport stubbed, seam correct).
- No secrets are committed; passwords and tokens are not leaked in logs or responses.

## References

- Phase source: `context/phases.md` (Phase 2)
- Client brief: `context/docs/plans/01-client-brief.md` (Accounts section)
- Project overview: `context/project-overview.md` (Auth Flow, Users)
- Coding standards: `context/coding-standards.md` (Security, Auth, Pydantic, SQLAlchemy/Alembic)
- Architecture playbook: `context/backend-architecture-playbook.md` (Security Baseline, Reliability Patterns)
- Implementation modules: `backend/src/auth/`, `backend/src/users/models.py`, `backend/src/core/security.py`, `backend/src/core/config.py`, `backend/src/core/dependencies.py`, `backend/src/core/database.py`, `backend/src/integrations/email.py`
- AI interaction/workflow: `context/ai-interaction.md`

## Notes

- This project does not use the `phase-N-complete` git-tag convention referenced by the generic spec workflow (there is no `context/git-conventions.md` and no phase tags exist). Prior-phase completion was verified by artifact presence: Phase 1 deliverables (SQLAlchemy models + Alembic baseline `1aa8bf86d9fb`, DB verified in sync) exist and pass `alembic check`.
- Email delivery is stubbed (`src/integrations/email.py`); real provider wiring + retry resilience is Phase 6. Implement the verification/reset email seams now so Phase 6 only swaps the transport.
- Rate limiting and anomaly detection for auth endpoints are deferred to Phase 7 (hardening); design auth endpoints to be rate-limit-ready.
- The key open design decision is the revocation approach (Redis blacklist vs persisted refresh-token rotation). Recommendation: persisted rotation in PostgreSQL to keep Redis non-authoritative per the playbook.
- Rich public-profile fields (avatar, bio, links) are not on the current `Profile` model; if needed for account lifecycle, add them via a forward migration in this phase, otherwise defer. Minimal profile retrieval (`/users/me`, `/users/{slug}`) is in scope.
- Expected git workflow: branch `phase-2-authentication-authorization-account-lifecycle`, merge to `main`, then mark complete in `context/current-feature.md`.
- Security is company-critical per the client brief ("Leaking either one ends the company"); treat password secrecy and pre-launch product secrecy as hard constraints throughout.
