from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base_model import Base, CreatedAtMixin, TimestampMixin, enum_values

if TYPE_CHECKING:
    from src.community.models import Comment, Vote
    from src.topics.models import Topic
    from src.users.models import Profile


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    LIVE = "live"
    INACTIVE = "inactive"


class LaunchState(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ExportStatus(str, enum.Enum):
    PREPARING = "preparing"
    READY = "ready"
    FAILED = "failed"


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    product_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    one_line_pitch: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    logo_url: Mapped[str] = mapped_column(String(255), nullable=False)
    screenshot_urls: Mapped[list[str] | None] = mapped_column(ARRAY(String(255)))
    website_url: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=ProductStatus.DRAFT,
        server_default=text("'draft'"),
    )

    profile: Mapped[Profile] = relationship(back_populates="products")
    product_topics: Mapped[list[ProductTopic]] = relationship(back_populates="product")
    product_launch: Mapped[ProductLaunch] = relationship(back_populates="product", uselist=False)
    submissions: Mapped[list[Submission]] = relationship(back_populates="product")
    votes: Mapped[list[Vote]] = relationship(back_populates="product")
    comments: Mapped[list[Comment]] = relationship(back_populates="product")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'scheduled', 'live', 'inactive')",
            name="ck_products_status",
        ),
        Index("products_idx_1", "status", "created_at"),
        Index("products_idx_2", "name"),
        # Full-text search index created by migration c2a9f1e4d7b3 via raw SQL.
        # Declared here using PostgreSQL's normalized expression form so ORM
        # metadata and the migrated schema agree and ``alembic check`` is clean.
        Index(
            "products_search_idx",
            text("to_tsvector('english'::regconfig, (name::text || ' '::text) || description)"),
            postgresql_using="gin",
        ),
    )


class ProductTopic(CreatedAtMixin, Base):
    __tablename__ = "product_topics"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    product_topic_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="product_topics")
    topic: Mapped[Topic] = relationship()

    __table_args__ = (
        UniqueConstraint("product_id", "topic_id", name="uq_product_topics_product_topic"),
    )


class ProductLaunch(TimestampMixin, Base):
    __tablename__ = "product_launches"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    product_launch_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    launch_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[LaunchState] = mapped_column(
        Enum(
            LaunchState,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=LaunchState.SCHEDULED,
        server_default=text("'scheduled'"),
    )
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[Product] = relationship(back_populates="product_launch")

    __table_args__ = (
        CheckConstraint(
            "state IN ('scheduled', 'live', 'archived', 'cancelled')",
            name="ck_product_launches_state",
        ),
        Index("product_launches_idx_0", "launch_date", "state"),
    )


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    submission_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(
            SubmissionStatus,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=SubmissionStatus.DRAFT,
        server_default=text("'draft'"),
    )
    reviewed_by_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[Profile] = relationship(
        back_populates="submissions", foreign_keys="Submission.profile_id"
    )
    product: Mapped[Product] = relationship(back_populates="submissions")
    reviewed_by_profile: Mapped[Profile | None] = relationship(
        foreign_keys="Submission.reviewed_by_profile_id"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'in_review', 'approved', 'rejected', 'changes_requested')",
            name="ck_submissions_status",
        ),
        Index("submissions_idx_0", "status", "created_at"),
        Index("submissions_idx_1", "product_id", "created_at"),
    )


class FounderExport(TimestampMixin, Base):
    """A founder-requested export of their product's dashboard data.

    The export is generated asynchronously: a row is created in ``PREPARING``
    when the founder requests it, a background job writes the artifact and flips
    it to ``READY`` (or ``FAILED``), and the founder is notified on completion.
    This is job bookkeeping, not analytics — the artifact itself is the file at
    ``artifact_path``.
    """

    __tablename__ = "founder_exports"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    export_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ExportStatus] = mapped_column(
        Enum(
            ExportStatus,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=ExportStatus.PREPARING,
        server_default=text("'preparing'"),
    )
    artifact_path: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)

    product: Mapped[Product] = relationship()
    requested_by_profile: Mapped[Profile] = relationship()

    __table_args__ = (
        Index("founder_exports_idx_0", "product_id", "created_at"),
        Index("founder_exports_idx_1", "requested_by_profile_id", "created_at"),
    )


class FeaturedProduct(CreatedAtMixin, Base):
    """A staff-featured product promoted on the front page.

    At most one row per product (``product_id`` is unique); unfeaturing deletes
    the row rather than toggling a flag. ``created_at`` is when it was featured
    and ``ends_at`` optionally expires the feature. Written only by the admin
    feature endpoint — founders cannot feature their own products.
    """

    __tablename__ = "featured_products"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    featured_product_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    featured_by_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[Product] = relationship()

    __table_args__ = (Index("featured_products_idx_0", "created_at"),)
