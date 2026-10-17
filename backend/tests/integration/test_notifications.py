from __future__ import annotations

import uuid

from sqlalchemy import select

from src.core.config import settings
from src.integrations import email as email_integration
from src.notifications.models import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
)
from src.notifications.schemas import NotificationPreferenceUpdate
from src.notifications.service import NotificationPreferenceService, NotificationService
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _member(db_session, *, verified: bool = True):
    user = UserService(db_session).create(
        UserCreate(
            email=_unique_email(),
            first_name="Test",
            last_name="User",
            auth_provider=AuthProvider.EMAIL,
        )
    )
    profile = ProfileService(db_session).create_for_user(
        user, ProfileCreate(role_slug="member", nick_name="test")
    )
    user.email_verified = verified
    db_session.commit()
    return UserService(db_session).get_by_id(user.id), profile


def _emit(db_session, profile_id: int, event_type=NotificationEventType.COMMENT_CREATED):
    notification = NotificationService(db_session).emit(
        recipient_profile_id=profile_id,
        event_type=event_type,
        payload={"product_name": "Acme"},
    )
    db_session.commit()
    delivery = db_session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.notification_id == notification.id)
    )
    return notification, delivery


# --- emit + preference gating ---


def test_signup_creates_verification_notification(client):
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "email": _unique_email(),
            "password": "password123",
            "first_name": "Test",
            "last_name": "User",
            "role": "member",
        },
    )
    assert resp.status_code == 201, resp.text
    headers = _bearer(resp.json()["access_token"])

    listed = client.get("/api/v1/notifications", headers=headers)
    assert listed.status_code == 200
    assert [item["event_type"] for item in listed.json()] == ["email.verification_requested"]

    count = client.get("/api/v1/notifications/unread-count", headers=headers).json()
    assert count["count"] == 1


def test_email_enabled_sends_email_delivery(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    user, profile = _member(db_session)

    _, delivery = _emit(db_session, profile.id)

    assert delivery is not None
    assert delivery.status == NotificationDeliveryStatus.PENDING
    assert NotificationService(db_session).unread_count(user) == 1


def test_email_disabled_keeps_in_app_only(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", False)
    user, profile = _member(db_session)

    notification, delivery = _emit(db_session, profile.id)

    assert notification.id is not None
    assert delivery is None
    assert NotificationService(db_session).unread_count(user) == 1


def test_disabled_preference_suppresses_email_but_keeps_in_app(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    user, profile = _member(db_session)
    NotificationPreferenceService(db_session).update(
        user, NotificationPreferenceUpdate(comment_alert_enabled=False)
    )
    user = UserService(db_session).get_by_id(user.id)

    notification, delivery = _emit(db_session, profile.id)

    assert notification.id is not None
    assert delivery is None  # email suppressed for the gated event
    assert NotificationService(db_session).unread_count(user) == 1  # in-app still recorded


# --- reads ---


def test_mark_read_and_read_all(client, db_session):
    user, profile = _member(db_session)
    first, _ = _emit(db_session, profile.id)
    _emit(db_session, profile.id)

    service = NotificationService(db_session)
    assert service.unread_count(user) == 2

    service.mark_read(user, first.id)
    assert service.unread_count(user) == 1

    assert service.mark_all_read(user) == 1
    assert service.unread_count(user) == 0


def test_preferences_read_and_update(client, db_session):
    user, _profile = _member(db_session)
    service = NotificationPreferenceService(db_session)

    current = service.read(user)
    assert current.comment_alert_enabled is True

    updated = service.update(user, NotificationPreferenceUpdate(daily_top_five_enabled=False))
    assert updated.daily_top_five_enabled is False
    assert updated.comment_alert_enabled is True


def test_ensure_preference_is_idempotent(db_session):
    """Repeated ensure never duplicates a preference row (race-safe create)."""
    from sqlalchemy import func, select

    from src.notifications.models import NotificationPreference

    _user, profile = _member(db_session)
    service = NotificationPreferenceService(db_session)

    service.ensure_for_profile(profile.id)
    service.ensure_for_profile(profile.id)

    count = db_session.scalar(
        select(func.count(NotificationPreference.id)).where(
            NotificationPreference.profile_id == profile.id
        )
    )
    assert count == 1


# --- delivery dispatch + provider-outage resilience ---


def test_dispatch_marks_sent(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    sent: list[email_integration.EmailMessage] = []
    monkeypatch.setattr(
        email_integration, "send_email", lambda message: (sent.append(message), "provider-1")[1]
    )
    _user, profile = _member(db_session)
    _notification, delivery = _emit(db_session, profile.id)

    NotificationService(db_session).dispatch(delivery.id)
    db_session.refresh(delivery)

    assert delivery.status == NotificationDeliveryStatus.SENT
    assert delivery.provider_message_id == "provider-1"
    assert delivery.attempt_count == 1
    assert len(sent) == 1


def test_dispatch_retries_then_sends(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    calls = {"n": 0}

    def flaky(message):
        calls["n"] += 1
        if calls["n"] == 1:
            raise email_integration.EmailSendError("provider down")
        return "provider-ok"

    monkeypatch.setattr(email_integration, "send_email", flaky)
    _user, profile = _member(db_session)
    _notification, delivery = _emit(db_session, profile.id)
    service = NotificationService(db_session)

    service.dispatch(delivery.id)  # first attempt fails
    db_session.refresh(delivery)
    assert delivery.status == NotificationDeliveryStatus.RETRYING
    assert delivery.attempt_count == 1
    assert delivery.next_retry_at is not None
    assert delivery.last_error == "provider down"

    service.dispatch(delivery.id)  # provider recovered on the retry
    db_session.refresh(delivery)
    assert delivery.status == NotificationDeliveryStatus.SENT
    assert delivery.provider_message_id == "provider-ok"


def test_dispatch_terminal_failure_after_max_attempts(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "notification_max_attempts", 1)

    def always_fail(message):
        raise email_integration.EmailSendError("still down")

    monkeypatch.setattr(email_integration, "send_email", always_fail)
    _user, profile = _member(db_session)
    _notification, delivery = _emit(db_session, profile.id)

    NotificationService(db_session).dispatch(delivery.id)
    db_session.refresh(delivery)

    assert delivery.status == NotificationDeliveryStatus.FAILED
    assert delivery.next_retry_at is None


def test_dispatch_is_idempotent_after_sent(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    sent: list[email_integration.EmailMessage] = []
    monkeypatch.setattr(
        email_integration, "send_email", lambda message: (sent.append(message), "p1")[1]
    )
    _user, profile = _member(db_session)
    _notification, delivery = _emit(db_session, profile.id)
    service = NotificationService(db_session)

    service.dispatch(delivery.id)
    service.dispatch(delivery.id)  # already SENT -> no double-send

    assert len(sent) == 1
