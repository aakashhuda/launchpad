from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Identity, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.db.models.user import Profile


class StaffAction(CreatedAtMixin, Base):
    __tablename__ = "staff_actions"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    staff_action_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    actor_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    actor_profile: Mapped[Profile] = relationship()

    __table_args__ = (
        Index("staff_actions_idx_0", "actor_profile_id", "created_at"),
        Index("staff_actions_idx_1", "target_type", "target_id", "created_at"),
    )


class AuditLog(CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    audit_log_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    actor_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)

    actor_profile: Mapped[Profile | None] = relationship()

    __table_args__ = (
        Index("audit_logs_idx_0", "event_type", "created_at"),
        Index("audit_logs_idx_1", "entity_type", "entity_id", "created_at"),
        Index("audit_logs_idx_2", "actor_profile_id", "created_at"),
    )
