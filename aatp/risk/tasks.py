"""Celery tasks for the risk engine.

Provides scheduled daily risk assessment and ad-hoc position assessment.
"""

from __future__ import annotations

import asyncio
import uuid

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("risk.tasks")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="aatp.risk.tasks.run_risk_assessment", max_retries=2)
def run_risk_assessment(self):
    """Run the daily full risk assessment across all open positions."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.risk.engine import run_full_assessment

            result = await run_full_assessment(session)

            logger.info(
                "risk_assessment_complete",
                positions_assessed=result["positions_assessed"],
                portfolio_snapshot_date=result.get("portfolio_snapshot_date"),
                portfolio_warnings=result.get("portfolio_warnings", 0),
                errors=result["errors"],
            )
            return result

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("risk_assessment_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)


@app.task(name="aatp.risk.tasks.assess_single_position")
def assess_single_position(position_id: str):
    """Run risk assessment for a single position -- for ad-hoc invocation."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.risk.engine import assess_position

            pos_id = uuid.UUID(position_id)
            assessment = await assess_position(session, pos_id)
            await session.commit()

            logger.info(
                "single_position_risk_complete",
                position_id=position_id,
                composite_risk=str(assessment.composite_risk_score),
            )
            return {
                "position_id": position_id,
                "composite_risk_score": str(assessment.composite_risk_score),
            }

    return _run_async(_run())
