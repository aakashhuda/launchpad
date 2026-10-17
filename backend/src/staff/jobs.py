"""Concrete staff-domain background jobs.

Job *infrastructure* lives in ``src.tasks``; this module owns the staff-domain
job bodies and registers them by string name so other domains can enqueue them
without importing staff.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.staff.models import AuditEntityType, AuditEventType
from src.staff.service import AuditLogService
from src.tasks.registry import register_job


@register_job("staff.evaluate_abuse_signal")
def evaluate_abuse_signal(
    db: Session,
    *,
    action: str,
    user_id: int,
    count: int,
    window_seconds: int,
) -> None:
    """Record a suspicious-activity signal for staff review (monitoring only).

    The signal is an immutable audit entry reviewers can read via
    ``GET /staff/audit-logs?event_type=abuse.signal_raised``. No automated
    enforcement happens here; a human decides.
    """
    AuditLogService(db).record(
        actor_profile_id=None,
        event_type=AuditEventType.ABUSE_SIGNAL_RAISED,
        entity_type=AuditEntityType.USER,
        entity_id=user_id,
        after_state={"action": action, "count": count, "window_seconds": window_seconds},
    )
    db.commit()
