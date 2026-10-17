# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Backend CI pipeline (`.github/workflows/backend-ci.yml`): ruff, black, isort,
  mypy, Alembic migration apply + drift check, OpenAPI compatibility check, and
  the unit + integration test suite on every PR and on `main`.
- API compatibility and versioning policy (`context/api-versioning-policy.md`)
  with a committed OpenAPI baseline (`backend/openapi.json`) enforced in CI.
- Release playbook (`context/release-playbook.md`) covering the release
  checklist, environment promotion, rollback, and tagging conventions.
- Operational runbook (`context/operational-runbook.md`).

### Fixed

- Declared the `products_search_idx` full-text index in the `Product` model so
  ORM metadata matches the migrated schema (`alembic check` is clean).
- Configured mypy (pydantic plugin + `jose`/`passlib` overrides) so `mypy src`
  passes.

### Notes

- Phase-by-phase build history lives in `context/current-feature.md`. The
  backend modules (auth, products, community, topics, notifications, discovery,
  staff) were implemented across Phases 1–7 prior to this changelog being added.
