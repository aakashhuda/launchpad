from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.staff.models import AuditEntityType, AuditEventType, StaffActionType, StaffTargetType


class StaffActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    actor_profile_id: int
    action_type: StaffActionType
    target_type: StaffTargetType
    target_id: int
    reason: str | None
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_profile_id: int | None
    event_type: AuditEventType
    entity_type: AuditEntityType
    entity_id: int | None
    before_state: dict | None
    after_state: dict | None
    correlation_id: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class SuspendMemberRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class TakedownProductRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class FeatureProductRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    ends_at: datetime | None = None
