from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.users import crud
from src.users.models import AuthProvider, Role, User
from src.users.schemas import ProfileRead, UserWithProfileRead

_MAX_SLUG_RETRIES = 3


def get_user_by_email(db: Session, email: str) -> User | None:
    return crud.get_user_by_email(db, email)


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return crud.get_user_by_id(db, user_id)


def get_user_by_auth_provider(db: Session, provider: AuthProvider, provider_id: str) -> User | None:
    return crud.get_user_by_auth_provider(db, provider, provider_id)


def get_profile_by_slug(db: Session, slug: str) -> ProfileRead | None:
    profile = crud.get_profile_by_slug(db, slug)
    if profile is None:
        return None
    return ProfileRead.model_validate(profile)


def get_current_user_read(db: Session, user: User) -> UserWithProfileRead:
    return UserWithProfileRead.model_validate(user)


def get_or_create_role(db: Session, slug: str, name: str, permissions: dict | None = None) -> Role:
    """Fetch a role, creating it if absent. Race-safe under concurrent creates."""
    role = crud.get_role_by_slug(db, slug)
    if role is not None:
        return role
    try:
        with db.begin_nested():
            return crud.create_role(db, slug=slug, name=name, permissions=permissions or {})
    except IntegrityError:
        # A concurrent request created it first; re-fetch.
        role = crud.get_role_by_slug(db, slug)
        if role is None:
            raise
        return role


def create_user_with_profile(
    db: Session,
    *,
    email: str,
    password_hash: str | None,
    first_name: str,
    last_name: str,
    auth_provider: AuthProvider,
    auth_provider_id: str | None,
    nick_name: str | None,
    role: Role,
) -> User:
    """Create a user + profile with a unique slug.

    Race-safe: a concurrent slug collision (or email collision) surfaces as an
    ``IntegrityError`` inside a savepoint. Slug collisions retry with a fresh
    slug; email collisions surface as 409.
    """
    base = nick_name or email
    for _ in range(_MAX_SLUG_RETRIES):
        slug = crud.generate_unique_slug(db, base)
        try:
            with db.begin_nested():
                return crud.create_user_with_profile(
                    db,
                    email=email,
                    password_hash=password_hash,
                    first_name=first_name,
                    last_name=last_name,
                    auth_provider=auth_provider,
                    auth_provider_id=auth_provider_id,
                    nick_name=nick_name,
                    role=role,
                    slug=slug,
                )
        except IntegrityError:
            if crud.get_user_by_email(db, email) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )
            continue  # slug collision — retry with a fresh slug

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not assign a unique profile slug",
    )
