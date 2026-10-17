import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def resolve_env_file() -> str:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return env_file

    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env == "production":
        return ".env.production"
    return ".env.development"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Launchpad Backend"
    app_env: str = "development"
    debug: bool = True
    secret_key: str
    database_url: str
    redis_url: str
    jwt_algorithm: str = "HS256"
    access_token_expire_min: int = 30
    refresh_token_expire_days: int = 7
    email_verification_expire_hours: int = 24
    password_reset_expire_hours: int = 1
    google_client_id: str | None = None
    max_launches_per_founder_per_day: int = 2
    discovery_cache_ttl_seconds: int = 60

    # Request correlation + structured logging (Phase 7). The header name is used
    # both to read an incoming id and to echo it back on responses.
    correlation_id_header: str = "X-Request-Id"

    # Redis-backed rate limiting for abuse-prone endpoints (auth, voting,
    # reporting, commenting). Disabled in tests via conftest. Fail-open: if the
    # limiter's Redis is unreachable the request is allowed. Non-authoritative.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_auth_per_minute: int = 30
    rate_limit_vote_per_minute: int = 120
    rate_limit_comment_per_minute: int = 30
    rate_limit_report_per_minute: int = 20

    # Suspicious-behavior monitoring thresholds (per member, in-window). Crossing
    # a threshold enqueues a staff review signal; it never blocks the request.
    abuse_window_seconds: int = 300
    abuse_vote_threshold: int = 40
    abuse_comment_threshold: int = 20
    abuse_report_threshold: int = 10

    # Outbound email. Disabled by default so dev/test runs need no provider;
    # the transport logs instead. Real delivery requires email_enabled=True plus
    # SMTP settings sourced from the environment (never committed).
    email_enabled: bool = False
    email_provider: str = "smtp"
    email_from_address: str = "no-reply@launchpad.local"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True

    # Notification delivery retry/backoff (provider-outage resilience).
    notification_max_attempts: int = 3
    notification_retry_base_seconds: float = 5.0
    notification_retry_max_seconds: float = 300.0

    # Directory for generated founder-export artifacts.
    export_dir: str = "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
