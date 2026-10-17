from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.notifications.models import NotificationEventType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: NotificationEventType
    payload: dict
    actor_profile_id: int | None
    read_at: datetime | None
    created_at: datetime


class NotificationPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_verification_enabled: bool
    password_reset_enabled: bool
    moderation_outcome_enabled: bool
    launch_reminder_enabled: bool
    product_live_enabled: bool
    comment_alert_enabled: bool
    daily_top_five_enabled: bool
    weekly_best_enabled: bool


class NotificationPreferenceUpdate(BaseModel):
    email_verification_enabled: bool | None = None
    password_reset_enabled: bool | None = None
    moderation_outcome_enabled: bool | None = None
    launch_reminder_enabled: bool | None = None
    product_live_enabled: bool | None = None
    comment_alert_enabled: bool | None = None
    daily_top_five_enabled: bool | None = None
    weekly_best_enabled: bool | None = None
