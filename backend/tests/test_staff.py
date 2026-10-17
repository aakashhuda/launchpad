from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from src.core.security import create_access_token, create_email_verification_token
from src.staff.models import AuditLog, StaffAction
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _signup(client, role: str, *, email: str | None = None, verify: bool = True):
    email = email or _unique_email()
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
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
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    return headers, email


def _staff(client, db_session, role_slug: str) -> dict:
    user = UserService(db_session).create(
        UserCreate(
            email=_unique_email(),
            first_name="Sta",
            last_name="Ff",
            auth_provider=AuthProvider.EMAIL,
        )
    )
    ProfileService(db_session).create_for_user(user, ProfileCreate(role_slug=role_slug))
    user.email_verified = True
    db_session.commit()
    return _bearer(create_access_token(str(user.id)))


def _me_id(client, headers) -> int:
    return client.get("/api/v1/users/me", headers=headers).json()["id"]


def _payload(**overrides) -> dict:
    payload = {
        "name": "Acme",
        "one_line_pitch": "Does things well",
        "description": "A longer description of the product.",
        "logo_url": "https://example.com/logo.png",
        "website_url": "https://example.com",
        "topics": ["AI"],
    }
    payload.update(overrides)
    return payload


def _create(client, headers, **overrides) -> dict:
    resp = client.post("/api/v1/products", json=_payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _visible_product(client, founder, reviewer, **overrides) -> dict:
    product = _create(client, founder, **overrides)
    submission = client.post(f"/api/v1/products/{product['id']}/submit", headers=founder).json()
    decide = client.post(
        f"/api/v1/staff/submissions/{submission['id']}/decision",
        json={"decision": "approve", "note": None},
        headers=reviewer,
    )
    assert decide.status_code == 200, decide.text
    launch = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _utc_today()},
        headers=founder,
    )
    assert launch.status_code == 200, launch.text
    return product


# --- permission gates ---


def test_governance_endpoints_require_admin(client, db_session):
    founder, _ = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member, _ = _signup(client, "member")
    member_id = _me_id(client, member)
    product = _visible_product(client, founder, reviewer)

    # Anonymous.
    assert (
        client.post(f"/api/v1/staff/users/{member_id}/suspend", json={"reason": "x"}).status_code
        == 401
    )
    # Reviewer and member are forbidden.
    for actor in (reviewer, member):
        assert (
            client.post(
                f"/api/v1/staff/users/{member_id}/suspend", json={"reason": "x"}, headers=actor
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/staff/products/{product['id']}/takedown",
                json={"reason": "x"},
                headers=actor,
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/staff/products/{product['id']}/feature",
                json={"reason": "x"},
                headers=actor,
            ).status_code
            == 403
        )


# --- suspend / reactivate ---


def test_admin_suspends_and_reactivates_member(client, db_session):
    admin = _staff(client, db_session, "admin")
    member, email = _signup(client, "member")
    member_id = _me_id(client, member)

    suspended = client.post(
        f"/api/v1/staff/users/{member_id}/suspend",
        json={"reason": "vote manipulation"},
        headers=admin,
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"

    # The member's still-valid access token is now rejected at the auth boundary.
    blocked = client.get("/api/v1/users/me", headers=member)
    assert blocked.status_code == 403
    assert "suspended" in blocked.json()["detail"].lower()

    # Fresh login is blocked too.
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 403

    # Suspending an already-suspended member conflicts.
    again = client.post(
        f"/api/v1/staff/users/{member_id}/suspend", json={"reason": "again"}, headers=admin
    )
    assert again.status_code == 409

    reactivated = client.post(f"/api/v1/staff/users/{member_id}/reactivate", headers=admin)
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "active"
    assert client.get("/api/v1/users/me", headers=member).status_code == 200

    # Reactivating a non-suspended member conflicts.
    assert (
        client.post(f"/api/v1/staff/users/{member_id}/reactivate", headers=admin).status_code == 409
    )

    actions = list(db_session.scalars(select(StaffAction)))
    kinds = {a.action_type.value for a in actions}
    assert {"suspend_member", "reactivate_member"} <= kinds
    logs = list(db_session.scalars(select(AuditLog)))
    events = {log.event_type.value for log in logs}
    assert {"user.suspended", "user.reactivated"} <= events


def test_admin_cannot_suspend_self_or_other_admin(client, db_session):
    admin = _staff(client, db_session, "admin")
    other_admin = _staff(client, db_session, "admin")
    admin_id = _me_id(client, admin)
    other_id = _me_id(client, other_admin)

    self_suspend = client.post(
        f"/api/v1/staff/users/{admin_id}/suspend", json={"reason": "x"}, headers=admin
    )
    assert self_suspend.status_code == 403

    other_suspend = client.post(
        f"/api/v1/staff/users/{other_id}/suspend", json={"reason": "x"}, headers=admin
    )
    assert other_suspend.status_code == 403


def test_suspend_unknown_member_is_404(client, db_session):
    admin = _staff(client, db_session, "admin")
    resp = client.post("/api/v1/staff/users/999999/suspend", json={"reason": "x"}, headers=admin)
    assert resp.status_code == 404


# --- takedown / restore ---


def test_takedown_hides_product_and_restore(client, db_session):
    admin = _staff(client, db_session, "admin")
    founder, _ = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _visible_product(client, founder, reviewer)

    assert client.get(f"/api/v1/products/{product['id']}").status_code == 200
    assert [i["product_id"] for i in client.get("/api/v1/discovery/today").json()] == [
        product["id"]
    ]

    takedown = client.post(
        f"/api/v1/staff/products/{product['id']}/takedown",
        json={"reason": "policy violation"},
        headers=admin,
    )
    assert takedown.status_code == 200, takedown.text
    assert takedown.json()["status"] == "inactive"

    # Hidden going forward from every public surface.
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 404
    assert client.get("/api/v1/discovery/today").json() == []

    # Double takedown conflicts.
    assert (
        client.post(
            f"/api/v1/staff/products/{product['id']}/takedown",
            json={"reason": "x"},
            headers=admin,
        ).status_code
        == 409
    )

    restored = client.post(f"/api/v1/staff/products/{product['id']}/restore", headers=admin)
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "approved"
    # Still not visible until the founder reschedules the (cancelled) launch.
    assert client.get(f"/api/v1/products/{product['id']}").status_code == 404
    assert (
        client.post(f"/api/v1/staff/products/{product['id']}/restore", headers=admin).status_code
        == 409
    )

    events = {log.event_type.value for log in db_session.scalars(select(AuditLog))}
    assert {"product.taken_down", "product.restored"} <= events


# --- feature / unfeature ---


def test_feature_pins_product_and_unfeature_reverses(client, db_session):
    admin = _staff(client, db_session, "admin")
    founder, _ = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    first = _visible_product(client, founder, reviewer, name="First")
    second = _visible_product(client, founder, reviewer, name="Second")

    # Default order is by product id (no votes), so First is on top.
    before = client.get("/api/v1/discovery/today").json()
    assert before[0]["product_id"] == first["id"]

    featured = client.post(
        f"/api/v1/staff/products/{second['id']}/feature",
        json={"reason": "Editor's pick"},
        headers=admin,
    )
    assert featured.status_code == 200, featured.text

    after = client.get("/api/v1/discovery/today").json()
    assert after[0]["product_id"] == second["id"]
    assert after[0]["featured"] is True

    listed = client.get("/api/v1/products/featured")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [second["id"]]

    # Featuring twice conflicts.
    assert (
        client.post(
            f"/api/v1/staff/products/{second['id']}/feature",
            json={"reason": "again"},
            headers=admin,
        ).status_code
        == 409
    )

    unfeatured = client.post(f"/api/v1/staff/products/{second['id']}/unfeature", headers=admin)
    assert unfeatured.status_code == 200, unfeatured.text
    assert client.get("/api/v1/products/featured").json() == []
    assert client.get("/api/v1/discovery/today").json()[0]["product_id"] == first["id"]

    events = {log.event_type.value for log in db_session.scalars(select(AuditLog))}
    assert {"product.featured", "product.unfeatured"} <= events


def test_feature_requires_public_product(client, db_session):
    admin = _staff(client, db_session, "admin")
    founder, _ = _signup(client, "founder")
    draft = _create(client, founder)

    resp = client.post(
        f"/api/v1/staff/products/{draft['id']}/feature",
        json={"reason": "x"},
        headers=admin,
    )
    assert resp.status_code == 409


# --- audit views ---


def test_audit_logs_endpoint_filters_and_captures_correlation(client, db_session):
    admin = _staff(client, db_session, "admin")
    founder, _ = _signup(client, "founder")

    track = "trace-abc-123"
    created = client.post(
        "/api/v1/products",
        json=_payload(),
        headers={**founder, "X-Request-Id": track},
    )
    assert created.status_code == 201
    assert created.headers["x-request-id"] == track

    resp = client.get("/api/v1/staff/audit-logs?event_type=product.created", headers=admin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["event_type"] == "product.created"
    assert entry["entity_type"] == "product"
    assert entry["correlation_id"] == track
    assert entry["ip_address"] is not None
    assert entry["user_agent"] is not None

    # Filtering by a non-matching event type yields nothing.
    assert (
        client.get("/api/v1/staff/audit-logs?event_type=user.suspended", headers=admin).json() == []
    )
    # Non-staff cannot read the audit trail.
    assert client.get("/api/v1/staff/audit-logs", headers=founder).status_code == 403


# --- moderation surface consolidation ---


def test_staff_reports_mirror(client, db_session):
    admin = _staff(client, db_session, "admin")
    founder, _ = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member, _ = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    report = client.post(
        f"/api/v1/community/products/{product['id']}/reports",
        json={"reason": "spam"},
        headers=member,
    ).json()

    mirrored = client.get("/api/v1/staff/reports", headers=admin)
    assert mirrored.status_code == 200
    assert [r["id"] for r in mirrored.json()] == [report["id"]]
