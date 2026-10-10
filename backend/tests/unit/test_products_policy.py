from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from src.products.models import LaunchState, ProductStatus, SubmissionStatus
from src.products.policy import (
    can_transition_product,
    can_transition_submission,
    is_publicly_visible,
    locked_fields_after_launch,
)


def test_submission_transitions_allowed_and_denied():
    assert can_transition_submission(SubmissionStatus.DRAFT, SubmissionStatus.IN_REVIEW)
    assert can_transition_submission(SubmissionStatus.IN_REVIEW, SubmissionStatus.APPROVED)
    assert can_transition_submission(SubmissionStatus.CHANGES_REQUESTED, SubmissionStatus.IN_REVIEW)
    # Illegal moves.
    assert not can_transition_submission(SubmissionStatus.DRAFT, SubmissionStatus.APPROVED)
    assert not can_transition_submission(SubmissionStatus.APPROVED, SubmissionStatus.IN_REVIEW)


def test_product_transitions_allowed_and_denied():
    assert can_transition_product(ProductStatus.DRAFT, ProductStatus.APPROVED)
    assert can_transition_product(ProductStatus.APPROVED, ProductStatus.SCHEDULED)
    assert can_transition_product(ProductStatus.SCHEDULED, ProductStatus.LIVE)
    assert not can_transition_product(ProductStatus.DRAFT, ProductStatus.LIVE)
    assert not can_transition_product(ProductStatus.LIVE, ProductStatus.SCHEDULED)


def _product(
    status: ProductStatus,
    launch_state=LaunchState.SCHEDULED,
    launch_date=None,
    *,
    verified: bool = True,
):
    launch = SimpleNamespace(state=launch_state, launch_date=launch_date)
    owner = SimpleNamespace(user=SimpleNamespace(email_verified=verified))
    return SimpleNamespace(
        status=status,
        product_launch=launch if launch_state else None,
        profile=owner,
    )


def test_visibility_requires_launch_day_to_arrive():
    today = date(2026, 1, 10)
    future = today + timedelta(days=3)

    assert is_publicly_visible(
        _product(ProductStatus.SCHEDULED, LaunchState.SCHEDULED, today), today
    )
    assert is_publicly_visible(_product(ProductStatus.LIVE, LaunchState.LIVE, today), today)
    assert not is_publicly_visible(
        _product(ProductStatus.SCHEDULED, LaunchState.SCHEDULED, future), today
    )
    assert not is_publicly_visible(_product(ProductStatus.APPROVED, None), today)
    assert not is_publicly_visible(_product(ProductStatus.DRAFT, None), today)
    assert not is_publicly_visible(
        _product(ProductStatus.SCHEDULED, LaunchState.CANCELLED, today), today
    )


def test_visibility_requires_verified_owner():
    today = date(2026, 1, 10)
    assert not is_publicly_visible(
        _product(ProductStatus.SCHEDULED, LaunchState.SCHEDULED, today, verified=False), today
    )
    assert is_publicly_visible(
        _product(ProductStatus.SCHEDULED, LaunchState.SCHEDULED, today, verified=True), today
    )


def test_post_launch_edit_lock_keeps_only_description_and_links():
    changes = {
        "name": "New name",
        "one_line_pitch": "New pitch",
        "description": "New description",
        "website_url": "https://example.com",
    }
    assert locked_fields_after_launch(changes) == {"name", "one_line_pitch"}
    assert locked_fields_after_launch({"description": "x"}) == set()
