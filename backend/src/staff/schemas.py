from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.staff.models import StaffActionType, StaffTargetType


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
