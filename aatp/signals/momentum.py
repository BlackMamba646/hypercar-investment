"""
Momentum signal generator.

Compares current normalised price trend vs fair value over 30/90-day windows.
Triggers when >5% deviation from expected appreciation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import FairValue, Signal, SignalType, Transaction

logger = get_logger("signals.momentum")

# Deviation threshold before a signal fires (5%)
DEVIATION_THRESHOLD = Decimal("0.05")


@dataclass
class MomentumResult:
    """Pure data result from momentum calculation."""

    deviation_30d: Optional[Decimal]
    deviation_90d: Optional[Decimal]
    direction: int  # -1, 0, +1
    strength: Decimal  # 0..1
    confidence: Decimal  # 0..1
    description: str
    supporting_data: dict
    triggered: bool


def compute_momentum(
    current_price: Optional[Decimal],
    fair_value_mid: Optional[Decimal],
    appreciation_rate_30d: Optional[Decimal],
    appreciation_rate_90d: Optional[Decimal],
    transaction_count: int,
) -> MomentumResult:
    """Pure calculation of momentum signal -- no DB required.

    Parameters
    ----------
    current_price : latest normalised transaction price (or None)
    fair_value_mid : most recent fair-value midpoint (or None)
    appreciation_rate_30d : 30-day appreciation rate from FairValue (or None)
    appreciation_rate_90d : 90-day appreciation rate from FairValue (or None)
    transaction_count : number of recent transactions considered

    Returns
    -------
    MomentumResult with .triggered indicating whether signal threshold is met.
    """
    if current_price is None or fair_value_mid is None or fair_value_mid == 0:
        return MomentumResult(
            deviation_30d=None,
            deviation_90d=None,
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Insufficient data for momentum calculation",
            supporting_data={},
            triggered=False,
        )

    # Compute deviation: how far actual price deviates from fair value
    deviation = (current_price - fair_value_mid) / fair_value_mid

    # Use the provided appreciation rates directly as window deviations
    deviation_30d = appreciation_rate_30d
    deviation_90d = appreciation_rate_90d

    # The primary signal is the price-vs-fair-value deviation
    abs_deviation = abs(deviation)

    if abs_deviation < DEVIATION_THRESHOLD:
        return MomentumResult(
            deviation_30d=deviation_30d,
            deviation_90d=deviation_90d,
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Price within expected range of fair value",
            supporting_data={
                "current_price": str(current_price),
                "fair_value_mid": str(fair_value_mid),
                "deviation_pct": str(deviation.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            },
            triggered=False,
        )

    # Direction: +1 if appreciating faster than expected, -1 if slower/declining
    direction = 1 if deviation > 0 else -1

    # Strength proportional to deviation magnitude, capped at 1.0
    strength = min(abs_deviation / Decimal("0.30"), Decimal("1"))
    strength = strength.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Confidence based on transaction count and whether both windows agree
    base_confidence = min(Decimal(str(transaction_count)) / Decimal("10"), Decimal("1"))
    # Boost confidence if 30d and 90d trends agree in direction
    if deviation_30d is not None and deviation_90d is not None:
        if (deviation_30d > 0 and deviation_90d > 0) or (deviation_30d < 0 and deviation_90d < 0):
            base_confidence = min(base_confidence + Decimal("0.1"), Decimal("1"))
    confidence = base_confidence.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    if direction == 1:
        desc = (
            f"Price {abs_deviation.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP) * 100}% "
            f"above fair value -- appreciating faster than expected"
        )
    else:
        desc = (
            f"Price {abs_deviation.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP) * 100}% "
            f"below fair value -- underperforming expectations"
        )

    return MomentumResult(
        deviation_30d=deviation_30d,
        deviation_90d=deviation_90d,
        direction=direction,
        strength=strength,
        confidence=confidence,
        description=desc,
        supporting_data={
            "current_price": str(current_price),
            "fair_value_mid": str(fair_value_mid),
            "deviation_pct": str(deviation.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            "appreciation_rate_30d": str(appreciation_rate_30d) if appreciation_rate_30d else None,
            "appreciation_rate_90d": str(appreciation_rate_90d) if appreciation_rate_90d else None,
            "transaction_count": transaction_count,
        },
        triggered=True,
    )


class MomentumSignalGenerator:
    """Generates momentum signals by querying latest prices and fair values."""

    def __init__(self, session: AsyncSession):
        self.db = session

    async def generate(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> Optional[Signal]:
        """Generate a momentum signal for a given asset model."""
        if as_of is None:
            as_of = date.today()

        current_price = await self._latest_normalised_price(asset_model_id, as_of)
        fair_value = await self._latest_fair_value(asset_model_id, as_of)

        if fair_value is None:
            logger.debug("no_fair_value", asset_model_id=str(asset_model_id))
            return None

        tx_count = await self._transaction_count_90d(asset_model_id, as_of)

        result = compute_momentum(
            current_price=current_price,
            fair_value_mid=fair_value.fair_value_mid,
            appreciation_rate_30d=fair_value.appreciation_rate_30d,
            appreciation_rate_90d=fair_value.appreciation_rate_90d,
            transaction_count=tx_count,
        )

        if not result.triggered:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            asset_model_id=asset_model_id,
            signal_type=SignalType.MOMENTUM,
            generated_at=now,
            strength=result.strength,
            direction=result.direction,
            confidence=result.confidence,
            description=result.description,
            supporting_data=result.supporting_data,
            transaction_count=tx_count,
            is_active=True,
            expires_at=now + timedelta(days=7),
        )

    async def _latest_normalised_price(
        self, asset_model_id: uuid.UUID, as_of: date
    ) -> Optional[Decimal]:
        stmt = (
            select(Transaction.normalised_price_usd)
            .where(
                and_(
                    Transaction.asset_model_id == asset_model_id,
                    Transaction.normalised_price_usd.isnot(None),
                    Transaction.transaction_date <= as_of,
                )
            )
            .order_by(Transaction.transaction_date.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        return row

    async def _latest_fair_value(
        self, asset_model_id: uuid.UUID, as_of: date
    ) -> Optional[FairValue]:
        stmt = (
            select(FairValue)
            .where(
                and_(
                    FairValue.asset_model_id == asset_model_id,
                    FairValue.valuation_date <= as_of,
                )
            )
            .order_by(FairValue.valuation_date.desc())
            .limit(1)
        )
        result = (await self.db.execute(stmt)).scalar_one_or_none()
        return result

    async def _transaction_count_90d(
        self, asset_model_id: uuid.UUID, as_of: date
    ) -> int:
        window_start = as_of - timedelta(days=90)
        stmt = (
            select(func.count())
            .select_from(Transaction)
            .where(
                and_(
                    Transaction.asset_model_id == asset_model_id,
                    Transaction.transaction_date >= window_start,
                    Transaction.transaction_date <= as_of,
                )
            )
        )
        return (await self.db.execute(stmt)).scalar_one()
