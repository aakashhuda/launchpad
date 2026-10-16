from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.dependencies import get_current_user, require_verified_role
from src.users.models import User
from src.users.schemas import ProfileRead, UserWithProfilesRead
from src.users.service import MemberFollowService, ProfileService, UserService

router = APIRouter()


@router.get("/me", response_model=UserWithProfilesRead)
def read_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserWithProfilesRead:
    return UserService(db).read_with_profiles(current_user)


@router.get("/me/following", response_model=list[ProfileRead])
def list_my_following(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> list[ProfileRead]:
    profiles = MemberFollowService(db).list_following(current_user)
    return [ProfileRead.model_validate(profile) for profile in profiles]


@router.get("/{slug}", response_model=ProfileRead)
def read_profile_by_slug(slug: str, db: Session = Depends(get_db)) -> ProfileRead:
    profile = ProfileService(db).read_by_slug(slug)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.post("/{slug}/follow", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def follow_member(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> ProfileRead:
    profile = MemberFollowService(db).follow_by_slug(current_user, slug)
    return ProfileRead.model_validate(profile)


@router.delete("/{slug}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_member(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> Response:
    MemberFollowService(db).unfollow_by_slug(current_user, slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
