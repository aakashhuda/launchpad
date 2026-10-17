"""Reset the development database and load dummy data for manual/API testing.

Wipes every application table, then seeds a known dataset so the Restfox
collection (`restfox/launchpad-api.restfox.json`) and the walkthrough in
`context/docs/plans/06-api-testing-with-restfox.md` work out of the box:

- roles (member / founder / reviewer / admin)
- accounts, all verified, password ``password123``:
    tester@example.com   (member)   founder@example.com  (founder)
    member2@example.com  (member)   reviewer@example.com (reviewer)
                                    admin@example.com    (admin)
- topics, products across lifecycle states (draft, in review, scheduled,
  live today, live yesterday), votes, a comment, an open report, a featured
  product, notifications, and a frozen day snapshot for yesterday.

Run from ``backend/`` with the virtualenv active:

    python scripts/seed_dev_data.py

Set ``DATABASE_URL`` to target a different database. Refuses to run when
``APP_ENV=production``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, text  # noqa: E402

import src.shared.registry  # noqa: F401,E402  (load every mapper)
from src.community.models import Comment, Report, ReportReason, Vote  # noqa: E402
from src.community.schemas import CommentCreate, ReportCreate  # noqa: E402
from src.community.service import CommentService, ReportService, VoteService  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.database import SessionLocal  # noqa: E402
from src.core.security import hash_password  # noqa: E402
from src.discovery.service import SnapshotService  # noqa: E402
from src.notifications.models import Notification, NotificationEventType  # noqa: E402
from src.notifications.service import NotificationService  # noqa: E402
from src.products import crud as products_crud  # noqa: E402
from src.products.models import FeaturedProduct, Product, ProductStatus  # noqa: E402
from src.products.schemas import (  # noqa: E402
    LaunchScheduleRequest,
    ProductCreate,
    SubmissionDecision,
    SubmissionDecisionRequest,
)
from src.products.service import (  # noqa: E402
    ProductFeatureService,
    ProductLaunchService,
    ProductService,
    ProductTopicService,
    SubmissionService,
)
from src.shared.base_model import Base  # noqa: E402
from src.topics.models import Topic  # noqa: E402
from src.users.models import AuthProvider, User  # noqa: E402
from src.users.schemas import ProfileCreate, UserCreate  # noqa: E402
from src.users.service import ProfileService, UserService  # noqa: E402

PASSWORD = "password123"

ROLES = {
    "member": ("Member", {"vote": True, "comment": True, "follow": True, "report": True}),
    "founder": (
        "Founder",
        {
            "vote": True,
            "comment": True,
            "follow": True,
            "report": True,
            "submit_product": True,
        },
    ),
    "reviewer": ("Reviewer", {"moderate_submissions": True, "moderate_reports": True}),
    "admin": (
        "Admin",
        {
            "moderate_submissions": True,
            "moderate_reports": True,
            "manage_users": True,
            "takedown_products": True,
            "feature_products": True,
            "manage_roles": True,
        },
    ),
}


def _utc_today():
    return datetime.now(timezone.utc).date()


def reset_database(db) -> None:
    """Truncate every application table and reset identity sequences."""
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    db.commit()


def seed_roles(db) -> None:
    from src.users.service import RoleService

    for slug, (name, permissions) in ROLES.items():
        RoleService(db).get_or_create(slug, name=name, permissions=permissions)
    db.commit()


def make_user(db, email: str, role: str, first_name: str, last_name: str):
    user = UserService(db).create(
        UserCreate(
            email=email,
            first_name=first_name,
            last_name=last_name,
            auth_provider=AuthProvider.EMAIL,
        ),
        password_hash=hash_password(PASSWORD),
    )
    user.email_verified = True
    ProfileService(db).create_for_user(user, ProfileCreate(role_slug=role))
    db.commit()
    db.refresh(user)
    return user


def profile_id_for(db, user, role: str) -> int:
    profile = ProfileService(db).profile_with_role(user, role)
    assert profile is not None, f"{user.email} has no {role} profile"
    return profile.id


def latest_submission_id(db, product_id: int) -> int:
    submission = products_crud.get_latest_submission_for_product(db, product_id)
    assert submission is not None
    return submission.id


def create_visible_product(db, founder, reviewer, name: str, topics: list[str]) -> int:
    """Create a product, submit it, approve it, and schedule it for today."""
    detail = ProductService(db).create_draft(
        founder,
        ProductCreate(
            name=name,
            one_line_pitch=f"{name} — a launchpad test product",
            description=f"{name} is dummy data seeded for API testing.",
            logo_url="https://example.com/logo.png",
            website_url="https://example.com",
            topics=topics,
        ),
    )
    product_id = detail.id
    SubmissionService(db).submit_for_review(founder, product_id)
    SubmissionService(db).decide(
        reviewer,
        latest_submission_id(db, product_id),
        SubmissionDecisionRequest(decision=SubmissionDecision.APPROVE, note="Looks good"),
    )
    ProductLaunchService(db).schedule(
        founder, product_id, LaunchScheduleRequest(launch_date=_utc_today())
    )
    return product_id


def main() -> None:
    if settings.app_env == "production":
        raise SystemExit("Refusing to run against APP_ENV=production")

    db = SessionLocal()
    try:
        print(f"Resetting and seeding {settings.database_url} ...")
        reset_database(db)
        seed_roles(db)

        tester = make_user(db, "tester@example.com", "member", "Terry", "Tester")
        member2 = make_user(db, "member2@example.com", "member", "Morgan", "Member")
        founder = make_user(db, "founder@example.com", "founder", "Fiona", "Founder")
        reviewer = make_user(db, "reviewer@example.com", "reviewer", "Rex", "Reviewer")
        admin = make_user(db, "admin@example.com", "admin", "Ada", "Admin")

        # --- live product (launched today), featured, voted, commented, reported
        live_id = create_visible_product(db, founder, reviewer, "Acme Rocket", ["AI", "DevTools"])
        ProductLaunchService(db).activate(live_id)

        # --- scheduled today (visible, not yet live)
        scheduled_id = create_visible_product(db, founder, reviewer, "Beta Widget", ["DevTools"])

        # --- in review (appears in the staff submission queue)
        pending = ProductService(db).create_draft(
            founder,
            ProductCreate(
                name="Gamma Tool",
                one_line_pitch="Awaiting review",
                description="Submitted but not yet decided.",
                logo_url="https://example.com/logo.png",
                website_url="https://example.com",
                topics=["Productivity"],
            ),
        )
        SubmissionService(db).submit_for_review(founder, pending.id)

        # --- draft (private to the founder)
        ProductService(db).create_draft(
            founder,
            ProductCreate(
                name="Delta Sketch",
                one_line_pitch="A not-yet-finished draft",
                description="Draft product for testing ownership/embargo.",
                logo_url="https://example.com/logo.png",
                website_url="https://example.com",
                topics=["Productivity"],
            ),
        )

        # --- launched yesterday (gives the frozen day snapshot something to hold)
        yesterday = _utc_today() - timedelta(days=1)
        founder_profile_id = profile_id_for(db, founder, "founder")
        yesterday_product = products_crud.create_product(
            db,
            profile_id=founder_profile_id,
            name="Yesterday Launch",
            one_line_pitch="Launched yesterday",
            description="Product launched yesterday so the day snapshot has data.",
            logo_url="https://example.com/logo.png",
            screenshot_urls=None,
            website_url="https://example.com",
        )
        products_crud.update_product(db, yesterday_product, status=ProductStatus.APPROVED)
        products_crud.create_launch(db, product_id=yesterday_product.id, launch_date=yesterday)
        db.commit()
        ProductTopicService(db).set_topics(yesterday_product, ["AI"])
        ProductLaunchService(db).activate(yesterday_product.id)

        # --- community interactions
        VoteService(db).vote(tester, live_id)
        VoteService(db).vote(member2, live_id)
        VoteService(db).vote(tester, scheduled_id)
        CommentService(db).create(tester, live_id, CommentCreate(text="Looks great!"))

        report = ReportService(db).report_product(
            member2, live_id, ReportCreate(reason=ReportReason.SPAM, details="Seeded report")
        )

        # --- featured product (front page)
        ProductFeatureService(db).feature(admin, live_id, "Editor's pick")

        # --- a frozen snapshot for yesterday
        SnapshotService(db).freeze(yesterday)

        # --- a notification for the default tester account
        tester_profile_id = profile_id_for(db, tester, "member")
        NotificationService(db).emit(
            recipient_profile_id=tester_profile_id,
            event_type=NotificationEventType.RANKING_DAILY_TOP_FIVE,
            payload={"date": yesterday.isoformat(), "items": []},
        )
        db.commit()

        # --- summary
        def count(model) -> int:
            return int(db.scalar(select(func.count()).select_from(model)) or 0)

        print("\nSeeded data:")
        print(f"  users={count(User)} topics={count(Topic)} products={count(Product)}")
        print(f"  votes={count(Vote)} comments={count(Comment)} reports={count(Report)}")
        print(f"  featured={count(FeaturedProduct)} notifications={count(Notification)}")
        print("\nAccounts (password: password123, all email-verified):")
        print("  tester@example.com    member   (matches the collection default)")
        print("  member2@example.com   member")
        print("  founder@example.com   founder")
        print("  reviewer@example.com  reviewer")
        print("  admin@example.com     admin")
        print(
            f"\nProduct ids: live={live_id} scheduled={scheduled_id} "
            f"pending={pending.id} report={report.id}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
