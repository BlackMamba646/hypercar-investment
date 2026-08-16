"""Tests for the signal engine -- Module 4.

Tests each signal generator's pure calculation logic (no DB) and the
composite scoring / threshold logic.
"""

from decimal import Decimal

import pytest

from aatp.signals.momentum import compute_momentum, DEVIATION_THRESHOLD
from aatp.signals.spread import compute_spread, MIN_SPREAD_PCT
from aatp.signals.catalyst import compute_catalyst, CATALYST_WINDOW_DAYS
from aatp.signals.volume import compute_volume_spike, SPIKE_MULTIPLIER, MIN_AVERAGE_VOLUME
from aatp.signals.comparable import compute_comparable_appreciation, MIN_APPRECIATION_PCT
from aatp.signals.pattern import compute_open_top_lag, OPEN_TOP_LAG_THRESHOLD, COUPE_APPRECIATION_THRESHOLD
from aatp.signals.scanner import (
    compute_composite_score,
    ScoringInput,
    SIGNAL_WEIGHTS,
    ACTIONABLE_THRESHOLD,
    WATCHLIST_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Momentum signal tests
# ---------------------------------------------------------------------------

class TestComputeMomentum:
    def test_no_data_returns_not_triggered(self):
        result = compute_momentum(None, None, None, None, 0)
        assert result.triggered is False
        assert result.direction == 0
        assert result.strength == Decimal("0")

    def test_zero_fair_value_returns_not_triggered(self):
        result = compute_momentum(Decimal("100000"), Decimal("0"), None, None, 5)
        assert result.triggered is False

    def test_within_threshold_not_triggered(self):
        # 3% deviation (below 5% threshold)
        result = compute_momentum(
            current_price=Decimal("103000"),
            fair_value_mid=Decimal("100000"),
            appreciation_rate_30d=Decimal("0.02"),
            appreciation_rate_90d=Decimal("0.03"),
            transaction_count=10,
        )
        assert result.triggered is False
        assert result.direction == 0

    def test_positive_deviation_triggers(self):
        # 10% above fair value
        result = compute_momentum(
            current_price=Decimal("110000"),
            fair_value_mid=Decimal("100000"),
            appreciation_rate_30d=Decimal("0.05"),
            appreciation_rate_90d=Decimal("0.08"),
            transaction_count=10,
        )
        assert result.triggered is True
        assert result.direction == 1
        assert result.strength > Decimal("0")
        assert result.confidence > Decimal("0")

    def test_negative_deviation_triggers(self):
        # 10% below fair value
        result = compute_momentum(
            current_price=Decimal("90000"),
            fair_value_mid=Decimal("100000"),
            appreciation_rate_30d=Decimal("-0.05"),
            appreciation_rate_90d=Decimal("-0.08"),
            transaction_count=8,
        )
        assert result.triggered is True
        assert result.direction == -1

    def test_strength_capped_at_one(self):
        # 50% deviation (well beyond 30% cap)
        result = compute_momentum(
            current_price=Decimal("150000"),
            fair_value_mid=Decimal("100000"),
            appreciation_rate_30d=Decimal("0.20"),
            appreciation_rate_90d=Decimal("0.30"),
            transaction_count=20,
        )
        assert result.triggered is True
        assert result.strength <= Decimal("1")

    def test_confidence_increases_with_transactions(self):
        result_low = compute_momentum(
            Decimal("112000"), Decimal("100000"), Decimal("0.05"), Decimal("0.08"), 2
        )
        result_high = compute_momentum(
            Decimal("112000"), Decimal("100000"), Decimal("0.05"), Decimal("0.08"), 15
        )
        assert result_low.triggered is True
        assert result_high.triggered is True
        assert result_high.confidence >= result_low.confidence

    def test_confidence_boosted_by_agreeing_windows(self):
        # Both windows positive
        result_agree = compute_momentum(
            Decimal("110000"), Decimal("100000"),
            Decimal("0.05"), Decimal("0.08"), 5
        )
        # Windows disagree
        result_disagree = compute_momentum(
            Decimal("110000"), Decimal("100000"),
            Decimal("0.05"), Decimal("-0.02"), 5
        )
        assert result_agree.confidence >= result_disagree.confidence


# ---------------------------------------------------------------------------
# Spread signal tests
# ---------------------------------------------------------------------------

class TestComputeSpread:
    def test_no_data_not_triggered(self):
        result = compute_spread(None, None, 0, 0)
        assert result.triggered is False

    def test_zero_auction_price_not_triggered(self):
        result = compute_spread(Decimal("100000"), Decimal("0"), 5, 0)
        assert result.triggered is False

    def test_small_spread_not_triggered(self):
        # 5% spread (below 10% threshold)
        result = compute_spread(
            avg_dealer_price=Decimal("105000"),
            avg_auction_price=Decimal("100000"),
            dealer_count=5,
            auction_count=5,
        )
        assert result.triggered is False

    def test_large_positive_spread_triggers(self):
        # 20% dealer premium
        result = compute_spread(
            avg_dealer_price=Decimal("120000"),
            avg_auction_price=Decimal("100000"),
            dealer_count=5,
            auction_count=5,
        )
        assert result.triggered is True
        assert result.direction == 1
        assert result.spread_pct == Decimal("0.200")

    def test_negative_spread_triggers(self):
        # Auction > dealer by 15%
        result = compute_spread(
            avg_dealer_price=Decimal("85000"),
            avg_auction_price=Decimal("100000"),
            dealer_count=3,
            auction_count=3,
        )
        assert result.triggered is True
        assert result.direction == -1

    def test_strength_proportional_to_spread(self):
        result_small = compute_spread(
            Decimal("112000"), Decimal("100000"), 5, 5
        )
        result_large = compute_spread(
            Decimal("130000"), Decimal("100000"), 5, 5
        )
        assert result_small.triggered is True
        assert result_large.triggered is True
        assert result_large.strength > result_small.strength


# ---------------------------------------------------------------------------
# Catalyst signal tests
# ---------------------------------------------------------------------------

class TestComputeCatalyst:
    def test_no_events_not_triggered(self):
        result = compute_catalyst(
            has_upcoming_auction=False,
            days_to_auction=None,
            auction_name=None,
            is_flagship_auction=False,
            has_import_eligibility=False,
            days_to_eligibility=None,
            estimated_price_impact_pct=None,
        )
        assert result.triggered is False

    def test_auction_event_triggers(self):
        result = compute_catalyst(
            has_upcoming_auction=True,
            days_to_auction=30,
            auction_name="Monterey Car Week",
            is_flagship_auction=True,
            has_import_eligibility=False,
            days_to_eligibility=None,
            estimated_price_impact_pct=None,
        )
        assert result.triggered is True
        assert result.direction == 1
        assert result.catalyst_type == "auction_event"
        assert "Monterey Car Week" in result.description

    def test_import_eligibility_triggers(self):
        result = compute_catalyst(
            has_upcoming_auction=False,
            days_to_auction=None,
            auction_name=None,
            is_flagship_auction=False,
            has_import_eligibility=True,
            days_to_eligibility=45,
            estimated_price_impact_pct=Decimal("15"),
        )
        assert result.triggered is True
        assert result.direction == 1
        assert result.catalyst_type == "import_eligibility"

    def test_closer_event_stronger_signal(self):
        result_far = compute_catalyst(
            True, 80, "Distant Sale", False, False, None, None
        )
        result_near = compute_catalyst(
            True, 10, "Near Sale", False, False, None, None
        )
        assert result_near.strength > result_far.strength

    def test_flagship_stronger_than_regular(self):
        result_reg = compute_catalyst(
            True, 30, "Regular Sale", False, False, None, None
        )
        result_flag = compute_catalyst(
            True, 30, "Flagship Sale", True, False, None, None
        )
        assert result_flag.strength > result_reg.strength

    def test_both_catalysts_picks_strongest(self):
        result = compute_catalyst(
            has_upcoming_auction=True,
            days_to_auction=10,
            auction_name="Big Auction",
            is_flagship_auction=True,
            has_import_eligibility=True,
            days_to_eligibility=80,
            estimated_price_impact_pct=Decimal("5"),
        )
        assert result.triggered is True
        # Auction at 10 days should be stronger than eligibility at 80 days
        assert result.catalyst_type == "auction_event"


# ---------------------------------------------------------------------------
# Volume spike tests
# ---------------------------------------------------------------------------

class TestComputeVolumeSpike:
    def test_low_historical_average_not_triggered(self):
        result = compute_volume_spike(recent_count=2, historical_avg_per_period=Decimal("0.5"))
        assert result.triggered is False

    def test_below_spike_threshold_not_triggered(self):
        result = compute_volume_spike(recent_count=3, historical_avg_per_period=Decimal("2"))
        assert result.triggered is False
        assert result.volume_ratio is not None

    def test_spike_triggers(self):
        # 4x the average
        result = compute_volume_spike(recent_count=8, historical_avg_per_period=Decimal("2"))
        assert result.triggered is True
        assert result.direction == 1
        assert result.volume_ratio == Decimal("4.000")

    def test_exactly_2x_triggers(self):
        result = compute_volume_spike(recent_count=6, historical_avg_per_period=Decimal("3"))
        assert result.triggered is True

    def test_strength_scales_with_ratio(self):
        result_2x = compute_volume_spike(recent_count=4, historical_avg_per_period=Decimal("2"))
        result_5x = compute_volume_spike(recent_count=10, historical_avg_per_period=Decimal("2"))
        assert result_2x.triggered is True
        assert result_5x.triggered is True
        assert result_5x.strength > result_2x.strength


# ---------------------------------------------------------------------------
# Comparable appreciation tests
# ---------------------------------------------------------------------------

class TestComputeComparableAppreciation:
    def test_empty_list_not_triggered(self):
        result = compute_comparable_appreciation([])
        assert result.triggered is False

    def test_below_threshold_not_triggered(self):
        result = compute_comparable_appreciation([
            {
                "related_model_id": "abc-123",
                "appreciation_rate_90d": Decimal("0.05"),
                "correlation_strength": Decimal("0.8"),
                "relationship_type": "successor",
            }
        ])
        assert result.triggered is False

    def test_above_threshold_triggers(self):
        result = compute_comparable_appreciation([
            {
                "related_model_id": "abc-123",
                "appreciation_rate_90d": Decimal("0.15"),
                "correlation_strength": Decimal("0.8"),
                "relationship_type": "successor",
            }
        ])
        assert result.triggered is True
        assert result.direction == 1
        assert result.best_appreciation_pct == Decimal("0.15")

    def test_weighted_by_correlation(self):
        result_low_corr = compute_comparable_appreciation([
            {
                "related_model_id": "abc",
                "appreciation_rate_90d": Decimal("0.20"),
                "correlation_strength": Decimal("0.3"),
                "relationship_type": "successor",
            }
        ])
        result_high_corr = compute_comparable_appreciation([
            {
                "related_model_id": "def",
                "appreciation_rate_90d": Decimal("0.20"),
                "correlation_strength": Decimal("0.9"),
                "relationship_type": "successor",
            }
        ])
        assert result_low_corr.triggered is True
        assert result_high_corr.triggered is True
        assert result_high_corr.strength > result_low_corr.strength

    def test_none_rate_ignored(self):
        result = compute_comparable_appreciation([
            {
                "related_model_id": "abc",
                "appreciation_rate_90d": None,
                "correlation_strength": Decimal("0.8"),
                "relationship_type": "successor",
            }
        ])
        assert result.triggered is False


# ---------------------------------------------------------------------------
# Pattern match tests
# ---------------------------------------------------------------------------

class TestComputeOpenTopLag:
    def test_not_open_top_not_triggered(self):
        result = compute_open_top_lag(
            source_is_open_top=False,
            source_appreciation_90d=None,
            coupe_appreciation_90d=None,
            coupe_appreciation_365d=Decimal("0.20"),
            source_fair_value=Decimal("100000"),
            coupe_fair_value=Decimal("130000"),
        )
        assert result.triggered is False

    def test_insufficient_data_not_triggered(self):
        result = compute_open_top_lag(
            source_is_open_top=True,
            source_appreciation_90d=None,
            coupe_appreciation_90d=None,
            coupe_appreciation_365d=None,
            source_fair_value=None,
            coupe_fair_value=None,
        )
        assert result.triggered is False

    def test_coupe_below_appreciation_threshold(self):
        result = compute_open_top_lag(
            source_is_open_top=True,
            source_appreciation_90d=Decimal("0.01"),
            coupe_appreciation_90d=Decimal("0.03"),
            coupe_appreciation_365d=Decimal("0.05"),  # below 10% threshold
            source_fair_value=Decimal("80000"),
            coupe_fair_value=Decimal("100000"),
        )
        assert result.triggered is False

    def test_small_value_gap_not_triggered(self):
        result = compute_open_top_lag(
            source_is_open_top=True,
            source_appreciation_90d=Decimal("0.02"),
            coupe_appreciation_90d=Decimal("0.05"),
            coupe_appreciation_365d=Decimal("0.15"),
            source_fair_value=Decimal("95000"),  # only 5% gap
            coupe_fair_value=Decimal("100000"),
        )
        assert result.triggered is False

    def test_pattern_triggers(self):
        result = compute_open_top_lag(
            source_is_open_top=True,
            source_appreciation_90d=Decimal("0.02"),
            coupe_appreciation_90d=Decimal("0.10"),
            coupe_appreciation_365d=Decimal("0.20"),
            source_fair_value=Decimal("80000"),  # 20% gap
            coupe_fair_value=Decimal("100000"),
        )
        assert result.triggered is True
        assert result.direction == 1
        assert result.pattern_name == "open_top_lag"

    def test_strength_scales_with_value_gap(self):
        result_small = compute_open_top_lag(
            True, Decimal("0.02"), Decimal("0.10"), Decimal("0.20"),
            Decimal("83000"), Decimal("100000"),  # 17% gap
        )
        result_large = compute_open_top_lag(
            True, Decimal("0.02"), Decimal("0.10"), Decimal("0.20"),
            Decimal("65000"), Decimal("100000"),  # 35% gap
        )
        assert result_small.triggered is True
        assert result_large.triggered is True
        assert result_large.strength > result_small.strength


# ---------------------------------------------------------------------------
# Composite scoring tests
# ---------------------------------------------------------------------------

class TestComputeCompositeScore:
    def test_empty_signals_returns_zero(self):
        result = compute_composite_score([])
        assert result.composite_score == Decimal("0")
        assert result.signal_count == 0
        assert result.status == "expired"

    def test_single_signal_scoring(self):
        result = compute_composite_score([
            ScoringInput(
                signal_type="momentum",
                strength=Decimal("0.5"),
                direction=1,
                confidence=Decimal("0.8"),
            )
        ])
        # weight=0.25 * strength=0.5 * direction=1 * confidence=0.8 * 10 = 1.0
        assert result.composite_score == Decimal("1.000")
        assert result.signal_count == 1
        assert result.status == "passed"  # below 2.0 watchlist threshold

    def test_actionable_threshold(self):
        # Create enough strong signals to exceed 4.0
        signals = [
            ScoringInput("momentum", Decimal("1.0"), 1, Decimal("1.0")),
            ScoringInput("dealer_auction_spread", Decimal("1.0"), 1, Decimal("1.0")),
            ScoringInput("catalyst", Decimal("1.0"), 1, Decimal("1.0")),
        ]
        result = compute_composite_score(signals)
        # 0.25*10 + 0.20*10 + 0.20*10 = 2.5 + 2.0 + 2.0 = 6.5
        assert result.composite_score >= ACTIONABLE_THRESHOLD
        assert result.status == "actionable"

    def test_watchlist_threshold(self):
        signals = [
            ScoringInput("momentum", Decimal("0.8"), 1, Decimal("0.8")),
            ScoringInput("catalyst", Decimal("0.6"), 1, Decimal("0.7")),
        ]
        result = compute_composite_score(signals)
        # 0.25*0.8*1*0.8*10 + 0.20*0.6*1*0.7*10 = 1.6 + 0.84 = 2.44
        assert result.composite_score >= WATCHLIST_THRESHOLD
        assert result.composite_score < ACTIONABLE_THRESHOLD
        assert result.status == "watchlist"

    def test_negative_direction_reduces_score(self):
        result_pos = compute_composite_score([
            ScoringInput("momentum", Decimal("0.5"), 1, Decimal("0.8")),
        ])
        result_neg = compute_composite_score([
            ScoringInput("momentum", Decimal("0.5"), -1, Decimal("0.8")),
        ])
        assert result_pos.composite_score > result_neg.composite_score
        assert result_neg.composite_score < Decimal("0")

    def test_signal_breakdown_has_all_signals(self):
        signals = [
            ScoringInput("momentum", Decimal("0.5"), 1, Decimal("0.7")),
            ScoringInput("volume_spike", Decimal("0.3"), 1, Decimal("0.5")),
        ]
        result = compute_composite_score(signals)
        assert "momentum" in result.signal_breakdown
        assert "volume_spike" in result.signal_breakdown
        assert result.signal_count == 2

    def test_all_signal_weights_sum_to_one(self):
        total = sum(SIGNAL_WEIGHTS.values())
        assert total == Decimal("1.00")

    def test_max_possible_score(self):
        # All 6 signals at full strength, direction +1, full confidence
        signals = [
            ScoringInput(st, Decimal("1.0"), 1, Decimal("1.0"))
            for st in SIGNAL_WEIGHTS
        ]
        result = compute_composite_score(signals)
        # Sum of all weights * 10 = 1.0 * 10 = 10.0
        assert result.composite_score == Decimal("10.000")
        assert result.status == "actionable"


# ---------------------------------------------------------------------------
# Signal constants / threshold tests
# ---------------------------------------------------------------------------

class TestSignalConstants:
    def test_deviation_threshold_is_five_pct(self):
        assert DEVIATION_THRESHOLD == Decimal("0.05")

    def test_spread_threshold_is_ten_pct(self):
        assert MIN_SPREAD_PCT == Decimal("0.10")

    def test_catalyst_window_is_90_days(self):
        assert CATALYST_WINDOW_DAYS == 90

    def test_spike_multiplier_is_two(self):
        assert SPIKE_MULTIPLIER == Decimal("2.0")

    def test_comparable_threshold_is_ten_pct(self):
        assert MIN_APPRECIATION_PCT == Decimal("0.10")

    def test_open_top_lag_threshold(self):
        assert OPEN_TOP_LAG_THRESHOLD == Decimal("0.15")

    def test_coupe_appreciation_threshold(self):
        assert COUPE_APPRECIATION_THRESHOLD == Decimal("0.10")

    def test_actionable_threshold(self):
        assert ACTIONABLE_THRESHOLD == Decimal("4.0")

    def test_watchlist_threshold(self):
        assert WATCHLIST_THRESHOLD == Decimal("2.0")
