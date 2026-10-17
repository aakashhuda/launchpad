from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Identity, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base_model import Base, CreatedAtMixin, enum_values

if TYPE_CHECKING:
    from src.users.models import Profile


class StaffActionType(str, enum.Enum):
    APPROVE_SUBMISSION = "approve_submission"
    REJECT_SUBMISSION = "reject_submission"
    REQUEST_SUBMISSION_CHANGES = "request_submission_changes"
    SCHEDULE_LAUNCH = "schedule_launch"
    RESCHEDULE_LAUNCH = "reschedule_launch"
    ACTIVATE_LAUNCH = "activate_launch"
    ASSIGN_REPORT = "assign_report"
    RESOLVE_REPORT = "resolve_report"
    DISMISS_REPORT = "dismiss_report"


class StaffTargetType(str, enum.Enum):
    PRODUCT = "product"
    SUBMISSION = "submission"
    LAUNCH = "launch"
    REPORT = "report"


class AuditEventType(str, enum.Enum):
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    SUBMISSION_SUBMITTED = "submission.submitted"
    SUBMISSION_APPROVED = "submission.approved"
    SUBMISSION_REJECTED = "submission.rejected"
    SUBMISSION_CHANGES_REQUESTED = "submission.changes_requested"
    LAUNCH_SCHEDULED = "launch.scheduled"
    LAUNCH_RESCHEDULED = "launch.rescheduled"
    LAUNCH_ACTIVATED = "launch.activated"
    REPORT_CREATED = "report.created"
    REPORT_ASSIGNED = "report.assigned"
    REPORT_RESOLVED = "report.resolved"
    REPORT_DISMISSED = "report.dismissed"
    SNAPSHOT_FROZEN = "snapshot.frozen"


class AuditEntityType(str, enum.Enum):
    PRODUCT = "product"
    SUBMISSION = "submission"
    LAUNCH = "launch"
    REPORT = "report"
    SNAPSHOT = "snapshot"


class StaffAction(CreatedAtMixin, Base):
    __tablename__ = "staff_actions"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    staff_action_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    actor_profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), nullable=False)
    action_type: Mapped[StaffActionType] = mapped_column(
        Enum(
            StaffActionType,
            native_enum=False,
            length=50,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    target_type: Mapped[StaffTargetType] = mapped_column(
        Enum(
            StaffTargetType,
            native_enum=False,
            length=50,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
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
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(
            AuditEventType,
            native_enum=False,
            length=100,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    entity_type: Mapped[AuditEntityType] = mapped_column(
        Enum(
            AuditEntityType,
            native_enum=False,
            length=50,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
    )
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
