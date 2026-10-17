from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from src.core.security import create_access_token, create_email_verification_token
from src.products import crud as products_crud
from src.tasks.scheduler import run_job
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _today():
    return datetime.now(timezone.utc).date()


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
        assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    return headers


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


def _approved(client, founder: dict, reviewer: dict, *, name: str = "Acme") -> dict:
    product = client.post(
        "/api/v1/products",
        json={
            "name": name,
            "one_line_pitch": "Does things well",
            "description": "A longer description of the product.",
            "logo_url": "https://example.com/logo.png",
            "website_url": "https://example.com",
            "topics": ["AI"],
        },
        headers=founder,
    ).json()
    submission = client.post(f"/api/v1/products/{product['id']}/submit", headers=founder).json()
    client.post(
        f"/api/v1/staff/submissions/{submission['id']}/decision",
        json={"decision": "approve", "note": None},
        headers=reviewer,
    )
    return product


def _schedule_today(client, founder: dict, product: dict) -> None:
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _today().isoformat()},
        headers=founder,
    )
    assert resp.status_code == 200, resp.text


def _move_launch_to(db_session, product_id: int, on_date) -> None:
    launch = products_crud.get_launch_for_product(db_session, product_id)
    launch.launch_date = on_date
    launch.launched_at = datetime.combine(on_date, time.min, tzinfo=timezone.utc) + timedelta(
        hours=12
    )
    db_session.commit()


def test_daily_top_five_digest_notifies_members(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")

    yesterday = _today() - timedelta(days=1)
    product = _approved(client, founder, reviewer, name="YesterdayApp")
    _schedule_today(client, founder, product)
    _move_launch_to(db_session, product["id"], yesterday)
    assert (
        client.post(f"/api/v1/community/products/{product['id']}/vote", headers=member).status_code
        == 200
    )

    notified = run_job(
        "discovery.send_daily_top_five", {"on_date": yesterday.isoformat()}, db=db_session
    )
    assert notified >= 1

    notifications = client.get("/api/v1/notifications", headers=member).json()
    digest = [item for item in notifications if item["event_type"] == "ranking.daily_top_five"]
    assert digest, "member should receive the daily digest"
    assert digest[0]["payload"]["items"][0]["product_id"] == product["id"]


def test_weekly_best_digest_notifies_members(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")

    product = _approved(client, founder, reviewer, name="WeeklyApp")
    _schedule_today(client, founder, product)
    client.post(f"/api/v1/community/products/{product['id']}/vote", headers=member)

    notified = run_job("discovery.send_weekly_best", {}, db=db_session)
    assert notified >= 1

    notifications = client.get("/api/v1/notifications", headers=member).json()
    assert any(item["event_type"] == "ranking.weekly_best" for item in notifications)


def test_launch_reminder_job_notifies_founder(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    tomorrow = _today() + timedelta(days=1)
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": tomorrow.isoformat()},
        headers=founder,
    )
    assert resp.status_code == 200, resp.text

    reminded = run_job("products.send_launch_reminders", {}, db=db_session)
    assert product["id"] in reminded

    notifications = client.get("/api/v1/notifications", headers=founder).json()
    assert any(item["event_type"] == "launch.reminder" for item in notifications)


def test_activate_daily_launches_emits_product_live(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)
    _schedule_today(client, founder, product)

    activated = run_job(
        "products.activate_daily_launches", {"on_date": _today().isoformat()}, db=db_session
    )
    assert product["id"] in activated

    notifications = client.get("/api/v1/notifications", headers=founder).json()
    assert any(item["event_type"] == "launch.activated" for item in notifications)


def test_moderation_outcome_notifies_founder(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    _approved(client, founder, reviewer)

    notifications = client.get("/api/v1/notifications", headers=founder).json()
    assert any(item["event_type"] == "submission.approved" for item in notifications)


def test_comment_notifies_product_founder(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product = _approved(client, founder, reviewer)
    _schedule_today(client, founder, product)

    resp = client.post(
        f"/api/v1/community/products/{product['id']}/comments",
        json={"text": "Looks great"},
        headers=member,
    )
    assert resp.status_code == 201, resp.text

    notifications = client.get("/api/v1/notifications", headers=founder).json()
    assert any(item["event_type"] == "comment.created" for item in notifications)
