from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.config import settings
from src.integrations import email as email_integration
from src.notifications import crud
from src.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationPreference,
)
from src.notifications.schemas import (
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
)
from src.tasks.retry import RetryPolicy
from src.tasks.scheduler import enqueue_job
from src.users.models import User

# Each client-brief trigger maps to exactly one per-event preference flag. An
# event absent from this map is transactional (e.g. an export the member
# explicitly requested) and is not user-suppressible.
EVENT_PREFERENCE_FLAGS: dict[NotificationEventType, str] = {
    NotificationEventType.EMAIL_VERIFICATION_REQUESTED: "email_verification_enabled",
    NotificationEventType.PASSWORD_RESET_REQUESTED: "password_reset_enabled",
    NotificationEventType.SUBMISSION_APPROVED: "moderation_outcome_enabled",
    NotificationEventType.SUBMISSION_REJECTED: "moderation_outcome_enabled",
    NotificationEventType.SUBMISSION_CHANGES_REQUESTED: "moderation_outcome_enabled",
    NotificationEventType.LAUNCH_REMINDER: "launch_reminder_enabled",
    NotificationEventType.LAUNCH_ACTIVATED: "product_live_enabled",
    NotificationEventType.COMMENT_CREATED: "comment_alert_enabled",
    NotificationEventType.RANKING_DAILY_TOP_FIVE: "daily_top_five_enabled",
    NotificationEventType.RANKING_WEEKLY_BEST: "weekly_best_enabled",
}

_EMAIL_CONTENT: dict[NotificationEventType, tuple[str, str]] = {
    NotificationEventType.EMAIL_VERIFICATION_REQUESTED: (
        "Confirm your Launchpad email",
        "Verify your email with this token: {token}",
    ),
    NotificationEventType.PASSWORD_RESET_REQUESTED: (
        "Reset your Launchpad password",
        "Reset your password with this token: {token}",
    ),
    NotificationEventType.SUBMISSION_APPROVED: (
        "Your product was approved",
        "Good news — {product_name} was approved. Pick a launch day next.",
    ),
    NotificationEventType.SUBMISSION_REJECTED: (
        "Your product was not approved",
        "Your submission for {product_name} was rejected.",
    ),
    NotificationEventType.SUBMISSION_CHANGES_REQUESTED: (
        "Changes requested on your product",
        "A reviewer requested changes to {product_name} before it can be approved.",
    ),
    NotificationEventType.LAUNCH_REMINDER: (
        "Your product launches tomorrow",
        "{product_name} is scheduled to launch tomorrow. Get ready!",
    ),
    NotificationEventType.LAUNCH_ACTIVATED: (
        "Your product is live",
        "{product_name} is live on Launchpad today.",
    ),
    NotificationEventType.COMMENT_CREATED: (
        "New comment on your product",
        "Someone commented on {product_name}.",
    ),
    NotificationEventType.RANKING_DAILY_TOP_FIVE: (
        "Today's top five",
        "Here are today's top five launches on Launchpad: {listing}",
    ),
    NotificationEventType.RANKING_WEEKLY_BEST: (
        "Best of the week",
        "Here are the best launches this week on Launchpad: {listing}",
    ),
    NotificationEventType.FOUNDER_EXPORT_READY: (
        "Your export is ready",
        "The data export for {product_name} is ready to download.",
    ),
    NotificationEventType.USER_SUSPENDED: (
        "Your Launchpad account was suspended",
        "Your account has been suspended. Reason: {reason}",
    ),
    NotificationEventType.USER_REACTIVATED: (
        "Your Launchpad account was reactivated",
        "Your account suspension has been lifted. Welcome back.",
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _retry_policy() -> RetryPolicy:
    return RetryPolicy(
        max_attempts=settings.notification_max_attempts,
        base_delay_seconds=settings.notification_retry_base_seconds,
        max_delay_seconds=settings.notification_retry_max_seconds,
    )


def _profile_ids(user: User) -> list[int]:
    return [profile.id for profile in user.profiles]


def _render_content(event_type: NotificationEventType, payload: dict) -> tuple[str, str]:
    subject, template = _EMAIL_CONTENT.get(event_type, ("Launchpad notification", "{text}"))
    items = payload.get("items") or []
    listing = ", ".join(str(item.get("name", "")) for item in items) or "—"
    values = {**payload, "listing": listing, "text": payload.get("text", "")}
    try:
        body = template.format(**values)
    except (KeyError, IndexError):
        body = template
    return subject, body


class NotificationPreferenceService:
    """Reads and updates a member's per-event notification preferences."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_for_profile(self, profile_id: int) -> NotificationPreference:
        """Fetch the profile's preferences, creating default-all-enabled ones.

        Race-safe: a concurrent create for the same profile hits the unique
        constraint and re-fetches, mirroring ``RoleService.get_or_create``.
        """
        preference = crud.get_preference(self.db, profile_id)
        if preference is not None:
            return preference
        try:
            with self.db.begin_nested():
                return crud.create_preference(self.db, profile_id=profile_id)
        except IntegrityError:
            preference = crud.get_preference(self.db, profile_id)
            if preference is None:
                raise
            return preference

    def read(self, user: User) -> NotificationPreferenceRead:
        return NotificationPreferenceRead.model_validate(self._primary(user))

    def update(
        self, user: User, payload: NotificationPreferenceUpdate
    ) -> NotificationPreferenceRead:
        changes = payload.model_dump(exclude_unset=True, exclude_none=True)
        primary = None
        for profile in user.profiles:
            preference = self.ensure_for_profile(profile.id)
            if changes:
                crud.update_preference(self.db, preference, **changes)
            if primary is None:
                primary = preference
        if primary is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No profile to configure"
            )
        self.db.commit()
        self.db.refresh(primary)
        return NotificationPreferenceRead.model_validate(primary)

    def _primary(self, user: User) -> NotificationPreference:
        if not user.profiles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No profile to configure"
            )
        return self.ensure_for_profile(user.profiles[0].id)


class NotificationService:
    """Creates, reads, and delivers member notifications.

    ``emit`` is the single entry point domains call; it records the in-app
    notification and, when the recipient's preference for the event is enabled,
    fans out a tracked email delivery on the durable queue. Callers own the
    transaction boundary (``emit`` flushes but does not commit) so a
    notification lands atomically with the action that produced it.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.preferences = NotificationPreferenceService(db)

    def emit(
        self,
        *,
        recipient_profile_id: int,
        event_type: NotificationEventType,
        actor_profile_id: int | None = None,
        payload: dict | None = None,
    ) -> Notification:
        notification = crud.create_notification(
            self.db,
            recipient_profile_id=recipient_profile_id,
            actor_profile_id=actor_profile_id,
            event_type=event_type,
            payload=payload or {},
        )
        if self._email_allowed(recipient_profile_id, event_type):
            delivery = crud.create_delivery(
                self.db,
                notification_id=notification.id,
                channel=NotificationChannel.EMAIL,
                provider=settings.email_provider,
            )
            enqueue_job("notifications.dispatch_delivery", {"delivery_id": delivery.id})
        self.db.flush()
        return notification

    def _email_allowed(self, profile_id: int, event_type: NotificationEventType) -> bool:
        if not settings.email_enabled:
            return False  # no provider configured → in-app only
        flag = EVENT_PREFERENCE_FLAGS.get(event_type)
        if flag is None:
            return True  # transactional event, not user-suppressible
        preference = self.preferences.ensure_for_profile(profile_id)
        return bool(getattr(preference, flag))

    # --- delivery ---

    def dispatch(self, delivery_id: int) -> None:
        """Send one email delivery, applying retry/backoff on provider failure.

        Idempotent: an already-sent or dropped delivery is left untouched, so a
        retried job never double-sends.
        """
        delivery = crud.get_delivery(self.db, delivery_id)
        if delivery is None:
            return
        if delivery.status in (
            NotificationDeliveryStatus.SENT,
            NotificationDeliveryStatus.DROPPED,
        ):
            return

        message = self._render_message(delivery)
        attempt = delivery.attempt_count + 1
        try:
            provider_message_id = email_integration.send_email(message)
        except email_integration.EmailSendError as exc:
            self._record_failure(delivery, attempt, str(exc))
            return

        crud.update_delivery(
            self.db,
            delivery,
            status=NotificationDeliveryStatus.SENT,
            attempt_count=attempt,
            provider_message_id=provider_message_id,
            last_error=None,
            next_retry_at=None,
            delivered_at=_utcnow(),
        )
        self.db.commit()

    def _record_failure(self, delivery: NotificationDelivery, attempt: int, error: str) -> None:
        policy = _retry_policy()
        if policy.should_retry(attempt):
            delay = policy.delay_for(attempt)
            crud.update_delivery(
                self.db,
                delivery,
                status=NotificationDeliveryStatus.RETRYING,
                attempt_count=attempt,
                last_error=error,
                next_retry_at=_utcnow() + timedelta(seconds=delay),
            )
            self.db.commit()
            enqueue_job(
                "notifications.dispatch_delivery",
                {"delivery_id": delivery.id},
                delay_seconds=delay,
            )
            return
        crud.update_delivery(
            self.db,
            delivery,
            status=NotificationDeliveryStatus.FAILED,
            attempt_count=attempt,
            last_error=error,
            next_retry_at=None,
        )
        self.db.commit()

    def _render_message(self, delivery: NotificationDelivery) -> email_integration.EmailMessage:
        notification = delivery.notification
        recipient_email = notification.recipient_profile.user.email
        subject, body = _render_content(notification.event_type, notification.payload)
        return email_integration.EmailMessage(to=recipient_email, subject=subject, body=body)

    # --- reads ---

    def list_for_user(self, user: User, *, limit: int, offset: int) -> list[NotificationRead]:
        notifications = crud.list_notifications(
            self.db, _profile_ids(user), limit=limit, offset=offset
        )
        return [NotificationRead.model_validate(item) for item in notifications]

    def unread_count(self, user: User) -> int:
        return crud.count_unread(self.db, _profile_ids(user))

    def mark_read(self, user: User, notification_id: int) -> NotificationRead:
        notification = crud.get_notification(self.db, notification_id)
        if notification is None or notification.recipient_profile_id not in set(_profile_ids(user)):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
            )
        crud.mark_read(self.db, notification)
        self.db.commit()
        self.db.refresh(notification)
        return NotificationRead.model_validate(notification)

    def mark_all_read(self, user: User) -> int:
        updated = crud.mark_all_read(self.db, _profile_ids(user))
        self.db.commit()
        return updated
