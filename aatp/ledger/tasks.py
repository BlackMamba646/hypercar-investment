from __future__ import annotations

import asyncio
from datetime import date

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("ledger.tasks")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(name="aatp.ledger.tasks.generate_recurring_costs")
def generate_recurring_costs_task():
    """Generate monthly recurring costs for all open positions."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.ledger.cost_service import generate_recurring_costs

            count = await generate_recurring_costs(session)
            await session.commit()
            return {"generated": count}

    result = _run_async(_run())
    logger.info("recurring_costs_task_complete", **result)
    return result


@app.task(name="aatp.ledger.tasks.daily_portfolio_snapshot")
def daily_portfolio_snapshot(snapshot_date_str: str | None = None):
    """Generate daily portfolio snapshot."""

    async def _run():
        async with async_session_factory() as session:
            from aatp.ledger.snapshot import generate_daily_snapshot

            snap_date = (
                date.fromisoformat(snapshot_date_str)
                if snapshot_date_str
                else date.today()
            )
            snapshot = await generate_daily_snapshot(session, snap_date)
            await session.commit()
            return {
                "snapshot_date": str(snapshot.snapshot_date),
                "open_positions": snapshot.open_positions_count,
                "total_market_value_usd": str(snapshot.total_market_value_usd),
            }

    result = _run_async(_run())
    logger.info("daily_snapshot_task_complete", **result)
    return result
