"""Tests for the comparable transaction valuation model."""

from decimal import Decimal

import numpy as np
import pytest

from aatp.valuation.comparable import weighted_percentiles


class TestWeightedPercentiles:
    def test_uniform_weights_match_standard_percentiles(self):
        values = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        weights = np.ones(5)
        low, mid, high = weighted_percentiles(values, weights, [25, 50, 75])

        assert low == 200.0
        assert mid == 300.0
        assert high == 400.0

    def test_heavy_weight_on_high_value_shifts_percentiles_up(self):
        values = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        weights = np.array([1.0, 1.0, 1.0, 1.0, 10.0])
        _, mid, _ = weighted_percentiles(values, weights, [25, 50, 75])

        assert mid >= 400.0

    def test_heavy_weight_on_low_value_shifts_percentiles_down(self):
        values = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        weights = np.array([10.0, 1.0, 1.0, 1.0, 1.0])
        _, mid, _ = weighted_percentiles(values, weights, [25, 50, 75])

        assert mid <= 200.0

    def test_single_value(self):
        values = np.array([350000.0])
        weights = np.array([1.0])
        low, mid, high = weighted_percentiles(values, weights, [25, 50, 75])

        assert low == 350000.0
        assert mid == 350000.0
        assert high == 350000.0

    def test_two_values(self):
        values = np.array([200000.0, 400000.0])
        weights = np.array([1.0, 1.0])
        low, mid, high = weighted_percentiles(values, weights, [25, 50, 75])

        assert low == 200000.0
        assert high == 400000.0

    def test_unsorted_input(self):
        values = np.array([500.0, 100.0, 300.0, 200.0, 400.0])
        weights = np.ones(5)
        low, mid, high = weighted_percentiles(values, weights, [25, 50, 75])

        assert low == 200.0
        assert mid == 300.0
        assert high == 400.0

    def test_low_always_lte_mid_lte_high(self):
        rng = np.random.default_rng(42)
        for _ in range(20):
            n = rng.integers(3, 30)
            values = rng.uniform(100000, 1000000, size=n)
            weights = rng.uniform(0.1, 5.0, size=n)
            low, mid, high = weighted_percentiles(values, weights, [25, 50, 75])
            assert low <= mid <= high


class TestComparableResultWarnings:
    """Test warning generation logic at the data level."""

    def test_few_comparables_warning_text(self):
        from aatp.valuation.comparable import ComparableTransactionModel
        model = ComparableTransactionModel.__new__(ComparableTransactionModel)

        prices = np.array([300000.0, 350000.0, 400000.0])

        class FakeTx:
            def __init__(self, src):
                self.source = src

        from aatp.db.models import TransactionSource
        txs = [FakeTx(TransactionSource.BRING_A_TRAILER) for _ in range(3)]

        warnings = model._generate_warnings(prices, txs, 12)
        assert any("Only 3 comparables" in w for w in warnings)

    def test_high_dispersion_warning(self):
        from aatp.valuation.comparable import ComparableTransactionModel
        model = ComparableTransactionModel.__new__(ComparableTransactionModel)

        prices = np.array([100000.0, 500000.0, 900000.0, 200000.0, 800000.0])

        class FakeTx:
            def __init__(self, src):
                self.source = src

        from aatp.db.models import TransactionSource
        txs = [
            FakeTx(TransactionSource.BRING_A_TRAILER),
            FakeTx(TransactionSource.RM_SOTHEBYS),
            FakeTx(TransactionSource.BRING_A_TRAILER),
            FakeTx(TransactionSource.RM_SOTHEBYS),
            FakeTx(TransactionSource.BRING_A_TRAILER),
        ]

        warnings = model._generate_warnings(prices, txs, 12)
        assert any("dispersion" in w.lower() for w in warnings)

    def test_single_source_warning(self):
        from aatp.valuation.comparable import ComparableTransactionModel
        model = ComparableTransactionModel.__new__(ComparableTransactionModel)

        prices = np.array([300000.0, 310000.0, 320000.0, 330000.0, 340000.0])

        class FakeTx:
            def __init__(self, src):
                self.source = src

        from aatp.db.models import TransactionSource
        txs = [FakeTx(TransactionSource.BRING_A_TRAILER) for _ in range(5)]

        warnings = model._generate_warnings(prices, txs, 12)
        assert any("single source" in w.lower() for w in warnings)

    def test_widened_window_warning(self):
        from aatp.valuation.comparable import ComparableTransactionModel
        model = ComparableTransactionModel.__new__(ComparableTransactionModel)

        prices = np.array([300000.0, 310000.0, 320000.0, 330000.0, 340000.0])

        class FakeTx:
            def __init__(self, src):
                self.source = src

        from aatp.db.models import TransactionSource
        txs = [
            FakeTx(TransactionSource.BRING_A_TRAILER),
            FakeTx(TransactionSource.RM_SOTHEBYS),
            FakeTx(TransactionSource.BRING_A_TRAILER),
            FakeTx(TransactionSource.RM_SOTHEBYS),
            FakeTx(TransactionSource.BRING_A_TRAILER),
        ]

        warnings = model._generate_warnings(prices, txs, 24)
        assert any("widened" in w.lower() for w in warnings)

    def test_no_warnings_for_good_data(self):
        from aatp.valuation.comparable import ComparableTransactionModel
        model = ComparableTransactionModel.__new__(ComparableTransactionModel)

        prices = np.array([300000.0, 305000.0, 310000.0, 315000.0, 320000.0])

        class FakeTx:
            def __init__(self, src):
                self.source = src

        from aatp.db.models import TransactionSource
        txs = [
            FakeTx(TransactionSource.BRING_A_TRAILER),
            FakeTx(TransactionSource.RM_SOTHEBYS),
            FakeTx(TransactionSource.BRING_A_TRAILER),
            FakeTx(TransactionSource.RM_SOTHEBYS),
            FakeTx(TransactionSource.BRING_A_TRAILER),
        ]

        warnings = model._generate_warnings(prices, txs, 12)
        assert len(warnings) == 0


class TestConfidenceScore:
    def test_high_confidence_scenario(self):
        from datetime import date, timedelta
        from aatp.valuation.comparable import ComparableTransactionModel

        model = ComparableTransactionModel.__new__(ComparableTransactionModel)
        model.half_life_days = 90

        prices = np.array([300000.0, 305000.0, 310000.0, 302000.0, 308000.0,
                           303000.0, 307000.0, 311000.0, 299000.0, 306000.0])
        weights = np.ones(10)
        today = date(2025, 6, 1)

        class FakeTx:
            def __init__(self, src, days_ago):
                self.source = src
                self.transaction_date = today - timedelta(days=days_ago)

        from aatp.db.models import TransactionSource
        txs = [
            FakeTx(TransactionSource.BRING_A_TRAILER, 10),
            FakeTx(TransactionSource.RM_SOTHEBYS, 20),
            FakeTx(TransactionSource.BRING_A_TRAILER, 30),
            FakeTx(TransactionSource.RM_SOTHEBYS, 40),
            FakeTx(TransactionSource.BRING_A_TRAILER, 50),
            FakeTx(TransactionSource.RM_SOTHEBYS, 60),
            FakeTx(TransactionSource.BRING_A_TRAILER, 70),
            FakeTx(TransactionSource.RM_SOTHEBYS, 80),
            FakeTx(TransactionSource.BRING_A_TRAILER, 90),
            FakeTx(TransactionSource.RM_SOTHEBYS, 100),
        ]

        score = model._confidence_score(prices, weights, txs, today)
        assert score > 0.7

    def test_low_confidence_few_old_transactions(self):
        from datetime import date, timedelta
        from aatp.valuation.comparable import ComparableTransactionModel

        model = ComparableTransactionModel.__new__(ComparableTransactionModel)
        model.half_life_days = 90

        prices = np.array([200000.0, 500000.0, 100000.0])
        weights = np.ones(3)
        today = date(2025, 6, 1)

        class FakeTx:
            def __init__(self, src, days_ago):
                self.source = src
                self.transaction_date = today - timedelta(days=days_ago)

        from aatp.db.models import TransactionSource
        txs = [
            FakeTx(TransactionSource.BRING_A_TRAILER, 300),
            FakeTx(TransactionSource.BRING_A_TRAILER, 320),
            FakeTx(TransactionSource.BRING_A_TRAILER, 340),
        ]

        score = model._confidence_score(prices, weights, txs, today)
        assert score < 0.4
