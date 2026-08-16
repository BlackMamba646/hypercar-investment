"""Tests for the asset model matcher."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from aatp.collectors.model_matcher import AssetModelMatcher, _CachedModel


def _make_model(name, variant=None, manufacturer="Ferrari", year_start=2018, year_end=2022):
    return _CachedModel(
        id=uuid.uuid4(),
        manufacturer_name=manufacturer,
        name=name,
        variant=variant,
        name_lower=name.lower(),
        variant_lower=variant.lower() if variant else None,
        tokens={manufacturer.lower()} | set(name.lower().split()) | (set(variant.lower().split()) if variant else set()),
        production_year_start=year_start,
        production_year_end=year_end,
    )


@pytest.fixture
def matcher():
    m = AssetModelMatcher.__new__(AssetModelMatcher)
    m.db = MagicMock()
    m._cache = [
        _make_model("488 Pista", None),
        _make_model("488 Pista", "Spider"),
        _make_model("812 Superfast", None, year_start=2017),
        _make_model("812 Superfast", "GTS", year_start=2019),
        _make_model("LaFerrari", None, year_start=2013, year_end=2016),
        _make_model("LaFerrari", "Aperta", year_start=2016, year_end=2018),
        _make_model("Chiron", "Super Sport", manufacturer="Bugatti", year_start=2021),
        _make_model("Senna", None, manufacturer="McLaren", year_start=2018, year_end=2020),
    ]
    return m


class TestExactMatching:
    @pytest.mark.asyncio
    async def test_exact_model_and_variant(self, matcher):
        result = await matcher.match("2019 Ferrari 488 Pista Spider")
        assert result is not None
        assert result.variant == "Spider"
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_exact_model_no_variant(self, matcher):
        result = await matcher.match("2019 Ferrari 488 Pista")
        assert result is not None
        assert result.variant is None
        assert result.confidence >= 0.5

    @pytest.mark.asyncio
    async def test_gts_variant(self, matcher):
        result = await matcher.match("2020 Ferrari 812 GTS")
        assert result is not None
        assert result.variant == "GTS"

    @pytest.mark.asyncio
    async def test_laferrari_aperta(self, matcher):
        result = await matcher.match("2017 Ferrari LaFerrari Aperta")
        assert result is not None
        assert result.variant == "Aperta"
        assert result.confidence >= 0.9


class TestManufacturerFiltering:
    @pytest.mark.asyncio
    async def test_bugatti(self, matcher):
        result = await matcher.match("2021 Bugatti Chiron Super Sport")
        assert result is not None
        assert result.manufacturer_name == "Bugatti"
        assert result.variant == "Super Sport"

    @pytest.mark.asyncio
    async def test_mclaren(self, matcher):
        result = await matcher.match("2019 McLaren Senna")
        assert result is not None
        assert result.manufacturer_name == "McLaren"


class TestYearFiltering:
    @pytest.mark.asyncio
    async def test_year_in_range(self, matcher):
        result = await matcher.match("2019 Ferrari 488 Pista Spider")
        assert result is not None

    @pytest.mark.asyncio
    async def test_year_out_of_range(self, matcher):
        result = await matcher.match("2010 Ferrari 488 Pista")
        assert result is None


class TestNoMatch:
    @pytest.mark.asyncio
    async def test_unknown_model(self, matcher):
        result = await matcher.match("2022 Toyota Corolla")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_string(self, matcher):
        result = await matcher.match("")
        assert result is None
