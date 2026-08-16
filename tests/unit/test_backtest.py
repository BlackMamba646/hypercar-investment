"""Tests for the backtesting environment -- Module 10.

Tests all pure-function logic: metrics, walk-forward window generation,
look-ahead bias detection, signal accuracy, return metrics, and weight
stability assessment.  No database required.
"""

from datetime import date
from decimal import Decimal

import pytest

from aatp.research.metrics import (
    accuracy_rate,
    f1_score,
    false_positive_rate,
    information_ratio,
    max_drawdown,
    per_model_validation,
    precision,
    recall,
    sharpe_ratio,
)
from aatp.research.walk_forward import (
    DateRange,
    assess_weight_stability,
    evaluate_window,
    generate_windows,
)
from aatp.research.backtest_runner import (
    check_look_ahead_bias,
    compute_return_metrics,
    compute_signal_accuracy,
)


# ---------------------------------------------------------------------------
# accuracy_rate
# ---------------------------------------------------------------------------

class TestAccuracyRate:
    def test_perfect_accuracy(self):
        assert accuracy_rate([1, -1, 0], [1, -1, 0]) == Decimal("1.000")

    def test_all_wrong(self):
        assert accuracy_rate([1, 1, 1], [-1, -1, -1]) == Decimal("0.000")

    def test_partial_accuracy(self):
        assert accuracy_rate([1, -1, 1, -1], [1, 1, 1, 1]) == Decimal("0.500")

    def test_empty_predictions(self):
        assert accuracy_rate([], []) == Decimal("0")

    def test_mismatched_lengths(self):
        assert accuracy_rate([1, -1], [1]) == Decimal("0")

    def test_single_correct(self):
        assert accuracy_rate([1], [1]) == Decimal("1.000")

    def test_single_incorrect(self):
        assert accuracy_rate([1], [-1]) == Decimal("0.000")


# ---------------------------------------------------------------------------
# precision
# ---------------------------------------------------------------------------

class TestPrecision:
    def test_perfect_precision(self):
        assert precision(5, 0) == Decimal("1.000")

    def test_zero_precision(self):
        assert precision(0, 5) == Decimal("0.000")

    def test_fifty_percent(self):
        assert precision(3, 3) == Decimal("0.500")

    def test_no_positives(self):
        assert precision(0, 0) == Decimal("0")


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------

class TestRecall:
    def test_perfect_recall(self):
        assert recall(5, 0) == Decimal("1.000")

    def test_zero_recall(self):
        assert recall(0, 5) == Decimal("0.000")

    def test_no_actual_positives(self):
        assert recall(0, 0) == Decimal("0")


# ---------------------------------------------------------------------------
# f1_score
# ---------------------------------------------------------------------------

class TestF1Score:
    def test_perfect_f1(self):
        assert f1_score(Decimal("1.000"), Decimal("1.000")) == Decimal("1.000")

    def test_zero_f1(self):
        assert f1_score(Decimal("0"), Decimal("0")) == Decimal("0")

    def test_harmonic_mean(self):
        # precision=0.8, recall=0.6 => F1 = 2*0.8*0.6/(0.8+0.6) = 0.685714...
        result = f1_score(Decimal("0.800"), Decimal("0.600"))
        assert result == Decimal("0.686")

    def test_one_zero(self):
        assert f1_score(Decimal("0.900"), Decimal("0")) == Decimal("0")


# ---------------------------------------------------------------------------
# false_positive_rate
# ---------------------------------------------------------------------------

class TestFalsePositiveRate:
    def test_no_false_positives(self):
        assert false_positive_rate(0, 10) == Decimal("0.000")

    def test_all_false_positives(self):
        assert false_positive_rate(5, 0) == Decimal("1.000")

    def test_fifty_percent_fpr(self):
        assert false_positive_rate(5, 5) == Decimal("0.500")

    def test_zero_denominator(self):
        assert false_positive_rate(0, 0) == Decimal("0")


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------

class TestSharpeRatio:
    def test_zero_std_returns_zero(self):
        # All identical returns => std = 0
        returns = [Decimal("0.01")] * 12
        assert sharpe_ratio(returns) == Decimal("0")

    def test_single_return_returns_zero(self):
        assert sharpe_ratio([Decimal("0.05")]) == Decimal("0")

    def test_empty_returns_zero(self):
        assert sharpe_ratio([]) == Decimal("0")

    def test_positive_returns_positive_sharpe(self):
        # All returns well above risk-free rate
        returns = [Decimal("0.02")] * 6 + [Decimal("0.03")] * 6
        result = sharpe_ratio(returns, risk_free_rate=Decimal("0.04"))
        assert result > Decimal("0")

    def test_negative_returns_negative_sharpe(self):
        # All returns below risk-free rate
        returns = [Decimal("-0.05"), Decimal("-0.03"), Decimal("-0.04"), Decimal("-0.02")]
        result = sharpe_ratio(returns, risk_free_rate=Decimal("0.04"))
        assert result < Decimal("0")

    def test_custom_risk_free_rate(self):
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")]
        r1 = sharpe_ratio(returns, risk_free_rate=Decimal("0.00"))
        r2 = sharpe_ratio(returns, risk_free_rate=Decimal("0.10"))
        # Lower risk-free => higher Sharpe
        assert r1 > r2


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_no_drawdown(self):
        cum = [Decimal("1"), Decimal("1.1"), Decimal("1.2"), Decimal("1.3")]
        assert max_drawdown(cum) == Decimal("0.000")

    def test_simple_drawdown(self):
        # Peak at 1.0, trough at 0.8 => 20% drawdown
        cum = [Decimal("1.0"), Decimal("0.8")]
        assert max_drawdown(cum) == Decimal("0.200")

    def test_multiple_drawdowns_returns_worst(self):
        cum = [
            Decimal("1.0"),
            Decimal("0.9"),   # 10% dd
            Decimal("1.1"),   # new peak
            Decimal("0.8"),   # 27.3% dd from 1.1
        ]
        result = max_drawdown(cum)
        # (1.1 - 0.8) / 1.1 = 0.2727...
        assert result == Decimal("0.273")

    def test_empty_returns_zero(self):
        assert max_drawdown([]) == Decimal("0")

    def test_single_value_no_drawdown(self):
        assert max_drawdown([Decimal("1.0")]) == Decimal("0.000")

    def test_continuously_declining(self):
        cum = [Decimal("1.0"), Decimal("0.9"), Decimal("0.7"), Decimal("0.5")]
        # Peak = 1.0, trough = 0.5 => 50%
        assert max_drawdown(cum) == Decimal("0.500")


# ---------------------------------------------------------------------------
# information_ratio
# ---------------------------------------------------------------------------

class TestInformationRatio:
    def test_positive_active_returns(self):
        result = information_ratio(
            [Decimal("0.02"), Decimal("0.04"), Decimal("0.03")],
            Decimal("0.01"),
        )
        assert result > Decimal("0")

    def test_zero_tracking_error(self):
        assert information_ratio([Decimal("0.01")], Decimal("0")) == Decimal("0")

    def test_empty_returns(self):
        assert information_ratio([], Decimal("0.05")) == Decimal("0")

    def test_negative_active_returns(self):
        result = information_ratio(
            [Decimal("-0.02"), Decimal("-0.03")],
            Decimal("0.01"),
        )
        assert result < Decimal("0")


# ---------------------------------------------------------------------------
# per_model_validation
# ---------------------------------------------------------------------------

class TestPerModelValidation:
    def test_perfect_model(self):
        preds = {"momentum": [(1, 1), (1, 1), (-1, -1)]}
        result = per_model_validation(preds)
        assert result["momentum"]["accuracy"] == Decimal("1.000")

    def test_empty_model(self):
        preds = {"momentum": []}
        result = per_model_validation(preds)
        assert result["momentum"]["accuracy"] == Decimal("0")
        assert result["momentum"]["f1"] == Decimal("0")

    def test_multiple_models(self):
        preds = {
            "momentum": [(1, 1), (1, -1)],
            "fundamental": [(1, 1), (1, 1), (-1, -1)],
        }
        result = per_model_validation(preds)
        assert "momentum" in result
        assert "fundamental" in result
        assert result["fundamental"]["accuracy"] > result["momentum"]["accuracy"]


# ---------------------------------------------------------------------------
# check_look_ahead_bias
# ---------------------------------------------------------------------------

class TestCheckLookAheadBias:
    def test_no_bias_all_past(self):
        assert check_look_ahead_bias(
            date(2024, 6, 1),
            [date(2024, 1, 1), date(2024, 3, 15), date(2024, 5, 30)],
        ) is False

    def test_bias_detected_future_date(self):
        assert check_look_ahead_bias(
            date(2024, 6, 1),
            [date(2024, 1, 1), date(2024, 7, 1)],
        ) is True

    def test_same_date_no_bias(self):
        assert check_look_ahead_bias(
            date(2024, 6, 1),
            [date(2024, 6, 1)],
        ) is False

    def test_empty_data_dates_no_bias(self):
        assert check_look_ahead_bias(date(2024, 6, 1), []) is False

    def test_single_future_date(self):
        assert check_look_ahead_bias(
            date(2024, 6, 1),
            [date(2025, 1, 1)],
        ) is True


# ---------------------------------------------------------------------------
# compute_signal_accuracy
# ---------------------------------------------------------------------------

class TestComputeSignalAccuracy:
    def test_all_correct(self):
        preds = [
            {"predicted_direction": 1, "was_correct": True},
            {"predicted_direction": -1, "was_correct": True},
        ]
        result = compute_signal_accuracy(preds)
        assert result["accuracy"] == Decimal("1.000")
        assert result["correct"] == 2
        assert result["incorrect"] == 0

    def test_all_incorrect(self):
        preds = [
            {"predicted_direction": 1, "was_correct": False},
            {"predicted_direction": 1, "was_correct": False},
        ]
        result = compute_signal_accuracy(preds)
        assert result["accuracy"] == Decimal("0.000")
        assert result["correct"] == 0

    def test_mixed(self):
        preds = [
            {"predicted_direction": 1, "was_correct": True},
            {"predicted_direction": 1, "was_correct": False},
            {"predicted_direction": -1, "was_correct": True},
            {"predicted_direction": -1, "was_correct": False},
        ]
        result = compute_signal_accuracy(preds)
        assert result["accuracy"] == Decimal("0.500")

    def test_unevaluated_skipped(self):
        preds = [
            {"predicted_direction": 1, "was_correct": True},
            {"predicted_direction": 1, "was_correct": None},
        ]
        result = compute_signal_accuracy(preds)
        assert result["total"] == 2
        assert result["evaluated"] == 1
        assert result["accuracy"] == Decimal("1.000")

    def test_empty_predictions(self):
        result = compute_signal_accuracy([])
        assert result["total"] == 0
        assert result["evaluated"] == 0
        assert result["accuracy"] == Decimal("0")

    def test_all_unevaluated(self):
        preds = [
            {"predicted_direction": 1, "was_correct": None},
            {"predicted_direction": -1, "was_correct": None},
        ]
        result = compute_signal_accuracy(preds)
        assert result["evaluated"] == 0
        assert result["accuracy"] == Decimal("0")


# ---------------------------------------------------------------------------
# compute_return_metrics
# ---------------------------------------------------------------------------

class TestComputeReturnMetrics:
    def test_basic_stats(self):
        returns = [Decimal("0.10"), Decimal("0.20"), Decimal("0.30")]
        result = compute_return_metrics(returns)
        assert result["avg"] == Decimal("0.200")
        assert result["median"] == Decimal("0.200")
        assert result["min"] == Decimal("0.100")
        assert result["max"] == Decimal("0.300")
        assert result["count"] == 3

    def test_empty_returns(self):
        result = compute_return_metrics([])
        assert result["avg"] == Decimal("0")
        assert result["count"] == 0

    def test_single_return(self):
        result = compute_return_metrics([Decimal("0.15")])
        assert result["avg"] == Decimal("0.150")
        assert result["median"] == Decimal("0.150")
        assert result["std"] == Decimal("0")
        assert result["count"] == 1

    def test_even_number_median(self):
        # median of [0.10, 0.20, 0.30, 0.40] = (0.20 + 0.30) / 2 = 0.25
        returns = [Decimal("0.10"), Decimal("0.20"), Decimal("0.30"), Decimal("0.40")]
        result = compute_return_metrics(returns)
        assert result["median"] == Decimal("0.250")

    def test_negative_returns(self):
        returns = [Decimal("-0.10"), Decimal("-0.20"), Decimal("-0.30")]
        result = compute_return_metrics(returns)
        assert result["avg"] == Decimal("-0.200")
        assert result["min"] == Decimal("-0.300")
        assert result["max"] == Decimal("-0.100")


# ---------------------------------------------------------------------------
# generate_windows
# ---------------------------------------------------------------------------

class TestGenerateWindows:
    def test_basic_window_generation(self):
        windows = generate_windows(
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
            train_months=12,
            test_months=6,
        )
        assert len(windows) > 0
        for train, test in windows:
            assert train.start < train.end
            assert test.start < test.end
            assert train.end < test.start

    def test_train_precedes_test(self):
        windows = generate_windows(
            date(2020, 1, 1), date(2022, 12, 31), 12, 6,
        )
        for train, test in windows:
            assert train.end < test.start

    def test_windows_slide_forward(self):
        windows = generate_windows(
            date(2020, 1, 1), date(2023, 12, 31), 12, 6,
        )
        for i in range(1, len(windows)):
            assert windows[i][0].start > windows[i - 1][0].start

    def test_no_test_past_end_date(self):
        windows = generate_windows(
            date(2020, 1, 1), date(2021, 12, 31), 12, 6,
        )
        for _, test in windows:
            assert test.end <= date(2021, 12, 31)

    def test_short_range_no_windows(self):
        # 6 months is not enough for 12-month train + 6-month test
        windows = generate_windows(
            date(2020, 1, 1), date(2020, 6, 30), 12, 6,
        )
        assert windows == []

    def test_zero_train_months(self):
        assert generate_windows(date(2020, 1, 1), date(2023, 1, 1), 0, 6) == []

    def test_zero_test_months(self):
        assert generate_windows(date(2020, 1, 1), date(2023, 1, 1), 12, 0) == []

    def test_exact_fit(self):
        # 12 train + 6 test = 18 months.  Range is exactly 18 months.
        windows = generate_windows(
            date(2020, 1, 1), date(2021, 6, 30), 12, 6,
        )
        assert len(windows) == 1
        assert windows[0][0].start == date(2020, 1, 1)


# ---------------------------------------------------------------------------
# evaluate_window
# ---------------------------------------------------------------------------

class TestEvaluateWindow:
    def test_perfect_train_and_test(self):
        train = [(1, 1), (-1, -1), (0, 0)]
        test = [(1, 1), (-1, -1)]
        result = evaluate_window(train, test)
        assert result["train_accuracy"] == Decimal("1.000")
        assert result["test_accuracy"] == Decimal("1.000")
        assert result["overfit_gap"] == Decimal("0.000")

    def test_overfit_detected(self):
        train = [(1, 1), (1, 1), (1, 1)]  # 100% train
        test = [(1, -1), (1, -1), (1, -1)]  # 0% test
        result = evaluate_window(train, test)
        assert result["overfit_gap"] == Decimal("1.000")

    def test_empty_sets(self):
        result = evaluate_window([], [])
        assert result["train_accuracy"] == Decimal("0")
        assert result["test_accuracy"] == Decimal("0")


# ---------------------------------------------------------------------------
# assess_weight_stability
# ---------------------------------------------------------------------------

class TestAssessWeightStability:
    def test_identical_weights_stable(self):
        windows = [
            {"momentum": Decimal("0.30"), "fundamental": Decimal("0.70")},
            {"momentum": Decimal("0.30"), "fundamental": Decimal("0.70")},
            {"momentum": Decimal("0.30"), "fundamental": Decimal("0.70")},
        ]
        result = assess_weight_stability(windows)
        assert result["stability_score"] == Decimal("1.000")
        assert result["is_stable"] is True

    def test_wildly_varying_weights_unstable(self):
        windows = [
            {"momentum": Decimal("0.10"), "fundamental": Decimal("0.90")},
            {"momentum": Decimal("0.90"), "fundamental": Decimal("0.10")},
        ]
        result = assess_weight_stability(windows)
        assert result["is_stable"] is False

    def test_empty_windows(self):
        result = assess_weight_stability([])
        assert result["stability_score"] == Decimal("0")
        assert result["is_stable"] is False

    def test_single_window_stable(self):
        windows = [{"momentum": Decimal("0.50")}]
        result = assess_weight_stability(windows)
        assert result["stability_score"] == Decimal("1.000")
        assert result["is_stable"] is True

    def test_moderate_variation(self):
        windows = [
            {"momentum": Decimal("0.30")},
            {"momentum": Decimal("0.35")},
            {"momentum": Decimal("0.28")},
        ]
        result = assess_weight_stability(windows)
        # Small variation => fairly stable
        assert result["stability_score"] > Decimal("0.5")

    def test_mean_weights_computed(self):
        windows = [
            {"momentum": Decimal("0.20"), "fundamental": Decimal("0.80")},
            {"momentum": Decimal("0.40"), "fundamental": Decimal("0.60")},
        ]
        result = assess_weight_stability(windows)
        assert result["mean_weights"]["momentum"] == Decimal("0.300")
        assert result["mean_weights"]["fundamental"] == Decimal("0.700")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_sharpe_two_identical_returns(self):
        """Two identical returns => std=0 => Sharpe=0."""
        assert sharpe_ratio([Decimal("0.05"), Decimal("0.05")]) == Decimal("0")

    def test_max_drawdown_all_zeros(self):
        assert max_drawdown([Decimal("0"), Decimal("0")]) == Decimal("0")

    def test_accuracy_with_all_zero_directions(self):
        """All neutral predictions matching all neutral actuals."""
        assert accuracy_rate([0, 0, 0], [0, 0, 0]) == Decimal("1.000")

    def test_f1_with_extreme_precision_recall_gap(self):
        # precision=1.0, recall=0.001
        result = f1_score(Decimal("1.000"), Decimal("0.001"))
        # F1 should be very small
        assert result < Decimal("0.010")

    def test_precision_recall_f1_roundtrip(self):
        """Compute TP/FP/FN -> precision -> recall -> F1 in sequence."""
        tp, fp, fn = 8, 2, 3
        p = precision(tp, fp)
        r = recall(tp, fn)
        f = f1_score(p, r)
        assert p == Decimal("0.800")
        assert r == Decimal("0.727")
        assert f > Decimal("0.700")

    def test_check_look_ahead_single_past_date(self):
        assert check_look_ahead_bias(
            date(2024, 12, 31),
            [date(2024, 1, 1)],
        ) is False

    def test_compute_return_metrics_all_same(self):
        returns = [Decimal("0.05")] * 5
        result = compute_return_metrics(returns)
        assert result["avg"] == Decimal("0.050")
        assert result["median"] == Decimal("0.050")
        assert result["std"] == Decimal("0.000")

    def test_information_ratio_exact(self):
        # mean = 0.03, tracking_error = 0.01 => IR = 3.0
        result = information_ratio(
            [Decimal("0.03"), Decimal("0.03"), Decimal("0.03")],
            Decimal("0.01"),
        )
        assert result == Decimal("3.000")
