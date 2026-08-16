"""Tests for BaT listing parser using cached HTML fixtures."""

from pathlib import Path

import pytest

from aatp.collectors.bat import BringATrailerScraper


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestBaTSearchParser:
    def test_extract_listing_urls(self):
        html = (FIXTURES / "bat_search.html").read_text()
        scraper = BringATrailerScraper.__new__(BringATrailerScraper)
        urls = scraper._extract_listing_urls(html)

        assert len(urls) == 4
        assert all("/listing/" in u for u in urls)
        assert "https://bringatrailer.com/about/" not in urls
        assert "https://bringatrailer.com/listing/2019-ferrari-488-pista-spider-3/" in urls
        # Relative URL should be expanded
        assert "https://bringatrailer.com/listing/2019-ferrari-488-pista-spider-5/" in urls


class TestBaTListingParser:
    @pytest.fixture
    def parsed(self):
        html = (FIXTURES / "bat_listing.html").read_text()
        scraper = BringATrailerScraper.__new__(BringATrailerScraper)
        return scraper._parse_listing("https://bringatrailer.com/listing/2019-ferrari-488-pista-spider-3/", html)

    def test_title(self, parsed):
        assert parsed["title"] == "2019 Ferrari 488 Pista Spider"

    def test_year(self, parsed):
        assert parsed["year"] == 2019

    def test_sold_status(self, parsed):
        assert parsed["sold"] is True

    def test_hammer_price(self, parsed):
        assert parsed["hammer_price"] == "485000"

    def test_currency(self, parsed):
        assert parsed["currency"] == "USD"

    def test_mileage(self, parsed):
        assert parsed["mileage"] == 2400

    def test_seller_location(self, parsed):
        assert parsed["seller_location"] is not None
        assert "Beverly Hills" in parsed["seller_location"] or "CA" in parsed["seller_location"]

    def test_colour_exterior(self, parsed):
        assert parsed["colour_exterior"] is not None
        assert "rosso" in parsed["colour_exterior"].lower() or "corsa" in parsed["colour_exterior"].lower()

    def test_colour_interior(self, parsed):
        assert parsed["colour_interior"] is not None
        assert "nero" in parsed["colour_interior"].lower()

    def test_vin(self, parsed):
        assert parsed["vin"] == "ZFF90HLA0K0244123"

    def test_slug(self, parsed):
        assert parsed["slug"] == "2019-ferrari-488-pista-spider-3"

    def test_auction_end_date(self, parsed):
        assert parsed["auction_end_date"] is not None

    def test_essentials_captured(self, parsed):
        essentials = {k: v for k, v in parsed.items() if k.startswith("essential_")}
        assert len(essentials) > 0


class TestBaTBuyerPremium:
    def test_premium_under_cap(self):
        from decimal import Decimal
        from aatp.collectors.bat import _compute_bat_premium
        assert _compute_bat_premium(Decimal("50000")) == Decimal("2500")

    def test_premium_at_cap(self):
        from decimal import Decimal
        from aatp.collectors.bat import _compute_bat_premium
        assert _compute_bat_premium(Decimal("100000")) == Decimal("5000")

    def test_premium_above_cap(self):
        from decimal import Decimal
        from aatp.collectors.bat import _compute_bat_premium
        assert _compute_bat_premium(Decimal("500000")) == Decimal("5000")

    def test_premium_none(self):
        from aatp.collectors.bat import _compute_bat_premium
        assert _compute_bat_premium(None) is None
