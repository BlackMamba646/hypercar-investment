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
    "daily-valuation": {
        "task": "aatp.valuation.tasks.run_valuation",
        "schedule": crontab(hour=8, minute=0),  # 8 AM UTC daily, after normalisation
    },
    "monthly-recurring-costs": {
        "task": "aatp.ledger.tasks.generate_recurring_costs",
        "schedule": crontab(hour=0, minute=0, day_of_month=1),  # 1st of month midnight UTC
    },
    "daily-portfolio-snapshot": {
        "task": "aatp.ledger.tasks.daily_portfolio_snapshot",
        "schedule": crontab(hour=10, minute=0),  # 10 AM UTC daily
    },
    "daily-signal-scan": {
        "task": "aatp.signals.tasks.run_signal_scan",
        "schedule": crontab(hour=9, minute=0),  # 9 AM UTC daily, after valuation
    },
    "daily-consensus-scan": {
        "task": "aatp.consensus.tasks.run_consensus_scan",
        "schedule": crontab(hour=9, minute=30),  # 9:30 AM UTC daily, after signals
    },
    "daily-risk-assessment": {
        "task": "aatp.risk.tasks.run_risk_assessment",
        "schedule": crontab(hour=11, minute=0),  # 11 AM UTC daily, after portfolio snapshot
    },
    "daily-reconciliation": {
        "task": "aatp.reconciliation.tasks.run_daily_reconciliation",
        "schedule": crontab(hour=12, minute=0),  # 12 PM UTC daily, after risk assessment
    },
    "hourly-health-check": {
        "task": "aatp.reconciliation.tasks.run_health_check",
        "schedule": crontab(minute=0),  # Every hour on the hour
    },
}
