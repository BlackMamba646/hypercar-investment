"""
Base scraper framework.

Every scraper inherits from BaseScraper and gets:
- Async httpx client with configurable rate limiting
- Retry logic via tenacity (exponential backoff)
- Raw HTML storage alongside parsed data
- DataProvenance record creation for every collected item
- ScraperRun lifecycle logging
- Structured logging throughout
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from aatp.core.config import settings
from aatp.core.logging import get_logger
from aatp.db.models import DataProvenance, ScraperRun, TransactionSource

logger = get_logger("collectors.base")

RAW_HTML_DIR = Path("raw_html")


@dataclass
class ScrapedItem:
    """A single item collected by a scraper before normalisation."""
    source_url: str
    raw_html: str
    parsed_data: dict[str, Any]
    external_id: str | None = None
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RateLimiter:
    """Token-bucket rate limiter for HTTP requests."""

    def __init__(self, requests_per_second: float = 0.5):
        self._delay = 1.0 / requests_per_second
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait_time = self._delay - (now - self._last_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_request = asyncio.get_event_loop().time()


class BaseScraper(ABC):
    """Abstract base for all data collectors."""

    source: TransactionSource
    scraper_name: str
    scraper_version: str = "0.1.0"

    def __init__(self, session: AsyncSession):
        self.db = session
        self._rate_limiter = RateLimiter(
            requests_per_second=1.0 / settings.scraper_request_delay_seconds
        )
        self._client: httpx.AsyncClient | None = None
        self._run_id: uuid.UUID | None = None
        self._items_collected = 0
        self._items_parsed = 0
        self._errors: list[dict[str, Any]] = []

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _fetch(self, url: str) -> httpx.Response:
        """Fetch a URL with rate limiting and retry logic."""
        await self._rate_limiter.acquire()
        client = await self._get_client()
        logger.debug("fetching", url=url, scraper=self.scraper_name)
        response = await client.get(url)
        response.raise_for_status()
        return response

    def _store_raw_html(self, item: ScrapedItem) -> str | None:
        """Store raw HTML to disk, return the file path."""
        source_dir = RAW_HTML_DIR / self.source.value
        source_dir.mkdir(parents=True, exist_ok=True)

        content_hash = hashlib.sha256(item.raw_html.encode()).hexdigest()
        date_prefix = item.collected_at.strftime("%Y%m%d")
        ext_id = item.external_id or content_hash[:12]
        filename = f"{date_prefix}_{ext_id}_{content_hash[:8]}.html"
        filepath = source_dir / filename

        filepath.write_text(item.raw_html, encoding="utf-8")
        return str(filepath)

    async def _create_provenance(self, item: ScrapedItem) -> DataProvenance:
        """Create a DataProvenance record for a collected item."""
        content_hash = hashlib.sha256(item.raw_html.encode()).hexdigest()
        html_path = self._store_raw_html(item)

        provenance = DataProvenance(
            source=self.source,
            source_url=item.source_url,
            collected_at=item.collected_at,
            raw_content_hash=content_hash,
            raw_html_path=html_path,
            parsed_content=item.parsed_data,
            scraper_version=self.scraper_version,
            is_valid=True,
        )
        self.db.add(provenance)
        await self.db.flush()
        return provenance

    async def _start_run(self) -> ScraperRun:
        """Log the start of a scraper run."""
        run = ScraperRun(
            scraper_name=self.scraper_name,
            source=self.source,
            status="running",
            config_used={
                "delay_seconds": settings.scraper_request_delay_seconds,
                "max_concurrent": settings.scraper_max_concurrent_requests,
                "version": self.scraper_version,
            },
        )
        self.db.add(run)
        await self.db.flush()
        self._run_id = run.id
        logger.info("scraper_run_started", scraper=self.scraper_name, run_id=str(run.id))
        return run

    async def _finish_run(self, run: ScraperRun, status: str = "completed") -> None:
        """Log the completion of a scraper run."""
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.items_collected = self._items_collected
        run.items_parsed = self._items_parsed
        run.errors = self._errors if self._errors else None
        await self.db.flush()
        logger.info(
            "scraper_run_finished",
            scraper=self.scraper_name,
            run_id=str(run.id),
            status=status,
            items_collected=self._items_collected,
            items_parsed=self._items_parsed,
            errors=len(self._errors),
        )

    def _record_error(self, error: Exception, context: dict[str, Any] | None = None) -> None:
        """Record an error during scraping."""
        err = {
            "type": type(error).__name__,
            "message": str(error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if context:
            err["context"] = context
        self._errors.append(err)
        logger.error("scraper_error", scraper=self.scraper_name, error=str(error), **({} if context is None else context))

    @abstractmethod
    async def discover_urls(self) -> list[str]:
        """Return URLs to scrape. Subclasses implement discovery logic."""
        ...

    @abstractmethod
    async def parse_page(self, url: str, html: str) -> list[ScrapedItem]:
        """Parse a fetched page into ScrapedItems. Subclasses implement parsing."""
        ...

    @abstractmethod
    async def store_items(self, items: list[ScrapedItem]) -> int:
        """Store parsed items to the database. Returns count of new items stored."""
        ...

    async def run(self, urls: list[str] | None = None) -> dict[str, Any]:
        """Execute a full scraper run."""
        run = await self._start_run()
        self._items_collected = 0
        self._items_parsed = 0
        self._errors = []

        try:
            if urls is None:
                urls = await self.discover_urls()

            logger.info("urls_discovered", scraper=self.scraper_name, count=len(urls))

            semaphore = asyncio.Semaphore(settings.scraper_max_concurrent_requests)

            async def process_url(url: str) -> list[ScrapedItem]:
                async with semaphore:
                    try:
                        response = await self._fetch(url)
                        self._items_collected += 1
                        items = await self.parse_page(url, response.text)
                        self._items_parsed += len(items)
                        return items
                    except Exception as e:
                        self._record_error(e, {"url": url})
                        return []

            all_items: list[ScrapedItem] = []
            tasks = [process_url(url) for url in urls]
            results = await asyncio.gather(*tasks)
            for batch in results:
                all_items.extend(batch)

            stored = await self.store_items(all_items)
            await self.db.commit()
            await self._finish_run(run, "completed")

            return {
                "run_id": str(run.id),
                "urls_processed": len(urls),
                "items_collected": self._items_collected,
                "items_parsed": self._items_parsed,
                "items_stored": stored,
                "errors": len(self._errors),
            }

        except Exception as e:
            self._record_error(e, {"phase": "run"})
            await self._finish_run(run, "failed")
            raise

        finally:
            if self._client and not self._client.is_closed:
                await self._client.aclose()

    async def check_for_duplicate(self, external_id: str) -> bool:
        """Check if we already have this item by external_id."""
        from aatp.db.models import Transaction
        result = await self.db.execute(
            select(Transaction.id).where(
                Transaction.source == self.source,
                Transaction.external_id == external_id,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None
