from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.notifications.schemas import (
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
)
from src.notifications.service import NotificationPreferenceService, NotificationService
from src.users.models import User

router = APIRouter()


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NotificationRead]:
    return NotificationService(db).list_for_user(current_user, limit=limit, offset=offset)


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    return {"count": NotificationService(db).unread_count(current_user)}


@router.get("/preferences", response_model=NotificationPreferenceRead)
def read_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationPreferenceRead:
    return NotificationPreferenceService(db).read(current_user)


@router.patch("/preferences", response_model=NotificationPreferenceRead)
def update_preferences(
    payload: NotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationPreferenceRead:
    return NotificationPreferenceService(db).update(current_user, payload)


@router.post("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    return {"updated": NotificationService(db).mark_all_read(current_user)}


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationRead:
    return NotificationService(db).mark_read(current_user, notification_id)
