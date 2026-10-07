from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Identity, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.user import Profile


class Topic(TimestampMixin, Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    topic_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    topic_follows: Mapped[list[TopicFollow]] = relationship(back_populates="topic")

    __table_args__ = (Index("topics_idx_0", "id", "topic_uuid", "slug"),)


class TopicFollow(CreatedAtMixin, Base):
    __tablename__ = "topic_follows"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    topic_follow_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )

    profile: Mapped[Profile] = relationship(back_populates="topic_follows")
    topic: Mapped[Topic] = relationship(back_populates="topic_follows")

    __table_args__ = (
        Index("topic_follows_idx_0", "profile_id", "created_at"),
        Index("topic_follows_idx_1", "topic_id", "created_at"),
    )
