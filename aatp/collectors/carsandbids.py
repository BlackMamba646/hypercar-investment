"""Cars & Bids scraper.

Online auction platform for modern enthusiast cars. Similar format to BaT
with daily rolling auctions. Uses Playwright — search results render via JS.

Structure:
- Past auctions: carsandbids.com/past-auctions/
- Search: carsandbids.com/search?q=<query>
- Listing: carsandbids.com/auctions/<id>/<slug>
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

logger = get_logger("collectors.carsandbids")

CAB_BASE = "https://carsandbids.com"

TARGET_SEARCH_TERMS = [
    "ferrari+812", "ferrari+488+pista", "ferrari+laferrari",
    "ferrari+f40", "ferrari+f50", "ferrari+458+speciale",
    "ferrari+sf90", "ferrari+296", "bugatti+chiron",
    "bugatti+veyron", "mclaren+senna", "mclaren+speedtail",
    "lamborghini+aventador+svj", "porsche+918",
    "ferrari+812+competizione", "ferrari+monza",
]


class CarsAndBidsScraper(PlaywrightScraper):
    source = TransactionSource.CARS_AND_BIDS
    scraper_name = "cars_and_bids_auctions"
    scraper_version = "0.2.0"

    def __init__(self, session, search_terms: list[str] | None = None):
        super().__init__(session)
        self._search_terms = search_terms or TARGET_SEARCH_TERMS
        self._matcher = AssetModelMatcher(session)

    async def discover_urls(self) -> list[str]:
        listing_urls: list[str] = []
        seen_slugs: set[str] = set()

        for term in self._search_terms:
            search_url = f"{CAB_BASE}/search?q={term}"
            try:
                html = await self._fetch_rendered(search_url, wait_selector="a[href*='/auctions/']")
                urls = self._extract_listing_urls(html)
                for url in urls:
                    slug = url.rstrip("/").split("/")[-1]
                    if slug not in seen_slugs:
                        seen_slugs.add(slug)
                        listing_urls.append(url)
            except Exception as e:
                self._record_error(e, {"search_term": term})

        logger.info("cab_urls_discovered", count=len(listing_urls))
        return listing_urls

    def _extract_listing_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/auctions/" in href and href != "/auctions/":
                clean = href.split("?")[0]
                full_url = clean if clean.startswith("http") else f"{CAB_BASE}{clean}"
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
                external_id=data.get("slug"),
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

        slug = url.rstrip("/").split("/")[-1]
        data: dict = {"title": title, "url": url, "slug": slug}

        year_match = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', title)
        if year_match:
            data["year"] = int(year_match.group(1))

        sold, price, currency = self._extract_result(soup)
        data["sold"] = sold
        if price is not None:
            data["hammer_price"] = str(price)
            data["currency"] = currency

        data["auction_end_date"] = self._extract_end_date(soup)
        data["mileage"] = self._extract_mileage(soup, title)
        data["seller_location"] = self._extract_location(soup)

        colours = self._extract_colours(soup)
        data.update(colours)

        vin = self._extract_vin(soup)
        if vin:
            data["vin"] = vin

        return data

    def _extract_result(self, soup: BeautifulSoup) -> tuple[bool | None, Decimal | None, str]:
        page_text = soup.get_text()
        sold_patterns = [
            re.compile(r'Sold\s+(?:for\s+)?\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Winning\s+Bid[:\s]+\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Final\s+Bid[:\s]+\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Bid\s+to\s+\$([0-9,]+)', re.IGNORECASE),
        ]
        for pattern in sold_patterns:
            match = pattern.search(page_text)
            if match:
                price_str = match.group(1).replace(",", "")
                sold = "sold" in match.group(0).lower() or "winning" in match.group(0).lower()
                return sold, Decimal(price_str), "USD"

        if re.search(r'\b(not\s+sold|reserve\s+not\s+met|no\s+sale)\b', page_text, re.IGNORECASE):
            bid_match = re.search(r'\$([0-9,]+)', page_text)
            if bid_match:
                return False, Decimal(bid_match.group(1).replace(",", "")), "USD"
            return False, None, "USD"

        return None, None, "USD"

    def _extract_end_date(self, soup: BeautifulSoup) -> str | None:
        time_el = soup.find("time")
        if time_el and time_el.get("datetime"):
            return time_el["datetime"]
        page_text = soup.get_text()
        date_match = re.search(r'(\w+\s+\d{1,2},?\s+\d{4})', page_text[:3000])
        return date_match.group(1) if date_match else None

    def _extract_mileage(self, soup: BeautifulSoup, title: str) -> int | None:
        page_text = soup.get_text()
        for pattern in [
            re.compile(r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|mi)\b', re.IGNORECASE),
            re.compile(r'(\d{1,3}(?:,\d{3})*)\s*(?:kilometers|km)\b', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                return int(match.group(1).replace(",", ""))
        title_match = re.search(r'(\d{1,3}(?:,\d{3})*)[- ](?:mile|km)', title, re.IGNORECASE)
        return int(title_match.group(1).replace(",", "")) if title_match else None

    def _extract_location(self, soup: BeautifulSoup) -> str | None:
        page_text = soup.get_text()
        loc_match = re.search(
            r'(?:located|seller)\s+(?:in\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})',
            page_text
        )
        return loc_match.group(1) if loc_match else None

    def _extract_colours(self, soup: BeautifulSoup) -> dict:
        colours: dict = {}
        page_text = soup.get_text()
        ext_match = re.search(
            r'(?:Exterior\s+Color|finished\s+in|painted)\s*[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})',
            page_text, re.IGNORECASE
        )
        if ext_match:
            colours["colour_exterior"] = ext_match.group(1).strip()
        int_match = re.search(
            r'(?:Interior\s+Color|interior\s+(?:is\s+)?(?:in\s+)?)\s*[:\s]+([A-Z][a-z]+(?:\s+[A-Za-z]+){0,3})',
            page_text, re.IGNORECASE
        )
        if int_match:
            colours["colour_interior"] = int_match.group(1).strip()
        return colours

    def _extract_vin(self, soup: BeautifulSoup) -> str | None:
        page_text = soup.get_text()
        vin_match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', page_text)
        if vin_match:
            return vin_match.group(1)
        chassis_match = re.search(r'(?:VIN|chassis)[:\s#]*\s*([A-Za-z0-9]{6,17})', page_text, re.IGNORECASE)
        return chassis_match.group(1) if chassis_match else None

    async def store_items(self, items: list[ScrapedItem]) -> int:
        stored = 0
        for item in items:
            data = item.parsed_data
            ext_id = data.get("slug")

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

            tx_date = date.today()
            if data.get("auction_end_date"):
                from aatp.collectors.bat import _parse_date_flexible
                parsed = _parse_date_flexible(data["auction_end_date"])
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
                buyer_premium=_compute_cab_premium(hammer_price),
                total_price=_compute_cab_total(hammer_price),
                currency=data.get("currency", "USD"),
                total_price_usd=_compute_cab_total(hammer_price),
                year=data.get("year"),
                mileage=data.get("mileage"),
                mileage_unit="miles",
                colour_exterior=data.get("colour_exterior"),
                colour_interior=data.get("colour_interior"),
                vin=data.get("vin"),
                sale_country="US",
                sale_region=data.get("seller_location"),
                auction_house="Cars & Bids",
                lot_description=data.get("title"),
                metadata_={
                    "match_confidence": match.confidence,
                    "match_method": match.match_method,
                },
            )
            self.db.add(transaction)
            stored += 1

        if stored:
            await self.db.flush()
        return stored


def _compute_cab_premium(hammer: Decimal | None) -> Decimal | None:
    """Cars & Bids charges 4.5% buyer's premium."""
    if hammer is None:
        return None
    return hammer * Decimal("0.045")


def _compute_cab_total(hammer: Decimal | None) -> Decimal | None:
    if hammer is None:
        return None
    return hammer + _compute_cab_premium(hammer)
