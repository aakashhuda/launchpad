"""add founder_exports tracking table

Revision ID: e5b6c7d8f9a0
Revises: c2a9f1e4d7b3
Create Date: 2026-10-17 00:00:00.000000

The Phase 6 ``Notification.event_type`` conversion to ``NotificationEventType``
is type-only: the column is declared with ``native_enum=False`` and therefore
still renders as ``VARCHAR(50)``, so no DDL is required for it. This migration
only adds the founder-export job bookkeeping table.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5b6c7d8f9a0"
down_revision: Union[str, None] = "c2a9f1e4d7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "founder_exports",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("export_uuid", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_profile_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="preparing", nullable=False),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("export_uuid"),
    )
    op.create_index(
        "founder_exports_idx_0", "founder_exports", ["product_id", "created_at"], unique=False
    )
    op.create_index(
        "founder_exports_idx_1",
        "founder_exports",
        ["requested_by_profile_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("founder_exports_idx_1", table_name="founder_exports")
    op.drop_index("founder_exports_idx_0", table_name="founder_exports")
    op.drop_table("founder_exports")
