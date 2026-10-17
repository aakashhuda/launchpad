from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.community import crud, policy
from src.community.models import Comment, Report, ReportStatus, ReportTargetType
from src.community.schemas import (
    CommentCreate,
    CommentRead,
    ReportCreate,
    ReportRead,
    ReportResolution,
    ReportResolveRequest,
    VoteRead,
)
from src.notifications.models import NotificationEventType
from src.notifications.service import NotificationService
from src.products import crud as products_crud
from src.products import policy as products_policy
from src.products.models import Product
from src.products.schemas import ProductRead
from src.staff.models import AuditEntityType, AuditEventType, StaffActionType, StaffTargetType
from src.staff.service import AuditLogService, StaffActionService
from src.users.models import Profile, User
from src.users.service import ProfileService

STAFF_ROLES = ("reviewer", "admin")

_RESOLUTION_TARGETS = {
    ReportResolution.RESOLVE: ReportStatus.RESOLVED,
    ReportResolution.DISMISS: ReportStatus.DISMISSED,
}

_RESOLUTION_ACTIONS = {
    ReportResolution.RESOLVE: StaffActionType.RESOLVE_REPORT,
    ReportResolution.DISMISS: StaffActionType.DISMISS_REPORT,
}

_RESOLUTION_EVENTS = {
    ReportResolution.RESOLVE: AuditEventType.REPORT_RESOLVED,
    ReportResolution.DISMISS: AuditEventType.REPORT_DISMISSED,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utcnow().date()


def _require_visible_product(db: Session, product_id: int) -> Product:
    product = products_crud.get_product(db, product_id)
    if product is None or not products_policy.is_publicly_visible(product, _today()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


def _acting_staff_profile(user: User) -> Profile:
    for profile in user.profiles:
        if profile.role is not None and profile.role.slug in STAFF_ROLES:
            return profile
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff profile required")


def _comment_read(comment: Comment) -> CommentRead:
    return CommentRead(
        id=comment.id,
        product_id=comment.product_id,
        profile_id=comment.profile_id,
        parent_comment_id=comment.parent_comment_id,
        text=comment.text,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        replies=[],
    )


def _build_comment_tree(comments: list[Comment]) -> list[CommentRead]:
    nodes = {comment.id: _comment_read(comment) for comment in comments}
    roots: list[CommentRead] = []
    for comment in comments:
        node = nodes[comment.id]
        parent = nodes.get(comment.parent_comment_id) if comment.parent_comment_id else None
        if parent is not None:
            parent.replies.append(node)
        else:
            roots.append(node)
    return roots


def _report_snapshot(report: Report) -> dict:
    return {
        "id": report.id,
        "status": report.status.value,
        "target_type": report.target_type.value,
    }


class VoteService:
    """One vote per member/product with no self-voting and visible-only targets."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = ProfileService(db)

    def vote(self, user: User, product_id: int) -> VoteRead:
        profile = self.profiles.require_member_profile(user)
        product = _require_visible_product(self.db, product_id)
        if product.profile.user_id == user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot vote for your own product",
            )
        if crud.get_vote(self.db, product.id, profile.id) is None:
            try:
                with self.db.begin_nested():
                    crud.create_vote(self.db, product.id, profile.id)
            except IntegrityError:
                pass  # a concurrent request already recorded the vote
        count = crud.count_votes_for_product(self.db, product.id)
        self.db.commit()
        return VoteRead(product_id=product.id, vote_count=count, has_voted=True)

    def unvote(self, user: User, product_id: int) -> VoteRead:
        profile = self.profiles.require_member_profile(user)
        product = products_crud.get_product(self.db, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        crud.delete_vote(self.db, product.id, profile.id)
        count = crud.count_votes_for_product(self.db, product.id)
        self.db.commit()
        return VoteRead(product_id=product.id, vote_count=count, has_voted=False)


class CommentService:
    """Threaded comments and replies on publicly visible products."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = ProfileService(db)
        self.notifications = NotificationService(db)

    def create(self, user: User, product_id: int, payload: CommentCreate) -> CommentRead:
        profile = self.profiles.require_member_profile(user)
        product = _require_visible_product(self.db, product_id)
        if payload.parent_comment_id is not None:
            parent = crud.get_comment(self.db, payload.parent_comment_id)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found"
                )
            if parent.product_id != product.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Parent comment belongs to another product",
                )
        comment = crud.create_comment(
            self.db,
            profile_id=profile.id,
            product_id=product.id,
            parent_comment_id=payload.parent_comment_id,
            text=payload.text,
        )
        if product.profile_id != profile.id:
            self.notifications.emit(
                recipient_profile_id=product.profile_id,
                actor_profile_id=profile.id,
                event_type=NotificationEventType.COMMENT_CREATED,
                payload={
                    "product_id": product.id,
                    "product_name": product.name,
                    "comment_id": comment.id,
                },
            )
        self.db.commit()
        self.db.refresh(comment)
        return _comment_read(comment)

    def list_for_product(self, product_id: int) -> list[CommentRead]:
        _require_visible_product(self.db, product_id)
        comments = crud.list_comments_by_product(self.db, product_id)
        return _build_comment_tree(comments)

    def delete(self, user: User, comment_id: int) -> None:
        comment = crud.get_comment(self.db, comment_id)
        if comment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        profile = self.profiles.require_member_profile(user)
        if comment.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to delete this comment",
            )
        crud.delete_comment(self.db, comment)
        self.db.commit()


class ReportService:
    """Member reporting of products/comments plus reviewer triage and resolution."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = ProfileService(db)
        self.staff_actions = StaffActionService(db)
        self.audit = AuditLogService(db)

    def report_product(self, user: User, product_id: int, payload: ReportCreate) -> ReportRead:
        profile = self.profiles.require_member_profile(user)
        product = _require_visible_product(self.db, product_id)
        if (
            crud.get_open_report_for_target(self.db, profile.id, target_product_id=product.id)
            is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already reported this product",
            )
        report = crud.create_report(
            self.db,
            reporter_profile_id=profile.id,
            target_type=ReportTargetType.PRODUCT,
            target_product_id=product.id,
            target_comment_id=None,
            reason=payload.reason,
            details=payload.details,
        )
        self.audit.record(
            actor_profile_id=profile.id,
            event_type=AuditEventType.REPORT_CREATED,
            entity_type=AuditEntityType.REPORT,
            entity_id=report.id,
            after_state=_report_snapshot(report),
        )
        self.db.commit()
        self.db.refresh(report)
        return ReportRead.model_validate(report)

    def report_comment(self, user: User, comment_id: int, payload: ReportCreate) -> ReportRead:
        profile = self.profiles.require_member_profile(user)
        comment = crud.get_comment(self.db, comment_id)
        if comment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        if (
            crud.get_open_report_for_target(self.db, profile.id, target_comment_id=comment.id)
            is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already reported this comment",
            )
        report = crud.create_report(
            self.db,
            reporter_profile_id=profile.id,
            target_type=ReportTargetType.COMMENT,
            target_product_id=None,
            target_comment_id=comment.id,
            reason=payload.reason,
            details=payload.details,
        )
        self.audit.record(
            actor_profile_id=profile.id,
            event_type=AuditEventType.REPORT_CREATED,
            entity_type=AuditEntityType.REPORT,
            entity_id=report.id,
            after_state=_report_snapshot(report),
        )
        self.db.commit()
        self.db.refresh(report)
        return ReportRead.model_validate(report)

    def list_queue(self, *, limit: int, offset: int) -> list[ReportRead]:
        reports = crud.list_reports_by_statuses(
            self.db, policy.REPORT_QUEUE_STATUSES, limit=limit, offset=offset
        )
        return [ReportRead.model_validate(report) for report in reports]

    def assign(self, user: User, report_id: int) -> ReportRead:
        report = self._require_report(report_id)
        actor = _acting_staff_profile(user)
        self._transition(report, ReportStatus.IN_REVIEW)
        crud.update_report(self.db, report, assigned_reviewer_profile_id=actor.id)
        self.staff_actions.record(
            actor_profile_id=actor.id,
            action_type=StaffActionType.ASSIGN_REPORT,
            target_type=StaffTargetType.REPORT,
            target_id=report.id,
            metadata={"status": report.status.value},
        )
        self.audit.record(
            actor_profile_id=actor.id,
            event_type=AuditEventType.REPORT_ASSIGNED,
            entity_type=AuditEntityType.REPORT,
            entity_id=report.id,
            after_state=_report_snapshot(report),
        )
        self.db.commit()
        self.db.refresh(report)
        return ReportRead.model_validate(report)

    def resolve(self, user: User, report_id: int, payload: ReportResolveRequest) -> ReportRead:
        report = self._require_report(report_id)
        actor = _acting_staff_profile(user)
        target = _RESOLUTION_TARGETS[payload.resolution]
        self._transition(report, target)
        crud.update_report(
            self.db,
            report,
            resolved_by_profile_id=actor.id,
            resolution_note=payload.note,
            resolved_at=_utcnow(),
        )
        self.staff_actions.record(
            actor_profile_id=actor.id,
            action_type=_RESOLUTION_ACTIONS[payload.resolution],
            target_type=StaffTargetType.REPORT,
            target_id=report.id,
            reason=payload.note,
            metadata={"status": report.status.value},
        )
        self.audit.record(
            actor_profile_id=actor.id,
            event_type=_RESOLUTION_EVENTS[payload.resolution],
            entity_type=AuditEntityType.REPORT,
            entity_id=report.id,
            after_state=_report_snapshot(report),
        )
        self.db.commit()
        self.db.refresh(report)
        return ReportRead.model_validate(report)

    def _require_report(self, report_id: int) -> Report:
        report = crud.get_report(self.db, report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        return report

    def _transition(self, report: Report, target: ReportStatus) -> None:
        if not policy.can_transition_report(report.status, target):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot move report from {report.status.value} to {target.value}",
            )
        crud.update_report(self.db, report, status=target)


class FeedService:
    """Retrieval paths for products from followed members and topics (Phase 5 seed)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = ProfileService(db)

    def feed(self, user: User, *, limit: int, offset: int) -> list[ProductRead]:
        profile = self.profiles.require_member_profile(user)
        return self.for_profile(profile.id, limit=limit, offset=offset)

    def for_profile(self, profile_id: int, *, limit: int, offset: int) -> list[ProductRead]:
        candidates = [
            *crud.list_products_from_followed_members(
                self.db, profile_id, limit=limit, offset=offset
            ),
            *crud.list_products_from_followed_topics(
                self.db, profile_id, limit=limit, offset=offset
            ),
        ]
        today = _today()
        seen: set[int] = set()
        feed: list[ProductRead] = []
        for product in candidates:
            if product.id in seen:
                continue
            seen.add(product.id)
            if products_policy.is_publicly_visible(product, today):
                feed.append(ProductRead.model_validate(product))
        return feed
