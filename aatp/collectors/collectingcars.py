"""Collecting Cars scraper.

Online auction platform for collector cars, primarily UK/EU-based. Uses
Playwright for JS rendering since the site relies on client-side React.

Structure:
- Past auctions: collectingcars.com/past-auctions/
- Search: collectingcars.com/search?q=<query>
- Listing: collectingcars.com/cars/<slug>/
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

logger = get_logger("collectors.collectingcars")

CC_BASE = "https://collectingcars.com"

TARGET_SEARCH_TERMS = [
    "ferrari+812", "ferrari+488+pista", "ferrari+laferrari",
    "ferrari+f40", "ferrari+f50", "ferrari+458+speciale",
    "ferrari+sf90", "ferrari+296", "bugatti+chiron",
    "bugatti+veyron", "mclaren+senna", "mclaren+speedtail",
    "lamborghini+aventador+svj", "porsche+918",
    "ferrari+812+competizione", "ferrari+monza",
]


class CollectingCarsScraper(PlaywrightScraper):
    source = TransactionSource.COLLECTING_CARS
    scraper_name = "collecting_cars_auctions"
    scraper_version = "0.1.0"

    def __init__(self, session, search_terms: list[str] | None = None):
        super().__init__(session)
        self._search_terms = search_terms or TARGET_SEARCH_TERMS
        self._matcher = AssetModelMatcher(session)

    async def discover_urls(self) -> list[str]:
        listing_urls: list[str] = []
        seen_slugs: set[str] = set()

        for term in self._search_terms:
            search_url = f"{CC_BASE}/search?q={term}"
            try:
                html = await self._fetch_rendered(search_url, wait_selector="a[href*='/cars/']")
                urls = self._extract_listing_urls(html)
                for url in urls:
                    slug = url.rstrip("/").split("/")[-1]
                    if slug not in seen_slugs:
                        seen_slugs.add(slug)
                        listing_urls.append(url)
            except Exception as e:
                self._record_error(e, {"search_term": term})

        logger.info("cc_urls_discovered", count=len(listing_urls))
        return listing_urls

    def _extract_listing_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/cars/" in href and href != "/cars/":
                full_url = href if href.startswith("http") else f"{CC_BASE}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

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

        data["mileage"] = self._extract_mileage(soup, title)

        vin = self._extract_vin(soup)
        if vin:
            data["vin"] = vin

        data.update(self._extract_location_info(soup))

        return data

    def _extract_result(self, soup: BeautifulSoup) -> tuple[bool | None, Decimal | None, str]:
        page_text = soup.get_text()

        for pattern, currency_default in [
            (re.compile(r'Sold\s+(?:for\s+)?£([0-9,]+)', re.IGNORECASE), "GBP"),
            (re.compile(r'Sold\s+(?:for\s+)?€([0-9,]+)', re.IGNORECASE), "EUR"),
            (re.compile(r'Sold\s+(?:for\s+)?\$([0-9,]+)', re.IGNORECASE), "USD"),
            (re.compile(r'Winning\s+Bid[:\s]+£([0-9,]+)', re.IGNORECASE), "GBP"),
            (re.compile(r'Winning\s+Bid[:\s]+€([0-9,]+)', re.IGNORECASE), "EUR"),
            (re.compile(r'Winning\s+Bid[:\s]+\$([0-9,]+)', re.IGNORECASE), "USD"),
            (re.compile(r'Final\s+(?:Bid|Price)[:\s]+£([0-9,]+)', re.IGNORECASE), "GBP"),
            (re.compile(r'Final\s+(?:Bid|Price)[:\s]+€([0-9,]+)', re.IGNORECASE), "EUR"),
            (re.compile(r'Final\s+(?:Bid|Price)[:\s]+\$([0-9,]+)', re.IGNORECASE), "USD"),
        ]:
            match = pattern.search(page_text)
            if match:
                price_str = match.group(1).replace(",", "")
                return True, Decimal(price_str), currency_default

        if re.search(r'\b(not\s+sold|reserve\s+not\s+met|no\s+sale)\b', page_text, re.IGNORECASE):
            return False, None, "GBP"

        return None, None, "GBP"

    def _extract_mileage(self, soup: BeautifulSoup, title: str) -> int | None:
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
        chassis_match = re.search(r'(?:chassis|vin|serial)[:\s#]*\s*([A-Za-z0-9]{6,17})', page_text, re.IGNORECASE)
        return chassis_match.group(1) if chassis_match else None

    def _extract_location_info(self, soup: BeautifulSoup) -> dict:
        result: dict = {}
        page_text = soup.get_text()
        loc_match = re.search(r'(?:Location|Located)[:\s]+([^\n,]+(?:,\s*[^\n]+)?)', page_text, re.IGNORECASE)
        if loc_match:
            result["seller_location"] = loc_match.group(1).strip()[:200]
        return result

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
            currency = data.get("currency", "GBP")

            premium = _compute_cc_premium(hammer_price)
            total = (hammer_price + premium) if hammer_price and premium else hammer_price

            tx_date = date.today()

            sale_country = "UK" if currency == "GBP" else ("EU" if currency == "EUR" else None)

            transaction = Transaction(
                provenance_id=provenance.id,
                asset_model_id=match.asset_model_id,
                source=self.source,
                external_id=ext_id,
                transaction_type=tx_type,
                transaction_date=tx_date,
                hammer_price=hammer_price,
                buyer_premium=premium,
                total_price=total,
                currency=currency,
                total_price_usd=None,
                year=data.get("year"),
                mileage=data.get("mileage"),
                mileage_unit="miles",
                vin=data.get("vin"),
                sale_country=sale_country,
                sale_region=data.get("seller_location"),
                auction_house="Collecting Cars",
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


def _compute_cc_premium(hammer: Decimal | None) -> Decimal | None:
    """Collecting Cars charges 6% buyer's premium."""
    if hammer is None:
        return None
    return hammer * Decimal("0.06")
