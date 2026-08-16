from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://aatp:aatp@localhost:5432/aatp"
    database_url_sync: str = "postgresql://aatp:aatp@localhost:5432/aatp"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    aatp_env: str = "development"
    aatp_log_level: str = "INFO"

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
