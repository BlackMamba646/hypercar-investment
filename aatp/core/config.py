import os

from pydantic_settings import BaseSettings


def _build_async_db_url() -> str:
    """Derive the asyncpg database URL.

    Railway sets DATABASE_URL as postgres://... (psycopg2 style).
    We need postgresql+asyncpg://...
    """
    raw = os.environ.get("DATABASE_URL", "")
    if raw:
        url = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url
    return "postgresql+asyncpg://aatp:aatp@localhost:5432/aatp"


def _build_sync_db_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if raw:
        url = raw.replace("postgres://", "postgresql://", 1)
        if not url.startswith("postgresql://"):
            url = "postgresql://" + url.split("://", 1)[-1]
        return url
    return "postgresql://aatp:aatp@localhost:5432/aatp"


class Settings(BaseSettings):
    database_url: str = _build_async_db_url()
    database_url_sync: str = _build_sync_db_url()
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    celery_broker_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
    celery_result_backend: str = os.environ.get("REDIS_URL", "redis://localhost:6379/2")

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


settings = Settings()
