from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Uuid,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base_model import Base, CreatedAtMixin, TimestampMixin, enum_values

if TYPE_CHECKING:
    from src.community.models import Comment, Report, Vote
    from src.notifications.models import Notification, NotificationPreference
    from src.products.models import Product, Submission
    from src.topics.models import TopicFollow


class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"
    GITHUB = "github"


class LastLoginRole(str, enum.Enum):
    MEMBER = "member"
    FOUNDER = "founder"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(
            AuthProvider,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=AuthProvider.EMAIL,
        server_default=text("'email'"),
    )
    auth_provider_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    last_login_role: Mapped[LastLoginRole | None] = mapped_column(
        Enum(
            LastLoginRole,
            native_enum=False,
            length=50,
            create_constraint=False,
            values_callable=enum_values,
        )
    )
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    profiles: Mapped[list[Profile]] = relationship(back_populates="user", order_by="Profile.id")

    __table_args__ = (
        CheckConstraint(
            "auth_provider IN ('email', 'google', 'github')", name="ck_users_auth_provider"
        ),
        CheckConstraint(
            "last_login_role IS NULL OR last_login_role IN ('member', 'founder', 'reviewer', 'admin')",
            name="ck_users_last_login_role",
        ),
        Index("users_idx_0", "id", "user_uuid", "email"),
    )


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    role_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    profiles: Mapped[list[Profile]] = relationship(back_populates="role")

    __table_args__ = (Index("roles_idx_0", "id", "role_uuid", "slug"),)


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    profile_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nick_name: Mapped[str | None] = mapped_column(String(100))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    public_profile_url: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="profiles")
    role: Mapped[Role] = relationship(back_populates="profiles")

    products: Mapped[list[Product]] = relationship(back_populates="profile")
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="profile", foreign_keys="Submission.profile_id"
    )
    votes: Mapped[list[Vote]] = relationship(back_populates="profile")
    comments: Mapped[list[Comment]] = relationship(back_populates="profile")
    reports_made: Mapped[list[Report]] = relationship(
        back_populates="reporter_profile", foreign_keys="Report.reporter_profile_id"
    )
    notifications_received: Mapped[list[Notification]] = relationship(
        back_populates="recipient_profile", foreign_keys="Notification.recipient_profile_id"
    )
    notification_preference: Mapped[NotificationPreference] = relationship(
        back_populates="profile", uselist=False
    )
    member_following: Mapped[list[MemberFollow]] = relationship(
        back_populates="follower_profile", foreign_keys="MemberFollow.follower_profile_id"
    )
    member_followers: Mapped[list[MemberFollow]] = relationship(
        back_populates="followed_profile", foreign_keys="MemberFollow.followed_profile_id"
    )
    topic_follows: Mapped[list[TopicFollow]] = relationship(back_populates="profile")

    __table_args__ = (Index("profiles_idx_0", "id", "profile_uuid", "slug"),)


class MemberFollow(CreatedAtMixin, Base):
    __tablename__ = "member_follows"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    member_follow_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, default=uuid.uuid4
    )
    follower_profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    followed_profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )

    follower_profile: Mapped[Profile] = relationship(
        back_populates="member_following", foreign_keys=[follower_profile_id]
    )
    followed_profile: Mapped[Profile] = relationship(
        back_populates="member_followers", foreign_keys=[followed_profile_id]
    )

    __table_args__ = (
        CheckConstraint(
            "follower_profile_id <> followed_profile_id", name="ck_member_follows_not_self"
        ),
        Index("member_follows_idx_0", "follower_profile_id", "created_at"),
        Index("member_follows_idx_1", "followed_profile_id", "created_at"),
    )
