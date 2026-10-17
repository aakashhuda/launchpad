from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationPreference,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- preferences ---


def get_preference(db: Session, profile_id: int) -> NotificationPreference | None:
    return db.scalar(
        select(NotificationPreference).where(NotificationPreference.profile_id == profile_id)
    )


def create_preference(db: Session, *, profile_id: int, **flags: object) -> NotificationPreference:
    preference = NotificationPreference(profile_id=profile_id, **flags)
    db.add(preference)
    db.flush()
    return preference


def update_preference(
    db: Session, preference: NotificationPreference, **fields: object
) -> NotificationPreference:
    for key, value in fields.items():
        setattr(preference, key, value)
    db.flush()
    return preference


def list_profiles_with_flag(db: Session, flag: str) -> list[int]:
    """Profile ids whose preference ``flag`` (a boolean column name) is enabled."""
    column = getattr(NotificationPreference, flag)
    return list(db.scalars(select(NotificationPreference.profile_id).where(column.is_(True))))


# --- notifications ---


def create_notification(
    db: Session,
    *,
    recipient_profile_id: int,
    actor_profile_id: int | None,
    event_type: NotificationEventType,
    payload: dict,
) -> Notification:
    notification = Notification(
        recipient_profile_id=recipient_profile_id,
        actor_profile_id=actor_profile_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(notification)
    db.flush()
    return notification


def get_notification(db: Session, notification_id: int) -> Notification | None:
    return db.get(Notification, notification_id)


def list_notifications(
    db: Session, profile_ids: list[int], *, limit: int, offset: int
) -> list[Notification]:
    if not profile_ids:
        return []
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.recipient_profile_id.in_(profile_ids))
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def count_unread(db: Session, profile_ids: list[int]) -> int:
    if not profile_ids:
        return 0
    return int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_profile_id.in_(profile_ids),
                Notification.read_at.is_(None),
            )
        )
        or 0
    )


def mark_read(db: Session, notification: Notification, *, read_at: datetime | None = None) -> None:
    notification.read_at = read_at or _utcnow()
    db.flush()


def mark_all_read(db: Session, profile_ids: list[int]) -> int:
    if not profile_ids:
        return 0
    result = db.execute(
        update(Notification)
        .where(
            Notification.recipient_profile_id.in_(profile_ids),
            Notification.read_at.is_(None),
        )
        .values(read_at=_utcnow())
    )
    db.flush()
    return result.rowcount or 0


# --- deliveries ---


def create_delivery(
    db: Session,
    *,
    notification_id: int,
    channel: NotificationChannel,
    provider: str,
    status: NotificationDeliveryStatus = NotificationDeliveryStatus.PENDING,
) -> NotificationDelivery:
    delivery = NotificationDelivery(
        notification_id=notification_id,
        channel=channel,
        provider=provider,
        status=status,
    )
    db.add(delivery)
    db.flush()
    return delivery


def get_delivery(db: Session, delivery_id: int) -> NotificationDelivery | None:
    return db.get(NotificationDelivery, delivery_id)


def update_delivery(
    db: Session, delivery: NotificationDelivery, **fields: object
) -> NotificationDelivery:
    for key, value in fields.items():
        setattr(delivery, key, value)
    db.flush()
    return delivery
