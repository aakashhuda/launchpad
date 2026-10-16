from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base_model import Base, CreatedAtMixin, TimestampMixin, enum_values

if TYPE_CHECKING:
    from src.products.models import Product
    from src.users.models import Profile


class ReportTargetType(str, enum.Enum):
    PRODUCT = "product"
    COMMENT = "comment"


class ReportReason(str, enum.Enum):
    SPAM = "spam"
    ABUSE = "abuse"
    MISLEADING = "misleading"
    COPYRIGHT = "copyright"
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class Vote(CreatedAtMixin, Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    vote_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    profile: Mapped[Profile] = relationship(back_populates="votes")
    product: Mapped[Product] = relationship(back_populates="votes")

    __table_args__ = (
        UniqueConstraint("product_id", "profile_id", name="uq_votes_product_profile"),
        Index("votes_idx_0", "product_id", "created_at"),
        Index("votes_idx_1", "profile_id", "created_at"),
    )


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    comment_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    parent_comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    profile: Mapped[Profile] = relationship(back_populates="comments")
    product: Mapped[Product] = relationship(back_populates="comments")
    parent_comment: Mapped[Comment | None] = relationship(
        back_populates="replies", remote_side="Comment.id"
    )
    # passive_deletes defers to the DB's ON DELETE CASCADE so deleting a parent
    # removes its replies instead of orphaning them (nullifying parent_comment_id).
    replies: Mapped[list[Comment]] = relationship(
        back_populates="parent_comment", passive_deletes=True
    )

    __table_args__ = (
        Index("comments_idx_0", "product_id", "created_at"),
        Index("comments_idx_1", "parent_comment_id", "created_at"),
    )


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    report_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    reporter_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    target_type: Mapped[ReportTargetType] = mapped_column(
        Enum(
            ReportTargetType,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    target_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    target_comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE")
    )
    reason: Mapped[ReportReason] = mapped_column(
        Enum(
            ReportReason,
            native_enum=False,
            length=50,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(
            ReportStatus,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=ReportStatus.OPEN,
        server_default=text("'open'"),
    )
    assigned_reviewer_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    resolved_by_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reporter_profile: Mapped[Profile] = relationship(
        back_populates="reports_made", foreign_keys="Report.reporter_profile_id"
    )
    target_product: Mapped[Product | None] = relationship(foreign_keys="Report.target_product_id")
    target_comment: Mapped[Comment | None] = relationship(foreign_keys="Report.target_comment_id")
    assigned_reviewer_profile: Mapped[Profile | None] = relationship(
        foreign_keys="Report.assigned_reviewer_profile_id"
    )
    resolved_by_profile: Mapped[Profile | None] = relationship(
        foreign_keys="Report.resolved_by_profile_id"
    )

    __table_args__ = (
        CheckConstraint("target_type IN ('product', 'comment')", name="ck_reports_target_type"),
        CheckConstraint(
            "reason IN ('spam', 'abuse', 'misleading', 'copyright', 'other')",
            name="ck_reports_reason",
        ),
        CheckConstraint(
            "status IN ('open', 'in_review', 'resolved', 'dismissed')",
            name="ck_reports_status",
        ),
        CheckConstraint(
            "(target_type = 'product' AND target_product_id IS NOT NULL AND target_comment_id IS NULL) "
            "OR (target_type = 'comment' AND target_product_id IS NULL AND target_comment_id IS NOT NULL)",
            name="ck_reports_target_match",
        ),
        Index("reports_idx_0", "status", "created_at"),
        Index("reports_idx_1", "assigned_reviewer_profile_id", "status"),
    )
