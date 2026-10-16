from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.dependencies import require_verified_role
from src.topics.schemas import TopicRead
from src.topics.service import TopicFollowService
from src.users.models import User

router = APIRouter()


@router.get("/me/following", response_model=list[TopicRead])
def list_my_topic_follows(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> list[TopicRead]:
    topics = TopicFollowService(db).list_followed(current_user)
    return [TopicRead.model_validate(topic) for topic in topics]


@router.post("/{slug}/follow", response_model=TopicRead)
def follow_topic(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> TopicRead:
    topic = TopicFollowService(db).follow_by_slug(current_user, slug)
    return TopicRead.model_validate(topic)


@router.delete("/{slug}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_topic(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_verified_role("member")),
) -> Response:
    TopicFollowService(db).unfollow_by_slug(current_user, slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
