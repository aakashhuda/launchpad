-- Phase 1 role seed.
-- Run against the Launchpad database, e.g.:
--   psql "postgresql://postgres:postgres@localhost:5432/launchpad_dev" -f backend/scripts/seed_roles.sql
-- Idempotent: re-running refreshes name/permissions in place.
-- Requires PostgreSQL 13+ for gen_random_uuid().

INSERT INTO roles (role_uuid, name, slug, permissions)
VALUES
    (
        gen_random_uuid(),
        'Member',
        'member',
        '{"vote": true, "comment": true, "follow": true, "report": true}'::jsonb
    ),
    (
        gen_random_uuid(),
        'Founder',
        'founder',
        '{"vote": true, "comment": true, "follow": true, "report": true, "submit_product": true}'::jsonb
    ),
    (
        gen_random_uuid(),
        'Reviewer',
        'reviewer',
        '{"moderate_submissions": true, "moderate_reports": true}'::jsonb
    ),
    (
        gen_random_uuid(),
        'Admin',
        'admin',
        '{"moderate_submissions": true, "moderate_reports": true, "manage_users": true, "takedown_products": true, "feature_products": true, "manage_roles": true}'::jsonb
    )
ON CONFLICT (slug) DO UPDATE
    SET name = EXCLUDED.name,
        permissions = EXCLUDED.permissions;
