from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.core.database import engine, get_db
from src.main import app


@pytest.fixture(autouse=True)
def _clear_discovery_cache() -> Iterator[None]:
    """Drop cached discovery reads and queued jobs so tests stay independent."""
    try:
        from src.integrations.redis import get_redis_client

        redis = get_redis_client()
        keys = (
            list(redis.scan_iter("cache:discovery:*"))
            + list(redis.scan_iter("events:task*"))
            + list(redis.scan_iter("limits:*"))
            + list(redis.scan_iter("abuse:*"))
        )
        if keys:
            redis.delete(*keys)
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _disable_rate_limiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rate limiting is on by default; opt specific tests back in."""
    from src.core.config import settings

    monkeypatch.setattr(settings, "rate_limit_enabled", False)


@pytest.fixture()
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
