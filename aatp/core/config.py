import os

from pydantic import model_validator
from pydantic_settings import BaseSettings


def _to_async_url(raw: str) -> str:
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    return raw


def _to_sync_url(raw: str) -> str:
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    return raw


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://aatp:aatp@localhost:5432/aatp"
    database_url_sync: str = "postgresql://aatp:aatp@localhost:5432/aatp"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    aatp_env: str = "development"
    aatp_log_level: str = "INFO"

    port: int = int(os.environ.get("PORT", "8000"))

    scraper_request_delay_seconds: float = 2.0
    scraper_max_concurrent_requests: int = 3

    price_movement_alert_threshold_pct: float = 10.0
    consensus_actionable_threshold: int = 4
    consensus_watchlist_threshold: int = 2
    min_net_return_threshold_pct: float = 25.0
    max_hold_period_months: int = 24

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _fix_db_urls(self) -> "Settings":
        raw = os.environ.get("DATABASE_URL", "")
        if raw:
            self.database_url = _to_async_url(raw)
            self.database_url_sync = _to_sync_url(raw)
        return self


settings = Settings()
