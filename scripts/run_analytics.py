"""Run the full AATP analytics pipeline on scraped transaction data.

Pipeline order:
1. Normalisation — adjust raw prices for mileage, colour, options, geography, provenance, condition
2. Valuation — compute fair values per model from comparable transactions
3. Signals — generate opportunity signals (momentum, spread, catalyst, volume, comparable, pattern)
4. Consensus — run 6-model consensus engine and classify actionable/watchlist/passed
"""

import asyncio
import json
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from aatp.core.config import settings
from aatp.db.models import Transaction


async def run_pipeline():
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 60)
    print("AATP Analytics Pipeline")
    print("=" * 60)

    # 1. Normalisation
    print("\n[1/4] Normalising transactions...")
    async with session_factory() as session:
        from aatp.collectors.normalisation import NormalisationPipeline

        result = await session.execute(
            select(Transaction).where(Transaction.normalised_price_usd.is_(None))
        )
        pending = list(result.scalars().all())
        print(f"  Found {len(pending)} un-normalised transactions")

        if pending:
            pipeline = NormalisationPipeline(session)
            count = await pipeline.normalise_batch(pending)
            await session.commit()
            print(f"  Normalised {count} transactions")
        else:
            print("  All transactions already normalised")

    # 2. Valuation
    print("\n[2/4] Computing fair values...")
    async with session_factory() as session:
        from aatp.valuation.engine import ValuationEngine

        ve = ValuationEngine(session, min_comparables=2)
        result = await ve.value_all_models()
        await session.commit()
        print(f"  {json.dumps(result, indent=2, default=str)}")

    # 3. Signals
    print("\n[3/4] Generating signals...")
    async with session_factory() as session:
        from aatp.signals.scanner import OpportunityScanner

        scanner = OpportunityScanner(session)
        result = await scanner.scan_all()
        print(f"  Models scanned: {result.models_scanned}")
        print(f"  Signals generated: {result.signals_generated}")
        print(f"  Actionable: {result.actionable_count}")
        print(f"  Watchlist: {result.watchlist_count}")
        print(f"  Errors: {result.errors}")

    # 4. Consensus
    print("\n[4/4] Running consensus engine...")
    async with session_factory() as session:
        from aatp.consensus.engine import run_all_models

        result = await run_all_models(session)
        print(f"  {json.dumps(result, indent=2, default=str)}")

    await engine.dispose()
    print("\n" + "=" * 60)
    print("Pipeline complete.")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
