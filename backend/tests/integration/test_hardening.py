from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.core.config import settings
from src.core.security import create_access_token, create_email_verification_token
from src.shared.exceptions import register_exception_handlers
from src.staff.models import AuditLog
from src.tasks.registry import registered_job_names
from src.tasks.scheduler import run_job
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _signup(client, role: str):
    email = _unique_email()
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


def _visible_product(client, founder, reviewer) -> dict:
    product = client.post("/api/v1/products", json=_payload(), headers=founder).json()
    submission = client.post(f"/api/v1/products/{product['id']}/submit", headers=founder).json()
    client.post(
        f"/api/v1/staff/submissions/{submission['id']}/decision",
        json={"decision": "approve", "note": None},
        headers=reviewer,
    )
    client.post(
        f"/api/v1/products/{product['id']}/launch",
        json={"launch_date": _utc_today()},
        headers=founder,
    )
    return product


# --- rate limiting ---


def test_rate_limit_blocks_excess_and_returns_retry_after(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    _, email = _signup(client, "member")

    first = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    second = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    third = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "retry-after" in {k.lower() for k in third.headers}


def test_rate_limiting_is_disabled_by_default_in_tests(client):
    # The conftest fixture disables it so suites stay non-flaky.
    for _ in range(5):
        assert client.get("/api/v1/health").status_code == 200


# --- request correlation ---


def test_correlation_id_echoed_when_provided(client):
    resp = client.get("/api/v1/health", headers={"X-Request-Id": "trace-xyz"})
    assert resp.headers.get("x-request-id") == "trace-xyz"


def test_correlation_id_generated_when_absent(client):
    resp = client.get("/api/v1/health")
    assert resp.headers.get("x-request-id")


# --- readiness ---


def test_readiness_reports_database_and_redis(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["database"] == "ok"
    assert body["redis"] in {"ok", "unavailable"}
    assert body["status"] in {"ok", "degraded"}


# --- exception handling ---


def test_unhandled_exception_is_generic_and_http_exception_preserved():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    @app.get("/teapot")
    def teapot():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    test_client = TestClient(app, raise_server_exceptions=False)
    resp = test_client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"
    assert "secret internal detail" not in resp.text

    assert test_client.get("/teapot").status_code == 418


# --- abuse monitoring ---


def test_flag_if_suspicious_enqueues_and_job_records_signal(db_session):
    from src.staff.monitor import flag_if_suspicious

    assert "staff.evaluate_abuse_signal" in registered_job_names()

    assert flag_if_suspicious("vote", user_id=4242, threshold=1, window_seconds=60) is True
    run_job(
        "staff.evaluate_abuse_signal",
        {"action": "vote", "user_id": 4242, "count": 1, "window_seconds": 60},
        db=db_session,
    )
    logs = list(db_session.scalars(select(AuditLog)))
    signals = [log for log in logs if log.event_type.value == "abuse.signal_raised"]
    assert len(signals) == 1
    assert signals[0].after_state["action"] == "vote"

    # Below threshold → no signal.
    assert flag_if_suspicious("vote", user_id=99, threshold=5, window_seconds=60) is False


def test_monitoring_does_not_block_votes(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "abuse_vote_threshold", 1)
    founder, _ = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    member, _ = _signup(client, "member")
    product = _visible_product(client, founder, reviewer)

    resp = client.post(f"/api/v1/community/products/{product['id']}/vote", headers=member)
    assert resp.status_code == 200
    assert resp.json()["vote_count"] == 1
