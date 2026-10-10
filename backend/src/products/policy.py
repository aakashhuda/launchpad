from __future__ import annotations

from datetime import date

from src.products.models import LaunchState, Product, ProductStatus, SubmissionStatus

# Single source of truth for lifecycle transitions. A target outside the
# allowed set for the current status is rejected at the service layer.

SUBMISSION_TRANSITIONS: dict[SubmissionStatus, frozenset[SubmissionStatus]] = {
    SubmissionStatus.DRAFT: frozenset({SubmissionStatus.IN_REVIEW}),
    SubmissionStatus.IN_REVIEW: frozenset(
        {
            SubmissionStatus.APPROVED,
            SubmissionStatus.REJECTED,
            SubmissionStatus.CHANGES_REQUESTED,
        }
    ),
    SubmissionStatus.CHANGES_REQUESTED: frozenset({SubmissionStatus.IN_REVIEW}),
    SubmissionStatus.APPROVED: frozenset(),
    SubmissionStatus.REJECTED: frozenset(),
}

PRODUCT_TRANSITIONS: dict[ProductStatus, frozenset[ProductStatus]] = {
    ProductStatus.DRAFT: frozenset({ProductStatus.APPROVED}),
    ProductStatus.APPROVED: frozenset({ProductStatus.SCHEDULED}),
    ProductStatus.SCHEDULED: frozenset({ProductStatus.LIVE, ProductStatus.INACTIVE}),
    ProductStatus.LIVE: frozenset({ProductStatus.INACTIVE}),
    ProductStatus.INACTIVE: frozenset(),
}

# A product is only publicly visible once it is scheduled for a day that has
# arrived (embargo) or already live. Approved-without-a-date is not visible.
PUBLICLY_VISIBLE_STATUSES = frozenset({ProductStatus.SCHEDULED, ProductStatus.LIVE})

# Once live, only the description and links remain editable.
POST_LAUNCH_EDITABLE_FIELDS = frozenset({"description", "website_url", "screenshot_urls"})


def is_transition_allowed(
    transitions: dict,
    current: object,
    target: object,
) -> bool:
    return target in transitions.get(current, frozenset())


def can_transition_submission(current: SubmissionStatus, target: SubmissionStatus) -> bool:
    return is_transition_allowed(SUBMISSION_TRANSITIONS, current, target)


def can_transition_product(current: ProductStatus, target: ProductStatus) -> bool:
    return is_transition_allowed(PRODUCT_TRANSITIONS, current, target)


def is_launched(product: Product) -> bool:
    launch = product.product_launch
    return launch is not None and launch.state == LaunchState.LIVE


def is_publicly_visible(product: Product, today: date) -> bool:
    """Embargo- and verification-aware visibility predicate for public listings."""
    if product.status not in PUBLICLY_VISIBLE_STATUSES:
        return False
    owner = product.profile
    if owner is None or owner.user is None or not owner.user.email_verified:
        return False
    launch = product.product_launch
    if launch is None or launch.state == LaunchState.CANCELLED:
        return False
    return launch.launch_date <= today


def locked_fields_after_launch(changes: dict) -> set[str]:
    """Return the provided fields that may not change once a product is live."""
    if not changes:
        return set()
    return set(changes) - POST_LAUNCH_EDITABLE_FIELDS
