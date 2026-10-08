from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.users.models import AuthProvider


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    name: str


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    nick_name: str | None
    public_profile_url: str
    role: RoleRead


class UserRead(BaseModel):
    """Public-safe user projection (never includes password_hash)."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    user_uuid: UUID
    email: str
    first_name: str
    last_name: str
    auth_provider: AuthProvider
    email_verified: bool
    created_at: datetime


class UserWithProfileRead(UserRead):
    profile: ProfileRead
