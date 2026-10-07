from __future__ import annotations

import enum


class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"
    GITHUB = "github"


class LastLoginRole(str, enum.Enum):
    MEMBER = "member"
    FOUNDER = "founder"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    LIVE = "live"
    INACTIVE = "inactive"


class LaunchState(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class SubmissionStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ReportTargetType(str, enum.Enum):
    PRODUCT = "product"
    COMMENT = "comment"


class ReportReason(str, enum.Enum):
    SPAM = "spam"
    ABUSE = "abuse"
    MISLEADING = "misleading"
    COPYRIGHT = "copyright"
    OTHER = "other"


class ReportStatus(str, enum.Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    IN_APP = "in_app"


class NotificationDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    SENT = "sent"
    FAILED = "failed"
    DROPPED = "dropped"


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]
