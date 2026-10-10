from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.topics.models import Topic

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
