import uuid

import pytest
from fastapi import HTTPException

from src.auth import service as auth_service
from src.core.security import create_email_verification_token, create_password_reset_token


def _unique_email() -> str:
    return f"tester+{uuid.uuid4().hex[:8]}@example.com"


def _signup(client, email=None, password="password123", **extra):
    payload = {
        "email": email or _unique_email(),
        "password": password,
        "first_name": "Test",
        "last_name": "User",
        **extra,
    }
    return client.post("/api/v1/auth/signup", json=payload)


def _bearer(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def test_signup_returns_tokens(client):
    resp = _signup(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


def test_signup_rejects_duplicate_email(client):
    email = _unique_email()
    assert _signup(client, email=email).status_code == 201
    resp = _signup(client, email=email)
    assert resp.status_code == 409


def test_signup_rejects_short_password(client):
    resp = _signup(client, password="short")
    assert resp.status_code == 422


def test_login_success(client):
    email = _unique_email()
    _signup(client, email=email)
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password(client):
    email = _unique_email()
    _signup(client, email=email)
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "noone@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


def test_users_me_requires_auth(client):
    assert client.get("/api/v1/users/me").status_code == 401


def test_users_me_returns_current_user(client):
    email = _unique_email()
    tokens = _signup(client, email=email).json()
    resp = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == email
    assert "password_hash" not in body
    assert body["profiles"][0]["role"]["slug"] == "member"


def test_profile_by_slug(client):
    email = _unique_email()
    tokens = _signup(client, email=email).json()
    me = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"])).json()
    slug = me["profiles"][0]["slug"]
    resp = client.get(f"/api/v1/users/{slug}")
    assert resp.status_code == 200
    assert resp.json()["slug"] == slug


def test_profile_slug_not_found(client):
    assert client.get("/api/v1/users/no-such-slug").status_code == 404


def test_refresh_rotation_issues_new_token_and_revokes_old(client):
    tokens = _signup(client).json()
    old_refresh = tokens["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["refresh_token"] != old_refresh

    # Old refresh token is now revoked.
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert again.status_code == 401


def test_refresh_rejects_access_token(client):
    tokens = _signup(client).json()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


def test_logout_revokes_refresh(client):
    tokens = _signup(client).json()
    refresh = tokens["refresh_token"]
    client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401


def test_verify_email_flow(client):
    email = _unique_email()
    tokens = _signup(client, email=email).json()
    me_before = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"])).json()
    assert me_before["email_verified"] is False

    verify_token = create_email_verification_token(str(me_before["id"]))
    resp = client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    assert resp.status_code == 200

    me_after = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"])).json()
    assert me_after["email_verified"] is True


def test_verify_email_rejects_wrong_token_type(client):
    tokens = _signup(client).json()
    resp = client.post("/api/v1/auth/verify-email", json={"token": tokens["access_token"]})
    assert resp.status_code == 400


def test_forgot_password_is_idempotent_for_unknown_email(client):
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "noone@example.com"})
    assert resp.status_code == 200
    assert "reset email" in resp.json()["message"]


def test_reset_password_and_login_with_new_password(client):
    email = _unique_email()
    _signup(client, email=email)

    # Simulate the reset token the email seam would have sent.
    user = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    ).json()
    me = client.get("/api/v1/users/me", headers=_bearer(user["access_token"])).json()
    reset_token = create_password_reset_token(str(me["id"]))

    resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "newpass123"},
    )
    assert resp.status_code == 200

    # Old password no longer works.
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "password123"}
        ).status_code
        == 401
    )
    # New password works.
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "newpass123"}
        ).status_code
        == 200
    )


def test_change_password_requires_auth(client):
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "newpass123"},
    )
    assert resp.status_code == 401


def test_change_password_success_and_revokes_old_tokens(client):
    email = _unique_email()
    tokens = _signup(client, email=email).json()
    refresh = tokens["refresh_token"]

    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "password123", "new_password": "newpass123"},
        headers=_bearer(tokens["access_token"]),
    )
    assert resp.status_code == 200

    # Old refresh token revoked after password change.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_change_password_wrong_current(client):
    email = _unique_email()
    tokens = _signup(client, email=email).json()
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": "newpass123"},
        headers=_bearer(tokens["access_token"]),
    )
    assert resp.status_code == 400


def test_google_signin_unconfigured_returns_501(client):
    resp = client.post("/api/v1/auth/google", json={"id_token": "any"})
    assert resp.status_code == 501


def test_google_signin_creates_user_when_configured(client, monkeypatch):
    monkeypatch.setattr(auth_service.settings, "google_client_id", "google-client-id")
    fake_claims = {
        "sub": "g-123",
        "email": "googler@example.com",
        "email_verified": True,
        "given_name": "Google",
        "family_name": "User",
    }
    monkeypatch.setattr(auth_service, "verify_google_id_token", lambda token: fake_claims)

    resp = client.post("/api/v1/auth/google", json={"id_token": "ignored"})
    assert resp.status_code == 200
    tokens = resp.json()
    me = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"])).json()
    assert me["email"] == "googler@example.com"
    assert me["email_verified"] is True

    # Second sign-in with the same Google identity reuses the account.
    resp2 = client.post("/api/v1/auth/google", json={"id_token": "ignored"})
    assert resp2.status_code == 200
    me2 = client.get("/api/v1/users/me", headers=_bearer(resp2.json()["access_token"])).json()
    assert me2["id"] == me["id"]


def test_require_role_blocks_member_from_admin(client, db_session):
    from src.core.dependencies import require_role
    from src.users import service as users_service

    tokens = _signup(client).json()
    me = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"])).json()
    user = users_service.UserService(db_session).get_by_id(me["id"])

    with pytest.raises(HTTPException) as exc:
        require_role("admin")(current_user=user)
    assert exc.value.status_code == 403


def test_require_role_allows_matching_role(client, db_session):
    from src.core.dependencies import require_role
    from src.users import service as users_service

    tokens = _signup(client).json()
    me = client.get("/api/v1/users/me", headers=_bearer(tokens["access_token"])).json()
    user = users_service.UserService(db_session).get_by_id(me["id"])

    assert require_role("member")(current_user=user) is user


def test_signup_retries_on_slug_collision(client, db_session, monkeypatch):
    """A concurrent slug collision must retry, not 500."""
    from src.users import crud as users_crud

    first_email = _unique_email()
    first_tokens = _signup(client, email=first_email, nick_name="colliding-slug").json()
    first_me = client.get("/api/v1/users/me", headers=_bearer(first_tokens["access_token"])).json()
    occupied_slug = first_me["profiles"][0]["slug"]

    real_gen = users_crud.generate_unique_slug
    attempts = {"n": 0}

    def patched(db, base):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return occupied_slug  # force a collision on the first attempt
        return real_gen(db, base)

    monkeypatch.setattr(users_crud, "generate_unique_slug", patched)

    resp = _signup(client, nick_name="colliding-slug")
    assert resp.status_code == 201, resp.text
    assert attempts["n"] >= 2  # retried after the collision


def _profile_roles(client, access_token) -> set[str]:
    me = client.get("/api/v1/users/me", headers=_bearer(access_token)).json()
    return {p["role"]["slug"] for p in me["profiles"]}


def test_signup_as_founder_creates_founder_profile(client):
    resp = _signup(client, role="founder")
    assert resp.status_code == 201
    assert _profile_roles(client, resp.json()["access_token"]) == {"founder"}


def test_signup_rejects_non_self_serve_role(client):
    resp = _signup(client, role="admin")
    assert resp.status_code == 422


def test_signup_rejects_invalid_email(client):
    assert _signup(client, email="not-an-email").status_code == 422


def test_signup_rejects_malformed_phone(client):
    assert _signup(client, phone_number="abc").status_code == 422


def test_signup_rejects_duplicate_phone(client):
    phone = "+15551234567"
    assert _signup(client, phone_number=phone).status_code == 201
    resp = _signup(client, phone_number=phone)
    assert resp.status_code == 409


def test_signup_existing_member_adds_founder_after_confirmation(client):
    email = _unique_email()
    assert _signup(client, email=email, role="member").status_code == 201

    conflict = _signup(client, email=email, role="founder")
    assert conflict.status_code == 409
    assert "confirm" in conflict.json()["detail"].lower()

    confirmed = _signup(client, email=email, role="founder", confirm_add_profile=True)
    assert confirmed.status_code == 201
    assert _profile_roles(client, confirmed.json()["access_token"]) == {"member", "founder"}


def test_signup_existing_founder_adds_member_after_confirmation(client):
    email = _unique_email()
    assert _signup(client, email=email, role="founder").status_code == 201
    confirmed = _signup(client, email=email, role="member", confirm_add_profile=True)
    assert confirmed.status_code == 201
    assert _profile_roles(client, confirmed.json()["access_token"]) == {"member", "founder"}


def test_signup_same_role_twice_is_rejected(client):
    email = _unique_email()
    assert _signup(client, email=email, role="member").status_code == 201
    resp = _signup(client, email=email, role="member", confirm_add_profile=True)
    assert resp.status_code == 409
    assert "already have" in resp.json()["detail"].lower()


def test_signup_existing_email_wrong_password_rejected(client):
    email = _unique_email()
    assert _signup(client, email=email, role="member").status_code == 201
    resp = _signup(client, email=email, password="different123", role="founder")
    assert resp.status_code == 401


def test_require_role_allows_any_matching_profile(client, db_session):
    from src.core.dependencies import require_role
    from src.users import service as users_service

    email = _unique_email()
    _signup(client, email=email, role="member")
    confirmed = _signup(client, email=email, role="founder", confirm_add_profile=True).json()
    user = users_service.UserService(db_session).get_by_id(
        client.get("/api/v1/users/me", headers=_bearer(confirmed["access_token"])).json()["id"]
    )
    assert require_role("founder")(current_user=user) is user
    assert require_role("member", "founder")(current_user=user) is user
