"""
Bring a Trailer scraper.

BaT is the primary price discovery source: highest frequency public auction data
with rolling daily auctions. Every result includes model, year, mileage, colour,
options, hammer price, date, and full listing description.

Scraping strategy:
1. Discover recently completed auctions via search/listing pages
2. Fetch individual auction result pages
3. Parse structured data from the listing page HTML
4. Store with full provenance

BaT structure (as of scraper version):
- Search results: bringatrailer.com/search/?s=ferrari+488+pista
- Completed listings: bringatrailer.com/listing/<slug>/
- Auction results are embedded in the listing page with final bid data
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup, Tag
from sqlalchemy import select

from aatp.collectors.base import BaseScraper, ScrapedItem
from aatp.collectors.model_matcher import AssetModelMatcher
from aatp.core.logging import get_logger
from aatp.db.models import (
    DataProvenance,
    Transaction,
    TransactionSource,
    TransactionType,
)

logger = get_logger("collectors.bat")

BAT_BASE = "https://bringatrailer.com"

TARGET_SEARCH_TERMS = [
    "ferrari+812+superfast",
    "ferrari+812+gts",
    "ferrari+812+competizione",
    "ferrari+488+pista",
    "ferrari+488+pista+spider",
    "ferrari+laferrari",
    "ferrari+f40",
    "ferrari+f50",
    "ferrari+458+speciale",
    "ferrari+sp3+monza",
    "bugatti+chiron",
    "bugatti+veyron",
    "mclaren+senna",
    "mclaren+speedtail",
    "ferrari+sf90",
    "ferrari+296",
    "lamborghini+aventador+svj",
    "porsche+918",
]


class BringATrailerScraper(BaseScraper):
    source = TransactionSource.BRING_A_TRAILER
    scraper_name = "bat_auctions"
    scraper_version = "0.1.0"

    def __init__(self, session, search_terms: list[str] | None = None):
        super().__init__(session)
        self._search_terms = search_terms or TARGET_SEARCH_TERMS
        self._matcher = AssetModelMatcher(session)

    async def discover_urls(self) -> list[str]:
        """Discover completed auction listing URLs via search pages."""
        listing_urls: list[str] = []
        seen_slugs: set[str] = set()

        for term in self._search_terms:
            search_url = f"{BAT_BASE}/search/?s={term}"
            try:
                response = await self._fetch(search_url)
                urls = self._extract_listing_urls(response.text)
                for url in urls:
                    slug = url.rstrip("/").split("/")[-1]
                    if slug not in seen_slugs:
                        seen_slugs.add(slug)
                        listing_urls.append(url)
            except Exception as e:
                self._record_error(e, {"search_term": term})

        logger.info("bat_urls_discovered", count=len(listing_urls))
        return listing_urls

    def _extract_listing_urls(self, html: str) -> list[str]:
        """Extract listing URLs from a BaT search results page."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/listing/" in href and href.startswith(("http", "/")):
                full_url = href if href.startswith("http") else f"{BAT_BASE}{href}"
                if full_url not in urls:
                    urls.append(full_url)

        return urls

    async def parse_page(self, url: str, html: str) -> list[ScrapedItem]:
        """Parse a BaT listing page into a ScrapedItem."""
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
        """Extract structured data from a BaT listing page."""
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.find("h1", class_="post-title")
        if title_el is None:
            title_el = soup.find("h1")
        if title_el is None:
            return None

        title = title_el.get_text(strip=True)

        slug = url.rstrip("/").split("/")[-1]

        data: dict = {
            "title": title,
            "url": url,
            "slug": slug,
        }

        # Year extraction from title
        year_match = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', title)
        if year_match:
            data["year"] = int(year_match.group(1))

        # Sold status and price
        sold, price, currency = self._extract_result(soup)
        data["sold"] = sold
        if price is not None:
            data["hammer_price"] = str(price)
            data["currency"] = currency

        # Auction end date
        data["auction_end_date"] = self._extract_end_date(soup)

        # Mileage
        data["mileage"] = self._extract_mileage(soup, title)

        # Location
        data["seller_location"] = self._extract_location(soup)

        # Listing essentials section
        essentials = self._extract_essentials(soup)
        data.update(essentials)

        # Colours from description
        colours = self._extract_colours(soup)
        data.update(colours)

        # VIN
        vin = self._extract_vin(soup)
        if vin:
            data["vin"] = vin

        return data

    def _extract_result(self, soup: BeautifulSoup) -> tuple[bool | None, Decimal | None, str]:
        """Extract sold/not-sold status and hammer price."""
        # BaT shows result in a specific div
        result_div = soup.find("div", class_="post-excerpt")
        if result_div is None:
            result_div = soup.find("span", class_="info-value")

        # Look for price patterns in the page
        price_patterns = [
            re.compile(r'Sold\s+(?:for\s+)?\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Bid\s+to\s+\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Hammer\s+Price[:\s]+\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Final\s+Bid[:\s]+\$([0-9,]+)', re.IGNORECASE),
        ]

        page_text = soup.get_text()
        for pattern in price_patterns:
            match = pattern.search(page_text)
            if match:
                price_str = match.group(1).replace(",", "")
                sold = "sold" in match.group(0).lower()
                return sold, Decimal(price_str), "USD"

        # Check for "not sold" / "bid to" without sale
        if re.search(r'\b(not\s+sold|reserve\s+not\s+met|no\s+sale)\b', page_text, re.IGNORECASE):
            bid_match = re.search(r'\$([0-9,]+)', page_text)
            if bid_match:
                price_str = bid_match.group(1).replace(",", "")
                return False, Decimal(price_str), "USD"
            return False, None, "USD"

        return None, None, "USD"

    def _extract_end_date(self, soup: BeautifulSoup) -> str | None:
        """Extract auction end date."""
        # BaT typically shows date in listing-stats or post meta
        for cls in ("listing-available-date", "post-date", "listing-stats"):
            el = soup.find(class_=cls)
            if el:
                date_match = re.search(
                    r'(\w+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
                    el.get_text()
                )
                if date_match:
                    return date_match.group(1)

        time_el = soup.find("time")
        if time_el and time_el.get("datetime"):
            return time_el["datetime"]

        return None

    def _extract_mileage(self, soup: BeautifulSoup, title: str) -> int | None:
        """Extract mileage from listing essentials or title."""
        page_text = soup.get_text()

        patterns = [
            re.compile(r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|mi)\b', re.IGNORECASE),
            re.compile(r'(\d{1,3}(?:,\d{3})*)\s*(?:kilometers|km)\b', re.IGNORECASE),
            re.compile(r'~?(\d{1,3}(?:,\d{3})*)\s*(?:indicated|showing)\s*(?:miles|km)', re.IGNORECASE),
        ]

        for pattern in patterns:
            match = pattern.search(page_text)
            if match:
                return int(match.group(1).replace(",", ""))

        title_match = re.search(r'(\d{1,3}(?:,\d{3})*)[- ](?:mile|km)', title, re.IGNORECASE)
        if title_match:
            return int(title_match.group(1).replace(",", ""))

        return None

    def _extract_location(self, soup: BeautifulSoup) -> str | None:
        """Extract seller location."""
        for cls in ("listing-essentials-item", "essentials"):
            for el in soup.find_all(class_=cls):
                text = el.get_text()
                if "location" in text.lower() or "seller" in text.lower():
                    value = text.split(":")[-1].strip() if ":" in text else text
                    return value

        # Fallback: look for state/city patterns
        page_text = soup.get_text()
        loc_match = re.search(
            r'(?:located|seller)\s+(?:in\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})',
            page_text
        )
        if loc_match:
            return loc_match.group(1)

        return None

    def _extract_essentials(self, soup: BeautifulSoup) -> dict:
        """Extract listing essentials (chassis, engine, transmission, etc.)."""
        essentials: dict = {}

        # BaT uses a structured essentials section
        for item in soup.find_all(class_="listing-essentials-item"):
            text = item.get_text(strip=True)
            if ":" in text:
                key, _, value = text.partition(":")
                key = key.strip().lower().replace(" ", "_")
                essentials[f"essential_{key}"] = value.strip()

        # Also check for a structured data table
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True).lower().replace(" ", "_")
                    value = cells[1].get_text(strip=True)
                    essentials[f"detail_{key}"] = value

        return essentials

    def _extract_colours(self, soup: BeautifulSoup) -> dict:
        """Extract exterior and interior colour from description."""
        colours: dict = {}
        page_text = soup.get_text()

        ext_patterns = [
            re.compile(r'(?:finished|painted|exterior)\s+in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})', re.IGNORECASE),
            re.compile(r'(Rosso\s+\w+|Nero\s*\w*|Grigio\s+\w+|Giallo\s+\w+|Bianco\s+\w+|Blu\s+\w+|Argento\s+\w+|Verde\s+\w+)', re.IGNORECASE),
        ]
        for pattern in ext_patterns:
            match = pattern.search(page_text)
            if match:
                colours["colour_exterior"] = match.group(1).strip()
                break

        int_patterns = [
            re.compile(r'over\s+(Nero|Cuoio|Crema|Sabbia|Rosso|Beige|Tan|Black|Red|Brown|Blue)(?:\s+\w+)?(?:\s+leather|\s+interior|\s+Alcantara)?', re.IGNORECASE),
            re.compile(r'(Nero|Cuoio|Crema|Sabbia|Beige|Tan|Black|Brown)\s+(?:leather\s+)?interior', re.IGNORECASE),
            re.compile(r'interior\s+(?:is\s+)?(?:in\s+|trimmed\s+in\s+)(Nero|Cuoio|Crema|Sabbia|Beige|Tan|Black|Red|Brown|Blue)(?:\s+\w+)?', re.IGNORECASE),
        ]
        for pattern in int_patterns:
            match = pattern.search(page_text)
            if match:
                colours["colour_interior"] = match.group(1).strip()
                break

        return colours

    def _extract_vin(self, soup: BeautifulSoup) -> str | None:
        """Extract VIN/chassis number."""
        page_text = soup.get_text()
        vin_match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', page_text)
        if vin_match:
            return vin_match.group(1)

        chassis_match = re.search(r'(?:chassis|vin|serial)[:\s#]*\s*([A-Za-z0-9]{6,17})', page_text, re.IGNORECASE)
        if chassis_match:
            return chassis_match.group(1)

        return None

    async def store_items(self, items: list[ScrapedItem]) -> int:
        """Store parsed BaT auction results as transactions."""
        stored = 0

        for item in items:
            data = item.parsed_data
            ext_id = data.get("slug")

            if ext_id and await self.check_for_duplicate(ext_id):
                continue

            # Match to asset model
            match = await self._matcher.match(data.get("title", ""))
            if match is None:
                logger.debug("unmatched_listing", title=data.get("title"))
                continue

            provenance = await self._create_provenance(item)

            # Determine transaction type
            sold = data.get("sold")
            if sold is True:
                tx_type = TransactionType.AUCTION_SOLD
            elif sold is False:
                tx_type = TransactionType.AUCTION_NOT_SOLD
            else:
                continue

            # Parse price
            hammer_price = None
            if data.get("hammer_price"):
                hammer_price = Decimal(data["hammer_price"])

            # Parse date
            tx_date = date.today()
            if data.get("auction_end_date"):
                try:
                    parsed = _parse_date_flexible(data["auction_end_date"])
                    if parsed:
                        tx_date = parsed
                except Exception:
                    pass

            transaction = Transaction(
                provenance_id=provenance.id,
                asset_model_id=match.asset_model_id,
                source=self.source,
                external_id=ext_id,
                transaction_type=tx_type,
                transaction_date=tx_date,
                hammer_price=hammer_price,
                buyer_premium=_compute_bat_premium(hammer_price),
                total_price=_compute_bat_total(hammer_price),
                currency=data.get("currency", "USD"),
                total_price_usd=_compute_bat_total(hammer_price),
                year=data.get("year"),
                mileage=data.get("mileage"),
                mileage_unit="miles",
                colour_exterior=data.get("colour_exterior"),
                colour_interior=data.get("colour_interior"),
                drive_side=data.get("essential_drive_side") or data.get("detail_drive_side"),
                vin=data.get("vin"),
                options=_collect_options(data),
                sale_country="US",
                sale_region=data.get("seller_location"),
                auction_house="Bring a Trailer",
                lot_description=data.get("title"),
                metadata_={
                    "match_confidence": match.confidence,
                    "match_method": match.match_method,
                    "essentials": {k: v for k, v in data.items() if k.startswith(("essential_", "detail_"))},
                },
            )
            self.db.add(transaction)
            stored += 1

        if stored:
            await self.db.flush()

        return stored


def _compute_bat_premium(hammer: Decimal | None) -> Decimal | None:
    """BaT charges 5% buyer's premium, capped at $5,000."""
    if hammer is None:
        return None
    premium = hammer * Decimal("0.05")
    return min(premium, Decimal("5000"))


def _compute_bat_total(hammer: Decimal | None) -> Decimal | None:
    if hammer is None:
        return None
    premium = _compute_bat_premium(hammer)
    return hammer + (premium or Decimal("0"))


def _collect_options(data: dict) -> dict | None:
    """Collect options/equipment from parsed essentials."""
    options = {}
    for key, value in data.items():
        if key.startswith(("essential_", "detail_")):
            clean_key = key.replace("essential_", "").replace("detail_", "")
            options[clean_key] = value
    return options if options else None


def _parse_date_flexible(date_str: str) -> date | None:
    """Parse dates in various formats BaT uses."""
    import dateutil.parser
    try:
        dt = dateutil.parser.parse(date_str)
        return dt.date()
    except (ValueError, TypeError):
        return None
