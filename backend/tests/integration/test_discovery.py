from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from src.core.security import create_access_token, create_email_verification_token
from src.discovery.service import SnapshotService
from src.products import crud as products_crud
from src.products.service import ProductLaunchService
from src.tasks.registry import registered_job_names
from src.tasks.scheduler import enqueue_job, run_job
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_today() -> date:
    return _now().date()


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


def _approved(client, founder, reviewer, **overrides) -> dict:
    product = _create(client, founder, **overrides)
    submission = client.post(f"/api/v1/products/{product['id']}/submit", headers=founder).json()
    decided = client.post(
        f"/api/v1/staff/submissions/{submission['id']}/decision",
        json={"decision": "approve", "note": None},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text
    return product


def _visible_today(client, founder, reviewer, **overrides) -> dict:
    """Approve a product and schedule it for today (publicly visible, not yet live)."""
    product = _approved(client, founder, reviewer, **overrides)
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _utc_today().isoformat()},
        headers=founder,
    )
    assert resp.status_code == 200, resp.text
    return product


def _activate(db_session, product_id: int) -> None:
    ProductLaunchService(db_session).activate(product_id)


def _set_launched_at(db_session, product_id: int, moment: datetime) -> None:
    launch = products_crud.get_launch_for_product(db_session, product_id)
    launch.launched_at = moment
    db_session.commit()


def _vote(client, member: dict, product_id: int) -> None:
    resp = client.post(f"/api/v1/community/products/{product_id}/vote", headers=member)
    assert resp.status_code == 200, resp.text


# --- daily ranking ---


def test_today_page_ranks_by_velocity(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    voters = [_signup(client, "member") for _ in range(3)]

    earlier = _visible_today(client, founder, reviewer, name="Earlier")
    recent = _visible_today(client, founder, reviewer, name="Recent")
    _activate(db_session, earlier["id"])
    _activate(db_session, recent["id"])
    # Earlier product: older launch, more total votes. Recent: newer, fewer votes.
    _set_launched_at(db_session, earlier["id"], _now() - timedelta(hours=20))
    _set_launched_at(db_session, recent["id"], _now() - timedelta(minutes=30))
    for voter in voters:
        _vote(client, voter, earlier["id"])
    for voter in voters[:2]:
        _vote(client, voter, recent["id"])

    resp = client.get("/api/v1/discovery/today")
    assert resp.status_code == 200, resp.text
    ranks = {item["product_id"]: item["rank"] for item in resp.json()}
    # Fewer votes but far higher velocity wins the top slot.
    assert ranks[recent["id"]] == 1
    assert ranks[earlier["id"]] == 2


def test_today_excludes_invisible_products(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")

    visible = _visible_today(client, founder, reviewer, name="Visible")
    _create(client, founder, name="Draft")  # never reviewed
    future = _approved(client, founder, reviewer, name="Future")
    client.post(
        f"/api/v1/products/{future['id']}/launch",
        json={"launch_date": (_utc_today() + timedelta(days=3)).isoformat()},
        headers=founder,
    )

    resp = client.get("/api/v1/discovery/today")
    assert resp.status_code == 200
    assert [item["product_id"] for item in resp.json()] == [visible["id"]]


# --- day snapshots ---


def test_day_snapshot_is_immutable_after_freeze(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    other = _signup(client, "member")

    product = _visible_today(client, founder, reviewer)
    _activate(db_session, product["id"])
    _vote(client, member, product["id"])

    today = _utc_today()
    # Not visible as a historical day until it is frozen.
    assert client.get(f"/api/v1/discovery/launches/{today.isoformat()}").status_code == 404

    assert SnapshotService(db_session).freeze(today) is not None
    frozen = client.get(f"/api/v1/discovery/launches/{today.isoformat()}")
    assert frozen.status_code == 200
    assert frozen.json()["items"][0]["vote_count"] == 1

    # A vote arriving after the freeze never alters the frozen order.
    _vote(client, other, product["id"])
    again = client.get(f"/api/v1/discovery/launches/{today.isoformat()}").json()
    assert again["items"][0]["vote_count"] == 1

    # Re-freezing the same day is a no-op.
    assert SnapshotService(db_session).freeze(today) is None


def test_freeze_job_via_registry(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    _visible_today(client, founder, reviewer)

    today = _utc_today()
    assert "discovery.freeze_daily_snapshots" in registered_job_names()
    assert run_job("discovery.freeze_daily_snapshots", {"on_date": today}, db=db_session) == [today]
    # Second run is a no-op.
    assert run_job("discovery.freeze_daily_snapshots", {"on_date": today}, db=db_session) == []


# --- day activation ---


def test_activate_daily_launches_job(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _visible_today(client, founder, reviewer)

    today = _utc_today()
    queued = enqueue_job("products.activate_daily_launches", {"on_date": today.isoformat()})
    assert queued["status"] == "queued"
    assert "products.activate_daily_launches" in registered_job_names()

    assert run_job("products.activate_daily_launches", {"on_date": today}, db=db_session) == [
        product["id"]
    ]
    detail = client.get(f"/api/v1/products/{product['id']}").json()
    assert detail["status"] == "live"
    assert detail["launch"]["state"] == "live"

    # Idempotent: nothing left to activate.
    assert run_job("products.activate_daily_launches", {"on_date": today}, db=db_session) == []


# --- leaderboards ---


def test_topic_leaderboard_windows(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")

    product = _visible_today(client, founder, reviewer, topics=["AI"])
    _vote(client, member, product["id"])

    for window in ("week", "month", "all-time"):
        resp = client.get(f"/api/v1/discovery/topics/ai/leaderboard?window={window}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [item["product_id"] for item in body] == [product["id"]]
        assert body[0]["vote_count"] == 1
        assert body[0]["rank"] == 1

    assert client.get("/api/v1/discovery/topics/missing/leaderboard").status_code == 404
    assert client.get("/api/v1/discovery/topics/ai/leaderboard?window=decade").status_code == 422


# --- search ---


def test_search_by_name_description_topic_and_sort(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")

    alpha = _visible_today(
        client,
        founder,
        reviewer,
        name="Acme Rocket",
        description="A calm description",
        topics=["AI"],
    )
    beta = _visible_today(
        client,
        founder,
        reviewer,
        name="Beta",
        description="Acme helper utility",
        topics=["DevTools"],
    )

    by_name = client.get("/api/v1/discovery/products/search?q=Acme")
    assert by_name.status_code == 200, by_name.text
    matched = {item["product_id"] for item in by_name.json()}
    assert matched == {alpha["id"], beta["id"]}

    # Topic filter narrows to AI-tagged products.
    filtered = client.get("/api/v1/discovery/products/search?q=Acme&topic=ai").json()
    assert [item["product_id"] for item in filtered] == [alpha["id"]]

    # Description-only hit.
    desc = client.get("/api/v1/discovery/products/search?q=calm").json()
    assert [item["product_id"] for item in desc] == [alpha["id"]]

    # most_voted sorts the voted product first.
    _vote(client, member, beta["id"])
    voted = client.get("/api/v1/discovery/products/search?q=Acme&sort=most_voted").json()
    assert voted[0]["product_id"] == beta["id"]

    # q is required; unknown topic filter is a 404.
    assert client.get("/api/v1/discovery/products/search").status_code == 422
    assert client.get("/api/v1/discovery/products/search?q=Acme&topic=missing").status_code == 404
