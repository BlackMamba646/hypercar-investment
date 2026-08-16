"""Run all AATP scrapers directly (no Celery required)."""

import asyncio
import json
import sys

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from aatp.core.config import settings
from aatp.collectors.bat import BringATrailerScraper
from aatp.collectors.rmsothebys import RMSothebysScraper
from aatp.collectors.carsandbids import CarsAndBidsScraper
from aatp.collectors.bonhams import BonhamsScraper
from aatp.collectors.collectingcars import CollectingCarsScraper
from aatp.collectors.classiccom import ClassicComScraper


SCRAPERS = [
    ("Bring a Trailer", BringATrailerScraper),
    ("RM Sotheby's (Playwright)", RMSothebysScraper),
    ("Cars & Bids", CarsAndBidsScraper),
    ("Bonhams", BonhamsScraper),
    ("Collecting Cars (Playwright)", CollectingCarsScraper),
    ("Classic.com", ClassicComScraper),
]


async def run_all():
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 60)
    print("AATP Data Collection — Live Scraping")
    print("=" * 60)

    total = len(SCRAPERS)
    for i, (name, scraper_cls) in enumerate(SCRAPERS, 1):
        print(f"\n[{i}/{total}] {name} scraper starting...")
        async with session_factory() as session:
            scraper = scraper_cls(session)
            try:
                result = await scraper.run()
                print(f"  {name} complete: {json.dumps(result, indent=2, default=str)}")
            except Exception as e:
                print(f"  {name} error: {e}", file=sys.stderr)

    await engine.dispose()
    print("\n" + "=" * 60)
    print("Scraping complete.")


if __name__ == "__main__":
    asyncio.run(run_all())
