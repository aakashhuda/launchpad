"""add staff governance (user suspension, featured products)

Revision ID: f7a1b2c3d4e5
Revises: e5b6c7d8f9a0
Create Date: 2026-10-17 00:00:00.000000

Phase 7 staff tools. The staff enum member additions (``StaffActionType``,
``AuditEventType``, ``AuditEntityType``, ``StaffTargetType``) are type-only
because those columns are declared with ``native_enum=False`` (VARCHAR-backed),
so no DDL is required for them. This migration adds the user suspension columns
and the ``featured_products`` table.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f7a1b2c3d4e5"
down_revision: Union[str, None] = "e5b6c7d8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.add_column("users", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("suspension_reason", sa.Text(), nullable=True))
    op.create_check_constraint("ck_users_status", "users", "status IN ('active', 'suspended')")

    op.create_table(
        "featured_products",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("featured_product_uuid", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("featured_by_profile_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["featured_by_profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("featured_product_uuid"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index("featured_products_idx_0", "featured_products", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("featured_products_idx_0", table_name="featured_products")
    op.drop_table("featured_products")
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_column("users", "suspension_reason")
    op.drop_column("users", "suspended_at")
    op.drop_column("users", "status")
