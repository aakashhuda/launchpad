from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin
from app.db.models.enums import NotificationChannel, NotificationDeliveryStatus, enum_values

if TYPE_CHECKING:
    from app.db.models.user import Profile


class NotificationPreference(TimestampMixin, Base):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    preference_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    email_verification_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    password_reset_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    moderation_outcome_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    launch_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    product_live_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    comment_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    daily_top_five_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    weekly_best_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    profile: Mapped[Profile] = relationship(back_populates="notification_preference")


class Notification(CreatedAtMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    notification_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    recipient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    actor_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipient_profile: Mapped[Profile] = relationship(
        back_populates="notifications_received",
        foreign_keys="Notification.recipient_profile_id",
    )
    actor_profile: Mapped[Profile | None] = relationship(
        foreign_keys="Notification.actor_profile_id"
    )
    deliveries: Mapped[list[NotificationDelivery]] = relationship(back_populates="notification")

    __table_args__ = (
        Index("notifications_idx_0", "recipient_profile_id", "created_at"),
        Index("notifications_idx_1", "recipient_profile_id", "read_at"),
    )


class NotificationDelivery(TimestampMixin, Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    delivery_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        Enum(
            NotificationDeliveryStatus,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=NotificationDeliveryStatus.PENDING,
        server_default=text("'pending'"),
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notification: Mapped[Notification] = relationship(back_populates="deliveries")

    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'in_app')", name="ck_notification_deliveries_channel"
        ),
        CheckConstraint(
            "status IN ('pending', 'retrying', 'sent', 'failed', 'dropped')",
            name="ck_notification_deliveries_status",
        ),
        Index("notification_deliveries_idx_0", "status", "next_retry_at"),
        Index("notification_deliveries_idx_1", "notification_id", "status"),
    )
