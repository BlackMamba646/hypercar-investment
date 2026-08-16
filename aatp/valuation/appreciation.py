from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import (
    AssetModelRelationship,
    Transaction,
    TransactionType,
)

logger = get_logger("valuation.appreciation")

SOLD_TYPES = {
    TransactionType.AUCTION_SOLD,
    TransactionType.DEALER_SOLD,
    TransactionType.PRIVATE_SALE,
}

STAGES = ("discovery", "acceleration", "plateau", "correction")


@dataclass
class AppreciationResult:
    rate_30d: Optional[Decimal]
    rate_90d: Optional[Decimal]
    rate_365d: Optional[Decimal]
    stage: Optional[str]
    related_model_signals: list[dict] = field(default_factory=list)


class AppreciationCurveModel:

    def __init__(self, session: AsyncSession, min_data_points: int = 3):
        self.db = session
        self.min_data_points = min_data_points

    async def compute(
        self,
        asset_model_id: uuid.UUID,
        valuation_date: date,
    ) -> AppreciationResult:
        prices = await self._fetch_price_series(asset_model_id, valuation_date)

        rate_30d = self._rolling_rate(prices, valuation_date, 30)
        rate_90d = self._rolling_rate(prices, valuation_date, 90)
        rate_365d = self._rolling_rate(prices, valuation_date, 365)

        stage = classify_stage(
            rate_30d=rate_30d,
            rate_90d=rate_90d,
            rate_365d=rate_365d,
            comparable_count=len(prices),
        )

        related_signals = await self._related_model_signals(
            asset_model_id, valuation_date
        )

        return AppreciationResult(
            rate_30d=_to_decimal(rate_30d),
            rate_90d=_to_decimal(rate_90d),
            rate_365d=_to_decimal(rate_365d),
            stage=stage,
            related_model_signals=related_signals,
        )

    async def _fetch_price_series(
        self,
        asset_model_id: uuid.UUID,
        valuation_date: date,
    ) -> list[tuple[date, float]]:
        cutoff = valuation_date - timedelta(days=730)
        stmt = (
            select(Transaction.transaction_date, Transaction.normalised_price_usd)
            .where(
                and_(
                    Transaction.asset_model_id == asset_model_id,
                    Transaction.transaction_type.in_(SOLD_TYPES),
                    Transaction.normalised_price_usd.isnot(None),
                    Transaction.transaction_date >= cutoff,
                    Transaction.transaction_date <= valuation_date,
                )
            )
            .order_by(Transaction.transaction_date)
        )
        result = await self.db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    def _rolling_rate(
        self,
        prices: list[tuple[date, float]],
        valuation_date: date,
        window_days: int,
    ) -> Optional[float]:
        cutoff = valuation_date - timedelta(days=window_days)
        window = [(d, p) for d, p in prices if d >= cutoff]

        if len(window) < self.min_data_points:
            return None

        earlier = [p for d, p in window if d <= cutoff + timedelta(days=window_days // 3)]
        later = [p for d, p in window if d >= valuation_date - timedelta(days=window_days // 3)]

        if not earlier or not later:
            start_price = window[0][1]
            end_price = window[-1][1]
        else:
            start_price = float(np.median(earlier))
            end_price = float(np.median(later))

        if start_price <= 0:
            return None

        raw_rate = (end_price - start_price) / start_price
        annualised = raw_rate * (365.0 / window_days)
        return annualised

    async def _related_model_signals(
        self,
        asset_model_id: uuid.UUID,
        valuation_date: date,
    ) -> list[dict]:
        stmt = select(AssetModelRelationship).where(
            AssetModelRelationship.source_model_id == asset_model_id
        )
        result = await self.db.execute(stmt)
        relationships = list(result.scalars().all())

        signals = []
        for rel in relationships:
            related_prices = await self._fetch_price_series(
                rel.related_model_id, valuation_date
            )
            rate_365 = self._rolling_rate(related_prices, valuation_date, 365)
            if rate_365 is not None and abs(rate_365) > 0.05:
                signals.append({
                    "related_model_id": str(rel.related_model_id),
                    "relationship_type": rel.relationship_type,
                    "correlation_strength": float(rel.correlation_strength or 0),
                    "appreciation_rate_365d": round(rate_365, 4),
                })

        return signals


def classify_stage(
    rate_30d: Optional[float],
    rate_90d: Optional[float],
    rate_365d: Optional[float],
    comparable_count: int,
) -> Optional[str]:
    if rate_365d is None:
        return None

    if rate_90d is not None and rate_90d < 0:
        return "correction"

    if rate_365d > 0.05 and comparable_count < 10:
        return "discovery"

    if rate_90d is not None and rate_90d > 0.15:
        return "acceleration"

    if rate_90d is not None and abs(rate_90d) <= 0.05:
        return "plateau"

    if rate_365d > 0.05:
        return "acceleration"

    if rate_365d <= 0.05 and rate_365d >= -0.05:
        return "plateau"

    return "correction"


def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(round(value, 4)))
