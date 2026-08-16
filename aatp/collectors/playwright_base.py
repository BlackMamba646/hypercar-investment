"""Playwright-based scraper for JS-rendered pages.

Some auction sites (RM Sotheby's, Collecting Cars) rely heavily on client-side
JavaScript rendering. This module provides a Playwright-aware fetch method that
renders pages in headless Chromium before returning HTML.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright, Browser, BrowserContext

from aatp.collectors.base import BaseScraper
from aatp.core.logging import get_logger

logger = get_logger("collectors.playwright_base")


class PlaywrightScraper(BaseScraper):
    """BaseScraper subclass that fetches pages via headless Chromium."""

    _browser: Browser | None = None
    _context: BrowserContext | None = None
    _pw = None

    async def _ensure_browser(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        return self._context

    async def _fetch_rendered(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch a URL using Playwright, wait for JS to render, return HTML."""
        await self._rate_limiter.acquire()
        ctx = await self._ensure_browser()
        page = await ctx.new_page()
        try:
            logger.debug("playwright_fetch", url=url, scraper=self.scraper_name)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=8000)
                except Exception:
                    pass
            else:
                await page.wait_for_timeout(3000)
            html = await page.content()
            return html
        finally:
            await page.close()

    async def _close_browser(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    async def run(self, urls: list[str] | None = None) -> dict:
        try:
            return await super().run(urls)
        finally:
            await self._close_browser()
