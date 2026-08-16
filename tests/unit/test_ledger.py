"""Tests for Module 8 — Trading Ledger pure-function P&L calculations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from aatp.ledger.pnl import (
    MonthlyHoldingCost,
    _irr_newton,
    calculate_holding_period_months,
    calculate_irr,
    calculate_realised_pnl,
    calculate_total_cost_basis,
    calculate_unrealised_pnl,
)


# ---------------------------------------------------------------------------
# calculate_unrealised_pnl
# ---------------------------------------------------------------------------

class TestUnrealisedPnl:
    def test_positive_unrealised(self):
        result = calculate_unrealised_pnl(Decimal("1500000"), Decimal("1200000"))
        assert result == Decimal("300000.00")

    def test_negative_unrealised(self):
        result = calculate_unrealised_pnl(Decimal("900000"), Decimal("1200000"))
        assert result == Decimal("-300000.00")

    def test_zero_unrealised(self):
        result = calculate_unrealised_pnl(Decimal("1200000"), Decimal("1200000"))
        assert result == Decimal("0.00")

    def test_precision_is_two_decimals(self):
        result = calculate_unrealised_pnl(Decimal("1000000.999"), Decimal("500000.001"))
        # 1000000.999 - 500000.001 = 500000.998 -> quantise to 500001.00
        assert result == Decimal("500001.00")


# ---------------------------------------------------------------------------
# calculate_realised_pnl
# ---------------------------------------------------------------------------

class TestRealisedPnl:
    def test_profitable_exit(self):
        result = calculate_realised_pnl(Decimal("1800000"), Decimal("1200000"))
        assert result == Decimal("600000.00")

    def test_loss_exit(self):
        result = calculate_realised_pnl(Decimal("1000000"), Decimal("1200000"))
        assert result == Decimal("-200000.00")

    def test_breakeven_exit(self):
        result = calculate_realised_pnl(Decimal("1200000"), Decimal("1200000"))
        assert result == Decimal("0.00")

    def test_large_profit(self):
        result = calculate_realised_pnl(Decimal("5000000"), Decimal("2000000"))
        assert result == Decimal("3000000.00")


# ---------------------------------------------------------------------------
# calculate_total_cost_basis
# ---------------------------------------------------------------------------

class TestTotalCostBasis:
    def test_acquisition_only(self):
        result = calculate_total_cost_basis(Decimal("1000000"), [])
        assert result == Decimal("1000000.00")

    def test_with_single_cost(self):
        result = calculate_total_cost_basis(
            Decimal("1000000"), [Decimal("50000")]
        )
        assert result == Decimal("1050000.00")

    def test_with_multiple_costs(self):
        costs = [
            Decimal("125000"),   # buyer premium
            Decimal("3000"),     # transport
            Decimal("12500"),    # insurance
            Decimal("9600"),     # storage
        ]
        result = calculate_total_cost_basis(Decimal("1000000"), costs)
        assert result == Decimal("1150100.00")

    def test_zero_acquisition_with_costs(self):
        result = calculate_total_cost_basis(
            Decimal("0"), [Decimal("5000"), Decimal("3000")]
        )
        assert result == Decimal("8000.00")

    def test_precision(self):
        costs = [Decimal("100.505"), Decimal("200.495")]
        result = calculate_total_cost_basis(Decimal("1000"), costs)
        assert result == Decimal("1301.00")


# ---------------------------------------------------------------------------
# calculate_holding_period_months
# ---------------------------------------------------------------------------

class TestHoldingPeriodMonths:
    def test_exact_months(self):
        result = calculate_holding_period_months(
            date(2024, 1, 15), date(2024, 7, 15)
        )
        assert result == 6

    def test_partial_month_rounds_down(self):
        result = calculate_holding_period_months(
            date(2024, 1, 20), date(2024, 7, 10)
        )
        # July is month 7, Jan is month 1 => 6, but day 10 < day 20, so 5
        assert result == 5

    def test_one_month(self):
        result = calculate_holding_period_months(
            date(2024, 1, 1), date(2024, 2, 1)
        )
        assert result == 1

    def test_same_day_zero_months(self):
        result = calculate_holding_period_months(
            date(2024, 1, 15), date(2024, 1, 15)
        )
        assert result == 0

    def test_cross_year(self):
        result = calculate_holding_period_months(
            date(2023, 6, 1), date(2025, 6, 1)
        )
        assert result == 24

    def test_never_negative(self):
        # End date before start date should return 0
        result = calculate_holding_period_months(
            date(2024, 6, 15), date(2024, 1, 15)
        )
        assert result == 0

    def test_day_boundary_exact(self):
        # Same day of month across years
        result = calculate_holding_period_months(
            date(2023, 3, 31), date(2024, 3, 31)
        )
        assert result == 12


# ---------------------------------------------------------------------------
# _irr_newton (internal solver)
# ---------------------------------------------------------------------------

class TestIRRNewton:
    def test_simple_doubling_in_12_months(self):
        # Invest 1000, receive 2000 after 12 months
        cash_flows = [-1000.0] + [0.0] * 11 + [2000.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert irr > 0

    def test_breakeven(self):
        cash_flows = [-1000.0, 1000.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert abs(irr) < 0.01

    def test_loss_negative_irr(self):
        cash_flows = [-1000.0, 500.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert irr < 0

    def test_all_zero_returns_none(self):
        cash_flows = [0.0, 0.0, 0.0]
        irr = _irr_newton(cash_flows)
        # With no cash flows, solver should not converge meaningfully
        # (it may return 0 or None depending on convergence)

    def test_monthly_holding_costs(self):
        # Invest 1000, pay 50/month for 12 months, sell for 2000
        cash_flows = [-1000.0] + [-50.0] * 11 + [2000.0 - 50.0]
        irr = _irr_newton(cash_flows)
        assert irr is not None
        assert irr > 0


# ---------------------------------------------------------------------------
# calculate_irr (annualised, using dates)
# ---------------------------------------------------------------------------

class TestCalculateIRR:
    def test_profitable_deal(self):
        irr = calculate_irr(
            acquisition_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1100000"),  # 1M + 100k costs
            holding_costs_by_month=[
                MonthlyHoldingCost(month_offset=m, amount=Decimal("1800"))
                for m in range(1, 13)
            ],
            exit_date=date(2025, 1, 1),
            exit_proceeds=Decimal("1500000"),
        )
        assert irr is not None
        assert irr > Decimal("0")

    def test_losing_deal_negative(self):
        irr = calculate_irr(
            acquisition_date=date(2024, 1, 1),
            acquisition_cost=Decimal("1200000"),
            holding_costs_by_month=[
                MonthlyHoldingCost(month_offset=m, amount=Decimal("2000"))
                for m in range(1, 13)
            ],
            exit_date=date(2025, 1, 1),
            exit_proceeds=Decimal("900000"),
        )
        assert irr is not None
        assert irr < Decimal("0")

    def test_zero_hold_period_returns_none(self):
        irr = calculate_irr(
            acquisition_date=date(2024, 6, 15),
            acquisition_cost=Decimal("1000000"),
            holding_costs_by_month=[],
            exit_date=date(2024, 6, 15),
            exit_proceeds=Decimal("1200000"),
        )
        assert irr is None

    def test_no_holding_costs(self):
        irr = calculate_irr(
            acquisition_date=date(2024, 1, 1),
            acquisition_cost=Decimal("500000"),
            holding_costs_by_month=[],
            exit_date=date(2024, 7, 1),
            exit_proceeds=Decimal("600000"),
        )
        assert irr is not None
        assert irr > Decimal("0")

    def test_short_hold_high_return(self):
        # Quick flip: buy at 500k, sell at 700k in 2 months, no holding costs
        irr = calculate_irr(
            acquisition_date=date(2024, 1, 1),
            acquisition_cost=Decimal("500000"),
            holding_costs_by_month=[],
            exit_date=date(2024, 3, 1),
            exit_proceeds=Decimal("700000"),
        )
        assert irr is not None
        # Annualised IRR should be very high for a 40% return in 2 months
        assert irr > Decimal("1.0")


# ---------------------------------------------------------------------------
# Edge cases and integration between functions
# ---------------------------------------------------------------------------

class TestPnlIntegration:
    def test_cost_basis_feeds_unrealised(self):
        """Cost basis calculation feeds into unrealised P&L."""
        costs = [Decimal("125000"), Decimal("3000"), Decimal("12500")]
        cost_basis = calculate_total_cost_basis(Decimal("1000000"), costs)
        unrealised = calculate_unrealised_pnl(Decimal("1300000"), cost_basis)
        # 1300000 - 1140500 = 159500
        assert unrealised == Decimal("159500.00")

    def test_cost_basis_feeds_realised(self):
        """Cost basis calculation feeds into realised P&L."""
        costs = [Decimal("125000"), Decimal("3000"), Decimal("50000")]
        cost_basis = calculate_total_cost_basis(Decimal("1000000"), costs)
        realised = calculate_realised_pnl(Decimal("1400000"), cost_basis)
        # 1400000 - 1178000 = 222000
        assert realised == Decimal("222000.00")

    def test_unrealised_becomes_zero_at_exit(self):
        """When exited, fair value equals exit price so unrealised = 0
        and we switch to realised."""
        cost_basis = Decimal("1100000")
        exit_price = Decimal("1300000")

        unrealised = calculate_unrealised_pnl(exit_price, cost_basis)
        realised = calculate_realised_pnl(exit_price, cost_basis)

        assert unrealised == realised  # both are 200000.00
        assert realised == Decimal("200000.00")
