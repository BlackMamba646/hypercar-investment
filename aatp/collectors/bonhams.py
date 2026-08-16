"""Bonhams auction house scraper.

Major international auction house with motor car department. Uses Playwright
for JS rendering. Discovers lots via their search page.

Structure:
- Search: bonhams.com/search/?q=<query>&type=results
- Lot page: cars.bonhams.com/auction/<sale_id>/preview-lot/<lot_id>/<slug>/
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

logger = get_logger("collectors.bonhams")

BONHAMS_BASE = "https://www.bonhams.com"

TARGET_SEARCH_TERMS = [
    "ferrari+812", "ferrari+488+pista", "ferrari+laferrari",
    "ferrari+f40", "ferrari+f50", "ferrari+458+speciale",
    "ferrari+sf90", "bugatti+chiron", "bugatti+veyron",
    "mclaren+senna", "porsche+918",
    "lamborghini+aventador+svj",
]

TARGET_KEYWORDS = [
    "ferrari", "bugatti", "mclaren", "lamborghini", "porsche",
    "pagani", "koenigsegg", "aston martin",
]


class BonhamsScraper(PlaywrightScraper):
    source = TransactionSource.BONHAMS
    scraper_name = "bonhams_motor_cars"
    scraper_version = "0.2.0"

    def __init__(self, session, search_terms: list[str] | None = None):
        super().__init__(session)
        self._search_terms = search_terms or TARGET_SEARCH_TERMS
        self._matcher = AssetModelMatcher(session)

    async def discover_urls(self) -> list[str]:
        lot_urls: list[str] = []
        seen_ids: set[str] = set()

        for term in self._search_terms:
            search_url = f"{BONHAMS_BASE}/search/?q={term}&type=results"
            try:
                html = await self._fetch_rendered(search_url, wait_selector="a[href*='bonhams.com']")
                urls = self._extract_lot_urls(html)
                for url in urls:
                    lot_id = url.rstrip("/").split("/")[-1]
                    if lot_id not in seen_ids:
                        seen_ids.add(lot_id)
                        lot_urls.append(url)
            except Exception as e:
                self._record_error(e, {"search_term": term})

        logger.info("bonhams_lots_discovered", count=len(lot_urls))
        return lot_urls

    def _extract_lot_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: list[str] = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if ("preview-lot" in href or "/lot/" in href) and "bonhams.com" in href:
                if href not in urls:
                    urls.append(href)
            elif ("/auction/" in href or "/lot/" in href) and href.startswith("/"):
                full_url = f"{BONHAMS_BASE}{href}"
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
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.find("h1")
        if title_el is None:
            return None
        title = title_el.get_text(strip=True)

        if not any(kw in title.lower() for kw in TARGET_KEYWORDS):
            return None

        lot_id = url.rstrip("/").split("/")[-1]
        data: dict = {"title": title, "url": url, "lot_id": lot_id}

        year_match = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', title)
        if year_match:
            data["year"] = int(year_match.group(1))

        data.update(self._extract_estimate(soup))
        data.update(self._extract_result(soup))
        data.update(self._extract_sale_info(soup))
        data.update(self._extract_lot_details(soup))

        return data

    def _extract_estimate(self, soup: BeautifulSoup) -> dict:
        result: dict = {}
        page_text = soup.get_text()
        for pattern in [
            re.compile(r'Estimate[:\s]*[\$€£]([0-9,]+)\s*[-–]\s*[\$€£]([0-9,]+)', re.IGNORECASE),
            re.compile(r'Est\.\s*[\$€£]([0-9,]+)\s*[-–]\s*[\$€£]([0-9,]+)', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                result["estimate_low"] = match.group(1).replace(",", "")
                result["estimate_high"] = match.group(2).replace(",", "")
                prefix = page_text[match.start():match.start() + 50]
                if "€" in prefix:
                    result["estimate_currency"] = "EUR"
                elif "£" in prefix:
                    result["estimate_currency"] = "GBP"
                else:
                    result["estimate_currency"] = "USD"
                break
        return result

    def _extract_result(self, soup: BeautifulSoup) -> dict:
        result: dict = {}
        page_text = soup.get_text()

        for pattern in [
            re.compile(r'Sold\s+(?:for\s+)?[\$€£]([0-9,]+)', re.IGNORECASE),
            re.compile(r'Hammer\s+Price[:\s]*[\$€£]([0-9,]+)', re.IGNORECASE),
            re.compile(r'Price\s+(?:Realized|Realised)[:\s]*[\$€£]([0-9,]+)', re.IGNORECASE),
        ]:
            match = pattern.search(page_text)
            if match:
                result["sold"] = True
                result["hammer_price"] = match.group(1).replace(",", "")
                prefix = page_text[match.start():match.start() + 50]
                if "€" in prefix:
                    result["currency"] = "EUR"
                elif "£" in prefix:
                    result["currency"] = "GBP"
                else:
                    result["currency"] = "USD"
                break

        if "sold" not in result:
            if re.search(r'(not\s+sold|withdrawn|passed|bought[\s-]in)', page_text, re.IGNORECASE):
                result["sold"] = False

        if result.get("hammer_price"):
            hp = Decimal(result["hammer_price"])
            premium = self._compute_bonhams_premium(hp)
            result["buyer_premium"] = str(premium)
            result["total_price"] = str(hp + premium)

        return result

    @staticmethod
    def _compute_bonhams_premium(hammer: Decimal) -> Decimal:
        """Bonhams motor car buyer's premium: 15% on first $250K, 12% on $250K-$4M, 10% above."""
        if hammer <= 250_000:
            return hammer * Decimal("0.15")
        elif hammer <= 4_000_000:
            premium = Decimal("250000") * Decimal("0.15")
            premium += (hammer - Decimal("250000")) * Decimal("0.12")
            return premium
        else:
            premium = Decimal("250000") * Decimal("0.15")
            premium += Decimal("3750000") * Decimal("0.12")
            premium += (hammer - Decimal("4000000")) * Decimal("0.10")
            return premium

    def _extract_sale_info(self, soup: BeautifulSoup) -> dict:
        result: dict = {}
        page_text = soup.get_text()

        for cls in ("sale-title", "auction-title", "event-name"):
            el = soup.find(class_=cls)
            if el:
                result["auction_event"] = el.get_text(strip=True)
                break

        date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4})', page_text[:2000])
        if date_match:
            result["event_date"] = date_match.group(1)

        return result

    def _extract_lot_details(self, soup: BeautifulSoup) -> dict:
        details: dict = {}
        page_text = soup.get_text()

        mileage_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:miles|km|kilometres)', page_text, re.IGNORECASE)
        if mileage_match:
            details["mileage"] = int(mileage_match.group(1).replace(",", ""))
            details["mileage_unit"] = "km" if "km" in mileage_match.group(0).lower() else "miles"

        vin_match = re.search(r'(?:chassis|vin|serial)[:\s#]*\s*([A-Za-z0-9]{6,17})', page_text, re.IGNORECASE)
        if vin_match:
            details["vin"] = vin_match.group(1)

        return details

    async def store_items(self, items: list[ScrapedItem]) -> int:
        stored = 0
        for item in items:
            data = item.parsed_data
            ext_id = data.get("lot_id")

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
            buyer_premium = Decimal(data["buyer_premium"]) if data.get("buyer_premium") else None
            total_price = Decimal(data["total_price"]) if data.get("total_price") else None
            currency = data.get("currency", "USD")

            tx_date = date.today()
            if data.get("event_date"):
                from aatp.collectors.bat import _parse_date_flexible
                parsed = _parse_date_flexible(data["event_date"])
                if parsed:
                    tx_date = parsed

            sale_country = _infer_country(data.get("auction_event", ""))

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
                auction_house="Bonhams",
                auction_event=data.get("auction_event"),
                lot_description=data.get("title"),
                metadata_={
                    "match_confidence": match.confidence,
                    "match_method": match.match_method,
                    "estimate_low": data.get("estimate_low"),
                    "estimate_high": data.get("estimate_high"),
                    "estimate_currency": data.get("estimate_currency"),
                },
            )
            self.db.add(transaction)
            stored += 1

        if stored:
            await self.db.flush()
        return stored


def _infer_country(event_name: str) -> str | None:
    event_lower = event_name.lower()
    mapping = {
        "monterey": "US", "quail": "US", "scottsdale": "US",
        "amelia": "US", "greenwich": "US", "laguna": "US",
        "london": "UK", "goodwood": "UK", "bond street": "UK",
        "paris": "FR", "chantilly": "FR",
        "zurich": "CH", "gstaad": "CH",
    }
    for keyword, country in mapping.items():
        if keyword in event_lower:
            return country
    return None
