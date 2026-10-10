from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.products.models import LaunchState, ProductStatus, SubmissionStatus

MAX_TOPICS_PER_PRODUCT = 3


def _clean_topics(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        topic = raw.strip()
        if not topic or topic.lower() in seen:
            continue
        seen.add(topic.lower())
        cleaned.append(topic)
    if len(cleaned) > MAX_TOPICS_PER_PRODUCT:
        raise ValueError(f"At most {MAX_TOPICS_PER_PRODUCT} topics are allowed")
    return cleaned


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    one_line_pitch: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)
    logo_url: str = Field(..., min_length=1, max_length=255)
    screenshot_urls: list[str] | None = Field(default=None, max_length=10)
    website_url: str | None = Field(default=None, max_length=255)
    topics: list[str] = Field(default_factory=list)

    @field_validator("topics")
    @classmethod
    def _validate_topics(cls, value: list[str]) -> list[str]:
        return _clean_topics(value)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    one_line_pitch: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1)
    logo_url: str | None = Field(default=None, min_length=1, max_length=255)
    screenshot_urls: list[str] | None = Field(default=None, max_length=10)
    website_url: str | None = Field(default=None, max_length=255)
    topics: list[str] | None = None

    @field_validator("topics")
    @classmethod
    def _validate_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _clean_topics(value)


class TopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    slug: str


class LaunchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    launch_date: date
    state: LaunchState
    launched_at: datetime | None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    one_line_pitch: str
    status: ProductStatus
    created_at: datetime


class ProductDetailRead(ProductRead):
    description: str
    logo_url: str
    screenshot_urls: list[str] | None
    website_url: str | None
    topics: list[str] = Field(default_factory=list)
    launch: LaunchRead | None = None


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    profile_id: int
    status: SubmissionStatus
    review_note: str | None
    reviewed_by_profile_id: int | None
    reviewed_at: datetime | None
    created_at: datetime


class SubmissionDecision(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class SubmissionDecisionRequest(BaseModel):
    decision: SubmissionDecision
    note: str | None = Field(default=None, max_length=2000)


class LaunchScheduleRequest(BaseModel):
    launch_date: date

    @field_validator("launch_date")
    @classmethod
    def _not_in_the_past(cls, value: date) -> date:
        if value < datetime.now(timezone.utc).date():
            raise ValueError("Launch date cannot be in the past")
        return value
