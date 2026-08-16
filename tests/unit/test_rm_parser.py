"""Tests for RM Sotheby's lot parser using cached HTML fixtures."""

from pathlib import Path

import pytest

from aatp.collectors.rmsothebys import RMSothebysScraper, _infer_country_from_event


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestRMLotParser:
    @pytest.fixture
    def parsed(self):
        html = (FIXTURES / "rm_lot.html").read_text()
        scraper = RMSothebysScraper.__new__(RMSothebysScraper)
        return scraper._parse_lot("https://rmsothebys.com/en/auctions/mo25/monterey/lots/r0001", html)

    def test_title(self, parsed):
        assert parsed["title"] == "2021 Ferrari 812 Competizione"

    def test_year(self, parsed):
        assert parsed["year"] == 2021

    def test_sold(self, parsed):
        assert parsed["sold"] is True

    def test_hammer_price(self, parsed):
        assert parsed["hammer_price"] == "725000"

    def test_buyer_premium(self, parsed):
        from decimal import Decimal
        assert "buyer_premium" in parsed
        premium = Decimal(parsed["buyer_premium"])
        assert premium > 0

    def test_total_price(self, parsed):
        from decimal import Decimal
        assert Decimal(parsed["total_price"]) > Decimal(parsed["hammer_price"])

    def test_estimate(self, parsed):
        assert parsed.get("estimate_low") == "650000"
        assert parsed.get("estimate_high") == "750000"

    def test_auction_event(self, parsed):
        assert parsed["auction_event"] == "Monterey 2025"

    def test_catalogue_description(self, parsed):
        assert "Grigio Silverstone" in parsed.get("catalogue_description", "")

    def test_mileage(self, parsed):
        assert parsed.get("mileage") is not None


class TestRMBuyerPremium:
    def test_under_250k(self):
        from decimal import Decimal
        premium = RMSothebysScraper._compute_rm_premium(Decimal("200000"))
        assert premium == Decimal("25000")

    def test_between_250k_and_1m(self):
        from decimal import Decimal
        premium = RMSothebysScraper._compute_rm_premium(Decimal("500000"))
        expected = Decimal("250000") * Decimal("0.125") + Decimal("250000") * Decimal("0.12")
        assert premium == expected

    def test_above_1m(self):
        from decimal import Decimal
        premium = RMSothebysScraper._compute_rm_premium(Decimal("2000000"))
        expected = (
            Decimal("250000") * Decimal("0.125") +
            Decimal("750000") * Decimal("0.12") +
            Decimal("1000000") * Decimal("0.10")
        )
        assert premium == expected


class TestCountryInference:
    def test_monterey(self):
        assert _infer_country_from_event("Monterey 2025") == "US"

    def test_london(self):
        assert _infer_country_from_event("London Evening Sale") == "UK"

    def test_paris(self):
        assert _infer_country_from_event("Paris Rétromobile") == "FR"

    def test_unknown(self):
        assert _infer_country_from_event("Some Random Event") is None
