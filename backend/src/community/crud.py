from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.community.models import (
    Comment,
    Report,
    ReportReason,
    ReportStatus,
    ReportTargetType,
    Vote,
)
from src.products.models import Product, ProductTopic
from src.topics.models import TopicFollow
from src.users.models import MemberFollow

# --- votes ---


def get_vote(db: Session, product_id: int, profile_id: int) -> Vote | None:
    return db.scalar(
        select(Vote).where(Vote.product_id == product_id, Vote.profile_id == profile_id)
    )


def create_vote(db: Session, product_id: int, profile_id: int) -> Vote:
    vote = Vote(product_id=product_id, profile_id=profile_id)
    db.add(vote)
    db.flush()
    return vote


def delete_vote(db: Session, product_id: int, profile_id: int) -> None:
    vote = get_vote(db, product_id, profile_id)
    if vote is not None:
        db.delete(vote)
        db.flush()


def count_votes_for_product(db: Session, product_id: int) -> int:
    return int(db.scalar(select(func.count(Vote.id)).where(Vote.product_id == product_id)) or 0)


# --- comments ---


def get_comment(db: Session, comment_id: int) -> Comment | None:
    return db.get(Comment, comment_id)


def create_comment(
    db: Session,
    *,
    profile_id: int,
    product_id: int,
    parent_comment_id: int | None,
    text: str,
) -> Comment:
    comment = Comment(
        profile_id=profile_id,
        product_id=product_id,
        parent_comment_id=parent_comment_id,
        text=text,
    )
    db.add(comment)
    db.flush()
    return comment


def list_comments_by_product(db: Session, product_id: int) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.product_id == product_id)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
        )
    )


def delete_comment(db: Session, comment: Comment) -> None:
    db.delete(comment)
    db.flush()


# --- reports ---


def get_report(db: Session, report_id: int) -> Report | None:
    return db.get(Report, report_id)


def create_report(
    db: Session,
    *,
    reporter_profile_id: int,
    target_type: ReportTargetType,
    target_product_id: int | None,
    target_comment_id: int | None,
    reason: ReportReason,
    details: str | None,
) -> Report:
    report = Report(
        reporter_profile_id=reporter_profile_id,
        target_type=target_type,
        target_product_id=target_product_id,
        target_comment_id=target_comment_id,
        reason=reason,
        details=details,
        status=ReportStatus.OPEN,
    )
    db.add(report)
    db.flush()
    return report


def get_open_report_for_target(
    db: Session,
    reporter_profile_id: int,
    *,
    target_product_id: int | None = None,
    target_comment_id: int | None = None,
) -> Report | None:
    stmt = select(Report).where(
        Report.reporter_profile_id == reporter_profile_id,
        Report.status == ReportStatus.OPEN,
    )
    if target_product_id is not None:
        stmt = stmt.where(Report.target_product_id == target_product_id)
    if target_comment_id is not None:
        stmt = stmt.where(Report.target_comment_id == target_comment_id)
    return db.scalar(stmt)


def list_reports_by_statuses(
    db: Session, statuses: tuple[ReportStatus, ...], *, limit: int, offset: int
) -> list[Report]:
    return list(
        db.scalars(
            select(Report)
            .where(Report.status.in_(statuses))
            .order_by(Report.created_at.asc(), Report.id.asc())
            .limit(limit)
            .offset(offset)
        )
    )


def update_report(db: Session, report: Report, **fields: object) -> Report:
    for key, value in fields.items():
        setattr(report, key, value)
    db.flush()
    return report


# --- feed scaffolding ---


def list_products_from_followed_members(
    db: Session, profile_id: int, *, limit: int, offset: int
) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .join(MemberFollow, MemberFollow.followed_profile_id == Product.profile_id)
            .where(MemberFollow.follower_profile_id == profile_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def list_products_from_followed_topics(
    db: Session, profile_id: int, *, limit: int, offset: int
) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .join(ProductTopic, ProductTopic.product_id == Product.id)
            .join(TopicFollow, TopicFollow.topic_id == ProductTopic.topic_id)
            .where(TopicFollow.profile_id == profile_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .distinct()
            .limit(limit)
            .offset(offset)
        )
    )
