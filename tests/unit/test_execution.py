"""Tests for the execution engine -- Module 7.

Tests acquisition channel ranking, exit strategy selection,
round-trip cost calculation, and spec scoring.  All functions under
test are pure (no DB).
"""

from datetime import date
from decimal import Decimal

import pytest

from aatp.execution.acquisition import (
    AcquisitionChannel,
    recommend_acquisition_channel,
    _calculate_bat_premium,
    _calculate_rm_premium,
    _calculate_dealer_premium,
)
from aatp.execution.exit_strategy import (
    ExitStrategy,
    UpcomingEvent,
    recommend_exit_channel,
    generate_preparation_checklist,
    _calculate_bat_exit_fees,
    _calculate_rm_exit_fees,
)
from aatp.execution.cost_calculator import (
    AcquisitionCostBreakdown,
    ExitCostBreakdown,
    RoundTripCost,
    calculate_acquisition_cost,
    calculate_exit_cost,
    calculate_round_trip_cost,
)
from aatp.execution.spec_guide import (
    RecommendedSpec,
    SpecScore,
    score_spec,
)


# ---------------------------------------------------------------------------
# Acquisition channel tests
# ---------------------------------------------------------------------------


class TestBaTBuyerPremium:
    def test_small_value_full_percentage(self):
        # 5% of $50,000 = $2,500 (under cap)
        assert _calculate_bat_premium(Decimal("50000")) == Decimal("2500.00")

    def test_cap_applied(self):
        # 5% of $200,000 = $10,000, capped at $5,000
        assert _calculate_bat_premium(Decimal("200000")) == Decimal("5000")

    def test_exactly_at_cap_threshold(self):
        # 5% of $100,000 = $5,000 (equals cap)
        assert _calculate_bat_premium(Decimal("100000")) == Decimal("5000.00")


class TestRMBuyerPremium:
    def test_under_250k(self):
        # 12.5% of $200,000 = $25,000
        assert _calculate_rm_premium(Decimal("200000")) == Decimal("25000.00")

    def test_between_250k_and_1m(self):
        # $250k * 12.5% + $250k * 12% = $31,250 + $30,000 = $61,250
        assert _calculate_rm_premium(Decimal("500000")) == Decimal("61250.00")

    def test_above_1m(self):
        # $250k * 12.5% + $750k * 12% + $500k * 10%
        # = $31,250 + $90,000 + $50,000 = $171,250
        assert _calculate_rm_premium(Decimal("1500000")) == Decimal("171250.00")

    def test_exactly_at_250k(self):
        assert _calculate_rm_premium(Decimal("250000")) == Decimal("31250.00")

    def test_exactly_at_1m(self):
        # $250k * 12.5% + $750k * 12% = $31,250 + $90,000 = $121,250
        assert _calculate_rm_premium(Decimal("1000000")) == Decimal("121250.00")


class TestAcquisitionChannelRanking:
    def test_low_value_prefers_bat(self):
        """For a $50k asset, BaT should score well due to low fees."""
        results = recommend_acquisition_channel(
            Decimal("50000"), "US"
        )
        assert len(results) == 4
        # BaT or private sale should be near the top for low value
        channel_names = [r.channel_name for r in results]
        assert "bat_auction" in channel_names

    def test_high_value_includes_rm(self):
        """For a $1M asset, RM Sotheby's should be included."""
        results = recommend_acquisition_channel(
            Decimal("1000000"), "US"
        )
        channel_names = [r.channel_name for r in results]
        assert "rm_sothebys" in channel_names

    def test_results_sorted_by_score_desc(self):
        results = recommend_acquisition_channel(
            Decimal("300000"), "US"
        )
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_filter_available_channels(self):
        results = recommend_acquisition_channel(
            Decimal("100000"), "US", available_channels=["bat_auction", "private_sale"]
        )
        assert len(results) == 2
        channel_names = {r.channel_name for r in results}
        assert channel_names == {"bat_auction", "private_sale"}

    def test_zero_value_returns_empty(self):
        assert recommend_acquisition_channel(Decimal("0"), "US") == []

    def test_negative_value_returns_empty(self):
        assert recommend_acquisition_channel(Decimal("-100"), "US") == []

    def test_each_channel_has_pros_and_cons(self):
        results = recommend_acquisition_channel(
            Decimal("200000"), "US"
        )
        for r in results:
            assert len(r.pros) > 0
            assert len(r.cons) > 0

    def test_estimated_total_cost_exceeds_asset_value(self):
        results = recommend_acquisition_channel(
            Decimal("150000"), "US"
        )
        for r in results:
            assert r.estimated_total_cost > Decimal("150000")


# ---------------------------------------------------------------------------
# Exit strategy tests
# ---------------------------------------------------------------------------


class TestExitFeeCalculations:
    def test_bat_exit_fees_under_cap(self):
        # $99 listing + 5% of $50,000 = $2,500, total $2,599
        assert _calculate_bat_exit_fees(Decimal("50000")) == Decimal("2599")

    def test_bat_exit_fees_cap_applied(self):
        # $99 + min(5% of $200,000, $5,000) = $99 + $5,000 = $5,099
        assert _calculate_bat_exit_fees(Decimal("200000")) == Decimal("5099")

    def test_rm_exit_fees(self):
        # 10% of $500,000 = $50,000
        assert _calculate_rm_exit_fees(Decimal("500000")) == Decimal("50000.00")


class TestExitStrategyRecommendation:
    def test_high_value_recommends_rm_flagship(self):
        strategies = recommend_exit_channel(
            Decimal("750000"), hold_months=12, geography="US"
        )
        channels = [s.channel for s in strategies]
        assert "rm_sothebys_flagship" in channels

    def test_mid_value_recommends_bat_and_bonhams(self):
        strategies = recommend_exit_channel(
            Decimal("200000"), hold_months=6, geography="US"
        )
        channels = [s.channel for s in strategies]
        assert "bat_auction" in channels
        assert "bonhams" in channels

    def test_low_value_recommends_bat(self):
        strategies = recommend_exit_channel(
            Decimal("50000"), hold_months=6, geography="US"
        )
        channels = [s.channel for s in strategies]
        assert "bat_auction" in channels

    def test_always_includes_private_and_dealer(self):
        strategies = recommend_exit_channel(
            Decimal("300000"), hold_months=6, geography="US"
        )
        channels = [s.channel for s in strategies]
        assert "private_sale" in channels
        assert "dealer_consignment" in channels

    def test_sorted_by_net_proceeds(self):
        strategies = recommend_exit_channel(
            Decimal("200000"), hold_months=6, geography="US"
        )
        proceeds = [s.estimated_net_proceeds for s in strategies]
        assert proceeds == sorted(proceeds, reverse=True)

    def test_zero_value_returns_empty(self):
        assert recommend_exit_channel(Decimal("0"), 6, "US") == []

    def test_long_hold_adds_warning(self):
        strategies = recommend_exit_channel(
            Decimal("200000"), hold_months=30, geography="US"
        )
        for s in strategies:
            assert "WARNING" in s.timing_notes

    def test_upcoming_flagship_event_used(self):
        events = [
            UpcomingEvent(
                name="Monterey 2026",
                event_date=date(2026, 8, 15),
                is_flagship=True,
                auction_house="RM Sotheby's",
                consignment_deadline=date(2026, 5, 1),
            ),
        ]
        strategies = recommend_exit_channel(
            Decimal("750000"),
            hold_months=12,
            geography="US",
            upcoming_events=events,
        )
        rm_flagship = [s for s in strategies if s.channel == "rm_sothebys_flagship"]
        assert len(rm_flagship) == 1
        assert "Monterey 2026" in rm_flagship[0].timing_notes


class TestPreparationChecklist:
    def test_basic_checklist_always_present(self):
        checklist = generate_preparation_checklist(
            needs_certification=False, needs_detailing=False
        )
        assert any("photography" in step.lower() for step in checklist)
        assert any("service history" in step.lower() for step in checklist)
        assert any("vin" in step.lower() for step in checklist)

    def test_certification_steps_included(self):
        checklist = generate_preparation_checklist(
            needs_certification=True, needs_detailing=False
        )
        assert any("certification" in step.lower() for step in checklist)

    def test_detailing_steps_included(self):
        checklist = generate_preparation_checklist(
            needs_certification=False, needs_detailing=True
        )
        assert any("paint correction" in step.lower() for step in checklist)
        assert any("interior" in step.lower() for step in checklist)

    def test_full_checklist_length(self):
        checklist = generate_preparation_checklist(
            needs_certification=True, needs_detailing=True
        )
        # Should have base steps + cert steps + detailing steps
        assert len(checklist) >= 10


# ---------------------------------------------------------------------------
# Cost calculator tests
# ---------------------------------------------------------------------------


class TestAcquisitionCostCalculation:
    def test_bat_acquisition(self):
        result = calculate_acquisition_cost(
            Decimal("80000"), "bat_auction", "US"
        )
        assert result.buyer_premium == Decimal("4000.00")
        assert result.purchase_price == Decimal("80000")
        assert result.total > Decimal("80000")

    def test_rm_acquisition(self):
        result = calculate_acquisition_cost(
            Decimal("300000"), "rm_sothebys", "US"
        )
        # $250k * 12.5% + $50k * 12% = $31,250 + $6,000 = $37,250
        assert result.buyer_premium == Decimal("37250.00")

    def test_uk_geography_applies_duty_and_vat(self):
        result = calculate_acquisition_cost(
            Decimal("100000"), "private_sale", "UK"
        )
        assert result.import_duty > Decimal("0")
        assert result.vat > Decimal("0")

    def test_us_geography_minimal_duty(self):
        result = calculate_acquisition_cost(
            Decimal("100000"), "bat_auction", "US"
        )
        # US has 2.5% import duty, 0% VAT
        assert result.import_duty == Decimal("2500.00")
        assert result.vat == Decimal("0.00")

    def test_custom_overrides(self):
        result = calculate_acquisition_cost(
            Decimal("100000"),
            "private_sale",
            "US",
            transport=Decimal("5000"),
            import_duty_pct=Decimal("0"),
            vat_pct=Decimal("0"),
        )
        assert result.transport == Decimal("5000")
        assert result.import_duty == Decimal("0.00")
        assert result.vat == Decimal("0.00")


class TestExitCostCalculation:
    def test_rm_exit(self):
        result = calculate_exit_cost(Decimal("400000"), "rm_sothebys")
        assert result.seller_commission == Decimal("40000.00")
        assert result.net_proceeds == Decimal("400000") - Decimal("40000") - Decimal("5000")

    def test_bat_exit(self):
        result = calculate_exit_cost(Decimal("60000"), "bat_auction")
        # $99 + min(5% * $60k, $5000) = $99 + $3000 = $3099
        assert result.seller_commission == Decimal("3099")

    def test_custom_preparation(self):
        result = calculate_exit_cost(
            Decimal("200000"), "private_sale", preparation=Decimal("10000")
        )
        assert result.preparation == Decimal("10000")


class TestRoundTripCost:
    def test_profitable_round_trip(self):
        result = calculate_round_trip_cost(
            acquisition_price=Decimal("200000"),
            exit_price=Decimal("280000"),
            hold_months=12,
            channel_in="bat_auction",
            channel_out="rm_sothebys",
            geography="US",
            import_duty_pct=Decimal("0"),
            vat_pct=Decimal("0"),
        )
        assert result.gross_profit == Decimal("80000")
        assert result.net_profit < result.gross_profit  # costs reduce profit
        assert result.total_all_costs > Decimal("0")
        assert result.hold_months == 12

    def test_unprofitable_round_trip(self):
        result = calculate_round_trip_cost(
            acquisition_price=Decimal("200000"),
            exit_price=Decimal("200000"),  # no appreciation
            hold_months=12,
            channel_in="rm_sothebys",
            channel_out="rm_sothebys",
            geography="US",
            import_duty_pct=Decimal("0"),
            vat_pct=Decimal("0"),
        )
        assert result.net_profit < Decimal("0")
        assert result.net_return_pct < Decimal("0")

    def test_holding_costs_scale_with_months(self):
        short = calculate_round_trip_cost(
            Decimal("100000"), Decimal("120000"), 6,
            "bat_auction", "bat_auction", "US",
            import_duty_pct=Decimal("0"), vat_pct=Decimal("0"),
        )
        long = calculate_round_trip_cost(
            Decimal("100000"), Decimal("120000"), 24,
            "bat_auction", "bat_auction", "US",
            import_duty_pct=Decimal("0"), vat_pct=Decimal("0"),
        )
        assert long.total_holding_costs > short.total_holding_costs
        assert long.insurance_total > short.insurance_total
        assert long.storage_total > short.storage_total

    def test_insurance_and_storage_breakdown(self):
        result = calculate_round_trip_cost(
            acquisition_price=Decimal("100000"),
            exit_price=Decimal("120000"),
            hold_months=12,
            channel_in="private_sale",
            channel_out="private_sale",
            geography="US",
            import_duty_pct=Decimal("0"),
            vat_pct=Decimal("0"),
        )
        # Insurance: 1.25% of $100k * 12/12 = $1,250
        assert result.insurance_total == Decimal("1250.00")
        # Storage: $800 * 12 = $9,600
        assert result.storage_total == Decimal("9600.00")


# ---------------------------------------------------------------------------
# Spec scoring tests
# ---------------------------------------------------------------------------


class TestSpecScoring:
    @pytest.fixture
    def ideal_spec(self):
        return RecommendedSpec(
            recommended_colours=["Rosso Corsa", "Nero", "Argento Nurburgring"],
            recommended_options=["Carbon fibre racing seats", "Front axle lift"],
            avoid_options=["Aftermarket exhaust", "Non-OEM wheels"],
            mileage_ceiling=10000,
            drive_side_preference="LHD",
            certification_required=True,
            certification_type="Ferrari Classiche",
        )

    def test_perfect_spec(self, ideal_spec):
        result = score_spec(
            colour_exterior="Rosso Corsa",
            colour_interior="Nero",
            options=["Carbon fibre racing seats", "Front axle lift"],
            mileage=5000,
            drive_side="LHD",
            has_certification=True,
            recommended_spec=ideal_spec,
        )
        assert result.total_score >= Decimal("80")
        assert result.colour_score == Decimal("100.00")
        assert result.certification_score == Decimal("100")
        assert len(result.deductions) == 0

    def test_bad_colour_penalised(self, ideal_spec):
        result = score_spec(
            colour_exterior="Giallo Modena",
            colour_interior="Red",
            options=["Carbon fibre racing seats", "Front axle lift"],
            mileage=5000,
            drive_side="LHD",
            has_certification=True,
            recommended_spec=ideal_spec,
        )
        assert result.colour_score < Decimal("100")
        assert any("exterior" in d.lower() for d in result.deductions)

    def test_avoided_options_penalised(self, ideal_spec):
        result = score_spec(
            colour_exterior="Rosso Corsa",
            colour_interior="Nero",
            options=["Carbon fibre racing seats", "Aftermarket exhaust"],
            mileage=5000,
            drive_side="LHD",
            has_certification=True,
            recommended_spec=ideal_spec,
        )
        assert result.options_score < Decimal("100")
        assert any("avoided option" in d.lower() for d in result.deductions)

    def test_high_mileage_penalised(self, ideal_spec):
        result = score_spec(
            colour_exterior="Rosso Corsa",
            colour_interior="Nero",
            options=["Carbon fibre racing seats", "Front axle lift"],
            mileage=25000,
            drive_side="LHD",
            has_certification=True,
            recommended_spec=ideal_spec,
        )
        assert result.mileage_score < Decimal("80")
        assert any("exceeds ceiling" in d.lower() for d in result.deductions)

    def test_missing_certification_penalised(self, ideal_spec):
        result = score_spec(
            colour_exterior="Rosso Corsa",
            colour_interior="Nero",
            options=["Carbon fibre racing seats", "Front axle lift"],
            mileage=5000,
            drive_side="LHD",
            has_certification=False,
            recommended_spec=ideal_spec,
        )
        assert result.certification_score == Decimal("0")
        assert any("certification" in d.lower() for d in result.deductions)

    def test_drive_side_mismatch_penalised(self, ideal_spec):
        result = score_spec(
            colour_exterior="Rosso Corsa",
            colour_interior="Nero",
            options=["Carbon fibre racing seats", "Front axle lift"],
            mileage=5000,
            drive_side="RHD",
            has_certification=True,
            recommended_spec=ideal_spec,
        )
        assert any("drive side" in d.lower() for d in result.deductions)
        # Score should be lower than perfect
        perfect = score_spec(
            colour_exterior="Rosso Corsa",
            colour_interior="Nero",
            options=["Carbon fibre racing seats", "Front axle lift"],
            mileage=5000,
            drive_side="LHD",
            has_certification=True,
            recommended_spec=ideal_spec,
        )
        assert result.total_score < perfect.total_score

    def test_score_stays_in_bounds(self, ideal_spec):
        """Even with multiple penalties, score stays 0-100."""
        result = score_spec(
            colour_exterior="Pink",
            colour_interior="Pink",
            options=["Aftermarket exhaust", "Non-OEM wheels"],
            mileage=100000,
            drive_side="RHD",
            has_certification=False,
            recommended_spec=ideal_spec,
        )
        assert Decimal("0") <= result.total_score <= Decimal("100")

    def test_no_recommended_spec_lenient(self):
        """With empty recommendations, scoring is lenient."""
        lenient_spec = RecommendedSpec(
            recommended_colours=[],
            recommended_options=[],
            avoid_options=[],
            mileage_ceiling=None,
            drive_side_preference=None,
            certification_required=False,
        )
        result = score_spec(
            colour_exterior="Any Colour",
            colour_interior="Any Interior",
            options=["Some option"],
            mileage=5000,
            drive_side="LHD",
            has_certification=False,
            recommended_spec=lenient_spec,
        )
        assert result.total_score >= Decimal("70")
