from __future__ import annotations

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.users.models import AuthProvider, Profile, Role, User

# Slug sanitization
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "user"


def generate_unique_slug(db: Session, base: str) -> str:
    """Best-effort unique slug. The DB unique constraint is the real guard."""
    candidate = _slugify(base)
    while db.scalar(select(Profile).where(Profile.slug == candidate)) is not None:
        candidate = f"{_slugify(base)}-{secrets.token_hex(2)}"
    return candidate


def get_role_by_slug(db: Session, slug: str) -> Role | None:
    return db.scalar(select(Role).where(Role.slug == slug))


def create_role(db: Session, *, slug: str, name: str, permissions: dict) -> Role:
    role = Role(slug=slug, name=name, permissions=permissions or {})
    db.add(role)
    db.flush()
    return role


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.scalar(select(User).where(User.id == user_id))


def get_user_by_auth_provider(db: Session, provider: AuthProvider, provider_id: str) -> User | None:
    return db.scalar(
        select(User).where(User.auth_provider == provider, User.auth_provider_id == provider_id)
    )


def get_profile_by_slug(db: Session, slug: str) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.slug == slug))


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
    slug: str,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        first_name=first_name,
        last_name=last_name,
        auth_provider=auth_provider,
        auth_provider_id=auth_provider_id,
    )
    db.add(user)
    db.flush()  # populate user.id

    profile = Profile(
        user_id=user.id,
        role_id=role.id,
        nick_name=nick_name,
        slug=slug,
        public_profile_url=f"/users/{slug}",
    )
    db.add(profile)
    db.flush()
    user.profile = profile
    return user
