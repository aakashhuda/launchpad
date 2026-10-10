from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.staff.models import (
    AuditEntityType,
    AuditEventType,
    AuditLog,
    StaffAction,
    StaffActionType,
    StaffTargetType,
)


def create_staff_action(
    db: Session,
    *,
    actor_profile_id: int,
    action_type: StaffActionType,
    target_type: StaffTargetType,
    target_id: int,
    reason: str | None = None,
    metadata: dict | None = None,
) -> StaffAction:
    action = StaffAction(
        actor_profile_id=actor_profile_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        metadata_json=metadata or {},
    )
    db.add(action)
    db.flush()
    return action


def list_staff_actions(db: Session, *, limit: int, offset: int) -> list[StaffAction]:
    return list(
        db.scalars(
            select(StaffAction)
            .order_by(StaffAction.created_at.desc(), StaffAction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def create_audit_log(
    db: Session,
    *,
    actor_profile_id: int | None,
    event_type: AuditEventType,
    entity_type: AuditEntityType,
    entity_id: int | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_profile_id=actor_profile_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        correlation_id=correlation_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.flush()
    return log
