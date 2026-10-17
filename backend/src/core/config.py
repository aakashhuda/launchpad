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
