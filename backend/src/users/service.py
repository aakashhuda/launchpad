from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.users import crud
from src.users.models import AuthProvider, MemberFollow, Profile, Role, User
from src.users.schemas import ProfileCreate, ProfileRead, UserCreate, UserWithProfilesRead

_MAX_SLUG_RETRIES = 3

_DEFAULT_ROLE_NAMES = {
    "member": "Member",
    "founder": "Founder",
    "reviewer": "Reviewer",
    "admin": "Admin",
}


class RoleService:
    """Business logic for roles."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_slug(self, slug: str) -> Role | None:
        return crud.get_role_by_slug(self.db, slug)

    def get_or_create(
        self, slug: str, name: str | None = None, permissions: dict | None = None
    ) -> Role:
        """Fetch a role, creating it if absent. Race-safe under concurrent creates."""
        role = crud.get_role_by_slug(self.db, slug)
        if role is not None:
            return role
        try:
            with self.db.begin_nested():
                return crud.create_role(
                    self.db,
                    slug=slug,
                    name=name or _DEFAULT_ROLE_NAMES.get(slug, slug.title()),
                    permissions=permissions or {},
                )
        except IntegrityError:
            # A concurrent request created it first; re-fetch.
            role = crud.get_role_by_slug(self.db, slug)
            if role is None:
                raise
            return role


class UserService:
    """Business logic for user identities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return crud.get_user_by_id(self.db, user_id)

    def get_by_email(self, email: str) -> User | None:
        return crud.get_user_by_email(self.db, email.lower())

    def get_by_phone(self, phone_number: str) -> User | None:
        return crud.get_user_by_phone(self.db, phone_number)

    def get_by_auth_provider(self, provider: AuthProvider, provider_id: str) -> User | None:
        return crud.get_user_by_auth_provider(self.db, provider, provider_id)

    def create(self, payload: UserCreate, *, password_hash: str | None = None) -> User:
        """Create a user, surfacing unique email/phone collisions as 409."""
        email = payload.email.lower()
        try:
            with self.db.begin_nested():
                return crud.create_user(
                    self.db,
                    email=email,
                    password_hash=password_hash,
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                    phone_number=payload.phone_number,
                    auth_provider=payload.auth_provider,
                    auth_provider_id=payload.auth_provider_id,
                )
        except IntegrityError:
            if crud.get_user_by_email(self.db, email) is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
                )
            if (
                payload.phone_number
                and crud.get_user_by_phone(self.db, payload.phone_number) is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Phone number already registered",
                )
            raise

    def read_with_profiles(self, user: User) -> UserWithProfilesRead:
        return UserWithProfilesRead.model_validate(user)


class ProfileService:
    """Business logic for profiles."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_slug(self, slug: str) -> Profile | None:
        return crud.get_profile_by_slug(self.db, slug)

    def get_by_user_and_role(self, user_id: int, role_id: int) -> Profile | None:
        return crud.get_profile_by_user_and_role(self.db, user_id, role_id)

    def list_for_user(self, user_id: int) -> list[Profile]:
        return crud.list_profiles_by_user(self.db, user_id)

    def role_slugs(self, user: User) -> set[str]:
        return {profile.role.slug for profile in user.profiles if profile.role is not None}

    def profile_with_role(self, user: User, slug: str) -> Profile | None:
        for profile in user.profiles:
            if profile.role is not None and profile.role.slug == slug:
                return profile
        return None

    def member_profile(self, user: User) -> Profile | None:
        return self.profile_with_role(user, "member")

    def require_member_profile(self, user: User) -> Profile:
        """Resolve the acting member profile, or fail if the user has none."""
        profile = self.member_profile(user)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Member profile required"
            )
        return profile

    def read_by_slug(self, slug: str) -> ProfileRead | None:
        profile = self.get_by_slug(slug)
        if profile is None:
            return None
        return ProfileRead.model_validate(profile)

    def create_for_user(self, user: User, payload: ProfileCreate) -> Profile:
        """Create a profile for ``user`` with a race-safe unique slug."""
        role = RoleService(self.db).get_or_create(payload.role_slug)
        base = payload.nick_name or user.email
        for _ in range(_MAX_SLUG_RETRIES):
            slug = crud.generate_unique_slug(self.db, base)
            try:
                with self.db.begin_nested():
                    return crud.create_profile(
                        self.db,
                        user=user,
                        role_id=role.id,
                        nick_name=payload.nick_name,
                        slug=slug,
                    )
            except IntegrityError:
                continue  # slug collision — retry with a fresh slug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not assign a unique profile slug",
        )


class MemberFollowService:
    """Business logic for member follows (consumed by later feed phases)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def is_following(self, follower_profile_id: int, followed_profile_id: int) -> bool:
        return crud.get_member_follow(self.db, follower_profile_id, followed_profile_id) is not None

    def follow(self, follower_profile_id: int, followed_profile_id: int) -> MemberFollow:
        if follower_profile_id == followed_profile_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself"
            )
        existing = crud.get_member_follow(self.db, follower_profile_id, followed_profile_id)
        if existing is not None:
            return existing
        follow = crud.create_member_follow(self.db, follower_profile_id, followed_profile_id)
        self.db.commit()
        return follow

    def unfollow(self, follower_profile_id: int, followed_profile_id: int) -> None:
        crud.delete_member_follow(self.db, follower_profile_id, followed_profile_id)
        self.db.commit()

    def list_following(self, user: User) -> list[Profile]:
        follower = ProfileService(self.db).require_member_profile(user)
        return crud.list_followed_profiles(self.db, follower.id)

    def follow_by_slug(self, user: User, slug: str) -> Profile:
        follower = ProfileService(self.db).require_member_profile(user)
        target = self._require_profile(slug)
        self.follow(follower.id, target.id)
        return target

    def unfollow_by_slug(self, user: User, slug: str) -> None:
        follower = ProfileService(self.db).require_member_profile(user)
        target = self._require_profile(slug)
        self.unfollow(follower.id, target.id)

    def _require_profile(self, slug: str) -> Profile:
        profile = crud.get_profile_by_slug(self.db, slug)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        return profile
