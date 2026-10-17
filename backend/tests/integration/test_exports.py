from __future__ import annotations

import uuid

from src.core.config import settings
from src.core.security import create_access_token, create_email_verification_token
from src.integrations import email as email_integration
from src.tasks.scheduler import run_job
from src.users.models import AuthProvider
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


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
        "topics": ["AI"],
    }
    payload.update(overrides)
    return payload


def _approved(client, founder: dict, reviewer: dict, **overrides) -> dict:
    created = client.post("/api/v1/products", json=_payload(**overrides), headers=founder)
    assert created.status_code == 201, created.text
    product = created.json()
    submission = client.post(f"/api/v1/products/{product['id']}/submit", headers=founder).json()
    decided = client.post(
        f"/api/v1/staff/submissions/{submission['id']}/decision",
        json={"decision": "approve", "note": None},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text
    return product


def test_founder_export_runs_async_and_notifies(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "export_dir", str(tmp_path))
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(email_integration, "send_email", lambda message: "provider-1")

    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    requested = client.post(f"/api/v1/products/{product['id']}/export", headers=founder)
    assert requested.status_code == 202, requested.text
    export = requested.json()
    assert export["status"] == "preparing"

    # The request returns immediately; the job has not run yet.
    pending = client.get(
        f"/api/v1/products/{product['id']}/export/{export['id']}", headers=founder
    ).json()
    assert pending["status"] == "preparing"

    run_job("products.generate_founder_export", {"export_id": export["id"]}, db=db_session)

    ready = client.get(
        f"/api/v1/products/{product['id']}/export/{export['id']}", headers=founder
    ).json()
    assert ready["status"] == "ready"
    assert ready["artifact_path"]

    # The founder is notified on completion.
    notifications = client.get("/api/v1/notifications", headers=founder).json()
    assert any(item["event_type"] == "founder.export_ready" for item in notifications)

    download = client.get(
        f"/api/v1/products/{product['id']}/export/{export['id']}/download", headers=founder
    )
    assert download.status_code == 200
    assert download.json()["product"]["id"] == product["id"]


def test_export_requires_ownership(client, db_session):
    owner = _signup(client, "founder")
    intruder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, owner, reviewer)

    resp = client.post(f"/api/v1/products/{product['id']}/export", headers=intruder)
    assert resp.status_code == 403


def test_export_download_409_before_ready(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "export_dir", str(tmp_path))
    founder = _signup(client, "founder")
    reviewer = _staff(client, db_session, "reviewer")
    product = _approved(client, founder, reviewer)

    export = client.post(f"/api/v1/products/{product['id']}/export", headers=founder).json()
    resp = client.get(
        f"/api/v1/products/{product['id']}/export/{export['id']}/download", headers=founder
    )
    assert resp.status_code == 409
