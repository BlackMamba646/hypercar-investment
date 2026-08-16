"""Celery tasks for the multi-model consensus engine.

Provides scheduled daily consensus scan and ad-hoc single-model consensus.
"""

from __future__ import annotations

import asyncio
import uuid

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("consensus.tasks")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="aatp.consensus.tasks.run_consensus_scan", max_retries=2)
def run_consensus_scan(self):
    """Run the daily consensus scan across all asset models."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.consensus.engine import run_all_models

            result = await run_all_models(session)

            logger.info(
                "consensus_scan_complete",
                models_scanned=result["models_scanned"],
                actionable=result["actionable"],
                watchlist=result["watchlist"],
                vetoed=result["vetoed"],
                errors=result["errors"],
            )
            return result

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("consensus_scan_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)


@app.task(name="aatp.consensus.tasks.run_consensus_single")
def run_consensus_single(asset_model_id: str):
    """Run consensus engine for a single asset model -- for ad-hoc invocation."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.consensus.engine import run_consensus

            model_id = uuid.UUID(asset_model_id)
            result = await run_consensus(session, model_id)

            logger.info(
                "consensus_single_complete",
                asset_model_id=asset_model_id,
                **result,
            )
            return result

    return _run_async(_run())
