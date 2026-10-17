# API Compatibility & Versioning Policy

Launchpad's HTTP API is versioned from day one under `/api/v1`
(`backend/src/core/constants.py::API_V1_PREFIX`). This policy defines what may
change within a version and how breaking changes are introduced.

## Additive changes (allowed on `/api/v1`)

These do not break existing clients and may land directly:

- Adding a new endpoint.
- Adding a new **optional** request field, or a new optional query parameter.
- Adding a new field to a response body.
- Adding a new value to an enum that clients are expected to tolerate.
- Relaxing validation (e.g. a field that was required becomes optional).

After an additive change, refresh the committed OpenAPI baseline (see below).

## Breaking changes (require a new version or deprecation window)

These break existing clients and must **not** land silently on `/api/v1`:

- Removing or renaming a response field, request field, or endpoint.
- Changing a field's type (e.g. `int` → `string`).
- Making a previously optional request field required.
- Removing an enum value clients could receive.
- Changing the semantics or status code of an existing response.

Introduce breaking changes either by:

1. Adding a **new version segment** (e.g. `/api/v2`) alongside the existing one
   and migrating clients over time, or
2. Shipping an explicit **deprecation window**: announce the change, keep the
   old behavior working for a documented period, then remove it in a later
   release.

## Enforcement

The committed `backend/openapi.json` is the contract baseline. CI regenerates
the schema and runs `scripts/openapi_compat.py`, which fails the build on
breaking changes (removed/renamed fields, type changes, removed endpoints,
newly-required fields, removed enum values). Purely additive changes are
accepted once the baseline is regenerated and committed.

Refresh the baseline deliberately:

```bash
cd backend
python scripts/export_openapi.py
python scripts/openapi_compat.py openapi.json openapi.json   # sanity: no changes
```
