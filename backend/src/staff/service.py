from __future__ import annotations

from sqlalchemy.orm import Session

from src.staff import crud
from src.staff.models import (
    AuditEntityType,
    AuditEventType,
    AuditLog,
    StaffAction,
    StaffActionType,
    StaffTargetType,
)


class StaffActionService:
    """Records reviewer/admin actions with actor and timestamp.

    Writes are flushed but not committed — the owning domain service owns the
    transaction boundary so the action and its side effects land atomically.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        actor_profile_id: int,
        action_type: StaffActionType,
        target_type: StaffTargetType,
        target_id: int,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> StaffAction:
        return crud.create_staff_action(
            self.db,
            actor_profile_id=actor_profile_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            metadata=metadata,
        )

    def list(self, *, limit: int, offset: int) -> list[StaffAction]:
        return crud.list_staff_actions(self.db, limit=limit, offset=offset)


class AuditLogService:
    """Appends audit-log entries for lifecycle and moderation events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        actor_profile_id: int | None,
        event_type: AuditEventType,
        entity_type: AuditEntityType,
        entity_id: int | None = None,
        before_state: dict | None = None,
        after_state: dict | None = None,
        correlation_id: str | None = None,
    ) -> AuditLog:
        return crud.create_audit_log(
            self.db,
            actor_profile_id=actor_profile_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
            after_state=after_state,
            correlation_id=correlation_id,
        )
