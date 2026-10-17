from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.security import TokenType, decode_token_of_type
from src.users.models import User, UserStatus
from src.users.service import UserService

bearer_scheme = HTTPBearer(auto_error=False)


def _reject_if_suspended(user: User) -> None:
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    claims = decode_token_of_type(credentials.credentials, TokenType.ACCESS)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token subject",
        )

    user = UserService(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    _reject_if_suspended(user)
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Best-effort auth: returns the user when a valid access token is present, else None."""
    if credentials is None or not credentials.credentials:
        return None
    claims = decode_token_of_type(credentials.credentials, TokenType.ACCESS)
    if claims is None:
        return None
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        return None
    user = UserService(db).get_by_id(user_id)
    if user is None or user.status == UserStatus.SUSPENDED:
        return None
    return user


def require_verified_email(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return current_user


def require_role(*slugs: str):
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        user_roles = {
            profile.role.slug for profile in current_user.profiles if profile.role is not None
        }
        if user_roles.isdisjoint(slugs):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role",
            )
        return current_user

    return _dependency


def require_verified_role(*slugs: str):
    """Role guard for member actions that additionally requires a confirmed email.

    Visitors (anonymous) are unaffected because they never reach a role-guarded
    route; every authenticated actor other than a visitor must be verified.
    """
    check_role = require_role(*slugs)

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required",
            )
        return check_role(current_user)

    return _dependency


def assert_owner(owner_id: int, current_user: User) -> None:
    """Raise 403 if ``current_user`` does not own resource owned by ``owner_id``."""
    if current_user.id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to access this resource",
        )
