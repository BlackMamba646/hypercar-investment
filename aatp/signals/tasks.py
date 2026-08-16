"""
Celery tasks for the signal engine.

Provides scheduled and ad-hoc signal scanning tasks.
"""

from __future__ import annotations

import asyncio
import uuid

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("signals.tasks")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="aatp.signals.tasks.run_signal_scan", max_retries=2)
def run_signal_scan(self):
    """Run the daily signal scan across all asset models."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.signals.scanner import OpportunityScanner

            scanner = OpportunityScanner(session)
            result = await scanner.scan_all()

            logger.info(
                "signal_scan_complete",
                models_scanned=result.models_scanned,
                signals_generated=result.signals_generated,
                actionable=result.actionable_count,
                watchlist=result.watchlist_count,
                errors=result.errors,
            )
            return {
                "models_scanned": result.models_scanned,
                "signals_generated": result.signals_generated,
                "opportunities_scored": result.opportunities_scored,
                "actionable": result.actionable_count,
                "watchlist": result.watchlist_count,
                "errors": result.errors,
            }

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("signal_scan_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)


@app.task(name="aatp.signals.tasks.scan_single_model")
def scan_single_model(asset_model_id: str):
    """Run signal scan for a single model -- for ad-hoc invocation."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.signals.scanner import OpportunityScanner

            scanner = OpportunityScanner(session)
            model_id = uuid.UUID(asset_model_id)
            result = await scanner.scan_model(model_id)
            await session.commit()

            logger.info(
                "single_model_scan_complete",
                asset_model_id=asset_model_id,
                **result,
            )
            return result

    return _run_async(_run())
