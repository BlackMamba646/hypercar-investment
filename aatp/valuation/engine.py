from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import AssetModel, FairValue
from aatp.valuation.appreciation import AppreciationCurveModel
from aatp.valuation.comparable import ComparableTransactionModel
from aatp.valuation.cost_return import CostReturnCalculator

logger = get_logger("valuation.engine")


class ValuationEngine:

    def __init__(
        self,
        session: AsyncSession,
        lookback_months: int = 12,
        half_life_days: int = 90,
        min_comparables: int = 3,
    ):
        self.db = session
        self.comparable_model = ComparableTransactionModel(
            session,
            lookback_months=lookback_months,
            half_life_days=half_life_days,
            min_comparables=min_comparables,
        )
        self.appreciation_model = AppreciationCurveModel(session)
        self.cost_return_calc = CostReturnCalculator(session)

    async def value_model(
        self,
        asset_model_id: uuid.UUID,
        valuation_date: Optional[date] = None,
    ) -> Optional[FairValue]:
        if valuation_date is None:
            valuation_date = date.today()

        comp_result = await self.comparable_model.compute(
            asset_model_id, valuation_date
        )
        if comp_result is None:
            logger.warning(
                "insufficient_comparables",
                asset_model_id=str(asset_model_id),
            )
            return None

        appr_result = await self.appreciation_model.compute(
            asset_model_id, valuation_date
        )

        warnings = list(comp_result.warnings)

        cost_return_data = None
        if comp_result.fair_value_mid > 0:
            try:
                cost_return_data = await self.cost_return_calc.compute(
                    acquisition_price=comp_result.fair_value_mid,
                    projected_exit_price=comp_result.fair_value_high,
                    hold_months=12,
                )
                warnings.extend(cost_return_data.warnings)
            except Exception as e:
                logger.warning("cost_return_failed", error=str(e))

        if appr_result.stage:
            await self._update_model_stage(asset_model_id, appr_result.stage)

        model_parameters = {
            "lookback_months": self.comparable_model.lookback_months,
            "half_life_days": self.comparable_model.half_life_days,
            "min_comparables": self.comparable_model.min_comparables,
        }
        if cost_return_data:
            model_parameters["cost_adjusted_net_return_pct"] = str(
                cost_return_data.net_return_pct
            )
            if cost_return_data.irr is not None:
                model_parameters["projected_irr"] = str(cost_return_data.irr)
            if cost_return_data.break_even_months is not None:
                model_parameters["break_even_months"] = cost_return_data.break_even_months

        if appr_result.related_model_signals:
            model_parameters["related_model_signals"] = appr_result.related_model_signals

        methodology_parts = [
            f"Comparable transaction model: {comp_result.comparable_count} comparables "
            f"over {comp_result.comparable_window_months} months, "
            f"exponential decay half-life {self.comparable_model.half_life_days}d."
        ]
        if appr_result.stage:
            methodology_parts.append(
                f"Appreciation stage: {appr_result.stage}."
            )
        if cost_return_data:
            methodology_parts.append(
                f"Cost-adjusted net return: {cost_return_data.net_return_pct}%."
            )

        fair_value = FairValue(
            asset_model_id=asset_model_id,
            valuation_date=valuation_date,
            currency="USD",
            fair_value_low=comp_result.fair_value_low,
            fair_value_mid=comp_result.fair_value_mid,
            fair_value_high=comp_result.fair_value_high,
            confidence_score=comp_result.confidence_score,
            comparable_count=comp_result.comparable_count,
            comparable_window_months=comp_result.comparable_window_months,
            appreciation_stage=appr_result.stage,
            appreciation_rate_30d=appr_result.rate_30d,
            appreciation_rate_90d=appr_result.rate_90d,
            appreciation_rate_365d=appr_result.rate_365d,
            methodology=" ".join(methodology_parts),
            comparable_transaction_ids=comp_result.comparable_transaction_ids,
            model_parameters=model_parameters,
            warnings=warnings if warnings else None,
        )

        self.db.add(fair_value)
        return fair_value

    async def value_all_models(
        self,
        valuation_date: Optional[date] = None,
    ) -> dict:
        if valuation_date is None:
            valuation_date = date.today()

        result = await self.db.execute(select(AssetModel.id))
        model_ids = [row[0] for row in result.all()]

        valued = 0
        skipped = 0
        errors = 0

        for model_id in model_ids:
            try:
                fv = await self.value_model(model_id, valuation_date)
                if fv is not None:
                    valued += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(
                    "valuation_error",
                    asset_model_id=str(model_id),
                    error=str(e),
                )
                errors += 1

        return {
            "total_models": len(model_ids),
            "valued": valued,
            "skipped_insufficient_data": skipped,
            "errors": errors,
            "valuation_date": str(valuation_date),
        }

    async def _update_model_stage(
        self, asset_model_id: uuid.UUID, stage: str
    ) -> None:
        result = await self.db.execute(
            select(AssetModel).where(AssetModel.id == asset_model_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.appreciation_stage = stage
