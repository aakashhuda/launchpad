from __future__ import annotations

from src.products.models import ProductStatus
from src.products.policy import can_admin_restore, can_admin_takedown

_NON_INACTIVE = (
    ProductStatus.DRAFT,
    ProductStatus.APPROVED,
    ProductStatus.SCHEDULED,
    ProductStatus.LIVE,
)


def test_can_admin_takedown_any_non_inactive():
    assert all(can_admin_takedown(status) for status in _NON_INACTIVE)
    assert can_admin_takedown(ProductStatus.INACTIVE) is False


def test_can_admin_restore_only_inactive():
    assert can_admin_restore(ProductStatus.INACTIVE) is True
    assert not any(can_admin_restore(status) for status in _NON_INACTIVE)
