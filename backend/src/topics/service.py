from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.topics import crud
from src.topics.models import Topic
from src.users.models import User
from src.users.service import ProfileService


class TopicService:
    """Read access to topics."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_slug(self, slug: str) -> Topic | None:
        return crud.get_topic_by_slug(self.db, slug)


class TopicFollowService:
    """Followers of topics, used by member feeds (consumed by later feed phases)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.profiles = ProfileService(db)

    def is_following(self, profile_id: int, topic_id: int) -> bool:
        return crud.get_topic_follow(self.db, profile_id, topic_id) is not None

    def follow_by_slug(self, user: User, slug: str) -> Topic:
        profile = self.profiles.require_member_profile(user)
        topic = self._require_topic(slug)
        if not self.is_following(profile.id, topic.id):  # idempotent
            crud.create_topic_follow(self.db, profile.id, topic.id)
            self.db.commit()
        return topic

    def unfollow_by_slug(self, user: User, slug: str) -> None:
        profile = self.profiles.require_member_profile(user)
        topic = self._require_topic(slug)
        crud.delete_topic_follow(self.db, profile.id, topic.id)
        self.db.commit()

    def list_followed(self, user: User) -> list[Topic]:
        profile = self.profiles.require_member_profile(user)
        return crud.list_followed_topics(self.db, profile.id)

    def _require_topic(self, slug: str) -> Topic:
        topic = crud.get_topic_by_slug(self.db, slug)
        if topic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
        return topic
