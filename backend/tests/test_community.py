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


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _signup(client, role: str, *, verify: bool = True, email: str | None = None) -> dict:
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email or _unique_email(),
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


def _multi_role_signup(client, roles: list[str]) -> dict:
    """Sign up one account holding several profiles (e.g. member + founder)."""
    email = _unique_email()
    headers: dict | None = None
    for index, role in enumerate(roles):
        resp = client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "password123",
                "first_name": "Test",
                "last_name": "User",
                "role": role,
                "confirm_add_profile": index > 0,
            },
        )
        assert resp.status_code == 201, resp.text
        headers = _bearer(resp.json()["access_token"])
    me = client.get("/api/v1/users/me", headers=headers).json()
    token = create_email_verification_token(str(me["id"]))
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
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


def _profile_slug(client, headers: dict, role_slug: str = "member") -> str:
    me = client.get("/api/v1/users/me", headers=headers).json()
    for profile in me["profiles"]:
        if profile["role"]["slug"] == role_slug:
            return profile["slug"]
    raise AssertionError(f"no {role_slug} profile on account")


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


def _decide(client, headers, submission_id: int, decision: str):
    return client.post(
        f"/api/v1/staff/submissions/{submission_id}/decision",
        json={"decision": decision, "note": None},
        headers=headers,
    )


def _visible_product(client, founder, reviewer, **overrides) -> dict:
    """Approve a product and land it on today's launch list (publicly visible)."""
    product = _create(client, founder, **overrides)
    submission = _submit(client, founder, product["id"])
    assert _decide(client, reviewer, submission["id"], "approve").status_code == 200
    resp = client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _utc_today()},
        headers=founder,
    )
    assert resp.status_code == 200, resp.text
    return product


# --- voting ---


def test_member_casts_and_removes_vote(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    cast = client.post(f"/api/v1/community/products/{product['id']}/vote", headers=member)
    assert cast.status_code == 200, cast.text
    assert cast.json() == {"product_id": product["id"], "vote_count": 1, "has_voted": True}

    # A second vote is idempotent — still one vote.
    again = client.post(f"/api/v1/community/products/{product['id']}/vote", headers=member)
    assert again.status_code == 200
    assert again.json()["vote_count"] == 1

    removed = client.delete(f"/api/v1/community/products/{product['id']}/vote", headers=member)
    assert removed.status_code == 200
    assert removed.json() == {"product_id": product["id"], "vote_count": 0, "has_voted": False}

    # Unvoting when there is no vote is idempotent.
    assert (
        client.delete(
            f"/api/v1/community/products/{product['id']}/vote", headers=member
        ).status_code
        == 200
    )


def test_vote_requires_member_role_and_verified_email(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _visible_product(client, founder, reviewer)
    url = f"/api/v1/community/products/{product['id']}/vote"

    # Anonymous visitor.
    assert client.post(url).status_code == 401
    # Founder-only account holds no member profile.
    assert client.post(url, headers=founder).status_code == 403
    # Unverified member.
    unverified = _signup(client, "member", verify=False)
    assert client.post(url, headers=unverified).status_code == 403


def test_cannot_vote_for_own_product(client, db_session):
    reviewer = _staff(client, db_session, "reviewer")
    owner = _multi_role_signup(client, ["member", "founder"])
    product = _visible_product(client, owner, reviewer)

    resp = client.post(f"/api/v1/community/products/{product['id']}/vote", headers=owner)
    assert resp.status_code == 403


def test_cannot_vote_on_invisible_product(client, db_session):
    founder = _signup(client, "founder")
    member = _signup(client, "member")
    product = _create(client, founder)  # still a draft

    resp = client.post(f"/api/v1/community/products/{product['id']}/vote", headers=member)
    assert resp.status_code == 404


# --- comments ---


def test_member_comments_and_replies_threaded(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    other = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)
    base = f"/api/v1/community/products/{product['id']}/comments"

    top = client.post(base, json={"text": "Looks great"}, headers=member)
    assert top.status_code == 201, top.text

    reply = client.post(
        base, json={"text": "Agreed", "parent_comment_id": top.json()["id"]}, headers=other
    )
    assert reply.status_code == 201, reply.text

    listed = client.get(base)
    assert listed.status_code == 200
    tree = listed.json()
    assert len(tree) == 1
    assert tree[0]["id"] == top.json()["id"]
    assert [r["id"] for r in tree[0]["replies"]] == [reply.json()["id"]]


def test_reply_parent_must_belong_to_same_product(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product_a = _visible_product(client, founder, reviewer, name="A")
    product_b = _visible_product(client, founder, reviewer, name="B")

    comment = client.post(
        f"/api/v1/community/products/{product_a['id']}/comments",
        json={"text": "On A"},
        headers=member,
    ).json()

    resp = client.post(
        f"/api/v1/community/products/{product_b['id']}/comments",
        json={"text": "Bad reply", "parent_comment_id": comment["id"]},
        headers=member,
    )
    assert resp.status_code == 409


def test_only_owner_can_delete_comment(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    other = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)
    base = f"/api/v1/community/products/{product['id']}/comments"

    comment = client.post(base, json={"text": "Mine"}, headers=member).json()

    assert (
        client.delete(f"/api/v1/community/comments/{comment['id']}", headers=other).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/community/comments/{comment['id']}", headers=member).status_code
        == 204
    )
    assert client.get(base).json() == []


def test_deleting_parent_comment_removes_replies(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    other = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)
    base = f"/api/v1/community/products/{product['id']}/comments"

    top = client.post(base, json={"text": "Parent"}, headers=member).json()
    client.post(base, json={"text": "Reply", "parent_comment_id": top["id"]}, headers=other)

    deleted = client.delete(f"/api/v1/community/comments/{top['id']}", headers=member)
    assert deleted.status_code == 204
    assert client.get(base).json() == []


# --- reporting ---


def test_report_product_and_duplicate_conflicts(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)
    url = f"/api/v1/community/products/{product['id']}/reports"

    resp = client.post(url, json={"reason": "spam", "details": "Promotional"}, headers=member)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["target_type"] == "product"
    assert body["target_product_id"] == product["id"]
    assert body["status"] == "open"

    duplicate = client.post(url, json={"reason": "spam"}, headers=member)
    assert duplicate.status_code == 409


def test_report_comment(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    comment = client.post(
        f"/api/v1/community/products/{product['id']}/comments",
        json={"text": "Offensive"},
        headers=member,
    ).json()

    resp = client.post(
        f"/api/v1/community/comments/{comment['id']}/reports",
        json={"reason": "abuse"},
        headers=member,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["target_type"] == "comment"
    assert resp.json()["target_comment_id"] == comment["id"]


def test_report_queue_assignment_and_resolution_audited(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    report = client.post(
        f"/api/v1/community/products/{product['id']}/reports",
        json={"reason": "misleading"},
        headers=member,
    ).json()

    # Only staff can read the queue.
    assert client.get("/api/v1/community/reports", headers=member).status_code == 403
    queue = client.get("/api/v1/community/reports", headers=reviewer)
    assert queue.status_code == 200
    assert any(r["id"] == report["id"] for r in queue.json())

    assigned = client.post(f"/api/v1/community/reports/{report['id']}/assign", headers=reviewer)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "in_review"
    assert assigned.json()["assigned_reviewer_profile_id"] is not None

    resolved = client.post(
        f"/api/v1/community/reports/{report['id']}/resolve",
        json={"resolution": "resolve", "note": "Handled"},
        headers=reviewer,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolution_note"] == "Handled"
    assert resolved.json()["resolved_at"] is not None

    logs = list(db_session.scalars(select(AuditLog)))
    assert any(log.event_type.value == "report.resolved" for log in logs)
    actions = list(db_session.scalars(select(StaffAction)))
    assert any(action.action_type.value == "resolve_report" for action in actions)


def test_report_dismiss_and_illegal_transition(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    report = client.post(
        f"/api/v1/community/products/{product['id']}/reports",
        json={"reason": "other"},
        headers=member,
    ).json()

    # Cannot resolve straight from open — must be assigned first.
    illegal = client.post(
        f"/api/v1/community/reports/{report['id']}/resolve",
        json={"resolution": "resolve"},
        headers=reviewer,
    )
    assert illegal.status_code == 409

    client.post(f"/api/v1/community/reports/{report['id']}/assign", headers=reviewer)
    dismissed = client.post(
        f"/api/v1/community/reports/{report['id']}/resolve",
        json={"resolution": "dismiss"},
        headers=reviewer,
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"


# --- follows ---


def test_member_follow_and_unfollow(client, db_session):
    follower = _signup(client, "member")
    target = _signup(client, "member")
    slug = _profile_slug(client, target)
    url = f"/api/v1/users/{slug}/follow"

    assert client.post(url, headers=follower).status_code == 201
    # Following twice is idempotent.
    assert client.post(url, headers=follower).status_code == 201

    following = client.get("/api/v1/users/me/following", headers=follower)
    assert following.status_code == 200
    assert [p["slug"] for p in following.json()] == [slug]

    assert client.delete(url, headers=follower).status_code == 204
    assert client.get("/api/v1/users/me/following", headers=follower).json() == []


def test_cannot_follow_self(client):
    member = _signup(client, "member")
    slug = _profile_slug(client, member)
    assert client.post(f"/api/v1/users/{slug}/follow", headers=member).status_code == 400


def test_topic_follow_and_unfollow(client, db_session):
    founder = _signup(client, "founder")
    member = _signup(client, "member")
    _create(client, founder, topics=["AI"])

    follow = client.post("/api/v1/topics/ai/follow", headers=member)
    assert follow.status_code == 200, follow.text
    assert follow.json()["slug"] == "ai"
    # Idempotent.
    assert client.post("/api/v1/topics/ai/follow", headers=member).status_code == 200

    listed = client.get("/api/v1/topics/me/following", headers=member)
    assert [t["slug"] for t in listed.json()] == ["ai"]

    assert client.delete("/api/v1/topics/ai/follow", headers=member).status_code == 204
    assert client.get("/api/v1/topics/me/following", headers=member).json() == []

    assert client.post("/api/v1/topics/missing/follow", headers=member).status_code == 404


# --- feed ---


def test_feed_includes_products_from_followed_member(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    follower = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    founder_slug = _profile_slug(client, founder, "founder")
    client.post(f"/api/v1/users/{founder_slug}/follow", headers=follower)

    feed = client.get("/api/v1/community/feed", headers=follower)
    assert feed.status_code == 200, feed.text
    assert any(p["id"] == product["id"] for p in feed.json())


def test_feed_includes_products_from_followed_topic(client, db_session):
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    follower = _signup(client, "member")
    product = _visible_product(client, founder, reviewer, topics=["AI"])

    client.post("/api/v1/topics/ai/follow", headers=follower)

    feed = client.get("/api/v1/community/feed", headers=follower)
    assert feed.status_code == 200
    assert [p["id"] for p in feed.json()] == [product["id"]]


def test_feed_excludes_invisible_products(client, db_session):
    founder = _signup(client, "founder")
    follower = _signup(client, "member")
    _create(client, founder, topics=["AI"])  # draft, not visible

    founder_slug = _profile_slug(client, founder, "founder")
    client.post(f"/api/v1/users/{founder_slug}/follow", headers=follower)
    client.post("/api/v1/topics/ai/follow", headers=follower)

    assert client.get("/api/v1/community/feed", headers=follower).json() == []
