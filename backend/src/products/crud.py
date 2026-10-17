from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.products.models import (
    FeaturedProduct,
    FounderExport,
    LaunchState,
    Product,
    ProductLaunch,
    ProductStatus,
    ProductTopic,
    Submission,
    SubmissionStatus,
)
from src.topics.models import Topic


def create_product(
    db: Session,
    *,
    profile_id: int,
    name: str,
    one_line_pitch: str,
    description: str,
    logo_url: str,
    screenshot_urls: list[str] | None,
    website_url: str | None,
) -> Product:
    product = Product(
        profile_id=profile_id,
        name=name,
        one_line_pitch=one_line_pitch,
        description=description,
        logo_url=logo_url,
        screenshot_urls=screenshot_urls,
        website_url=website_url,
        status=ProductStatus.DRAFT,
    )
    db.add(product)
    db.flush()
    return product


def get_product(db: Session, product_id: int) -> Product | None:
    return db.get(Product, product_id)


def list_products_by_profile(db: Session, profile_id: int) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .where(Product.profile_id == profile_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
        )
    )


def update_product(db: Session, product: Product, **fields: object) -> Product:
    for key, value in fields.items():
        setattr(product, key, value)
    db.flush()
    return product


def set_product_topics(db: Session, product: Product, topics: list[Topic]) -> None:
    db.execute(delete(ProductTopic).where(ProductTopic.product_id == product.id))
    db.flush()
    for topic in topics:
        db.add(ProductTopic(product_id=product.id, topic_id=topic.id))
    db.flush()
    db.expire(product, ["product_topics"])


def create_submission(
    db: Session,
    *,
    profile_id: int,
    product_id: int,
    status: SubmissionStatus = SubmissionStatus.DRAFT,
) -> Submission:
    submission = Submission(profile_id=profile_id, product_id=product_id, status=status)
    db.add(submission)
    db.flush()
    return submission


def get_submission(db: Session, submission_id: int) -> Submission | None:
    return db.get(Submission, submission_id)


def get_latest_submission_for_product(db: Session, product_id: int) -> Submission | None:
    return db.scalar(
        select(Submission)
        .where(Submission.product_id == product_id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
    )


def list_submissions_by_status(
    db: Session, status: SubmissionStatus, *, limit: int, offset: int
) -> list[Submission]:
    return list(
        db.scalars(
            select(Submission)
            .where(Submission.status == status)
            .order_by(Submission.created_at.asc(), Submission.id.asc())
            .limit(limit)
            .offset(offset)
        )
    )


def update_submission(db: Session, submission: Submission, **fields: object) -> Submission:
    for key, value in fields.items():
        setattr(submission, key, value)
    db.flush()
    return submission


def create_launch(db: Session, *, product_id: int, launch_date: date) -> ProductLaunch:
    launch = ProductLaunch(
        product_id=product_id,
        launch_date=launch_date,
        state=LaunchState.SCHEDULED,
    )
    db.add(launch)
    db.flush()
    return launch


def get_launch_for_product(db: Session, product_id: int) -> ProductLaunch | None:
    return db.scalar(select(ProductLaunch).where(ProductLaunch.product_id == product_id))


def set_launch_date(db: Session, launch: ProductLaunch, launch_date: date) -> ProductLaunch:
    launch.launch_date = launch_date
    db.flush()
    return launch


def set_launch_state(
    db: Session, launch: ProductLaunch, state: LaunchState, **fields: object
) -> ProductLaunch:
    launch.state = state
    for key, value in fields.items():
        setattr(launch, key, value)
    db.flush()
    return launch


def list_scheduled_product_ids_for_date(db: Session, on_date: date) -> list[int]:
    """Product ids whose launch is scheduled to arrive on ``on_date``."""
    return list(
        db.scalars(
            select(ProductLaunch.product_id)
            .where(
                ProductLaunch.launch_date == on_date,
                ProductLaunch.state == LaunchState.SCHEDULED,
            )
            .order_by(ProductLaunch.id.asc())
        )
    )


def count_launches_for_profile_on_date(
    db: Session,
    profile_id: int,
    launch_date: date,
    *,
    exclude_product_id: int | None = None,
) -> int:
    stmt = (
        select(func.count(ProductLaunch.id))
        .join(Product, Product.id == ProductLaunch.product_id)
        .where(
            Product.profile_id == profile_id,
            ProductLaunch.launch_date == launch_date,
            ProductLaunch.state != LaunchState.CANCELLED,
        )
    )
    if exclude_product_id is not None:
        stmt = stmt.where(ProductLaunch.product_id != exclude_product_id)
    return int(db.scalar(stmt) or 0)


def create_export(db: Session, *, product_id: int, requested_by_profile_id: int) -> FounderExport:
    export = FounderExport(product_id=product_id, requested_by_profile_id=requested_by_profile_id)
    db.add(export)
    db.flush()
    return export


def get_export(db: Session, export_id: int) -> FounderExport | None:
    return db.get(FounderExport, export_id)


def update_export(db: Session, export: FounderExport, **fields: object) -> FounderExport:
    for key, value in fields.items():
        setattr(export, key, value)
    db.flush()
    return export


# --- featured products (Phase 7 staff governance) ---


def get_featured_product(db: Session, product_id: int) -> FeaturedProduct | None:
    return db.scalar(select(FeaturedProduct).where(FeaturedProduct.product_id == product_id))


def create_featured_product(
    db: Session,
    *,
    product_id: int,
    featured_by_profile_id: int,
    reason: str,
    ends_at: datetime | None,
) -> FeaturedProduct:
    featured = FeaturedProduct(
        product_id=product_id,
        featured_by_profile_id=featured_by_profile_id,
        reason=reason,
        ends_at=ends_at,
    )
    db.add(featured)
    db.flush()
    return featured


def delete_featured_product(db: Session, featured: FeaturedProduct) -> None:
    db.delete(featured)
    db.flush()


def list_active_featured_product_ids(db: Session, *, at: datetime) -> list[int]:
    """Product ids whose feature is still active (no expiry, or expiry in the future)."""
    return list(
        db.scalars(
            select(FeaturedProduct.product_id)
            .where((FeaturedProduct.ends_at.is_(None)) | (FeaturedProduct.ends_at > at))
            .order_by(FeaturedProduct.created_at.desc(), FeaturedProduct.id.desc())
        )
    )


def list_active_featured_products(
    db: Session, *, at: datetime, limit: int, offset: int
) -> list[FeaturedProduct]:
    return list(
        db.scalars(
            select(FeaturedProduct)
            .where((FeaturedProduct.ends_at.is_(None)) | (FeaturedProduct.ends_at > at))
            .order_by(FeaturedProduct.created_at.desc(), FeaturedProduct.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
