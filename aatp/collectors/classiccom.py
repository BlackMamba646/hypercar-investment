"""Classic.com scraper.

Auction results aggregator — collects results from multiple auction houses.
Useful for filling gaps and cross-referencing prices. Uses Playwright since
the site blocks non-browser requests.

Structure:
- Search: classic.com/s/?q=<query>
- Model page: classic.com/m/<make>/<model>/
- Listing: classic.com/l/<listing-id>/
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bs4 import BeautifulSoup

from aatp.collectors.playwright_base import PlaywrightScraper
from aatp.collectors.base import ScrapedItem
from aatp.collectors.model_matcher import AssetModelMatcher
from aatp.core.logging import get_logger
from aatp.db.models import Transaction, TransactionSource, TransactionType

logger = get_logger("collectors.classiccom")

CLASSIC_BASE = "https://www.classic.com"

TARGET_SEARCH_TERMS = [
    "ferrari+812+superfast", "ferrari+812+gts",
    "ferrari+488+pista", "ferrari+laferrari",
    "ferrari+f40", "ferrari+f50", "ferrari+458+speciale",
    "ferrari+sf90", "ferrari+296+gtb",
    "bugatti+chiron", "bugatti+veyron",
    "mclaren+senna", "mclaren+speedtail",
    "lamborghini+aventador+svj", "porsche+918+spyder",
    "ferrari+812+competizione", "ferrari+monza+sp",
]


class ClassicComScraper(PlaywrightScraper):
    source = TransactionSource.CLASSIC_COM
    scraper_name = "classic_com_results"
    scraper_version = "0.2.0"

    def __init__(self, session, search_terms: list[str] | None = None):
        super().__init__(session)
        self._search_terms = search_terms or TARGET_SEARCH_TERMS
        self._matcher = AssetModelMatcher(session)

    async def discover_urls(self) -> list[str]:
        listing_urls: list[str] = []
        seen_ids: set[str] = set()

        for term in self._search_terms:
            search_url = f"{CLASSIC_BASE}/s/?q={term}"
            try:
                html = await self._fetch_rendered(search_url, wait_selector="a[href*='/l/']")
                urls = self._extract_listing_urls(html)
                for url in urls:
                    lid = url.rstrip("/").split("/")[-1]
                    if lid not in seen_ids:
                        seen_ids.add(lid)
                        listing_urls.append(url)
            except Exception as e:
                self._record_error(e, {"search_term": term})

        logger.info("classic_urls_discovered", count=len(listing_urls))
        return listing_urls

    def _extract_listing_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/l/" in href or "/listing/" in href:
                full_url = href if href.startswith("http") else f"{CLASSIC_BASE}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    async def run(self, urls: list[str] | None = None) -> dict:
        run = await self._start_run()
        self._items_collected = 0
        self._items_parsed = 0
        self._errors = []
        try:
            if urls is None:
                urls = await self.discover_urls()
            logger.info("urls_discovered", scraper=self.scraper_name, count=len(urls))
            all_items: list[ScrapedItem] = []
            for url in urls:
                try:
                    html = await self._fetch_rendered(url, wait_selector="h1")
                    self._items_collected += 1
                    items = await self.parse_page(url, html)
                    self._items_parsed += len(items)
                    all_items.extend(items)
                except Exception as e:
                    self._record_error(e, {"url": url})
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
            await self._close_browser()

    async def parse_page(self, url: str, html: str) -> list[ScrapedItem]:
        try:
            data = self._parse_listing(url, html)
            if data is None:
                return []
            return [ScrapedItem(
                source_url=url,
                raw_html=html,
                parsed_data=data,
                external_id=data.get("listing_id"),
            )]
        except Exception as e:
            self._record_error(e, {"url": url, "phase": "parse"})
            return []

    def _parse_listing(self, url: str, html: str) -> dict | None:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.find("h1")
        if title_el is None:
            return None
        title = title_el.get_text(strip=True)

        listing_id = url.rstrip("/").split("/")[-1]
        data: dict = {"title": title, "url": url, "listing_id": listing_id}

        year_match = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', title)
        if year_match:
            data["year"] = int(year_match.group(1))

        sold, price, currency = self._extract_result(soup)
        data["sold"] = sold
        if price is not None:
            data["hammer_price"] = str(price)
            data["currency"] = currency

        data.update(self._extract_sale_info(soup))
        data["mileage"] = self._extract_mileage(soup)

        vin = self._extract_vin(soup)
        if vin:
            data["vin"] = vin

        return data

    def _extract_result(self, soup: BeautifulSoup) -> tuple[bool | None, Decimal | None, str]:
        page_text = soup.get_text()

        for pattern in [
            re.compile(r'Sold\s+(?:for\s+)?\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Hammer\s+Price[:\s]*\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Result[:\s]*\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Price[:\s]*\$([0-9,]+)', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                price_str = match.group(1).replace(",", "")
                return True, Decimal(price_str), "USD"

        for pattern in [
            re.compile(r'Sold\s+(?:for\s+)?€([0-9,]+)', re.IGNORECASE),
            re.compile(r'Result[:\s]*€([0-9,]+)', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                price_str = match.group(1).replace(",", "")
                return True, Decimal(price_str), "EUR"

        for pattern in [
            re.compile(r'Sold\s+(?:for\s+)?£([0-9,]+)', re.IGNORECASE),
            re.compile(r'Result[:\s]*£([0-9,]+)', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                price_str = match.group(1).replace(",", "")
                return True, Decimal(price_str), "GBP"

        if re.search(r'\b(not\s+sold|bid\s+to|withdrawn)\b', page_text, re.IGNORECASE):
            bid_match = re.search(r'[\$€£]([0-9,]+)', page_text)
            if bid_match:
                return False, Decimal(bid_match.group(1).replace(",", "")), "USD"
            return False, None, "USD"

        return None, None, "USD"

    def _extract_sale_info(self, soup: BeautifulSoup) -> dict:
        result: dict = {}
        page_text = soup.get_text()

        house_patterns = [
            re.compile(r'(?:Auction\s+House|Sold\s+(?:at|by)|Source)[:\s]+([^\n]+)', re.IGNORECASE),
            re.compile(r'(RM\s+Sotheby|Bonhams|Gooding|Mecum|Barrett[\s-]Jackson|Artcurial)', re.IGNORECASE),
        ]
        for pattern in house_patterns:
            match = pattern.search(page_text)
            if match:
                result["source_auction_house"] = match.group(1).strip()[:200]
                break

        date_match = re.search(r'(\w+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+\w+\s+\d{4})', page_text[:3000])
        if date_match:
            result["sale_date"] = date_match.group(1)

        loc_match = re.search(r'(?:Location|Venue)[:\s]+([^\n]+)', page_text, re.IGNORECASE)
        if loc_match:
            result["sale_location"] = loc_match.group(1).strip()[:200]

        return result

    def _extract_mileage(self, soup: BeautifulSoup) -> int | None:
        page_text = soup.get_text()
        for pattern in [
            re.compile(r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|mi)\b', re.IGNORECASE),
            re.compile(r'(\d{1,3}(?:,\d{3})*)\s*(?:kilometers|km)\b', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                return int(match.group(1).replace(",", ""))
        return None

    def _extract_vin(self, soup: BeautifulSoup) -> str | None:
        page_text = soup.get_text()
        vin_match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', page_text)
        if vin_match:
            return vin_match.group(1)
        return None

    async def store_items(self, items: list[ScrapedItem]) -> int:
        stored = 0
        for item in items:
            data = item.parsed_data
            ext_id = data.get("listing_id")

            if ext_id and await self.check_for_duplicate(ext_id):
                continue

            match = await self._matcher.match(data.get("title", ""))
            if match is None:
                continue

            provenance = await self._create_provenance(item)

            sold = data.get("sold")
            if sold is True:
                tx_type = TransactionType.AUCTION_SOLD
            elif sold is False:
                tx_type = TransactionType.AUCTION_NOT_SOLD
            else:
                continue

            hammer_price = Decimal(data["hammer_price"]) if data.get("hammer_price") else None
            currency = data.get("currency", "USD")

            tx_date = date.today()
            if data.get("sale_date"):
                from aatp.collectors.bat import _parse_date_flexible
                parsed = _parse_date_flexible(data["sale_date"])
                if parsed:
                    tx_date = parsed

            transaction = Transaction(
                provenance_id=provenance.id,
                asset_model_id=match.asset_model_id,
                source=self.source,
                external_id=ext_id,
                transaction_type=tx_type,
                transaction_date=tx_date,
                hammer_price=hammer_price,
                total_price=hammer_price,
                currency=currency,
                total_price_usd=hammer_price if currency == "USD" else None,
                year=data.get("year"),
                mileage=data.get("mileage"),
                mileage_unit="miles",
                vin=data.get("vin"),
                sale_region=data.get("sale_location"),
                auction_house=data.get("source_auction_house", "Classic.com"),
                lot_description=data.get("title"),
                metadata_={
                    "match_confidence": match.confidence,
                    "match_method": match.match_method,
                    "aggregator": "classic.com",
                },
            )
            self.db.add(transaction)
            stored += 1

        if stored:
            await self.db.flush()
        return stored
