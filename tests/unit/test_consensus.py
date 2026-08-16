"""Tests for the multi-model consensus engine -- Module 5.

Tests each scoring function's pure calculation logic (no DB) and the
aggregate/veto/disagreement/classification logic in the engine.
"""

from decimal import Decimal

import pytest

from aatp.consensus.models.momentum import (
    score_momentum,
    STRONG_UPTREND_PCT,
    CRASH_PCT,
)
from aatp.consensus.models.fundamental import (
    score_fundamental,
    STRONG_UNDERVALUED_PCT,
    STRONG_OVERVALUED_PCT,
)
from aatp.consensus.models.liquidity import (
    score_liquidity,
    HIGH_TRANSACTION_COUNT_12M,
)
from aatp.consensus.models.sentiment import (
    score_sentiment,
    VERY_POSITIVE_SENTIMENT,
    VERY_NEGATIVE_SENTIMENT,
)
from aatp.consensus.models.macro import score_macro
from aatp.consensus.models.rules import score_rules
from aatp.consensus.engine import (
    _aggregate_scores,
    _run_all_scoring_models,
    _compute_confidence,
    ACTIONABLE_THRESHOLD,
    WATCHLIST_THRESHOLD,
    DISAGREEMENT_SPREAD_THRESHOLD,
    VETO_SCORE,
)
from aatp.db.models import ConsensusModelType


# ---------------------------------------------------------------------------
# Momentum model tests
# ---------------------------------------------------------------------------

class TestScoreMomentum:
    def test_no_data_returns_zero(self):
        score, rationale, data = score_momentum(None, None, False, None)
        assert score == 0
        assert "Insufficient data" in rationale

    def test_strong_uptrend_scores_plus_two(self):
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("0.25"),
            appreciation_rate_365d=Decimal("0.25"),
            has_momentum_signal=False,
            signal_direction=None,
        )
        assert score == 2
        assert "Strong uptrend" in rationale

    def test_moderate_uptrend_scores_plus_one(self):
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("0.10"),
            appreciation_rate_365d=Decimal("0.10"),
            has_momentum_signal=False,
            signal_direction=None,
        )
        assert score == 1

    def test_flat_trend_scores_zero(self):
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("0.01"),
            appreciation_rate_365d=Decimal("0.01"),
            has_momentum_signal=False,
            signal_direction=None,
        )
        assert score == 0

    def test_declining_trend_scores_minus_one(self):
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("-0.10"),
            appreciation_rate_365d=Decimal("-0.10"),
            has_momentum_signal=False,
            signal_direction=None,
        )
        assert score == -1

    def test_crash_scores_minus_two(self):
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("-0.30"),
            appreciation_rate_365d=Decimal("-0.25"),
            has_momentum_signal=False,
            signal_direction=None,
        )
        assert score == -2

    def test_momentum_signal_nudges_up(self):
        # Moderate uptrend (+1) + positive signal => +2
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("0.10"),
            appreciation_rate_365d=Decimal("0.10"),
            has_momentum_signal=True,
            signal_direction=1,
        )
        assert score == 2

    def test_momentum_signal_nudges_down(self):
        # Flat (0) + negative signal => -1
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("0.01"),
            appreciation_rate_365d=Decimal("0.01"),
            has_momentum_signal=True,
            signal_direction=-1,
        )
        assert score == -1

    def test_score_clamped_at_plus_two(self):
        # Strong uptrend (+2) + positive signal should stay at +2
        score, _, _ = score_momentum(
            appreciation_rate_90d=Decimal("0.30"),
            appreciation_rate_365d=Decimal("0.30"),
            has_momentum_signal=True,
            signal_direction=1,
        )
        assert score == 2

    def test_only_90d_data_used_when_365d_missing(self):
        score, rationale, data = score_momentum(
            appreciation_rate_90d=Decimal("0.25"),
            appreciation_rate_365d=None,
            has_momentum_signal=False,
            signal_direction=None,
        )
        assert score == 2
        assert "Strong uptrend" in rationale


# ---------------------------------------------------------------------------
# Fundamental model tests
# ---------------------------------------------------------------------------

class TestScoreFundamental:
    def test_no_data_returns_zero(self):
        score, rationale, _ = score_fundamental(None, None, None)
        assert score == 0
        assert "Insufficient data" in rationale

    def test_strongly_undervalued(self):
        # Fair value 100k, price 80k => 20% undervalued
        score, rationale, data = score_fundamental(
            Decimal("100000"), Decimal("80000"), Decimal("0.9")
        )
        assert score == 2
        assert "Strongly undervalued" in rationale

    def test_moderately_undervalued(self):
        # Fair value 100k, price 92k => 8% undervalued
        score, _, _ = score_fundamental(
            Decimal("100000"), Decimal("92000"), Decimal("0.9")
        )
        assert score == 1

    def test_fairly_valued(self):
        # Fair value 100k, price 98k => 2% undervalued
        score, _, _ = score_fundamental(
            Decimal("100000"), Decimal("98000"), Decimal("0.9")
        )
        assert score == 0

    def test_moderately_overvalued(self):
        # Fair value 100k, price 110k => 10% overvalued
        score, _, _ = score_fundamental(
            Decimal("100000"), Decimal("110000"), Decimal("0.9")
        )
        assert score == -1

    def test_strongly_overvalued(self):
        # Fair value 100k, price 120k => 20% overvalued
        score, _, _ = score_fundamental(
            Decimal("100000"), Decimal("120000"), Decimal("0.9")
        )
        assert score == -2

    def test_low_confidence_reduces_positive_score(self):
        # Would be +2 but low confidence reduces to +1
        score, rationale, data = score_fundamental(
            Decimal("100000"), Decimal("80000"), Decimal("0.3")
        )
        assert score == 1
        assert "low confidence" in rationale

    def test_low_confidence_moves_negative_toward_neutral(self):
        # Would be -2 but low confidence reduces to -1
        score, rationale, _ = score_fundamental(
            Decimal("100000"), Decimal("120000"), Decimal("0.3")
        )
        assert score == -1

    def test_zero_price_returns_zero(self):
        score, _, _ = score_fundamental(
            Decimal("100000"), Decimal("0"), Decimal("0.9")
        )
        assert score == 0


# ---------------------------------------------------------------------------
# Liquidity model tests
# ---------------------------------------------------------------------------

class TestScoreLiquidity:
    def test_no_transactions_scores_minus_two(self):
        score, rationale, _ = score_liquidity(0, 0, 0, None)
        assert score == -2
        assert "No comparable transactions" in rationale

    def test_high_volume_multi_source_scores_high(self):
        score, _, _ = score_liquidity(
            transaction_count_12m=15,
            transaction_count_6m=10,
            distinct_sources=4,
            avg_days_on_market=20,
        )
        assert score == 2

    def test_thin_volume_single_source(self):
        score, _, _ = score_liquidity(
            transaction_count_12m=2,
            transaction_count_6m=1,
            distinct_sources=1,
            avg_days_on_market=None,
        )
        assert score <= 0

    def test_slow_days_on_market_penalises(self):
        # Use moderate volume so the days-on-market difference isn't capped away
        score_fast, _, _ = score_liquidity(5, 3, 2, 20)
        score_slow, _, _ = score_liquidity(5, 3, 2, 200)
        assert score_fast > score_slow

    def test_accelerating_recent_activity_bonus(self):
        # 80% of 12m transactions in the last 6m => accelerating
        score, rationale, _ = score_liquidity(
            transaction_count_12m=5,
            transaction_count_6m=4,
            distinct_sources=2,
            avg_days_on_market=None,
        )
        assert "accelerating" in rationale


# ---------------------------------------------------------------------------
# Sentiment model tests
# ---------------------------------------------------------------------------

class TestScoreSentiment:
    def test_no_data_returns_zero(self):
        score, rationale, _ = score_sentiment(None, None, None, False)
        assert score == 0

    def test_negative_catalyst_scores_minus_two(self):
        score, rationale, _ = score_sentiment(
            avg_sentiment=Decimal("0.8"),
            mention_volume_change_pct=Decimal("50"),
            news_sentiment_avg=Decimal("0.5"),
            has_negative_catalyst=True,
        )
        assert score == -2
        assert "Negative catalyst" in rationale

    def test_very_positive_sentiment(self):
        score, _, _ = score_sentiment(
            avg_sentiment=Decimal("0.8"),
            mention_volume_change_pct=Decimal("40"),
            news_sentiment_avg=Decimal("0.5"),
            has_negative_catalyst=False,
        )
        assert score == 2

    def test_very_negative_sentiment(self):
        score, _, _ = score_sentiment(
            avg_sentiment=Decimal("-0.8"),
            mention_volume_change_pct=None,
            news_sentiment_avg=Decimal("-0.5"),
            has_negative_catalyst=False,
        )
        assert score == -2

    def test_rising_interest_amplifies_positive(self):
        # Positive sentiment + rising interest => higher score
        score_rising, _, _ = score_sentiment(
            avg_sentiment=Decimal("0.3"),
            mention_volume_change_pct=Decimal("50"),
            news_sentiment_avg=None,
            has_negative_catalyst=False,
        )
        score_flat, _, _ = score_sentiment(
            avg_sentiment=Decimal("0.3"),
            mention_volume_change_pct=Decimal("0"),
            news_sentiment_avg=None,
            has_negative_catalyst=False,
        )
        assert score_rising >= score_flat


# ---------------------------------------------------------------------------
# Macro model tests
# ---------------------------------------------------------------------------

class TestScoreMacro:
    def test_no_data_returns_zero(self):
        score, rationale, _ = score_macro(None, None, None)
        assert score == 0
        assert "Insufficient macro data" in rationale

    def test_all_tailwinds(self):
        score, rationale, _ = score_macro(
            luxury_index_trend=Decimal("0.10"),
            interest_rate_trend=Decimal("-0.08"),
            wealth_indicator_trend=Decimal("0.06"),
        )
        assert score == 2

    def test_all_headwinds(self):
        score, _, _ = score_macro(
            luxury_index_trend=Decimal("-0.10"),
            interest_rate_trend=Decimal("0.08"),
            wealth_indicator_trend=Decimal("-0.06"),
        )
        assert score == -2

    def test_mixed_signals(self):
        score, _, _ = score_macro(
            luxury_index_trend=Decimal("0.06"),
            interest_rate_trend=Decimal("0.06"),
            wealth_indicator_trend=Decimal("0.002"),
        )
        # Luxury up (+2) but rates up (-1) => +1
        assert score == 1


# ---------------------------------------------------------------------------
# Rules model tests
# ---------------------------------------------------------------------------

class TestScoreRules:
    def test_no_flags_returns_zero(self):
        score, rationale, _ = score_rules(0, 0, 0, False)
        assert score == 0

    def test_import_eligibility_soon_scores_high(self):
        score, rationale, _ = score_rules(0, 0, 0, True)
        assert score == 2
        assert "25-year import eligibility" in rationale

    def test_negative_flags_score_low(self):
        score, _, _ = score_rules(2, 0, 2, False)
        assert score == -2

    def test_single_negative_flag(self):
        score, _, _ = score_rules(1, 0, 1, False)
        assert score == -1

    def test_mixed_flags_with_eligibility(self):
        # 1 negative (-1) + eligibility (+2) => clamped to +1
        score, _, _ = score_rules(2, 1, 1, True)
        assert score == 2  # +1 positive + (-1 negative) + 2 eligibility = +2


# ---------------------------------------------------------------------------
# Aggregate / Veto / Classification tests
# ---------------------------------------------------------------------------

def _make_scores(**overrides):
    """Helper to build a scores dict for _aggregate_scores.

    Default: all models score 0 with 0.5 confidence.
    Pass model_name=score to override.
    """
    defaults = {
        ConsensusModelType.MOMENTUM: (0, Decimal("0.5"), "neutral", {}),
        ConsensusModelType.FUNDAMENTAL_VALUE: (0, Decimal("0.5"), "neutral", {}),
        ConsensusModelType.LIQUIDITY: (0, Decimal("0.5"), "neutral", {}),
        ConsensusModelType.SENTIMENT: (0, Decimal("0.5"), "neutral", {}),
        ConsensusModelType.MACRO: (0, Decimal("0.5"), "neutral", {}),
        ConsensusModelType.RULES: (0, Decimal("0.5"), "neutral", {}),
    }
    for model_type, score_val in overrides.items():
        if isinstance(score_val, int):
            defaults[model_type] = (score_val, Decimal("0.5"), f"score={score_val}", {})
        else:
            defaults[model_type] = score_val
    return defaults


class TestAggregateScores:
    def test_all_zeros_is_passed(self):
        result = _aggregate_scores(_make_scores())
        assert result["aggregate_score"] == 0
        assert result["status"] == "passed"
        assert result["actionable"] is False
        assert result["has_veto"] is False

    def test_aggregate_sum_correct(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 1,
            ConsensusModelType.LIQUIDITY: 1,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == 4

    def test_actionable_threshold(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 1,
            ConsensusModelType.LIQUIDITY: 1,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == ACTIONABLE_THRESHOLD
        assert result["status"] == "actionable"
        assert result["actionable"] is True

    def test_watchlist_threshold(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 1,
            ConsensusModelType.FUNDAMENTAL_VALUE: 1,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == WATCHLIST_THRESHOLD
        assert result["status"] == "watchlist"
        assert result["actionable"] is False

    def test_below_watchlist_is_passed(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 1,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == 1
        assert result["status"] == "passed"


class TestVetoLogic:
    def test_single_veto_kills_high_aggregate(self):
        """Even +8 aggregate is killed by a single -2 veto."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 2,
            ConsensusModelType.LIQUIDITY: -2,  # VETO
            ConsensusModelType.SENTIMENT: 2,
            ConsensusModelType.MACRO: 2,
            ConsensusModelType.RULES: 2,
        })
        result = _aggregate_scores(scores)
        assert result["has_veto"] is True
        assert result["veto_model"] == "liquidity"
        assert result["status"] == "passed"
        assert result["actionable"] is False
        # Aggregate is still computed correctly
        assert result["aggregate_score"] == 8

    def test_all_models_plus_two_no_veto(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 2,
            ConsensusModelType.LIQUIDITY: 2,
            ConsensusModelType.SENTIMENT: 2,
            ConsensusModelType.MACRO: 2,
            ConsensusModelType.RULES: 2,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == 12
        assert result["has_veto"] is False
        assert result["actionable"] is True

    def test_all_models_minus_two_is_vetoed(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: -2,
            ConsensusModelType.FUNDAMENTAL_VALUE: -2,
            ConsensusModelType.LIQUIDITY: -2,
            ConsensusModelType.SENTIMENT: -2,
            ConsensusModelType.MACRO: -2,
            ConsensusModelType.RULES: -2,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == -12
        assert result["has_veto"] is True
        assert result["actionable"] is False

    def test_veto_at_boundary_aggregate(self):
        """Aggregate exactly at +4 but one model scores -2 => vetoed."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 2,
            ConsensusModelType.LIQUIDITY: 2,
            ConsensusModelType.SENTIMENT: -2,  # VETO
        })
        result = _aggregate_scores(scores)
        assert result["has_veto"] is True
        assert result["status"] == "passed"
        assert result["actionable"] is False

    def test_minus_one_does_not_veto(self):
        """-1 is negative but not a veto."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 2,
            ConsensusModelType.LIQUIDITY: -1,
            ConsensusModelType.SENTIMENT: 1,
        })
        result = _aggregate_scores(scores)
        assert result["has_veto"] is False
        assert result["aggregate_score"] == 4
        assert result["actionable"] is True


class TestDisagreementDetection:
    def test_no_disagreement_when_all_same(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 1,
            ConsensusModelType.FUNDAMENTAL_VALUE: 1,
            ConsensusModelType.LIQUIDITY: 1,
            ConsensusModelType.SENTIMENT: 1,
            ConsensusModelType.MACRO: 1,
            ConsensusModelType.RULES: 1,
        })
        result = _aggregate_scores(scores)
        assert result["disagreement_summary"] is None

    def test_disagreement_detected_with_large_spread(self):
        """Spread of 4 (from -2 to +2) exceeds threshold of 3."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: -2,
        })
        result = _aggregate_scores(scores)
        assert result["disagreement_summary"] is not None
        assert "Manual review" in result["disagreement_summary"]

    def test_spread_of_3_does_not_trigger(self):
        """Spread of exactly 3 does NOT trigger (must exceed, not equal)."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: -1,
        })
        result = _aggregate_scores(scores)
        assert result["disagreement_summary"] is None

    def test_spread_of_4_triggers(self):
        """Spread of 4 triggers."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.LIQUIDITY: -2,
        })
        result = _aggregate_scores(scores)
        assert result["disagreement_summary"] is not None


class TestRunAllScoringModels:
    def test_returns_all_six_models(self):
        inputs = {}
        results = _run_all_scoring_models(inputs)
        assert len(results) == 6
        assert set(results.keys()) == {
            ConsensusModelType.MOMENTUM,
            ConsensusModelType.FUNDAMENTAL_VALUE,
            ConsensusModelType.LIQUIDITY,
            ConsensusModelType.SENTIMENT,
            ConsensusModelType.MACRO,
            ConsensusModelType.RULES,
        }

    def test_all_scores_in_valid_range(self):
        inputs = {
            "appreciation_rate_90d": Decimal("0.10"),
            "appreciation_rate_365d": Decimal("0.12"),
            "has_momentum_signal": True,
            "signal_direction": 1,
            "fair_value_mid": Decimal("100000"),
            "latest_transaction_price": Decimal("85000"),
            "fair_value_confidence": Decimal("0.9"),
            "transaction_count_12m": 8,
            "transaction_count_6m": 5,
            "distinct_sources": 3,
            "avg_days_on_market": 45,
            "avg_sentiment": Decimal("0.5"),
            "mention_volume_change_pct": Decimal("20"),
            "news_sentiment_avg": Decimal("0.3"),
            "has_negative_catalyst": False,
            "luxury_index_trend": Decimal("0.03"),
            "interest_rate_trend": Decimal("-0.02"),
            "wealth_indicator_trend": Decimal("0.04"),
            "active_rule_flags": 1,
            "positive_flag_count": 1,
            "negative_flag_count": 0,
            "has_import_eligibility_soon": False,
        }
        results = _run_all_scoring_models(inputs)
        for model_type, (score, confidence, rationale, data) in results.items():
            assert -2 <= score <= 2, f"{model_type.value} score {score} out of range"
            assert Decimal("0") <= confidence <= Decimal("1"), f"{model_type.value} confidence out of range"
            assert isinstance(rationale, str) and len(rationale) > 0
            assert isinstance(data, dict)

    def test_empty_inputs_mostly_neutral(self):
        """With no data, most models score 0; liquidity scores -2 (no transactions)."""
        results = _run_all_scoring_models({})
        for model_type, (score, _, _, _) in results.items():
            if model_type == ConsensusModelType.LIQUIDITY:
                assert score == -2, "liquidity should be -2 with no transactions"
            else:
                assert score == 0, f"{model_type.value} should be 0 with no data"


class TestComputeConfidence:
    def test_no_data_low_confidence(self):
        assert _compute_confidence(0, False) == Decimal("0.300")

    def test_has_data_neutral_score(self):
        assert _compute_confidence(0, True) == Decimal("0.500")

    def test_has_data_non_zero_score(self):
        assert _compute_confidence(2, True) == Decimal("0.800")
        assert _compute_confidence(-1, True) == Decimal("0.800")


# ---------------------------------------------------------------------------
# Edge case and integration-style tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_plus_two_is_actionable(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 2,
            ConsensusModelType.LIQUIDITY: 2,
            ConsensusModelType.SENTIMENT: 2,
            ConsensusModelType.MACRO: 2,
            ConsensusModelType.RULES: 2,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == 12
        assert result["actionable"] is True
        assert result["has_veto"] is False

    def test_all_minus_two_is_vetoed_and_passed(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: -2,
            ConsensusModelType.FUNDAMENTAL_VALUE: -2,
            ConsensusModelType.LIQUIDITY: -2,
            ConsensusModelType.SENTIMENT: -2,
            ConsensusModelType.MACRO: -2,
            ConsensusModelType.RULES: -2,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == -12
        assert result["has_veto"] is True
        assert result["actionable"] is False

    def test_single_veto_kills_plus_eight_aggregate(self):
        """The canonical veto test: +2 from 5 models (+10) but -2 from one."""
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 2,
            ConsensusModelType.FUNDAMENTAL_VALUE: 2,
            ConsensusModelType.LIQUIDITY: 2,
            ConsensusModelType.SENTIMENT: 2,
            ConsensusModelType.MACRO: 2,
            ConsensusModelType.RULES: -2,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == 8
        assert result["has_veto"] is True
        assert result["actionable"] is False
        assert result["status"] == "passed"

    def test_aggregate_just_below_actionable(self):
        scores = _make_scores(**{
            ConsensusModelType.MOMENTUM: 1,
            ConsensusModelType.FUNDAMENTAL_VALUE: 1,
            ConsensusModelType.LIQUIDITY: 1,
        })
        result = _aggregate_scores(scores)
        assert result["aggregate_score"] == 3
        assert result["status"] == "watchlist"
        assert result["actionable"] is False

    def test_score_values_are_integers(self):
        """All score return values must be Python ints in [-2, +2]."""
        test_cases = [
            score_momentum(Decimal("0.1"), Decimal("0.1"), False, None),
            score_fundamental(Decimal("100000"), Decimal("90000"), Decimal("0.8")),
            score_liquidity(5, 3, 2, 60),
            score_sentiment(Decimal("0.3"), Decimal("10"), None, False),
            score_macro(Decimal("0.03"), Decimal("-0.02"), Decimal("0.04")),
            score_rules(1, 1, 0, False),
        ]
        for score, rationale, data in test_cases:
            assert isinstance(score, int), f"Score {score} is not an int"
            assert -2 <= score <= 2, f"Score {score} out of range"
            assert isinstance(rationale, str)
            assert isinstance(data, dict)

    def test_supporting_data_always_dict(self):
        """Every scoring function must return a dict as supporting_data."""
        _, _, data = score_momentum(None, None, False, None)
        assert isinstance(data, dict)
        _, _, data = score_fundamental(None, None, None)
        assert isinstance(data, dict)
        _, _, data = score_liquidity(0, 0, 0, None)
        assert isinstance(data, dict)
        _, _, data = score_sentiment(None, None, None, False)
        assert isinstance(data, dict)
        _, _, data = score_macro(None, None, None)
        assert isinstance(data, dict)
        _, _, data = score_rules(0, 0, 0, False)
        assert isinstance(data, dict)
