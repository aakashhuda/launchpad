from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base_model import Base, CreatedAtMixin

if TYPE_CHECKING:
    from src.products.models import Product


class DaySnapshot(CreatedAtMixin, Base):
    """Immutable frozen ranking for a closed launch day.

    One row per launch date (uniqueness is the immutability guarantee: a day can
    be frozen exactly once). Rows are write-once — the service layer exposes no
    update or delete path.
    """

    __tablename__ = "day_snapshots"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    snapshot_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    launch_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list[DaySnapshotItem]] = relationship(
        back_populates="snapshot",
        order_by="DaySnapshotItem.rank",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("day_snapshots_idx_0", "launch_date"),)


class DaySnapshotItem(CreatedAtMixin, Base):
    """One ranked product entry within a day snapshot."""

    __tablename__ = "day_snapshot_items"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    item_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("day_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    snapshot: Mapped[DaySnapshot] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "product_id", name="uq_day_snapshot_items_snapshot_product"
        ),
        UniqueConstraint("snapshot_id", "rank", name="uq_day_snapshot_items_snapshot_rank"),
        Index("day_snapshot_items_idx_0", "snapshot_id", "rank"),
    )
