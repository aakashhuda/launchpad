from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Select, func, literal_column, select, update
from sqlalchemy.orm import Session, selectinload

from src.community.models import Vote
from src.discovery.models import DaySnapshot, DaySnapshotItem
from src.products.models import LaunchState, Product, ProductLaunch, ProductTopic
from src.products.policy import PUBLICLY_VISIBLE_STATUSES
from src.users.models import Profile, User

# --- shared visibility predicate ---


def _vote_counts_subquery():
    return (
        select(Vote.product_id.label("product_id"), func.count(Vote.id).label("vote_count"))
        .group_by(Vote.product_id)
        .subquery()
    )


def _visible_conditions(today: date) -> list:
    """SQL mirror of ``products.policy.is_publicly_visible``.

    A product is public when its status is visible, its owner's email is
    verified, and its launch is not cancelled and has arrived.
    """
    return [
        Product.status.in_(list(PUBLICLY_VISIBLE_STATUSES)),
        User.email_verified.is_(True),
        ProductLaunch.state != LaunchState.CANCELLED,
        ProductLaunch.launch_date <= today,
    ]


def _ranked_products_stmt(today: date) -> Select:
    """Select of ``(Product, ProductLaunch, vote_count)`` over visible products."""
    votes = _vote_counts_subquery()
    return (
        select(Product, ProductLaunch, func.coalesce(votes.c.vote_count, 0).label("vote_count"))
        .join(ProductLaunch, ProductLaunch.product_id == Product.id)
        .join(Profile, Profile.id == Product.profile_id)
        .join(User, User.id == Profile.user_id)
        .outerjoin(votes, votes.c.product_id == Product.id)
        .where(*_visible_conditions(today))
    )


def _search_vector():
    # Expression index ``products_search_idx`` must match this expression exactly.
    return func.to_tsvector(
        literal_column("'english'::regconfig"),
        Product.name.op("||")(literal_column("' '")).op("||")(Product.description),
    )


# --- daily ranking ---


def list_launches_for_date(
    db: Session, on_date: date, *, today: date | None = None
) -> list[tuple[Product, ProductLaunch, int]]:
    stmt = _ranked_products_stmt(today or on_date).where(ProductLaunch.launch_date == on_date)
    return [tuple(row) for row in db.execute(stmt).all()]


def list_topic_launches(
    db: Session,
    topic_id: int,
    *,
    today: date,
    since: date | None,
    limit: int,
    offset: int,
) -> list[tuple[Product, ProductLaunch, int]]:
    votes = _vote_counts_subquery()
    conditions = [*_visible_conditions(today), ProductTopic.topic_id == topic_id]
    if since is not None:
        conditions.append(ProductLaunch.launch_date >= since)
    stmt = (
        select(Product, ProductLaunch, func.coalesce(votes.c.vote_count, 0).label("vote_count"))
        .join(ProductLaunch, ProductLaunch.product_id == Product.id)
        .join(Profile, Profile.id == Product.profile_id)
        .join(User, User.id == Profile.user_id)
        .join(ProductTopic, ProductTopic.product_id == Product.id)
        .outerjoin(votes, votes.c.product_id == Product.id)
        .where(*conditions)
        .order_by(func.coalesce(votes.c.vote_count, 0).desc(), Product.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


# --- search ---


def search_products(
    db: Session,
    *,
    query: str,
    topic_id: int | None,
    order_by_votes: bool,
    today: date,
    limit: int,
    offset: int,
) -> list[tuple[Product, int]]:
    votes = _vote_counts_subquery()
    tsquery = func.plainto_tsquery(literal_column("'english'::regconfig"), query)
    conditions = [*_visible_conditions(today), _search_vector().op("@@")(tsquery)]
    stmt = (
        select(Product, func.coalesce(votes.c.vote_count, 0).label("vote_count"))
        .join(ProductLaunch, ProductLaunch.product_id == Product.id)
        .join(Profile, Profile.id == Product.profile_id)
        .join(User, User.id == Profile.user_id)
        .outerjoin(votes, votes.c.product_id == Product.id)
        .where(*conditions)
    )
    if topic_id is not None:
        stmt = stmt.join(ProductTopic, ProductTopic.product_id == Product.id).where(
            ProductTopic.topic_id == topic_id
        )
    if order_by_votes:
        stmt = stmt.order_by(func.coalesce(votes.c.vote_count, 0).desc(), Product.id.asc())
    else:
        stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
    return [tuple(row) for row in db.execute(stmt.limit(limit).offset(offset)).all()]


# --- day snapshots (write-once) ---


def get_snapshot_by_date(db: Session, on_date: date) -> DaySnapshot | None:
    # Eager-load items + their products so the read path is single-round-trip
    # (no N+1 when serializing a day's ranked entries).
    return db.scalar(
        select(DaySnapshot)
        .options(selectinload(DaySnapshot.items).joinedload(DaySnapshotItem.product))
        .where(DaySnapshot.launch_date == on_date)
    )


def create_snapshot(db: Session, *, on_date: date, frozen_at: datetime) -> DaySnapshot:
    snapshot = DaySnapshot(launch_date=on_date, frozen_at=frozen_at)
    db.add(snapshot)
    db.flush()
    return snapshot


def create_snapshot_item(
    db: Session,
    *,
    snapshot_id: int,
    product_id: int,
    rank: int,
    vote_count: int,
    score: float,
) -> DaySnapshotItem:
    item = DaySnapshotItem(
        snapshot_id=snapshot_id,
        product_id=product_id,
        rank=rank,
        vote_count=vote_count,
        score=score,
    )
    db.add(item)
    db.flush()
    return item


def stamp_launches_frozen(db: Session, on_date: date, frozen_at: datetime) -> int:
    result = db.execute(
        update(ProductLaunch)
        .where(ProductLaunch.launch_date == on_date)
        .values(snapshot_frozen_at=frozen_at)
    )
    db.flush()
    return result.rowcount or 0
