from __future__ import annotations

import asyncio
from datetime import date

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("valuation.tasks")


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="aatp.valuation.tasks.run_valuation", max_retries=2)
def run_valuation(self, valuation_date_str: str | None = None):
    async def _run():
        async with async_session_factory() as session:
            from aatp.valuation.engine import ValuationEngine

            valuation_date = (
                date.fromisoformat(valuation_date_str)
                if valuation_date_str
                else date.today()
            )
            engine = ValuationEngine(session)
            result = await engine.value_all_models(valuation_date)
            await session.commit()

            logger.info("valuation_run_complete", **result)
            return result

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("valuation_run_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)


@app.task(name="aatp.valuation.tasks.value_single_model")
def value_single_model(asset_model_id: str, valuation_date_str: str | None = None):
    import uuid

    async def _run():
        async with async_session_factory() as session:
            from aatp.valuation.engine import ValuationEngine

            valuation_date = (
                date.fromisoformat(valuation_date_str)
                if valuation_date_str
                else date.today()
            )
            engine = ValuationEngine(session)
            fv = await engine.value_model(
                uuid.UUID(asset_model_id), valuation_date
            )
            await session.commit()

            if fv:
                logger.info(
                    "single_valuation_complete",
                    asset_model_id=asset_model_id,
                    mid=str(fv.fair_value_mid),
                )
                return {
                    "asset_model_id": asset_model_id,
                    "fair_value_mid": str(fv.fair_value_mid),
                    "confidence": str(fv.confidence_score),
                }
            return {"asset_model_id": asset_model_id, "result": "skipped"}

    return _run_async(_run())
