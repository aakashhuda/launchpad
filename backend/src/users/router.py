from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.users.models import User
from src.users.schemas import ProfileRead, UserWithProfilesRead
from src.users.service import ProfileService, UserService

router = APIRouter()


@router.get("/me", response_model=UserWithProfilesRead)
def read_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserWithProfilesRead:
    return UserService(db).read_with_profiles(current_user)


@router.get("/{slug}", response_model=ProfileRead)
def read_profile_by_slug(slug: str, db: Session = Depends(get_db)) -> ProfileRead:
    profile = ProfileService(db).read_by_slug(slug)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile
