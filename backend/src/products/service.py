from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core.config import settings
from src.products import crud, policy
from src.products.models import (
    LaunchState,
    Product,
    ProductLaunch,
    ProductStatus,
    Submission,
    SubmissionStatus,
)
from src.products.schemas import (
    LaunchRead,
    LaunchScheduleRequest,
    ProductCreate,
    ProductDetailRead,
    ProductRead,
    ProductUpdate,
    SubmissionDecision,
    SubmissionDecisionRequest,
    SubmissionRead,
)
from src.staff.models import AuditEntityType, AuditEventType, StaffActionType, StaffTargetType
from src.staff.service import AuditLogService, StaffActionService
from src.topics import crud as topics_crud
from src.users.models import Profile, User

FOUNDER_ROLE = "founder"
STAFF_ROLES = ("reviewer", "admin")

_DECISION_TARGETS = {
    SubmissionDecision.APPROVE: SubmissionStatus.APPROVED,
    SubmissionDecision.REJECT: SubmissionStatus.REJECTED,
    SubmissionDecision.REQUEST_CHANGES: SubmissionStatus.CHANGES_REQUESTED,
}

_DECISION_ACTIONS = {
    SubmissionDecision.APPROVE: StaffActionType.APPROVE_SUBMISSION,
    SubmissionDecision.REJECT: StaffActionType.REJECT_SUBMISSION,
    SubmissionDecision.REQUEST_CHANGES: StaffActionType.REQUEST_SUBMISSION_CHANGES,
}

_DECISION_EVENTS = {
    SubmissionDecision.APPROVE: AuditEventType.SUBMISSION_APPROVED,
    SubmissionDecision.REJECT: AuditEventType.SUBMISSION_REJECTED,
    SubmissionDecision.REQUEST_CHANGES: AuditEventType.SUBMISSION_CHANGES_REQUESTED,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _product_snapshot(product: Product) -> dict:
    return {"id": product.id, "name": product.name, "status": product.status.value}


class ProductTopicService:
    """Resolves and (re)binds a product's topics (max three, enforced by schema)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def set_topics(self, product: Product, texts: list[str]) -> None:
        topics = [topics_crud.get_or_create_topic(self.db, text) for text in texts]
        crud.set_product_topics(self.db, product, topics)


class ProductService:
    """Product drafting, ownership, visibility, and post-launch edit rules."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.topics = ProductTopicService(db)
        self.audit = AuditLogService(db)

    # --- founder operations ---

    def create_draft(self, user: User, payload: ProductCreate) -> ProductDetailRead:
        profile = self.require_founder(user)
        product = crud.create_product(
            self.db,
            profile_id=profile.id,
            name=payload.name,
            one_line_pitch=payload.one_line_pitch,
            description=payload.description,
            logo_url=payload.logo_url,
            screenshot_urls=payload.screenshot_urls,
            website_url=payload.website_url,
        )
        self.topics.set_topics(product, payload.topics)
        crud.create_submission(self.db, profile_id=profile.id, product_id=product.id)
        self.audit.record(
            actor_profile_id=profile.id,
            event_type=AuditEventType.PRODUCT_CREATED,
            entity_type=AuditEntityType.PRODUCT,
            entity_id=product.id,
            after_state=_product_snapshot(product),
        )
        self.db.commit()
        self.db.refresh(product)
        return self.detail(product)

    def list_for_user(self, user: User) -> list[ProductRead]:
        profile = self.require_founder(user)
        return [
            ProductRead.model_validate(product)
            for product in crud.list_products_by_profile(self.db, profile.id)
        ]

    def update(self, user: User, product_id: int, payload: ProductUpdate) -> ProductDetailRead:
        product, profile = self.require_owned_product(user, product_id)
        changes = payload.model_dump(exclude_unset=True)

        if policy.is_launched(product):
            locked = policy.locked_fields_after_launch(changes)
            if locked:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Fields not editable after launch: {', '.join(sorted(locked))}",
                )

        before = _product_snapshot(product)
        topics = changes.pop("topics", None)
        crud.update_product(self.db, product, **changes)
        if topics is not None:
            self.topics.set_topics(product, topics)
        self.audit.record(
            actor_profile_id=profile.id,
            event_type=AuditEventType.PRODUCT_UPDATED,
            entity_type=AuditEntityType.PRODUCT,
            entity_id=product.id,
            before_state=before,
            after_state=_product_snapshot(product),
        )
        self.db.commit()
        self.db.refresh(product)
        return self.detail(product)

    # --- reads ---

    def get_readable(self, user: User | None, product_id: int) -> ProductDetailRead:
        product = crud.get_product(self.db, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        if user is not None and self.owns(user, product):
            return self.detail(product)
        if policy.is_publicly_visible(product, _utcnow().date()):
            return self.detail(product)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # --- ownership helpers (shared with sibling services) ---

    @staticmethod
    def founder_profile(user: User) -> Profile | None:
        for profile in user.profiles:
            if profile.role is not None and profile.role.slug == FOUNDER_ROLE:
                return profile
        return None

    def require_founder(self, user: User) -> Profile:
        profile = self.founder_profile(user)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Founder profile required"
            )
        return profile

    def owns(self, user: User, product: Product) -> bool:
        profile = self.founder_profile(user)
        return profile is not None and product.profile_id == profile.id

    def require_owned_product(self, user: User, product_id: int) -> tuple[Product, Profile]:
        product = crud.get_product(self.db, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        profile = self.require_founder(user)
        if product.profile_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not allowed to modify this product",
            )
        return product, profile

    @staticmethod
    def detail(product: Product) -> ProductDetailRead:
        return ProductDetailRead(
            id=product.id,
            name=product.name,
            one_line_pitch=product.one_line_pitch,
            description=product.description,
            logo_url=product.logo_url,
            screenshot_urls=product.screenshot_urls,
            website_url=product.website_url,
            status=product.status,
            created_at=product.created_at,
            topics=[link.topic.text for link in product.product_topics],
            launch=(
                LaunchRead.model_validate(product.product_launch)
                if product.product_launch is not None
                else None
            ),
        )


class SubmissionService:
    """Founder submission intake and reviewer decision workflow."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.products = ProductService(db)
        self.staff_actions = StaffActionService(db)
        self.audit = AuditLogService(db)

    def submit_for_review(self, user: User, product_id: int) -> SubmissionRead:
        product, profile = self.products.require_owned_product(user, product_id)
        submission = crud.get_latest_submission_for_product(self.db, product.id)
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
            )
        self._transition(submission, SubmissionStatus.IN_REVIEW)
        self.audit.record(
            actor_profile_id=profile.id,
            event_type=AuditEventType.SUBMISSION_SUBMITTED,
            entity_type=AuditEntityType.SUBMISSION,
            entity_id=submission.id,
            after_state={"status": submission.status.value},
        )
        self.db.commit()
        self.db.refresh(submission)
        return SubmissionRead.model_validate(submission)

    def list_queue(self, *, limit: int, offset: int) -> list[SubmissionRead]:
        submissions = crud.list_submissions_by_status(
            self.db, SubmissionStatus.IN_REVIEW, limit=limit, offset=offset
        )
        return [SubmissionRead.model_validate(submission) for submission in submissions]

    def decide(
        self, reviewer: User, submission_id: int, payload: SubmissionDecisionRequest
    ) -> SubmissionRead:
        submission = crud.get_submission(self.db, submission_id)
        if submission is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
            )

        target = _DECISION_TARGETS[payload.decision]
        self._transition(submission, target)

        actor = self.acting_staff_profile(reviewer)
        crud.update_submission(
            self.db,
            submission,
            reviewed_by_profile_id=actor.id,
            review_note=payload.note,
            reviewed_at=_utcnow(),
        )

        if target == SubmissionStatus.APPROVED:
            product = crud.get_product(self.db, submission.product_id)
            if product is not None and policy.can_transition_product(
                product.status, ProductStatus.APPROVED
            ):
                crud.update_product(self.db, product, status=ProductStatus.APPROVED)

        self.staff_actions.record(
            actor_profile_id=actor.id,
            action_type=_DECISION_ACTIONS[payload.decision],
            target_type=StaffTargetType.SUBMISSION,
            target_id=submission.id,
            reason=payload.note,
            metadata={"product_id": submission.product_id},
        )
        self.audit.record(
            actor_profile_id=actor.id,
            event_type=_DECISION_EVENTS[payload.decision],
            entity_type=AuditEntityType.SUBMISSION,
            entity_id=submission.id,
            after_state={"status": target.value},
        )
        self.db.commit()
        self.db.refresh(submission)
        return SubmissionRead.model_validate(submission)

    @staticmethod
    def acting_staff_profile(user: User) -> Profile:
        for profile in user.profiles:
            if profile.role is not None and profile.role.slug in STAFF_ROLES:
                return profile
        if not user.profiles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No profile available for staff action",
            )
        return user.profiles[0]

    def _transition(self, submission: Submission, target: SubmissionStatus) -> None:
        if not policy.can_transition_submission(submission.status, target):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot move submission from {submission.status.value} " f"to {target.value}"
                ),
            )
        crud.update_submission(self.db, submission, status=target)


class ProductLaunchService:
    """Launch-day scheduling with the per-founder/day cap and activation seam."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.products = ProductService(db)
        self.staff_actions = StaffActionService(db)
        self.audit = AuditLogService(db)

    def schedule(
        self, user: User, product_id: int, payload: LaunchScheduleRequest
    ) -> ProductDetailRead:
        product, profile = self.products.require_owned_product(user, product_id)
        if product.status not in (ProductStatus.APPROVED, ProductStatus.SCHEDULED):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product must be approved before scheduling a launch",
            )

        launch = crud.get_launch_for_product(self.db, product.id)
        if launch is not None and launch.state != LaunchState.SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Launched products cannot be rescheduled",
            )

        scheduled_same_day = crud.count_launches_for_profile_on_date(
            self.db, profile.id, payload.launch_date, exclude_product_id=product.id
        )
        if scheduled_same_day >= settings.max_launches_per_founder_per_day:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Daily launch limit reached for this founder",
            )

        if launch is None:
            launch = crud.create_launch(
                self.db, product_id=product.id, launch_date=payload.launch_date
            )
            action_type = StaffActionType.SCHEDULE_LAUNCH
            event_type = AuditEventType.LAUNCH_SCHEDULED
        else:
            crud.set_launch_date(self.db, launch, payload.launch_date)
            action_type = StaffActionType.RESCHEDULE_LAUNCH
            event_type = AuditEventType.LAUNCH_RESCHEDULED

        if product.status == ProductStatus.APPROVED:
            crud.update_product(self.db, product, status=ProductStatus.SCHEDULED)

        launch_date_iso = payload.launch_date.isoformat()
        self.staff_actions.record(
            actor_profile_id=profile.id,
            action_type=action_type,
            target_type=StaffTargetType.LAUNCH,
            target_id=launch.id,
            metadata={"launch_date": launch_date_iso},
        )
        self.audit.record(
            actor_profile_id=profile.id,
            event_type=event_type,
            entity_type=AuditEntityType.LAUNCH,
            entity_id=launch.id,
            after_state={"launch_date": launch_date_iso},
        )
        self.db.commit()
        self.db.refresh(product)
        return self.products.detail(product)

    def activate(self, product_id: int) -> ProductLaunch:
        """Idempotent ``scheduled`` -> ``live`` seam for the Phase 5 day scheduler."""
        launch = crud.get_launch_for_product(self.db, product_id)
        if launch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Launch not found")
        if launch.state == LaunchState.LIVE:
            return launch
        if launch.state != LaunchState.SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only scheduled launches can go live",
            )

        crud.set_launch_state(self.db, launch, LaunchState.LIVE, launched_at=_utcnow())
        product = crud.get_product(self.db, product_id)
        if product is not None and policy.can_transition_product(
            product.status, ProductStatus.LIVE
        ):
            crud.update_product(self.db, product, status=ProductStatus.LIVE)

        self.audit.record(
            actor_profile_id=None,
            event_type=AuditEventType.LAUNCH_ACTIVATED,
            entity_type=AuditEntityType.LAUNCH,
            entity_id=launch.id,
            after_state={"state": LaunchState.LIVE.value},
        )
        self.db.commit()
        return launch
