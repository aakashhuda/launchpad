from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.topics.models import Topic, TopicFollow

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "topic"


def get_topic_by_slug(db: Session, slug: str) -> Topic | None:
    return db.scalar(select(Topic).where(Topic.slug == slug))


def get_or_create_topic(db: Session, text: str) -> Topic:
    """Resolve a topic by slug, creating it when absent (idempotent by slug)."""
    slug = slugify(text)
    topic = get_topic_by_slug(db, slug)
    if topic is not None:
        return topic
    topic = Topic(text=text.strip(), slug=slug)
    db.add(topic)
    db.flush()
    return topic


def get_topic_follow(db: Session, profile_id: int, topic_id: int) -> TopicFollow | None:
    return db.scalar(
        select(TopicFollow).where(
            TopicFollow.profile_id == profile_id, TopicFollow.topic_id == topic_id
        )
    )


def create_topic_follow(db: Session, profile_id: int, topic_id: int) -> TopicFollow:
    follow = TopicFollow(profile_id=profile_id, topic_id=topic_id)
    db.add(follow)
    db.flush()
    return follow


def delete_topic_follow(db: Session, profile_id: int, topic_id: int) -> None:
    follow = get_topic_follow(db, profile_id, topic_id)
    if follow is not None:
        db.delete(follow)
        db.flush()


def list_followed_topics(db: Session, profile_id: int) -> list[Topic]:
    return list(
        db.scalars(
            select(Topic)
            .join(TopicFollow, TopicFollow.topic_id == Topic.id)
            .where(TopicFollow.profile_id == profile_id)
            .order_by(TopicFollow.created_at.desc(), TopicFollow.id.desc())
        )
    )
