"""API endpoint to trigger the data collection + analytics pipeline."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from aatp.core.config import settings
from aatp.core.logging import get_logger
from aatp.db.models import Transaction

logger = get_logger("api.pipeline")

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_running = False


async def _run_pipeline():
    global _running
    if _running:
        return
    _running = True

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        logger.info("pipeline_starting")

        # 1. BaT scraper (httpx — no Playwright needed)
        logger.info("pipeline_step", step="scraping", scraper="BringATrailer")
        async with session_factory() as session:
            from aatp.collectors.bat import BringATrailerScraper

            scraper = BringATrailerScraper(session)
            result = await scraper.run()
            logger.info("pipeline_scrape_done", result=json.dumps(result, default=str))

        # 2. Normalisation
        logger.info("pipeline_step", step="normalisation")
        async with session_factory() as session:
            from aatp.collectors.normalisation import NormalisationPipeline

            pending_result = await session.execute(
                select(Transaction).where(Transaction.normalised_price_usd.is_(None))
            )
            pending = list(pending_result.scalars().all())
            if pending:
                pipeline = NormalisationPipeline(session)
                count = await pipeline.normalise_batch(pending)
                await session.commit()
                logger.info("pipeline_normalised", count=count)

        # 3. Valuation
        logger.info("pipeline_step", step="valuation")
        async with session_factory() as session:
            from aatp.valuation.engine import ValuationEngine

            ve = ValuationEngine(session, min_comparables=2)
            await ve.value_all_models()
            await session.commit()

        # 4. Signals
        logger.info("pipeline_step", step="signals")
        async with session_factory() as session:
            from aatp.signals.scanner import OpportunityScanner

            scanner = OpportunityScanner(session)
            await scanner.scan_all()

        # 5. Consensus
        logger.info("pipeline_step", step="consensus")
        async with session_factory() as session:
            from aatp.consensus.engine import run_all_models

            await run_all_models(session)

        logger.info("pipeline_complete")
    except Exception:
        logger.exception("pipeline_error")
    finally:
        await engine.dispose()
        _running = False


@router.post("/run")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    if _running:
        return {"status": "already_running"}
    background_tasks.add_task(_run_pipeline)
    return {"status": "started", "message": "BaT scraper + analytics pipeline running in background. Refresh the dashboard in ~2 minutes."}


@router.get("/status")
async def pipeline_status():
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        tx_count = (await session.execute(select(func.count(Transaction.id)))).scalar() or 0

    await engine.dispose()
    return {
        "running": _running,
        "transactions": tx_count,
    }
