"""Tests for the appreciation curve model and stage classification."""

from decimal import Decimal

import pytest

from aatp.valuation.appreciation import classify_stage, _to_decimal


class TestClassifyStage:
    def test_correction_negative_90d(self):
        assert classify_stage(rate_30d=-0.10, rate_90d=-0.05, rate_365d=0.10, comparable_count=20) == "correction"

    def test_discovery_low_volume_positive_365d(self):
        assert classify_stage(rate_30d=0.02, rate_90d=0.06, rate_365d=0.08, comparable_count=5) == "discovery"

    def test_acceleration_high_90d(self):
        assert classify_stage(rate_30d=0.10, rate_90d=0.20, rate_365d=0.15, comparable_count=20) == "acceleration"

    def test_plateau_flat_90d(self):
        assert classify_stage(rate_30d=0.01, rate_90d=0.02, rate_365d=0.03, comparable_count=20) == "plateau"

    def test_no_data_returns_none(self):
        assert classify_stage(rate_30d=None, rate_90d=None, rate_365d=None, comparable_count=0) is None

    def test_only_365d_positive(self):
        result = classify_stage(rate_30d=None, rate_90d=None, rate_365d=0.10, comparable_count=20)
        assert result == "acceleration"

    def test_only_365d_flat(self):
        result = classify_stage(rate_30d=None, rate_90d=None, rate_365d=0.02, comparable_count=20)
        assert result == "plateau"

    def test_only_365d_negative(self):
        result = classify_stage(rate_30d=None, rate_90d=None, rate_365d=-0.10, comparable_count=20)
        assert result == "correction"

    def test_correction_overrides_discovery(self):
        result = classify_stage(rate_30d=-0.05, rate_90d=-0.10, rate_365d=0.08, comparable_count=5)
        assert result == "correction"

    def test_valid_stage_values(self):
        for stage in [
            classify_stage(0.0, -0.1, 0.1, 20),
            classify_stage(0.0, 0.2, 0.1, 20),
            classify_stage(0.0, 0.01, 0.02, 20),
            classify_stage(0.0, 0.05, 0.06, 5),
        ]:
            assert stage in ("discovery", "acceleration", "plateau", "correction")


class TestToDecimal:
    def test_none_returns_none(self):
        assert _to_decimal(None) is None

    def test_positive_float(self):
        result = _to_decimal(0.1234567)
        assert result == Decimal("0.1235")

    def test_negative_float(self):
        result = _to_decimal(-0.05)
        assert result == Decimal("-0.05")

    def test_zero(self):
        result = _to_decimal(0.0)
        assert result == Decimal("0.0")
