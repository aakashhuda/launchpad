from __future__ import annotations

from src.community.models import ReportStatus

# Single source of truth for the report moderation lifecycle. A target outside
# the allowed set for the current status is rejected at the service layer.
REPORT_TRANSITIONS: dict[ReportStatus, frozenset[ReportStatus]] = {
    ReportStatus.OPEN: frozenset({ReportStatus.IN_REVIEW}),
    ReportStatus.IN_REVIEW: frozenset({ReportStatus.RESOLVED, ReportStatus.DISMISSED}),
    ReportStatus.RESOLVED: frozenset(),
    ReportStatus.DISMISSED: frozenset(),
}

# Reports a reviewer still has to act on.
REPORT_QUEUE_STATUSES: tuple[ReportStatus, ...] = (ReportStatus.OPEN, ReportStatus.IN_REVIEW)


def can_transition_report(current: ReportStatus, target: ReportStatus) -> bool:
    return target in REPORT_TRANSITIONS.get(current, frozenset())
