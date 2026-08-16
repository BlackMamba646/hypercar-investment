from celery import Celery
from celery.schedules import crontab

from aatp.core.config import settings

app = Celery(
    "aatp",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

app.conf.beat_schedule = {
    "bat-daily-scrape": {
        "task": "aatp.collectors.tasks.run_bat_scraper",
        "schedule": crontab(hour=6, minute=0),  # 6 AM UTC daily
    },
    "rm-weekly-scrape": {
        "task": "aatp.collectors.tasks.run_rm_scraper",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Monday 8 AM UTC
    },
    "normalise-unnormalised": {
        "task": "aatp.collectors.tasks.normalise_pending_transactions",
        "schedule": crontab(hour=7, minute=0),  # 7 AM UTC daily, after BaT scrape
    },
}
