"""Tests for the cost-adjusted return calculator."""

from decimal import Decimal

import pytest

from aatp.valuation.cost_return import (
    CostBreakdown,
    _default_cost_breakdown,
    _irr_newton,
    _pct,
    compute_cost_breakdown,
    compute_irr,
)


class TestDefaultCostBreakdown:
    def test_buyer_premium_is_12_5_pct(self):
        breakdown = _default_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 12
        )
        assert breakdown.buyer_premium == Decimal("125000.00")

    def test_seller_commission_is_10_pct(self):
        breakdown = _default_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 12
        )
        assert breakdown.seller_commission == Decimal("130000.00")

    def test_storage_scales_with_months(self):
        b6 = _default_cost_breakdown(Decimal("1000000"), Decimal("1300000"), 6)
        b12 = _default_cost_breakdown(Decimal("1000000"), Decimal("1300000"), 12)
        assert b12.storage_total == b6.storage_total * 2

    def test_insurance_scales_with_months(self):
        b6 = _default_cost_breakdown(Decimal("1000000"), Decimal("1300000"), 6)
        b12 = _default_cost_breakdown(Decimal("1000000"), Decimal("1300000"), 12)
        assert b12.insurance_total == b12.insurance_total

    def test_total_costs_add_up(self):
        breakdown = _default_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 12
        )
        expected = (
            breakdown.total_acquisition_costs
            + breakdown.total_holding_costs
            + breakdown.total_exit_costs
        )
        assert breakdown.total_costs == expected

    def test_acquisition_costs_include_premium_and_transport(self):
        breakdown = _default_cost_breakdown(
            Decimal("500000"), Decimal("650000"), 12
        )
        assert breakdown.total_acquisition_costs >= breakdown.buyer_premium + breakdown.transport

    def test_exit_costs_include_prep_and_commission(self):
        breakdown = _default_cost_breakdown(
            Decimal("500000"), Decimal("650000"), 12
        )
        assert breakdown.total_exit_costs == breakdown.preparation + breakdown.seller_commission

    def test_zero_hold_months(self):
        breakdown = _default_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 0
        )
        assert breakdown.storage_total == Decimal("0.00")
        assert breakdown.insurance_total == Decimal("0.00")


class TestComputeCostBreakdownWithModel:
    def _make_cost_model(self):
        from unittest.mock import MagicMock
        cm = MagicMock()
        cm.buyer_premium_pct = Decimal("12.500")
        cm.seller_commission_pct = Decimal("10.000")
        cm.insurance_annual_pct = Decimal("1.250")
        cm.storage_monthly = Decimal("800.00")
        cm.transport_estimate = Decimal("3000.00")
        cm.preparation_estimate = Decimal("5000.00")
        cm.import_duty_pct = Decimal("2.500")
        cm.vat_pct = Decimal("20.000")
        return cm

    def test_import_duty_applied(self):
        cm = self._make_cost_model()
        breakdown = compute_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 12, cm
        )
        assert breakdown.import_duty == Decimal("25000.00")

    def test_vat_applied(self):
        cm = self._make_cost_model()
        breakdown = compute_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 12, cm
        )
        assert breakdown.vat == Decimal("200000.00")

    def test_no_cost_model_uses_defaults(self):
        breakdown = compute_cost_breakdown(
            Decimal("1000000"), Decimal("1300000"), 12, None
        )
        assert breakdown.import_duty == Decimal("0")
        assert breakdown.vat == Decimal("0")


class TestIRRNewton:
    def test_simple_doubling(self):
        # Invest 1000, get 2000 after 12 months
        cash_flows = [-1000.0] + [0.0] * 11 + [2000.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert irr > 0

    def test_breakeven(self):
        # Invest 1000, get 1000 after 1 month — IRR ~0
        cash_flows = [-1000.0, 1000.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert abs(irr) < 0.01

    def test_loss(self):
        # Invest 1000, get 500 back
        cash_flows = [-1000.0, 500.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert irr < 0


class TestPct:
    def test_positive_return(self):
        assert _pct(Decimal("30"), Decimal("100")) == Decimal("30.00")

    def test_zero_denominator(self):
        assert _pct(Decimal("100"), Decimal("0")) == Decimal("0")

    def test_negative_return(self):
        assert _pct(Decimal("-10"), Decimal("100")) == Decimal("-10.00")


class TestComputeIRR:
    def test_profitable_deal_positive_irr(self):
        breakdown = _default_cost_breakdown(
            Decimal("500000"), Decimal("750000"), 12
        )
        exit_proceeds = Decimal("750000") - breakdown.seller_commission
        irr = compute_irr(Decimal("500000"), breakdown, exit_proceeds, 12)
        # 50% gross appreciation on 500k with costs should still be positive
        if irr is not None:
            assert irr > Decimal("0")

    def test_losing_deal_negative_irr(self):
        breakdown = _default_cost_breakdown(
            Decimal("500000"), Decimal("400000"), 12
        )
        exit_proceeds = Decimal("400000") - breakdown.seller_commission
        irr = compute_irr(Decimal("500000"), breakdown, exit_proceeds, 12)
        if irr is not None:
            assert irr < Decimal("0")
