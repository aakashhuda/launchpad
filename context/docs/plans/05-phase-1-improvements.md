# 05 — Phase 1 Improvements

**Status:** In Progress
**Branch:** `feature/phase-1-improvements`
**Source prompt:** `context/docs/prompts/02-phase-1-improvements.md`

## Goal

Consolidate the Phase 1/2 baseline before product phases begin: align docs with
the `Profile` entity, adopt an OOP service-class convention, split Pydantic
schemas into Create/Update/Read, centralise validation in schemas, seed roles,
and extend signup to member/founder (including the confirmation path that adds a
second profile).

## Confirmed decisions

1. **Multiple profiles per user.** A user may hold more than one profile
   (member + founder). Requires a forward migration dropping
   `UNIQUE(profiles.user_id)` and an API shape change (`/users/me` returns a
   `profiles` list).
2. **Account -> Profile rename includes phase/spec titles.**
3. `config.py` needs no change — `pydantic-settings` resolves `secret_key` from
   `SECRET_KEY` case-insensitively; `env.str("SECRET_KEY")` is unnecessary.

## Changes

### Context docs

- `project-overview.md`: rename "A) Accounts & Authentication" -> "A) Profiles &
  Authentication"; replace the stale `app/` directory tree with the current
  `backend/src/` modular layout.
- `phases.md`, `docs/plans/02-backend-implementation-phases.md`, and
  `features/02-phase-2-...-spec.md`: rename the Phase 2 title
  "Account Lifecycle" -> "Profile Lifecycle".
- `coding-standards.md` and `backend-architecture-playbook.md`: document the
  service-class convention and the Create/Update/Read schema convention.

### Data model

- `src/users/models.py`: `User.profile` -> `User.profiles` (ordered by id);
  drop `unique=True` on `Profile.user_id`.
- New Alembic migration (forward-only) dropping the `profiles_user_id_key`
  unique constraint.

### Users module

- `crud.py`: split user/profile creation; add `get_user_by_phone`,
  `get_profile_by_user_and_role`, `list_profiles_by_user`.
- `schemas.py`: `UserCreate/Update/Read`, `ProfileCreate/Update/Read`,
  `RoleRead`, `UserWithProfilesRead`.
- `service.py`: `UserService`, `RoleService`, `ProfileService`,
  `MemberFollowService` — each constructed with a `Session`.

### Auth module

- `schemas.py`: `SignupRequest` gains `role` (`SignupRole` = member|founder),
  optional `phone_number`, and `confirm_add_profile`; validators for email,
  phone, and password.
- `service.py`: `AuthService`, `RefreshTokenService`, `GoogleSignInService`.
  `AuthService.signup` enforces:
  - role is exactly member or founder;
  - email/phone uniqueness;
  - if the email exists (email/password account), the password must match;
  - if a profile for the requested role already exists -> 409;
  - if the user holds the other profile and `confirm_add_profile` is false ->
    409 instructing the caller to confirm; `true` adds the second profile.

### Roles seed

- `backend/scripts/seed_roles.sql`: idempotent upsert of member, founder,
  reviewer, admin with permissions JSON.

### Guards

- `src/core/dependencies.py`: `require_role` passes when any of the user's
  profiles carries a matching role.

### Tests

- Update existing tests for the `profiles` list shape.
- Add signup tests: founder signup, invalid role, duplicate-role conflict,
  confirmation path, phone uniqueness.

## Out of scope

- Per-profile "active identity" selection (tokens stay user-scoped).
- Business logic for products/community/topics/notifications/staff (empty
  scaffolds; later phases).
