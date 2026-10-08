from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.auth.models import RefreshToken
from src.auth.schemas import TokenResponse
from src.core.config import settings
from src.core.security import (
    TokenType,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token_of_type,
    hash_password,
    verify_password,
)
from src.integrations import email as email_integration
from src.users import service as users_service
from src.users.models import AuthProvider, LastLoginRole, User

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SEC = 60 * 60


_ROLE_TO_LAST_LOGIN = {
    "member": LastLoginRole.MEMBER,
    "founder": LastLoginRole.FOUNDER,
    "reviewer": LastLoginRole.REVIEWER,
    "admin": LastLoginRole.ADMIN,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_expires_at() -> datetime:
    return _now() + timedelta(days=settings.refresh_token_expire_days)


def _persist_refresh_token(db: Session, user: User, jti: str) -> None:
    db.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            expires_at=_refresh_expires_at(),
            revoked=False,
        )
    )
    db.flush()


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    access = create_access_token(str(user.id))
    refresh, jti = create_refresh_token(str(user.id))
    _persist_refresh_token(db, user, jti)
    return TokenResponse(access_token=access, refresh_token=refresh)


def _revoke_all_user_refresh_tokens(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )


def _get_active_refresh_token(db: Session, jti: str) -> RefreshToken | None:
    token = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if token is None or token.revoked:
        return None
    if token.expires_at < _now():
        return None
    return token


def signup(
    db: Session,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    nick_name: str | None,
) -> TokenResponse:
    email = email.lower()
    if users_service.get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    role = users_service.get_or_create_role(db, "member", "Member")
    user = users_service.create_user_with_profile(
        db,
        email=email,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        auth_provider=AuthProvider.EMAIL,
        auth_provider_id=None,
        nick_name=nick_name,
        role=role,
    )
    tokens = _issue_tokens(db, user)
    db.commit()

    verification_token = create_email_verification_token(str(user.id))
    email_integration.send_verification_email(user.email, verification_token)
    return tokens


def login(db: Session, *, email: str, password: str) -> TokenResponse:
    user = users_service.get_user_by_email(db, email.lower())
    if user is None or user.password_hash is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    role_slug = user.profile.role.slug if user.profile and user.profile.role else "member"
    user.last_login_role = _ROLE_TO_LAST_LOGIN.get(role_slug, LastLoginRole.MEMBER)
    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens


def refresh(db: Session, *, refresh_token: str) -> TokenResponse:
    claims = decode_token_of_type(refresh_token, TokenType.REFRESH)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    jti = claims.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    stored = _get_active_refresh_token(db, jti)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired"
        )

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user = users_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Rotate: revoke the presented token, issue a fresh pair.
    stored.revoked = True
    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens


def logout(db: Session, *, refresh_token: str) -> None:
    claims = decode_token_of_type(refresh_token, TokenType.REFRESH)
    if claims is None:
        return  # idempotent: no account information leaked
    jti = claims.get("jti")
    if not jti:
        return
    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if stored is not None and not stored.revoked:
        stored.revoked = True
        db.commit()


def verify_email(db: Session, *, token: str) -> None:
    claims = decode_token_of_type(token, TokenType.EMAIL_VERIFICATION)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token"
        )
    user = users_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token"
        )
    user.email_verified = True
    db.commit()


def forgot_password(db: Session, *, email: str) -> None:
    user = users_service.get_user_by_email(db, email.lower())
    if user is None or user.auth_provider != AuthProvider.EMAIL:
        return  # no account enumeration
    reset_token = create_password_reset_token(str(user.id))
    email_integration.send_password_reset_email(user.email, reset_token)


def reset_password(db: Session, *, token: str, new_password: str) -> None:
    claims = decode_token_of_type(token, TokenType.PASSWORD_RESET)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
    user = users_service.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token")
    if user.auth_provider != AuthProvider.EMAIL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset is not available for this account",
        )
    user.password_hash = hash_password(new_password)
    _revoke_all_user_refresh_tokens(db, user.id)
    db.commit()


def change_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    if user.auth_provider != AuthProvider.EMAIL or user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change is not available for this account",
        )
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    user.password_hash = hash_password(new_password)
    _revoke_all_user_refresh_tokens(db, user.id)
    db.commit()


# --- Google sign-in seam ---


def _fetch_google_jwks() -> dict:
    with urllib.request.urlopen(
        GOOGLE_JWKS_URL, timeout=10
    ) as resp:  # noqa: S310 - trusted https URL
        return json.loads(resp.read().decode("utf-8"))


def _get_google_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache is None or (time.time() - _jwks_fetched_at) > _JWKS_TTL_SEC:
        _jwks_cache = _fetch_google_jwks()
        _jwks_fetched_at = time.time()
    return _jwks_cache


def verify_google_id_token(id_token: str) -> dict:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google sign-in is not configured",
        )
    try:
        claims = jwt.decode(
            id_token,
            _get_google_jwks(),
            algorithms=["RS256"],
            audience=settings.google_client_id,
            issuer=GOOGLE_ISSUERS,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Google ID token: {exc}",
        ) from exc
    return claims


def google(db: Session, *, id_token: str) -> TokenResponse:
    claims = verify_google_id_token(id_token)
    provider_id = claims.get("sub")
    email = (claims.get("email") or "").lower()
    if not provider_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Google token missing subject"
        )

    user = users_service.get_user_by_auth_provider(db, AuthProvider.GOOGLE, str(provider_id))
    if user is None and email:
        user = users_service.get_user_by_email(db, email)
        if user is not None:
            # Link an existing email account to Google.
            user.auth_provider = AuthProvider.GOOGLE
            user.auth_provider_id = str(provider_id)

    if user is None:
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token missing email",
            )
        role = users_service.get_or_create_role(db, "member", "Member")
        first_name = (claims.get("given_name") or email.split("@", 1)[0])[:255]
        last_name = (claims.get("family_name") or "User")[:255]
        user = users_service.create_user_with_profile(
            db,
            email=email,
            password_hash=None,
            first_name=first_name,
            last_name=last_name,
            auth_provider=AuthProvider.GOOGLE,
            auth_provider_id=str(provider_id),
            nick_name=first_name,
            role=role,
        )
        user.email_verified = bool(claims.get("email_verified"))

    tokens = _issue_tokens(db, user)
    db.commit()
    return tokens
