from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import CostModel

logger = get_logger("valuation.cost_return")


@dataclass
class CostBreakdown:
    buyer_premium: Decimal
    import_duty: Decimal
    vat: Decimal
    transport: Decimal
    insurance_total: Decimal
    storage_total: Decimal
    preparation: Decimal
    seller_commission: Decimal
    total_acquisition_costs: Decimal
    total_holding_costs: Decimal
    total_exit_costs: Decimal
    total_costs: Decimal


@dataclass
class ReturnResult:
    cost_breakdown: CostBreakdown
    gross_return_pct: Decimal
    net_return_pct: Decimal
    irr: Optional[Decimal]
    break_even_months: Optional[int]
    exit_proceeds: Decimal
    total_cost_basis: Decimal
    warnings: list[str] = field(default_factory=list)


class CostReturnCalculator:

    def __init__(self, session: AsyncSession):
        self.db = session

    async def compute(
        self,
        acquisition_price: Decimal,
        projected_exit_price: Decimal,
        hold_months: int,
        cost_model_name: Optional[str] = None,
        cost_model_id: Optional[uuid.UUID] = None,
    ) -> ReturnResult:
        cost_model = await self._load_cost_model(cost_model_name, cost_model_id)
        breakdown = compute_cost_breakdown(
            acquisition_price, projected_exit_price, hold_months, cost_model
        )

        total_cost_basis = acquisition_price + breakdown.total_costs
        exit_proceeds = projected_exit_price - breakdown.seller_commission
        gross_return_pct = _pct(projected_exit_price - acquisition_price, acquisition_price)
        net_return_pct = _pct(exit_proceeds - total_cost_basis, total_cost_basis)

        irr = compute_irr(
            acquisition_price, breakdown, exit_proceeds, hold_months
        )

        break_even = self._break_even_months(
            acquisition_price, projected_exit_price, cost_model, max_months=60
        )

        warnings = []
        if net_return_pct < Decimal("0"):
            warnings.append("Negative net return after costs")
        if hold_months > 24:
            warnings.append(f"Hold period {hold_months} months exceeds 24-month target")
        if cost_model is None:
            warnings.append("No cost model found — using defaults")

        return ReturnResult(
            cost_breakdown=breakdown,
            gross_return_pct=gross_return_pct,
            net_return_pct=net_return_pct,
            irr=irr,
            break_even_months=break_even,
            exit_proceeds=exit_proceeds,
            total_cost_basis=total_cost_basis,
            warnings=warnings,
        )

    async def _load_cost_model(
        self,
        name: Optional[str],
        model_id: Optional[uuid.UUID],
    ) -> Optional[CostModel]:
        if model_id:
            result = await self.db.execute(
                select(CostModel).where(CostModel.id == model_id)
            )
            return result.scalar_one_or_none()

        if name:
            result = await self.db.execute(
                select(CostModel).where(CostModel.name == name)
            )
            return result.scalar_one_or_none()

        result = await self.db.execute(select(CostModel).limit(1))
        return result.scalar_one_or_none()

    def _break_even_months(
        self,
        acquisition_price: Decimal,
        projected_exit_price: Decimal,
        cost_model: Optional[CostModel],
        max_months: int = 60,
    ) -> Optional[int]:
        if cost_model is None:
            return None

        for months in range(1, max_months + 1):
            breakdown = compute_cost_breakdown(
                acquisition_price, projected_exit_price, months, cost_model
            )
            total_cost_basis = acquisition_price + breakdown.total_costs
            exit_proceeds = projected_exit_price - breakdown.seller_commission
            if exit_proceeds > total_cost_basis:
                return months

        return None


def compute_cost_breakdown(
    acquisition_price: Decimal,
    projected_exit_price: Decimal,
    hold_months: int,
    cost_model: Optional[CostModel],
) -> CostBreakdown:
    if cost_model is None:
        return _default_cost_breakdown(acquisition_price, projected_exit_price, hold_months)

    buyer_premium = (acquisition_price * cost_model.buyer_premium_pct / 100).quantize(Decimal("0.01"))
    import_duty = (acquisition_price * cost_model.import_duty_pct / 100).quantize(Decimal("0.01"))
    vat = (acquisition_price * cost_model.vat_pct / 100).quantize(Decimal("0.01"))
    transport = cost_model.transport_estimate

    insurance_total = (
        acquisition_price * cost_model.insurance_annual_pct / 100 * hold_months / 12
    ).quantize(Decimal("0.01"))
    storage_total = (cost_model.storage_monthly * hold_months).quantize(Decimal("0.01"))
    preparation = cost_model.preparation_estimate

    seller_commission = (
        projected_exit_price * cost_model.seller_commission_pct / 100
    ).quantize(Decimal("0.01"))

    total_acquisition = buyer_premium + import_duty + vat + transport
    total_holding = insurance_total + storage_total
    total_exit = preparation + seller_commission
    total = total_acquisition + total_holding + total_exit

    return CostBreakdown(
        buyer_premium=buyer_premium,
        import_duty=import_duty,
        vat=vat,
        transport=transport,
        insurance_total=insurance_total,
        storage_total=storage_total,
        preparation=preparation,
        seller_commission=seller_commission,
        total_acquisition_costs=total_acquisition,
        total_holding_costs=total_holding,
        total_exit_costs=total_exit,
        total_costs=total,
    )


def _default_cost_breakdown(
    acquisition_price: Decimal,
    projected_exit_price: Decimal,
    hold_months: int,
) -> CostBreakdown:
    buyer_premium = (acquisition_price * Decimal("0.125")).quantize(Decimal("0.01"))
    import_duty = Decimal("0")
    vat = Decimal("0")
    transport = Decimal("3000.00")

    insurance_total = (
        acquisition_price * Decimal("0.0125") * hold_months / 12
    ).quantize(Decimal("0.01"))
    storage_total = (Decimal("800") * hold_months).quantize(Decimal("0.01"))
    preparation = Decimal("5000.00")

    seller_commission = (projected_exit_price * Decimal("0.10")).quantize(Decimal("0.01"))

    total_acquisition = buyer_premium + import_duty + vat + transport
    total_holding = insurance_total + storage_total
    total_exit = preparation + seller_commission
    total = total_acquisition + total_holding + total_exit

    return CostBreakdown(
        buyer_premium=buyer_premium,
        import_duty=import_duty,
        vat=vat,
        transport=transport,
        insurance_total=insurance_total,
        storage_total=storage_total,
        preparation=preparation,
        seller_commission=seller_commission,
        total_acquisition_costs=total_acquisition,
        total_holding_costs=total_holding,
        total_exit_costs=total_exit,
        total_costs=total,
    )


def compute_irr(
    acquisition_price: Decimal,
    breakdown: CostBreakdown,
    exit_proceeds: Decimal,
    hold_months: int,
) -> Optional[Decimal]:
    initial_outflow = float(acquisition_price + breakdown.total_acquisition_costs)
    monthly_holding = float(breakdown.total_holding_costs / hold_months) if hold_months > 0 else 0
    final_inflow = float(exit_proceeds - breakdown.preparation)

    cash_flows = [-initial_outflow]
    for _ in range(hold_months - 1):
        cash_flows.append(-monthly_holding)
    cash_flows.append(final_inflow - monthly_holding)

    try:
        irr_monthly = np.irr(cash_flows) if hasattr(np, "irr") else _irr_newton(cash_flows)
        if irr_monthly is None or not np.isfinite(irr_monthly):
            return None
        irr_annual = (1 + irr_monthly) ** 12 - 1
        return Decimal(str(round(irr_annual, 4)))
    except Exception:
        return None


def _irr_newton(
    cash_flows: list[float],
    tol: float = 1e-8,
    max_iter: int = 100,
) -> Optional[float]:
    for guess in [0.01, -0.3, 0.1, -0.5]:
        rate = guess
        converged = False
        for _ in range(max_iter):
            npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))
            d_npv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cash_flows))
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


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return ((numerator / denominator) * 100).quantize(Decimal("0.01"))
