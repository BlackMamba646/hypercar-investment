from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

from aatp.core.logging import get_logger

logger = get_logger("ledger.pnl")


def calculate_unrealised_pnl(
    current_fair_value: Decimal,
    total_cost_basis: Decimal,
) -> Decimal:
    """Unrealised P&L = Fair Value - Total Cost Basis."""
    return (current_fair_value - total_cost_basis).quantize(Decimal("0.01"))


def calculate_realised_pnl(
    exit_proceeds: Decimal,
    total_cost_basis: Decimal,
) -> Decimal:
    """Realised P&L = Exit Proceeds - Total Cost Basis."""
    return (exit_proceeds - total_cost_basis).quantize(Decimal("0.01"))


def calculate_total_cost_basis(
    acquisition_price: Decimal,
    cost_amounts: List[Decimal],
) -> Decimal:
    """Total Cost Basis = Acquisition Price + sum of all cost entries."""
    total_costs = sum(cost_amounts, Decimal("0"))
    return (acquisition_price + total_costs).quantize(Decimal("0.01"))


def calculate_holding_period_months(
    acquisition_date: date,
    end_date: date,
) -> int:
    """Calculate holding period in whole months between two dates."""
    months = (end_date.year - acquisition_date.year) * 12 + (
        end_date.month - acquisition_date.month
    )
    if end_date.day < acquisition_date.day:
        months -= 1
    return max(months, 0)


def _irr_newton(
    cash_flows: List[float],
    tol: float = 1e-8,
    max_iter: int = 100,
) -> Optional[float]:
    """Newton-Raphson IRR solver with multiple initial guesses."""
    for guess in [0.01, -0.3, 0.1, -0.5]:
        rate = guess
        converged = False
        for _ in range(max_iter):
            npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))
            d_npv = sum(
                -i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cash_flows)
            )
            if abs(d_npv) < 1e-14:
                break
            new_rate = rate - npv / d_npv
            if new_rate <= -1.0:
                break
            if abs(new_rate - rate) < tol:
                converged = True
                rate = new_rate
                break
            rate = new_rate
        if converged:
            return rate
    return None


@dataclass
class MonthlyHoldingCost:
    """A holding cost incurred in a specific month offset from acquisition."""
    month_offset: int
    amount: Decimal


def calculate_irr(
    acquisition_date: date,
    acquisition_cost: Decimal,
    holding_costs_by_month: List[MonthlyHoldingCost],
    exit_date: date,
    exit_proceeds: Decimal,
) -> Optional[Decimal]:
    """Calculate annualised IRR from actual cash flows.

    Parameters
    ----------
    acquisition_date : date
        Date the asset was acquired.
    acquisition_cost : Decimal
        Total acquisition outflow (acquisition price + acquisition-phase costs).
    holding_costs_by_month : list[MonthlyHoldingCost]
        Monthly holding costs with their month offsets.
    exit_date : date
        Date the asset was sold.
    exit_proceeds : Decimal
        Net cash received at exit (exit price minus exit costs).

    Returns
    -------
    Optional[Decimal]
        Annualised IRR rounded to 4 decimal places, or None if it cannot
        be computed.
    """
    hold_months = calculate_holding_period_months(acquisition_date, exit_date)
    if hold_months <= 0:
        return None

    # Build monthly cash-flow array
    cash_flows = [0.0] * (hold_months + 1)
    cash_flows[0] = -float(acquisition_cost)

    for hc in holding_costs_by_month:
        idx = hc.month_offset
        if 0 <= idx <= hold_months:
            cash_flows[idx] -= float(hc.amount)

    cash_flows[hold_months] += float(exit_proceeds)

    try:
        irr_monthly = _irr_newton(cash_flows)
        if irr_monthly is None:
            return None
        irr_annual = (1 + irr_monthly) ** 12 - 1
        return Decimal(str(round(irr_annual, 4)))
    except Exception:
        logger.warning("irr_calculation_failed", hold_months=hold_months)
        return None
