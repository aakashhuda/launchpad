from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.community.schemas import ReportRead
from src.community.service import ReportService
from src.core.database import get_db
from src.core.dependencies import require_verified_role
from src.products.schemas import ProductDetailRead, SubmissionDecisionRequest, SubmissionRead
from src.products.service import ProductAdminService, ProductFeatureService, SubmissionService
from src.staff.models import AuditEntityType, AuditEventType
from src.staff.schemas import (
    AuditLogRead,
    FeatureProductRequest,
    StaffActionRead,
    SuspendMemberRequest,
    TakedownProductRequest,
)
from src.staff.service import AuditLogService, StaffActionService
from src.users.models import User
from src.users.schemas import UserRead
from src.users.service import UserService

router = APIRouter()


@router.get("/submissions", response_model=list[SubmissionRead])
def review_queue(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> list[SubmissionRead]:
    return SubmissionService(db).list_queue(limit=limit, offset=offset)


@router.post("/submissions/{submission_id}/decision", response_model=SubmissionRead)
def decide_submission(
    submission_id: int,
    payload: SubmissionDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> SubmissionRead:
    return SubmissionService(db).decide(current_user, submission_id, payload)


@router.get("/reports", response_model=list[ReportRead])
def list_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> list[ReportRead]:
    return ReportService(db).list_queue(limit=limit, offset=offset)


@router.get("/actions", response_model=list[StaffActionRead])
def list_staff_actions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> list[StaffActionRead]:
    actions = StaffActionService(db).list(limit=limit, offset=offset)
    return [StaffActionRead.model_validate(action) for action in actions]


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    event_type: AuditEventType | None = Query(None),
    entity_type: AuditEntityType | None = Query(None),
    entity_id: int | None = Query(None),
    actor_profile_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> list[AuditLogRead]:
    logs = AuditLogService(db).list(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_profile_id=actor_profile_id,
        limit=limit,
        offset=offset,
    )
    return [AuditLogRead.model_validate(log) for log in logs]


# --- admin governance (admin only) ---


@router.post("/users/{user_id}/suspend", response_model=UserRead)
def suspend_member(
    user_id: int,
    payload: SuspendMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("admin")),
) -> UserRead:
    user = UserService(db).suspend(current_user, user_id, payload.reason)
    return UserRead.model_validate(user)


@router.post("/users/{user_id}/reactivate", response_model=UserRead)
def reactivate_member(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("admin")),
) -> UserRead:
    user = UserService(db).reactivate(current_user, user_id)
    return UserRead.model_validate(user)


@router.post("/products/{product_id}/takedown", response_model=ProductDetailRead)
def takedown_product(
    product_id: int,
    payload: TakedownProductRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("admin")),
) -> ProductDetailRead:
    return ProductAdminService(db).takedown(current_user, product_id, payload.reason)


@router.post("/products/{product_id}/restore", response_model=ProductDetailRead)
def restore_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("admin")),
) -> ProductDetailRead:
    return ProductAdminService(db).restore(current_user, product_id)


@router.post("/products/{product_id}/feature", response_model=ProductDetailRead)
def feature_product(
    product_id: int,
    payload: FeatureProductRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("admin")),
) -> ProductDetailRead:
    return ProductFeatureService(db).feature(
        current_user, product_id, payload.reason, payload.ends_at
    )


@router.post("/products/{product_id}/unfeature", response_model=ProductDetailRead)
def unfeature_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("admin")),
) -> ProductDetailRead:
    return ProductFeatureService(db).unfeature(current_user, product_id)
