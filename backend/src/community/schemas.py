from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.community.models import ReportReason, ReportStatus, ReportTargetType


class VoteRead(BaseModel):
    product_id: int
    vote_count: int
    has_voted: bool


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    parent_comment_id: int | None = None


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    profile_id: int
    parent_comment_id: int | None
    text: str
    created_at: datetime
    updated_at: datetime
    replies: list[CommentRead] = Field(default_factory=list)


CommentRead.model_rebuild()


class ReportCreate(BaseModel):
    reason: ReportReason
    details: str | None = Field(default=None, max_length=2000)


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_profile_id: int
    target_type: ReportTargetType
    target_product_id: int | None
    target_comment_id: int | None
    reason: ReportReason
    details: str | None
    status: ReportStatus
    assigned_reviewer_profile_id: int | None
    resolved_by_profile_id: int | None
    resolution_note: str | None
    resolved_at: datetime | None
    created_at: datetime


class ReportResolution(str, enum.Enum):
    RESOLVE = "resolve"
    DISMISS = "dismiss"


class ReportResolveRequest(BaseModel):
    resolution: ReportResolution
    note: str | None = Field(default=None, max_length=2000)
