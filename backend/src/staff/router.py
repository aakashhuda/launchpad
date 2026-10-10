from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.dependencies import require_verified_role
from src.products.schemas import SubmissionDecisionRequest, SubmissionRead
from src.products.service import SubmissionService
from src.staff.schemas import StaffActionRead
from src.staff.service import StaffActionService
from src.users.models import User

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


@router.get("/actions", response_model=list[StaffActionRead])
def list_staff_actions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> list[StaffActionRead]:
    actions = StaffActionService(db).list(limit=limit, offset=offset)
    return [StaffActionRead.model_validate(action) for action in actions]
