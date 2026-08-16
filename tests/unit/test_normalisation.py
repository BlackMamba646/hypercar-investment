"""Tests for the normalisation pipeline logic."""

from decimal import Decimal

import pytest

from aatp.collectors.normalisation import (
    COLOUR_TIER_ADJUSTMENTS,
    CONDITION_ADJUSTMENTS,
    DEFAULT_MILEAGE_BANDS,
    NormalisationPipeline,
    _grade_condition_from_text,
)
from aatp.db.models import ColourTier, ConditionGrade


class TestMileageBands:
    def test_delivery_miles_premium(self):
        for lower, upper, adj in DEFAULT_MILEAGE_BANDS:
            if lower <= 200 < upper:
                assert adj > 0, "Delivery miles should command a premium"
                break

    def test_baseline_is_zero(self):
        for lower, upper, adj in DEFAULT_MILEAGE_BANDS:
            if lower <= 4000 < upper:
                assert adj == 0, "3000-5000 miles is baseline"
                break

    def test_high_mileage_discount(self):
        for lower, upper, adj in DEFAULT_MILEAGE_BANDS:
            if lower <= 25000 < upper:
                assert adj < 0, "High mileage should be discounted"
                break

    def test_bands_are_contiguous(self):
        for i in range(len(DEFAULT_MILEAGE_BANDS) - 1):
            assert DEFAULT_MILEAGE_BANDS[i][1] == DEFAULT_MILEAGE_BANDS[i + 1][0]


class TestColourTierAdjustments:
    def test_tier_1_neutral(self):
        assert COLOUR_TIER_ADJUSTMENTS[ColourTier.TIER_1] == Decimal("0")

    def test_tier_2_discount(self):
        assert COLOUR_TIER_ADJUSTMENTS[ColourTier.TIER_2] < Decimal("0")

    def test_tier_3_heavy_discount(self):
        assert COLOUR_TIER_ADJUSTMENTS[ColourTier.TIER_3] < COLOUR_TIER_ADJUSTMENTS[ColourTier.TIER_2]


class TestConditionAdjustments:
    def test_concours_premium(self):
        assert CONDITION_ADJUSTMENTS[ConditionGrade.CONCOURS] > Decimal("0")

    def test_good_is_baseline(self):
        assert CONDITION_ADJUSTMENTS[ConditionGrade.GOOD] == Decimal("0")

    def test_project_heavy_discount(self):
        assert CONDITION_ADJUSTMENTS[ConditionGrade.PROJECT] < Decimal("-20")


class TestConditionNLP:
    def test_concours_keywords(self):
        assert _grade_condition_from_text("this is a concours quality restoration") == ConditionGrade.CONCOURS

    def test_excellent_keywords(self):
        assert _grade_condition_from_text("the car is in excellent condition throughout") == ConditionGrade.EXCELLENT

    def test_pristine(self):
        assert _grade_condition_from_text("a pristine example with low miles") == ConditionGrade.EXCELLENT

    def test_good_keywords(self):
        assert _grade_condition_from_text("a nice example in good condition") == ConditionGrade.GOOD

    def test_fair_keywords(self):
        assert _grade_condition_from_text("fair condition with some wear") == ConditionGrade.FAIR

    def test_project_keywords(self):
        assert _grade_condition_from_text("barn find project car needs restoration") == ConditionGrade.PROJECT

    def test_no_keywords(self):
        assert _grade_condition_from_text("a car for sale by owner") is None

    def test_negative_takes_priority(self):
        # If description mentions both damage and excellent, damage wins
        result = _grade_condition_from_text("needs restoration but was once excellent")
        assert result in (ConditionGrade.PROJECT, ConditionGrade.FAIR)
