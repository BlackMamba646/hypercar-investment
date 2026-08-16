"""Tests for the risk engine -- Module 6.

Tests each risk dimension scoring function's pure calculation logic (no DB),
composite risk calculation, portfolio concentration, scenario analysis,
and edge cases.
"""

from decimal import Decimal

import pytest

from aatp.risk.position_risk import (
    compute_composite_risk,
    score_concentration_risk,
    score_counterparty_risk,
    score_liquidity_risk,
    score_physical_risk,
    score_provenance_risk,
    score_spec_risk,
    _clamp,
    LIQUID_TX_12M,
    HIGH_POSITION_PCT,
    HIGH_MANUFACTURER_PCT,
)
from aatp.risk.portfolio_risk import (
    assess_era_concentration,
    assess_illiquid_exposure,
    assess_manufacturer_concentration,
    assess_type_concentration,
    MAX_MANUFACTURER_PCT,
    MAX_ERA_PCT,
    MAX_TYPE_PCT,
    MAX_ILLIQUID_PCT,
)
from aatp.risk.scenarios import (
    scenario_market_drop,
    scenario_no_flagship_auction,
    scenario_rate_change,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _d(value) -> Decimal:
    """Shorthand for Decimal conversion."""
    return Decimal(str(value))


# ===========================================================================
# Position-level: Liquidity Risk
# ===========================================================================

class TestScoreLiquidityRisk:
    def test_highly_liquid(self):
        score, explanation = score_liquidity_risk(
            transaction_count_12m=10,
            transaction_count_6m=6,
            days_since_last_sale=30,
            distinct_channels=3,
        )
        assert Decimal("0") <= score <= Decimal("1")
        assert score < _d("0.2"), f"Expected low risk, got {score}"
        assert "10 sales" in explanation

    def test_illiquid_no_sales(self):
        score, explanation = score_liquidity_risk(
            transaction_count_12m=0,
            transaction_count_6m=0,
            days_since_last_sale=None,
            distinct_channels=0,
        )
        assert score >= _d("0.7"), f"Expected high risk, got {score}"
        assert "No sales recorded" in explanation

    def test_moderate_liquidity(self):
        score, _ = score_liquidity_risk(
            transaction_count_12m=3,
            transaction_count_6m=1,
            days_since_last_sale=100,
            distinct_channels=2,
        )
        assert _d("0.2") <= score <= _d("0.6")

    def test_no_recent_activity(self):
        """12-month sales exist but nothing in last 6 months -> higher risk."""
        score, _ = score_liquidity_risk(
            transaction_count_12m=4,
            transaction_count_6m=0,
            days_since_last_sale=200,
            distinct_channels=1,
        )
        assert score >= _d("0.4")

    def test_old_last_sale(self):
        score, _ = score_liquidity_risk(
            transaction_count_12m=2,
            transaction_count_6m=0,
            days_since_last_sale=400,
            distinct_channels=1,
        )
        assert score >= _d("0.5")

    def test_single_channel(self):
        score_single, _ = score_liquidity_risk(
            transaction_count_12m=6,
            transaction_count_6m=3,
            days_since_last_sale=30,
            distinct_channels=1,
        )
        score_multi, _ = score_liquidity_risk(
            transaction_count_12m=6,
            transaction_count_6m=3,
            days_since_last_sale=30,
            distinct_channels=3,
        )
        assert score_single > score_multi


# ===========================================================================
# Position-level: Concentration Risk
# ===========================================================================

class TestScoreConcentrationRisk:
    def test_well_diversified(self):
        score, explanation = score_concentration_risk(
            position_value=_d("100000"),
            total_portfolio_value=_d("2000000"),
            manufacturer_count=10,
            same_manufacturer_count=2,
        )
        assert score < _d("0.4")
        assert "5.0%" in explanation

    def test_high_position_concentration(self):
        """Position is >20% of portfolio."""
        score, explanation = score_concentration_risk(
            position_value=_d("500000"),
            total_portfolio_value=_d("1000000"),
            manufacturer_count=5,
            same_manufacturer_count=1,
        )
        assert score >= _d("0.3")
        assert "50.0%" in explanation

    def test_extreme_concentration(self):
        """Single position is >40% of portfolio AND >40% manufacturer."""
        score, _ = score_concentration_risk(
            position_value=_d("800000"),
            total_portfolio_value=_d("1000000"),
            manufacturer_count=2,
            same_manufacturer_count=1,
        )
        assert score >= _d("0.5")

    def test_high_manufacturer_concentration(self):
        """Same manufacturer has >40% of positions."""
        score, explanation = score_concentration_risk(
            position_value=_d("100000"),
            total_portfolio_value=_d("1000000"),
            manufacturer_count=5,
            same_manufacturer_count=3,
        )
        assert score >= _d("0.3")
        assert "60%" in explanation

    def test_zero_portfolio_value(self):
        score, _ = score_concentration_risk(
            position_value=_d("100000"),
            total_portfolio_value=_d("0"),
            manufacturer_count=1,
            same_manufacturer_count=1,
        )
        assert score >= _d("0.5")


# ===========================================================================
# Position-level: Physical Risk
# ===========================================================================

class TestScorePhysicalRisk:
    def test_fully_covered(self):
        score, explanation = score_physical_risk(
            has_storage=True,
            has_insurance=True,
            storage_quality_score=_d("0.9"),
        )
        assert score < _d("0.2")
        assert "High-quality storage" in explanation
        assert "Insurance active" in explanation

    def test_no_storage_no_insurance(self):
        score, _ = score_physical_risk(
            has_storage=False,
            has_insurance=False,
            storage_quality_score=None,
        )
        assert score >= _d("0.8")

    def test_storage_but_no_insurance(self):
        score, explanation = score_physical_risk(
            has_storage=True,
            has_insurance=False,
            storage_quality_score=_d("0.5"),
        )
        assert _d("0.4") <= score <= _d("0.8")
        assert "No insurance" in explanation

    def test_insurance_but_no_storage(self):
        score, _ = score_physical_risk(
            has_storage=False,
            has_insurance=True,
            storage_quality_score=None,
        )
        assert _d("0.3") <= score <= _d("0.6")


# ===========================================================================
# Position-level: Counterparty Risk
# ===========================================================================

class TestScoreCounterpartyRisk:
    def test_top_tier_dealer(self):
        score, _ = score_counterparty_risk(
            dealer_tier="allocation_access",
            dealer_reliability=_d("0.95"),
            auction_house_tier=None,
        )
        assert score < _d("0.2")

    def test_unknown_counterparty(self):
        score, explanation = score_counterparty_risk(
            dealer_tier=None,
            dealer_reliability=None,
            auction_house_tier=None,
        )
        assert score >= _d("0.5")
        assert "No counterparty" in explanation

    def test_low_tier_dealer(self):
        score, _ = score_counterparty_risk(
            dealer_tier="secondary_standard",
            dealer_reliability=_d("0.40"),
            auction_house_tier=None,
        )
        assert score >= _d("0.4")

    def test_major_auction_house(self):
        score, _ = score_counterparty_risk(
            dealer_tier=None,
            dealer_reliability=None,
            auction_house_tier="major",
        )
        assert score < _d("0.3")

    def test_online_auction_house(self):
        score, _ = score_counterparty_risk(
            dealer_tier=None,
            dealer_reliability=None,
            auction_house_tier="online",
        )
        assert score >= _d("0.4")


# ===========================================================================
# Position-level: Spec Risk
# ===========================================================================

class TestScoreSpecRisk:
    def test_perfect_spec(self):
        score, _ = score_spec_risk(
            colour_tier=1,
            has_desirable_options=True,
            mileage=2000,
            mileage_ceiling=10000,
            has_certification=True,
        )
        assert score < _d("0.2")

    def test_undesirable_spec(self):
        score, _ = score_spec_risk(
            colour_tier=3,
            has_desirable_options=False,
            mileage=25000,
            mileage_ceiling=10000,
            has_certification=False,
        )
        assert score >= _d("0.6")

    def test_mileage_exceeds_ceiling(self):
        score, explanation = score_spec_risk(
            colour_tier=2,
            has_desirable_options=True,
            mileage=15000,
            mileage_ceiling=10000,
            has_certification=True,
        )
        assert score >= _d("0.2")
        assert "exceeds ceiling" in explanation

    def test_unknown_colour_tier(self):
        score, explanation = score_spec_risk(
            colour_tier=None,
            has_desirable_options=True,
            mileage=5000,
            mileage_ceiling=20000,
            has_certification=False,
        )
        assert "Colour tier unknown" in explanation

    def test_unknown_mileage(self):
        score, explanation = score_spec_risk(
            colour_tier=2,
            has_desirable_options=True,
            mileage=None,
            mileage_ceiling=None,
            has_certification=True,
        )
        assert "Mileage unknown" in explanation

    def test_low_mileage_no_ceiling(self):
        """Low mileage without a ceiling should still score low risk."""
        score, _ = score_spec_risk(
            colour_tier=1,
            has_desirable_options=True,
            mileage=1000,
            mileage_ceiling=None,
            has_certification=True,
        )
        assert score < _d("0.2")


# ===========================================================================
# Position-level: Provenance Risk
# ===========================================================================

class TestScoreProvenanceRisk:
    def test_perfect_provenance(self):
        score, _ = score_provenance_risk(
            has_books=True,
            has_service_history=True,
            single_owner=True,
            has_accident_history=False,
            ownership_gaps=0,
        )
        assert score < _d("0.1")

    def test_worst_provenance(self):
        score, _ = score_provenance_risk(
            has_books=False,
            has_service_history=False,
            single_owner=False,
            has_accident_history=True,
            ownership_gaps=5,
        )
        assert score >= _d("0.5")

    def test_accident_history_increases_risk(self):
        score_no_accident, _ = score_provenance_risk(
            has_books=True,
            has_service_history=True,
            single_owner=True,
            has_accident_history=False,
            ownership_gaps=0,
        )
        score_accident, _ = score_provenance_risk(
            has_books=True,
            has_service_history=True,
            single_owner=True,
            has_accident_history=True,
            ownership_gaps=0,
        )
        assert score_accident > score_no_accident

    def test_ownership_gaps_increase_risk(self):
        score_no_gaps, _ = score_provenance_risk(
            has_books=True,
            has_service_history=True,
            single_owner=False,
            has_accident_history=False,
            ownership_gaps=0,
        )
        score_gaps, _ = score_provenance_risk(
            has_books=True,
            has_service_history=True,
            single_owner=False,
            has_accident_history=False,
            ownership_gaps=4,
        )
        assert score_gaps > score_no_gaps


# ===========================================================================
# Composite Risk
# ===========================================================================

class TestComputeCompositeRisk:
    def test_equal_weights(self):
        scores = {
            "liquidity": _d("0.2"),
            "concentration": _d("0.4"),
            "physical": _d("0.1"),
            "counterparty": _d("0.3"),
            "spec": _d("0.5"),
            "provenance": _d("0.1"),
        }
        composite = compute_composite_risk(scores)
        # Average = (0.2+0.4+0.1+0.3+0.5+0.1)/6 = 1.6/6 = 0.267
        assert composite == _d("0.267")

    def test_custom_weights(self):
        scores = {
            "liquidity": _d("1.0"),
            "concentration": _d("0.0"),
        }
        weights = {
            "liquidity": _d("3"),
            "concentration": _d("1"),
        }
        composite = compute_composite_risk(scores, weights)
        # Weighted: (1.0*3 + 0.0*1) / 4 = 0.75
        assert composite == _d("0.750")

    def test_empty_scores(self):
        assert compute_composite_risk({}) == _d("0.000")

    def test_all_maximum(self):
        scores = {
            "liquidity": _d("1.0"),
            "concentration": _d("1.0"),
            "physical": _d("1.0"),
            "counterparty": _d("1.0"),
            "spec": _d("1.0"),
            "provenance": _d("1.0"),
        }
        assert compute_composite_risk(scores) == _d("1.000")

    def test_all_zero(self):
        scores = {
            "liquidity": _d("0.0"),
            "concentration": _d("0.0"),
            "physical": _d("0.0"),
            "counterparty": _d("0.0"),
            "spec": _d("0.0"),
            "provenance": _d("0.0"),
        }
        assert compute_composite_risk(scores) == _d("0.000")

    def test_clamp_prevents_overflow(self):
        """Verify _clamp keeps values in [0, 1]."""
        assert _clamp(_d("1.5")) == _d("1.000")
        assert _clamp(_d("-0.3")) == _d("0.000")
        assert _clamp(_d("0.555")) == _d("0.555")


# ===========================================================================
# Portfolio-level: Manufacturer Concentration
# ===========================================================================

class TestAssessManufacturerConcentration:
    def test_balanced_portfolio(self):
        positions = {
            "Ferrari": _d("300000"),
            "Porsche": _d("200000"),
            "Lamborghini": _d("250000"),
            "McLaren": _d("250000"),
        }
        concentration, warnings = assess_manufacturer_concentration(positions)
        assert len(warnings) == 0
        assert "Ferrari" in concentration
        assert Decimal(concentration["Ferrari"]) == _d("30.00")

    def test_over_40_pct_warning(self):
        positions = {
            "Ferrari": _d("600000"),
            "Porsche": _d("200000"),
            "Lamborghini": _d("200000"),
        }
        concentration, warnings = assess_manufacturer_concentration(positions)
        assert len(warnings) == 1
        assert "Ferrari" in warnings[0]
        assert "60.00%" in warnings[0]

    def test_empty_portfolio(self):
        concentration, warnings = assess_manufacturer_concentration({})
        assert concentration == {}
        assert warnings == []

    def test_single_manufacturer(self):
        positions = {"Ferrari": _d("1000000")}
        concentration, warnings = assess_manufacturer_concentration(positions)
        assert len(warnings) == 1
        assert Decimal(concentration["Ferrari"]) == _d("100.00")


# ===========================================================================
# Portfolio-level: Era Concentration
# ===========================================================================

class TestAssessEraConcentration:
    def test_balanced_eras(self):
        positions = {
            "1990s": _d("400000"),
            "2000s": _d("300000"),
            "2010s": _d("300000"),
        }
        _, warnings = assess_era_concentration(positions)
        assert len(warnings) == 0

    def test_over_60_pct_warning(self):
        positions = {
            "2000s": _d("700000"),
            "2010s": _d("300000"),
        }
        _, warnings = assess_era_concentration(positions)
        assert len(warnings) == 1
        assert "2000s" in warnings[0]

    def test_empty(self):
        concentration, warnings = assess_era_concentration({})
        assert concentration == {}
        assert warnings == []


# ===========================================================================
# Portfolio-level: Type Concentration
# ===========================================================================

class TestAssessTypeConcentration:
    def test_balanced_types(self):
        positions = {
            "coupe": _d("400000"),
            "open_top": _d("300000"),
            "suv": _d("300000"),
        }
        _, warnings = assess_type_concentration(positions)
        assert len(warnings) == 0

    def test_over_70_pct_warning(self):
        positions = {
            "coupe": _d("800000"),
            "open_top": _d("200000"),
        }
        _, warnings = assess_type_concentration(positions)
        assert len(warnings) == 1
        assert "coupe" in warnings[0]

    def test_single_type(self):
        positions = {"coupe": _d("1000000")}
        concentration, warnings = assess_type_concentration(positions)
        assert len(warnings) == 1
        assert Decimal(concentration["coupe"]) == _d("100.00")


# ===========================================================================
# Portfolio-level: Illiquid Exposure
# ===========================================================================

class TestAssessIlliquidExposure:
    def test_all_liquid(self):
        positions = [
            ("pos1", 30),
            ("pos2", 60),
            ("pos3", 45),
        ]
        pct, warnings = assess_illiquid_exposure(positions)
        assert pct == _d("0.00")
        assert len(warnings) == 0

    def test_over_30_pct_illiquid(self):
        positions = [
            ("pos1", 30),
            ("pos2", 100),
            ("pos3", 200),
            ("pos4", None),
        ]
        pct, warnings = assess_illiquid_exposure(positions)
        # 3 out of 4 are illiquid (>= 90 days or None)
        assert pct == _d("75.00")
        assert len(warnings) == 1
        assert "75.00%" in warnings[0]

    def test_none_days_treated_as_illiquid(self):
        positions = [("pos1", None)]
        pct, warnings = assess_illiquid_exposure(positions)
        assert pct == _d("100.00")
        assert len(warnings) == 1

    def test_empty_list(self):
        pct, warnings = assess_illiquid_exposure([])
        assert pct == _d("0.00")
        assert len(warnings) == 0

    def test_exactly_90_days_is_illiquid(self):
        positions = [("pos1", 90)]
        pct, warnings = assess_illiquid_exposure(positions)
        assert pct == _d("100.00")

    def test_89_days_is_liquid(self):
        positions = [("pos1", 89)]
        pct, warnings = assess_illiquid_exposure(positions)
        assert pct == _d("0.00")


# ===========================================================================
# Scenario Analysis: Market Drop
# ===========================================================================

class TestScenarioMarketDrop:
    def test_basic_drop(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("1000000")},
            {"position_id": "2", "manufacturer_name": "Porsche", "current_fair_value_usd": _d("500000")},
            {"position_id": "3", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("800000")},
        ]
        result = scenario_market_drop(positions, "Ferrari", _d("20"))
        assert result["affected_count"] == 2
        assert Decimal(result["estimated_impact_usd"]) == _d("360000.00")
        assert "Ferrari" in result["narrative"]

    def test_no_matching_manufacturer(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Porsche", "current_fair_value_usd": _d("500000")},
        ]
        result = scenario_market_drop(positions, "Ferrari", _d("20"))
        assert result["affected_count"] == 0
        assert Decimal(result["estimated_impact_usd"]) == _d("0.00")

    def test_case_insensitive_manufacturer(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "ferrari", "current_fair_value_usd": _d("1000000")},
        ]
        result = scenario_market_drop(positions, "Ferrari", _d("10"))
        assert result["affected_count"] == 1

    def test_empty_portfolio(self):
        result = scenario_market_drop([], "Ferrari", _d("50"))
        assert result["affected_count"] == 0


# ===========================================================================
# Scenario Analysis: Rate Change
# ===========================================================================

class TestScenarioRateChange:
    def test_rate_rise(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("1000000")},
        ]
        result = scenario_rate_change(positions, 200, _d("0.05"))
        assert result["affected_count"] == 1
        # 200bps = 2%, sensitivity 5% per 100bps -> impact = 2% * 5 = 10% of value
        assert Decimal(result["estimated_impact_usd"]) == _d("100000.00")
        assert "rise" in result["narrative"]

    def test_rate_fall(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("1000000")},
        ]
        result = scenario_rate_change(positions, -100, _d("0.05"))
        assert result["affected_count"] == 1
        assert "fall" in result["narrative"]

    def test_empty_portfolio(self):
        result = scenario_rate_change([], 200)
        assert result["affected_count"] == 0

    def test_custom_sensitivity(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("1000000")},
        ]
        result_high = scenario_rate_change(positions, 100, _d("0.10"))
        result_low = scenario_rate_change(positions, 100, _d("0.02"))
        assert Decimal(result_high["estimated_impact_usd"]) > Decimal(result_low["estimated_impact_usd"])


# ===========================================================================
# Scenario Analysis: No Flagship Auction
# ===========================================================================

class TestScenarioNoFlagshipAuction:
    def test_basic_cancellation(self):
        positions = [
            {
                "position_id": "1",
                "manufacturer_name": "Ferrari",
                "current_fair_value_usd": _d("1000000"),
                "target_auction_event": "Monterey Car Week",
            },
            {
                "position_id": "2",
                "manufacturer_name": "Porsche",
                "current_fair_value_usd": _d("500000"),
                "target_auction_event": "Paris Sale",
            },
        ]
        result = scenario_no_flagship_auction(positions, ["Monterey Car Week"])
        assert result["affected_count"] == 1
        assert Decimal(result["estimated_impact_usd"]) == _d("100000.00")  # 10% discount

    def test_no_matching_events(self):
        positions = [
            {
                "position_id": "1",
                "manufacturer_name": "Ferrari",
                "current_fair_value_usd": _d("1000000"),
                "target_auction_event": "Paris Sale",
            },
        ]
        result = scenario_no_flagship_auction(positions, ["Monterey Car Week"])
        assert result["affected_count"] == 0

    def test_multiple_events_cancelled(self):
        positions = [
            {
                "position_id": "1",
                "manufacturer_name": "Ferrari",
                "current_fair_value_usd": _d("1000000"),
                "target_auction_event": "Monterey Car Week",
            },
            {
                "position_id": "2",
                "manufacturer_name": "Porsche",
                "current_fair_value_usd": _d("500000"),
                "target_auction_event": "Amelia Island",
            },
        ]
        result = scenario_no_flagship_auction(
            positions, ["Monterey Car Week", "Amelia Island"]
        )
        assert result["affected_count"] == 2

    def test_no_target_event(self):
        positions = [
            {
                "position_id": "1",
                "manufacturer_name": "Ferrari",
                "current_fair_value_usd": _d("1000000"),
                "target_auction_event": "",
            },
        ]
        result = scenario_no_flagship_auction(positions, ["Monterey Car Week"])
        assert result["affected_count"] == 0

    def test_empty_portfolio(self):
        result = scenario_no_flagship_auction([], ["Monterey Car Week"])
        assert result["affected_count"] == 0


# ===========================================================================
# Edge Cases
# ===========================================================================

class TestEdgeCases:
    def test_single_position_portfolio(self):
        """Single position means maximum concentration."""
        score, _ = score_concentration_risk(
            position_value=_d("500000"),
            total_portfolio_value=_d("500000"),
            manufacturer_count=1,
            same_manufacturer_count=1,
        )
        assert score >= _d("0.8")

    def test_score_bounds(self):
        """All scores must be in [0, 1]."""
        # Minimum inputs
        score, _ = score_liquidity_risk(0, 0, None, 0)
        assert _d("0") <= score <= _d("1")

        score, _ = score_concentration_risk(_d("0"), _d("0"), 0, 0)
        assert _d("0") <= score <= _d("1")

        score, _ = score_physical_risk(False, False, None)
        assert _d("0") <= score <= _d("1")

        score, _ = score_counterparty_risk(None, None, None)
        assert _d("0") <= score <= _d("1")

        score, _ = score_spec_risk(None, False, None, None, False)
        assert _d("0") <= score <= _d("1")

        score, _ = score_provenance_risk(False, False, False, True, 10)
        assert _d("0") <= score <= _d("1")

    def test_composite_with_single_dimension(self):
        scores = {"liquidity": _d("0.750")}
        assert compute_composite_risk(scores) == _d("0.750")

    def test_market_drop_zero_pct(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("1000000")},
        ]
        result = scenario_market_drop(positions, "Ferrari", _d("0"))
        assert Decimal(result["estimated_impact_usd"]) == _d("0.00")

    def test_rate_change_zero_bps(self):
        positions = [
            {"position_id": "1", "manufacturer_name": "Ferrari", "current_fair_value_usd": _d("1000000")},
        ]
        result = scenario_rate_change(positions, 0)
        assert Decimal(result["estimated_impact_usd"]) == _d("0.00")

    def test_illiquid_boundary_values(self):
        """Test the exact 30% threshold for illiquid warnings."""
        # 30% exactly -> no warning (need >30%)
        positions = [
            ("pos1", 100),  # illiquid
            ("pos2", 100),  # illiquid
            ("pos3", 100),  # illiquid
            ("pos4", 30),
            ("pos5", 30),
            ("pos6", 30),
            ("pos7", 30),
            ("pos8", 30),
            ("pos9", 30),
            ("pos10", 30),
        ]
        pct, warnings = assess_illiquid_exposure(positions)
        assert pct == _d("30.00")
        assert len(warnings) == 0  # exactly 30% does not trigger (threshold is >30%)
