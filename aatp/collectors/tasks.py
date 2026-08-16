"""
Celery tasks for data collection and normalisation.

Each task creates its own database session and runs the appropriate
scraper or pipeline. Results are logged to scraper_runs.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("collectors.tasks")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="aatp.collectors.tasks.run_bat_scraper", max_retries=2)
def run_bat_scraper(self):
    """Run Bring a Trailer scraper."""
    async def _run():
        async with async_session_factory() as session:
            from aatp.collectors.bat import BringATrailerScraper
            scraper = BringATrailerScraper(session)
            result = await scraper.run()
            logger.info("bat_scraper_complete", **result)
            return result

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("bat_scraper_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)


@app.task(bind=True, name="aatp.collectors.tasks.run_rm_scraper", max_retries=2)
def run_rm_scraper(self):
    """Run RM Sotheby's scraper."""
    async def _run():
        async with async_session_factory() as session:
            from aatp.collectors.rmsothebys import RMSothebysScraper
            scraper = RMSothebysScraper(session)
            result = await scraper.run()
            logger.info("rm_scraper_complete", **result)
            return result

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("rm_scraper_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=600)


@app.task(name="aatp.collectors.tasks.normalise_pending_transactions")
def normalise_pending_transactions():
    """Find and normalise all transactions that haven't been normalised yet."""
    async def _run():
        async with async_session_factory() as session:
            from aatp.collectors.normalisation import NormalisationPipeline
            from aatp.db.models import Transaction

            result = await session.execute(
                select(Transaction).where(Transaction.normalised_price_usd.is_(None)).limit(500)
            )
            transactions = list(result.scalars().all())

            if not transactions:
                logger.info("no_transactions_to_normalise")
                return {"normalised": 0}

            pipeline = NormalisationPipeline(session)
            count = await pipeline.normalise_batch(transactions)
            await session.commit()

            logger.info("normalisation_complete", total=len(transactions), normalised=count)
            return {"total": len(transactions), "normalised": count}

    return _run_async(_run())


@app.task(name="aatp.collectors.tasks.run_scraper_by_name")
def run_scraper_by_name(scraper_name: str, **kwargs):
    """Run any scraper by name — for ad-hoc invocation."""
    scrapers = {
        "bat": "aatp.collectors.bat.BringATrailerScraper",
        "rm_sothebys": "aatp.collectors.rmsothebys.RMSothebysScraper",
    }

    if scraper_name not in scrapers:
        raise ValueError(f"Unknown scraper: {scraper_name}. Available: {list(scrapers.keys())}")

    async def _run():
        module_path, class_name = scrapers[scraper_name].rsplit(".", 1)
        import importlib
        module = importlib.import_module(module_path)
        scraper_cls = getattr(module, class_name)

        async with async_session_factory() as session:
            scraper = scraper_cls(session, **kwargs)
            return await scraper.run()

    return _run_async(_run())
