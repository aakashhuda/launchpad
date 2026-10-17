"""add discovery day snapshots and product search index

Revision ID: c2a9f1e4d7b3
Revises: b1f7c2d4a9e0
Create Date: 2026-10-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c2a9f1e4d7b3"
down_revision: Union[str, None] = "b1f7c2d4a9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "day_snapshots",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("snapshot_uuid", sa.Uuid(), nullable=False),
        sa.Column("launch_date", sa.Date(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("launch_date"),
        sa.UniqueConstraint("snapshot_uuid"),
    )
    op.create_index("day_snapshots_idx_0", "day_snapshots", ["launch_date"], unique=False)
    op.create_table(
        "day_snapshot_items",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("item_uuid", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("vote_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["day_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_uuid"),
        sa.UniqueConstraint(
            "snapshot_id", "product_id", name="uq_day_snapshot_items_snapshot_product"
        ),
        sa.UniqueConstraint("snapshot_id", "rank", name="uq_day_snapshot_items_snapshot_rank"),
    )
    op.create_index(
        "day_snapshot_items_idx_0", "day_snapshot_items", ["snapshot_id", "rank"], unique=False
    )
    # Expression GIN index backing full-text search over name + description.
    # Uses the built-in 'english' config (no extension required) and must match
    # the expression in src/discovery/crud.py::_search_vector exactly.
    op.execute(
        "CREATE INDEX products_search_idx ON products "
        "USING gin (to_tsvector('english'::regconfig, name || ' ' || description))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX products_search_idx")
    op.drop_index("day_snapshot_items_idx_0", table_name="day_snapshot_items")
    op.drop_table("day_snapshot_items")
    op.drop_index("day_snapshots_idx_0", table_name="day_snapshots")
    op.drop_table("day_snapshots")
