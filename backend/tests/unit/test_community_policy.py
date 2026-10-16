from __future__ import annotations

from src.community.models import ReportStatus
from src.community.policy import REPORT_QUEUE_STATUSES, can_transition_report


def test_report_transitions_allowed_and_denied():
    assert can_transition_report(ReportStatus.OPEN, ReportStatus.IN_REVIEW)
    assert can_transition_report(ReportStatus.IN_REVIEW, ReportStatus.RESOLVED)
    assert can_transition_report(ReportStatus.IN_REVIEW, ReportStatus.DISMISSED)
    # Illegal moves — resolve/dismiss must go through in_review first.
    assert not can_transition_report(ReportStatus.OPEN, ReportStatus.RESOLVED)
    assert not can_transition_report(ReportStatus.OPEN, ReportStatus.DISMISSED)
    assert not can_transition_report(ReportStatus.RESOLVED, ReportStatus.IN_REVIEW)
    assert not can_transition_report(ReportStatus.DISMISSED, ReportStatus.RESOLVED)


def test_report_queue_covers_actionable_statuses():
    assert REPORT_QUEUE_STATUSES == (ReportStatus.OPEN, ReportStatus.IN_REVIEW)
