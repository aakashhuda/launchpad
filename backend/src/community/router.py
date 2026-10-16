from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from src.community.schemas import (
    CommentCreate,
    CommentRead,
    ReportCreate,
    ReportRead,
    ReportResolveRequest,
    VoteRead,
)
from src.community.service import CommentService, FeedService, ReportService, VoteService
from src.core.database import get_db
from src.core.dependencies import require_verified_role
from src.products.schemas import ProductRead
from src.users.models import User

router = APIRouter()


@router.post("/products/{product_id}/vote", response_model=VoteRead)
def cast_vote(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> VoteRead:
    return VoteService(db).vote(current_user, product_id)


@router.delete("/products/{product_id}/vote", response_model=VoteRead)
def remove_vote(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> VoteRead:
    return VoteService(db).unvote(current_user, product_id)


@router.post(
    "/products/{product_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    product_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> CommentRead:
    return CommentService(db).create(current_user, product_id, payload)


@router.get("/products/{product_id}/comments", response_model=list[CommentRead])
def list_comments(
    product_id: int,
    db: Session = Depends(get_db),
) -> list[CommentRead]:
    return CommentService(db).list_for_product(product_id)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> Response:
    CommentService(db).delete(current_user, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/products/{product_id}/reports",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
)
def report_product(
    product_id: int,
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> ReportRead:
    return ReportService(db).report_product(current_user, product_id, payload)


@router.post(
    "/comments/{comment_id}/reports",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
)
def report_comment(
    comment_id: int,
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> ReportRead:
    return ReportService(db).report_comment(current_user, comment_id, payload)


@router.get("/reports", response_model=list[ReportRead])
def list_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> list[ReportRead]:
    return ReportService(db).list_queue(limit=limit, offset=offset)


@router.post("/reports/{report_id}/assign", response_model=ReportRead)
def assign_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> ReportRead:
    return ReportService(db).assign(current_user, report_id)


@router.post("/reports/{report_id}/resolve", response_model=ReportRead)
def resolve_report(
    report_id: int,
    payload: ReportResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("reviewer", "admin")),
) -> ReportRead:
    return ReportService(db).resolve(current_user, report_id, payload)


@router.get("/feed", response_model=list[ProductRead])
def read_feed(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> list[ProductRead]:
    return FeedService(db).feed(current_user, limit=limit, offset=offset)
