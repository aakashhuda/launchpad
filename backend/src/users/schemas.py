from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.users.models import AuthProvider


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    name: str


class ProfileCreate(BaseModel):
    role_slug: str = Field(..., min_length=1, max_length=50)
    nick_name: str | None = Field(default=None, max_length=100)


class ProfileUpdate(BaseModel):
    nick_name: str | None = Field(default=None, max_length=100)


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    nick_name: str | None
    public_profile_url: str
    role: RoleRead


class UserCreate(BaseModel):
    """Identity payload for creating a user (password hashing is an auth concern)."""

    email: str = Field(..., min_length=3, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=20)
    auth_provider: AuthProvider = AuthProvider.EMAIL
    auth_provider_id: str | None = Field(default=None, max_length=100)


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=20)


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


class UserWithProfilesRead(UserRead):
    profiles: list[ProfileRead]
