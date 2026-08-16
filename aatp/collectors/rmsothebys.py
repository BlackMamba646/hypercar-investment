"""
RM Sotheby's scraper.

Major event auctions with high-value transactions. Less frequent than BaT
but most important for price ceiling discovery. Handles both upcoming and
completed auction events.

Structure:
- Auction calendar: rmsothebys.com/en/auctions/
- Event page: rmsothebys.com/en/auctions/<slug>/
- Lot page: rmsothebys.com/en/auctions/<event>/<lot-slug>/
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup

from aatp.collectors.base import BaseScraper, ScrapedItem
from aatp.collectors.model_matcher import AssetModelMatcher
from aatp.core.logging import get_logger
from aatp.db.models import (
    Transaction,
    TransactionSource,
    TransactionType,
)

logger = get_logger("collectors.rmsothebys")

RM_BASE = "https://rmsothebys.com"

TARGET_KEYWORDS = [
    "ferrari", "bugatti", "mclaren", "lamborghini", "porsche",
    "pagani", "koenigsegg", "aston martin",
]


class RMSothebysScraper(BaseScraper):
    source = TransactionSource.RM_SOTHEBYS
    scraper_name = "rm_sothebys_auctions"
    scraper_version = "0.1.0"

    def __init__(self, session, max_events: int = 5):
        super().__init__(session)
        self._max_events = max_events
        self._matcher = AssetModelMatcher(session)

    async def discover_urls(self) -> list[str]:
        """Discover lot URLs from recent RM Sotheby's auction events."""
        lot_urls: list[str] = []

        try:
            calendar_url = f"{RM_BASE}/en/auctions/"
            response = await self._fetch(calendar_url)
            event_urls = self._extract_event_urls(response.text)

            for event_url in event_urls[:self._max_events]:
                try:
                    event_response = await self._fetch(event_url)
                    urls = self._extract_lot_urls(event_response.text, event_url)
                    lot_urls.extend(urls)
                except Exception as e:
                    self._record_error(e, {"event_url": event_url})

        except Exception as e:
            self._record_error(e, {"phase": "discover"})

        logger.info("rm_lots_discovered", count=len(lot_urls))
        return lot_urls

    def _extract_event_urls(self, html: str) -> list[str]:
        """Extract auction event URLs from the calendar page."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/en/auctions/" in href and href.count("/") >= 4:
                full_url = href if href.startswith("http") else f"{RM_BASE}{href}"
                if full_url not in urls and full_url != f"{RM_BASE}/en/auctions/":
                    urls.append(full_url)

        return urls

    def _extract_lot_urls(self, html: str, event_url: str) -> list[str]:
        """Extract individual lot URLs from an event page, filtered to target makes."""
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            link_text = link.get_text(strip=True).lower()

            is_lot_page = (
                "/lot/" in href or
                (href.count("/") >= 5 and any(kw in href.lower() for kw in TARGET_KEYWORDS))
            )

            is_relevant = any(kw in link_text or kw in href.lower() for kw in TARGET_KEYWORDS)

            if is_lot_page and is_relevant:
                full_url = href if href.startswith("http") else f"{RM_BASE}{href}"
                if full_url not in urls:
                    urls.append(full_url)

        return urls

    async def parse_page(self, url: str, html: str) -> list[ScrapedItem]:
        """Parse an RM Sotheby's lot page."""
        try:
            data = self._parse_lot(url, html)
            if data is None:
                return []

            return [ScrapedItem(
                source_url=url,
                raw_html=html,
                parsed_data=data,
                external_id=data.get("lot_id"),
            )]
        except Exception as e:
            self._record_error(e, {"url": url, "phase": "parse"})
            return []

    def _parse_lot(self, url: str, html: str) -> dict | None:
        """Extract structured data from an RM lot page."""
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.find("h1")
        if title_el is None:
            return None

        title = title_el.get_text(strip=True)
        if not any(kw in title.lower() for kw in TARGET_KEYWORDS):
            return None

        data: dict = {
            "title": title,
            "url": url,
            "lot_id": url.rstrip("/").split("/")[-1],
        }

        # Year
        year_match = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', title)
        if year_match:
            data["year"] = int(year_match.group(1))

        # Estimate range
        data.update(self._extract_estimate(soup))

        # Result (sold/not sold, hammer price)
        data.update(self._extract_result(soup))

        # Event name and date
        data.update(self._extract_event_info(soup))

        # Lot details
        data.update(self._extract_lot_details(soup))

        # Catalogue description
        desc_el = soup.find(class_="lot-description") or soup.find("div", class_="description")
        if desc_el:
            data["catalogue_description"] = desc_el.get_text(strip=True)[:5000]

        return data

    def _extract_estimate(self, soup: BeautifulSoup) -> dict:
        """Extract pre-sale estimate range."""
        result: dict = {}
        page_text = soup.get_text()

        estimate_patterns = [
            re.compile(r'Estimate[:\s]*\$([0-9,]+)\s*[-–]\s*\$([0-9,]+)', re.IGNORECASE),
            re.compile(r'Estimate[:\s]*€([0-9,]+)\s*[-–]\s*€([0-9,]+)', re.IGNORECASE),
            re.compile(r'Estimate[:\s]*£([0-9,]+)\s*[-–]\s*£([0-9,]+)', re.IGNORECASE),
        ]

        for pattern in estimate_patterns:
            match = pattern.search(page_text)
            if match:
                result["estimate_low"] = match.group(1).replace(",", "")
                result["estimate_high"] = match.group(2).replace(",", "")
                if "€" in pattern.pattern:
                    result["estimate_currency"] = "EUR"
                elif "£" in pattern.pattern:
                    result["estimate_currency"] = "GBP"
                else:
                    result["estimate_currency"] = "USD"
                break

        return result

    def _extract_result(self, soup: BeautifulSoup) -> dict:
        """Extract auction result — sold/not sold and hammer price."""
        result: dict = {}
        page_text = soup.get_text()

        sold_patterns = [
            re.compile(r'Sold\s+(?:for\s+)?[\$€£]([0-9,]+)', re.IGNORECASE),
            re.compile(r'Hammer\s+Price[:\s]*[\$€£]([0-9,]+)', re.IGNORECASE),
            re.compile(r'Price\s+Realized[:\s]*[\$€£]([0-9,]+)', re.IGNORECASE),
        ]

        for pattern in sold_patterns:
            match = pattern.search(page_text)
            if match:
                result["sold"] = True
                result["hammer_price"] = match.group(1).replace(",", "")
                # Detect currency from the symbol that precedes the number
                prefix = page_text[match.start():match.start() + 50]
                if "€" in prefix:
                    result["currency"] = "EUR"
                elif "£" in prefix:
                    result["currency"] = "GBP"
                else:
                    result["currency"] = "USD"
                break

        if "sold" not in result:
            not_sold = re.search(r'(not\s+sold|withdrawn|passed)', page_text, re.IGNORECASE)
            if not_sold:
                result["sold"] = False

        # RM buyer's premium is typically 12.5% on first $250k, scaling down
        if result.get("hammer_price"):
            hp = Decimal(result["hammer_price"])
            premium = self._compute_rm_premium(hp)
            result["buyer_premium"] = str(premium)
            result["total_price"] = str(hp + premium)

        return result

    @staticmethod
    def _compute_rm_premium(hammer: Decimal) -> Decimal:
        """RM Sotheby's tiered buyer's premium schedule."""
        if hammer <= 250_000:
            return hammer * Decimal("0.125")
        elif hammer <= 1_000_000:
            premium = Decimal("250000") * Decimal("0.125")
            premium += (hammer - Decimal("250000")) * Decimal("0.12")
            return premium
        else:
            premium = Decimal("250000") * Decimal("0.125")
            premium += Decimal("750000") * Decimal("0.12")
            premium += (hammer - Decimal("1000000")) * Decimal("0.10")
            return premium

    def _extract_event_info(self, soup: BeautifulSoup) -> dict:
        """Extract auction event name and date."""
        result: dict = {}

        event_el = soup.find(class_="auction-title") or soup.find(class_="event-name")
        if event_el:
            result["auction_event"] = event_el.get_text(strip=True)

        page_text = soup.get_text()
        date_patterns = [
            re.compile(r'(\d{1,2}\s+\w+\s+\d{4})'),
            re.compile(r'(\w+\s+\d{1,2},?\s+\d{4})'),
        ]
        for pattern in date_patterns:
            match = pattern.search(page_text[:2000])
            if match:
                result["event_date"] = match.group(1)
                break

        return result

    def _extract_lot_details(self, soup: BeautifulSoup) -> dict:
        """Extract structured lot details: chassis, engine, mileage, etc."""
        details: dict = {}

        for el in soup.find_all(["li", "tr", "div"], class_=re.compile(r'lot-detail|spec')):
            text = el.get_text(strip=True)
            if ":" in text:
                key, _, value = text.partition(":")
                key_clean = key.strip().lower().replace(" ", "_")
                details[f"detail_{key_clean}"] = value.strip()

        # Mileage extraction
        page_text = soup.get_text()
        mileage_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|km|kilometres)', page_text, re.IGNORECASE)
        if mileage_match:
            details["mileage"] = int(mileage_match.group(1).replace(",", ""))
            details["mileage_unit"] = "km" if "km" in mileage_match.group(0).lower() else "miles"

        # Chassis/VIN
        vin_match = re.search(r'(?:chassis|vin|serial)[:\s#]*\s*([A-Za-z0-9]{6,17})', page_text, re.IGNORECASE)
        if vin_match:
            details["vin"] = vin_match.group(1)

        return details

    async def store_items(self, items: list[ScrapedItem]) -> int:
        """Store parsed RM lots as transactions."""
        stored = 0

        for item in items:
            data = item.parsed_data
            ext_id = data.get("lot_id")

            if ext_id and await self.check_for_duplicate(ext_id):
                continue

            match = await self._matcher.match(data.get("title", ""))
            if match is None:
                logger.debug("unmatched_lot", title=data.get("title"))
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
            buyer_premium = Decimal(data["buyer_premium"]) if data.get("buyer_premium") else None
            total_price = Decimal(data["total_price"]) if data.get("total_price") else None

            currency = data.get("currency", "USD")

            tx_date = date.today()
            if data.get("event_date"):
                from aatp.collectors.bat import _parse_date_flexible
                parsed = _parse_date_flexible(data["event_date"])
                if parsed:
                    tx_date = parsed

            # Determine geography from event name
            sale_country = _infer_country_from_event(data.get("auction_event", ""))

            transaction = Transaction(
                provenance_id=provenance.id,
                asset_model_id=match.asset_model_id,
                source=self.source,
                external_id=ext_id,
                transaction_type=tx_type,
                transaction_date=tx_date,
                hammer_price=hammer_price,
                buyer_premium=buyer_premium,
                total_price=total_price,
                currency=currency,
                total_price_usd=total_price if currency == "USD" else None,
                year=data.get("year"),
                mileage=data.get("mileage"),
                mileage_unit=data.get("mileage_unit", "miles"),
                vin=data.get("vin"),
                sale_country=sale_country,
                auction_house="RM Sotheby's",
                auction_event=data.get("auction_event"),
                lot_description=data.get("catalogue_description", data.get("title")),
                metadata_={
                    "match_confidence": match.confidence,
                    "match_method": match.match_method,
                    "estimate_low": data.get("estimate_low"),
                    "estimate_high": data.get("estimate_high"),
                    "estimate_currency": data.get("estimate_currency"),
                    "details": {k: v for k, v in data.items() if k.startswith("detail_")},
                },
            )
            self.db.add(transaction)
            stored += 1

        if stored:
            await self.db.flush()

        return stored


def _infer_country_from_event(event_name: str) -> str | None:
    """Infer sale country from auction event name."""
    event_lower = event_name.lower()
    mapping = {
        "monterey": "US", "amelia": "US", "arizona": "US",
        "hershey": "US", "palm beach": "US", "auburn": "US",
        "london": "UK", "paris": "FR", "munich": "DE",
        "milan": "IT", "maranello": "IT",
        "abu dhabi": "AE", "dubai": "AE",
    }
    for keyword, country in mapping.items():
        if keyword in event_lower:
            return country
    return None
