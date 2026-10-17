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
from src.auth.schemas import LoginRequest, SignupRequest, TokenResponse
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
from src.notifications.models import NotificationEventType
from src.notifications.service import NotificationService
from src.users.models import AuthProvider, LastLoginRole, User
from src.users.schemas import ProfileCreate, UserCreate
from src.users.service import ProfileService, UserService

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


class RefreshTokenService:
    """Persistence, rotation, and revocation of refresh tokens."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def issue(self, user: User) -> TokenResponse:
        access = create_access_token(str(user.id))
        refresh, jti = create_refresh_token(str(user.id))
        self.db.add(
            RefreshToken(
                jti=jti,
                user_id=user.id,
                expires_at=_refresh_expires_at(),
                revoked=False,
            )
        )
        self.db.flush()
        return TokenResponse(access_token=access, refresh_token=refresh)

    def get_active(self, jti: str) -> RefreshToken | None:
        token = self.db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
        if token is None or token.revoked:
            return None
        if token.expires_at < _now():
            return None
        return token

    def revoke(self, token: RefreshToken) -> None:
        token.revoked = True

    def revoke_all_for_user(self, user_id: int) -> None:
        self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )


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


class GoogleSignInService:
    """Verify a Google ID token and resolve or create the matching user."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserService(db)
        self.profiles = ProfileService(db)
        self.tokens = RefreshTokenService(db)

    def sign_in(self, id_token: str) -> TokenResponse:
        claims = verify_google_id_token(id_token)
        provider_id = claims.get("sub")
        email = (claims.get("email") or "").lower()
        if not provider_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token missing subject",
            )

        user = self.users.get_by_auth_provider(AuthProvider.GOOGLE, str(provider_id))
        if user is None and email:
            user = self.users.get_by_email(email)
            if user is not None:
                # Link an existing email account to Google.
                user.auth_provider = AuthProvider.GOOGLE
                user.auth_provider_id = str(provider_id)

        if user is None:
            user = self._create_google_user(claims, email, str(provider_id))

        tokens = self.tokens.issue(user)
        self.db.commit()
        return tokens

    def _create_google_user(self, claims: dict, email: str, provider_id: str) -> User:
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token missing email",
            )
        first_name = (claims.get("given_name") or email.split("@", 1)[0])[:255]
        last_name = (claims.get("family_name") or "User")[:255]
        user = self.users.create(
            UserCreate(
                email=email,
                first_name=first_name,
                last_name=last_name,
                auth_provider=AuthProvider.GOOGLE,
                auth_provider_id=provider_id,
            )
        )
        self.profiles.create_for_user(user, ProfileCreate(role_slug="member", nick_name=first_name))
        user.email_verified = bool(claims.get("email_verified"))
        return user


class AuthService:
    """Orchestrates the account lifecycle (signup, login, tokens, passwords)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserService(db)
        self.profiles = ProfileService(db)
        self.tokens = RefreshTokenService(db)
        self.google = GoogleSignInService(db)
        self.notifications = NotificationService(db)

    # --- signup ---

    def signup(self, payload: SignupRequest) -> TokenResponse:
        existing = self.users.get_by_email(payload.email)
        self._guard_phone_uniqueness(payload.phone_number, existing)

        if existing is None:
            return self._create_account(payload)
        return self._add_profile_to_existing_account(payload, existing)

    def _guard_phone_uniqueness(self, phone_number: str | None, existing: User | None) -> None:
        if not phone_number:
            return
        owner = self.users.get_by_phone(phone_number)
        if owner is not None and (existing is None or owner.id != existing.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number already registered",
            )

    def _create_account(self, payload: SignupRequest) -> TokenResponse:
        user = self.users.create(
            UserCreate(
                email=payload.email,
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone_number=payload.phone_number,
                auth_provider=AuthProvider.EMAIL,
            ),
            password_hash=hash_password(payload.password),
        )
        profile = self.profiles.create_for_user(
            user,
            ProfileCreate(role_slug=payload.role.value, nick_name=payload.nick_name),
        )
        tokens = self.tokens.issue(user)

        verification_token = create_email_verification_token(str(user.id))
        self.notifications.emit(
            recipient_profile_id=profile.id,
            event_type=NotificationEventType.EMAIL_VERIFICATION_REQUESTED,
            payload={"token": verification_token},
        )
        self.db.commit()
        return tokens

    def _add_profile_to_existing_account(self, payload: SignupRequest, user: User) -> TokenResponse:
        if user.auth_provider != AuthProvider.EMAIL or user.password_hash is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is registered with a different sign-in method",
            )
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        requested = payload.role.value
        held_roles = self.profiles.role_slugs(user)
        if requested in held_roles:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You already have a {requested} profile",
            )
        if not payload.confirm_add_profile:
            held = ", ".join(sorted(held_roles)) or "an existing"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"You already have a {held} profile. " f"Confirm to add a {requested} profile."
                ),
            )

        self.profiles.create_for_user(
            user,
            ProfileCreate(role_slug=requested, nick_name=payload.nick_name),
        )
        tokens = self.tokens.issue(user)
        self.db.commit()
        return tokens

    # --- login / sessions ---

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self.users.get_by_email(payload.email)
        if (
            user is None
            or user.password_hash is None
            or not verify_password(payload.password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        user.last_login_role = self._last_login_role(user)
        tokens = self.tokens.issue(user)
        self.db.commit()
        return tokens

    def _last_login_role(self, user: User) -> LastLoginRole:
        if user.profiles and user.profiles[0].role is not None:
            slug = user.profiles[0].role.slug
            return _ROLE_TO_LAST_LOGIN.get(slug, LastLoginRole.MEMBER)
        return LastLoginRole.MEMBER

    def refresh(self, refresh_token: str) -> TokenResponse:
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

        stored = self.tokens.get_active(jti)
        if stored is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked or expired",
            )

        try:
            user_id = int(claims["sub"])
        except (KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        user = self.users.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Rotate: revoke the presented token, issue a fresh pair.
        self.tokens.revoke(stored)
        tokens = self.tokens.issue(user)
        self.db.commit()
        return tokens

    def logout(self, refresh_token: str) -> None:
        claims = decode_token_of_type(refresh_token, TokenType.REFRESH)
        if claims is None:
            return  # idempotent: no account information leaked
        jti = claims.get("jti")
        if not jti:
            return
        stored = self.db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
        if stored is not None and not stored.revoked:
            self.tokens.revoke(stored)
            self.db.commit()

    def google_sign_in(self, id_token: str) -> TokenResponse:
        return self.google.sign_in(id_token)

    # --- email + passwords ---

    def verify_email(self, token: str) -> None:
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
        user = self.users.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token"
            )
        user.email_verified = True
        self.db.commit()

    def forgot_password(self, email: str) -> None:
        user = self.users.get_by_email(email)
        if user is None or user.auth_provider != AuthProvider.EMAIL:
            return  # no account enumeration
        reset_token = create_password_reset_token(str(user.id))
        if not user.profiles:
            return
        self.notifications.emit(
            recipient_profile_id=user.profiles[0].id,
            event_type=NotificationEventType.PASSWORD_RESET_REQUESTED,
            payload={"token": reset_token},
        )
        self.db.commit()

    def reset_password(self, token: str, new_password: str) -> None:
        claims = decode_token_of_type(token, TokenType.PASSWORD_RESET)
        if claims is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )
        try:
            user_id = int(claims["sub"])
        except (KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token"
            )
        user = self.users.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token"
            )
        if user.auth_provider != AuthProvider.EMAIL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset is not available for this account",
            )
        user.password_hash = hash_password(new_password)
        self.tokens.revoke_all_for_user(user.id)
        self.db.commit()

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
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
        self.tokens.revoke_all_for_user(user.id)
        self.db.commit()
