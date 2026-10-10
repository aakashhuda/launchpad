from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from src.core.security import create_access_token, create_email_verification_token
from src.products import service as products_service
from src.products.models import ProductStatus, SubmissionStatus
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _utc_today() -> date:
    """Launch-day boundaries are evaluated in UTC by the service."""
    return datetime.now(timezone.utc).date()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _signup(client, role: str, *, verify: bool = True) -> dict:
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "email": _unique_email(),
            "password": "password123",
            "first_name": "Test",
            "last_name": "User",
            "role": role,
        },
    )
    assert resp.status_code == 201, resp.text
    headers = _bearer(resp.json()["access_token"])
    if verify:
        me = client.get("/api/v1/users/me", headers=headers).json()
        token = create_email_verification_token(str(me["id"]))
        verified = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert verified.status_code == 200, verified.text
    return headers


def _staff(client, db_session, role_slug: str, *, verified: bool = True) -> dict:
    user = UserService(db_session).create(
        UserCreate(
            email=_unique_email(),
            first_name="Sta",
            last_name="Ff",
            auth_provider=AuthProvider.EMAIL,
        )
    )
    ProfileService(db_session).create_for_user(user, ProfileCreate(role_slug=role_slug))
    user.email_verified = verified
    db_session.commit()
    return _bearer(create_access_token(str(user.id)))


def _current_user(client, db_session, headers: dict):
    me = client.get("/api/v1/users/me", headers=headers).json()
    return UserService(db_session).get_by_id(me["id"])


def _payload(**overrides) -> dict:
    payload = {
        "name": "Acme",
        "one_line_pitch": "Does things well",
        "description": "A longer description of the product.",
        "logo_url": "https://example.com/logo.png",
        "website_url": "https://example.com",
        "topics": ["AI", "DevTools"],
    }
    payload.update(overrides)
    return payload


def _create(client, headers, **overrides) -> dict:
    resp = client.post("/api/v1/products", json=_payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _submit(client, headers, product_id: int) -> dict:
    resp = client.post(f"/api/v1/products/{product_id}/submit", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _decide(client, headers, submission_id: int, decision: str, note: str | None = None):
    return client.post(
        f"/api/v1/staff/submissions/{submission_id}/decision",
        json={"decision": decision, "note": note},
        headers=headers,
    )


def _approved(client, founder, reviewer, **overrides) -> dict:
    product = _create(client, founder, **overrides)
    submission = _submit(client, founder, product["id"])
    resp = _decide(client, reviewer, submission["id"], "approve")
    assert resp.status_code == 200, resp.text
    return product


def test_founder_creates_draft_and_lists_it(client):
    founder = _signup(client, "founder")
    product = _create(client, founder)
    assert product["status"] == ProductStatus.DRAFT.value
    assert sorted(product["topics"]) == ["AI", "DevTools"]

    listed = client.get("/api/v1/products/mine", headers=founder)
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [product["id"]]


def test_create_requires_founder_role(client):
    member = _signup(client, "member")
    assert client.post("/api/v1/products", json=_payload(), headers=member).status_code == 403
    assert client.post("/api/v1/products", json=_payload()).status_code == 401


def test_more_than_three_topics_rejected(client):
    founder = _signup(client, "founder")
    resp = client.post(
        "/api/v1/products",
        json=_payload(topics=["a", "b", "c", "d"]),
        headers=founder,
    )
    assert resp.status_code == 422


def test_reviewer_queue_orders_oldest_first(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")

    first = _create(client, founder, name="First")
    second = _create(client, founder, name="Second")
    _submit(client, founder, first["id"])
    _submit(client, founder, second["id"])

    resp = client.get("/api/v1/staff/submissions", headers=reviewer)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert ids == sorted(ids)
    assert len(ids) == 2


def test_queue_requires_staff(client):
    member = _signup(client, "member")
    assert client.get("/api/v1/staff/submissions", headers=member).status_code == 403
    assert client.get("/api/v1/staff/submissions").status_code == 401


def test_only_owner_can_submit_others_product(client, db_session):
    owner = _signup(client, "founder")
    other = _signup(client, "founder")
    product = _create(client, owner)
    resp = client.post(f"/api/v1/products/{product['id']}/submit", headers=other)
    assert resp.status_code == 403


def test_approve_moves_submission_and_product(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _create(client, founder)
    submission = _submit(client, founder, product["id"])
    assert submission["status"] == SubmissionStatus.IN_REVIEW.value

    resp = _decide(client, reviewer, submission["id"], "approve", note="Looks good")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == SubmissionStatus.APPROVED.value
    assert body["review_note"] == "Looks good"
    assert body["reviewed_by_profile_id"] is not None
    assert body["reviewed_at"] is not None

    detail = client.get(f"/api/v1/products/{product['id']}", headers=founder).json()
    assert detail["status"] == ProductStatus.APPROVED.value


def test_reject_and_double_decision_conflict(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _create(client, founder)
    submission = _submit(client, founder, product["id"])

    resp = _decide(client, reviewer, submission["id"], "reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == SubmissionStatus.REJECTED.value

    again = _decide(client, reviewer, submission["id"], "approve")
    assert again.status_code == 409


def test_request_changes_then_resubmit(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _create(client, founder)
    submission = _submit(client, founder, product["id"])

    resp = _decide(client, reviewer, submission["id"], "request_changes")
    assert resp.status_code == 200
    assert resp.json()["status"] == SubmissionStatus.CHANGES_REQUESTED.value

    resubmitted = _submit(client, founder, product["id"])
    assert resubmitted["status"] == SubmissionStatus.IN_REVIEW.value


def test_embargo_hides_product_before_launch(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    assert client.get(f"/api/v1/products/{product['id']}").status_code == 404
    assert client.get(f"/api/v1/products/{product['id']}", headers=founder).status_code == 200


def test_scheduled_future_launch_stays_embargoed(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    future = (_utc_today() + timedelta(days=5)).isoformat()
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": future},
        headers=founder,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == ProductStatus.SCHEDULED.value
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 404


def test_visible_on_launch_day(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    today = _utc_today().isoformat()
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": today},
        headers=founder,
    )
    assert resp.status_code == 200

    public = client.get(f"/api/v1/products/{product['id']}")
    assert public.status_code == 200
    assert public.json()["id"] == product["id"]


def test_launch_cap_per_founder_per_day(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    today = _utc_today().isoformat()

    products = [_approved(client, founder, reviewer, name=f"P{i}") for i in range(3)]

    first = client.post(
        f"/api/v1/products/{products[0]['id']}/launch",
        json={"launch_date": today},
        headers=founder,
    )
    second = client.post(
        f"/api/v1/products/{products[1]['id']}/launch",
        json={"launch_date": today},
        headers=founder,
    )
    third = client.post(
        f"/api/v1/products/{products[2]['id']}/launch",
        json={"launch_date": today},
        headers=founder,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 409


def test_post_launch_edit_lock(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    today = _utc_today().isoformat()
    client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": today},
        headers=founder,
    )
    products_service.ProductLaunchService(db_session).activate(product["id"])

    locked = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"name": "Renamed"},
        headers=founder,
    )
    assert locked.status_code == 409

    allowed = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"description": "Updated after launch"},
        headers=founder,
    )
    assert allowed.status_code == 200
    assert allowed.json()["description"] == "Updated after launch"


def test_moderation_writes_staff_action_and_audit_log(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _create(client, founder)
    submission = _submit(client, founder, product["id"])
    assert _decide(client, reviewer, submission["id"], "approve").status_code == 200

    actions = client.get("/api/v1/staff/actions", headers=reviewer)
    assert actions.status_code == 200
    body = actions.json()
    assert any(a["action_type"] == "approve_submission" for a in body)
    assert all(a["created_at"] for a in body)

    from sqlalchemy import select

    from src.staff.models import AuditLog

    logs = list(db_session.scalars(select(AuditLog)))
    assert any(log.event_type.value == "submission.approved" for log in logs)


def test_schedule_requires_approved_product(client, db_session):
    founder = _signup(client, "founder")
    product = _create(client, founder)
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _utc_today().isoformat()},
        headers=founder,
    )
    assert resp.status_code == 409


def test_launch_date_cannot_be_in_the_past(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)
    past = (_utc_today() - timedelta(days=1)).isoformat()
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": past},
        headers=founder,
    )
    assert resp.status_code == 422


def test_unverified_founder_cannot_act(client):
    founder = _signup(client, "founder", verify=False)
    created = client.post("/api/v1/products", json=_payload(), headers=founder)
    assert created.status_code == 403
    assert "verif" in created.json()["detail"].lower()
    assert client.get("/api/v1/products/mine", headers=founder).status_code == 403


def test_unverified_member_cannot_act(client):
    member = _signup(client, "member", verify=False)
    assert client.get("/api/v1/products/mine", headers=member).status_code == 403


def test_unverified_reviewer_cannot_decide(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer", verified=False)
    product = _create(client, founder)
    submission = _submit(client, founder, product["id"])

    assert client.get("/api/v1/staff/submissions", headers=reviewer).status_code == 403
    decided = _decide(client, reviewer, submission["id"], "approve")
    assert decided.status_code == 403


def test_product_hidden_when_owner_unverified(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _utc_today().isoformat()},
        headers=founder,
    )
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 200

    owner = _current_user(client, db_session, founder)
    owner.email_verified = False
    db_session.commit()
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 404

    owner.email_verified = True
    db_session.commit()
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 200
