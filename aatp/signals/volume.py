"""
Volume spike signal generator.

Detects unusual transaction volume for a model vs historical average.
Spike = volume > 2x the 90-day rolling average.
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
from aatp.db.models import Signal, SignalType, Transaction

logger = get_logger("signals.volume")

# Volume must be at least this multiple of the average to trigger
SPIKE_MULTIPLIER = Decimal("2.0")

# Minimum average volume to avoid triggering on noise (need at least 1 tx/month avg)
MIN_AVERAGE_VOLUME = Decimal("1.0")


@dataclass
class VolumeResult:
    """Pure data result from volume spike calculation."""

    recent_count: int
    average_count: Decimal
    volume_ratio: Optional[Decimal]
    direction: int
    strength: Decimal
    confidence: Decimal
    description: str
    supporting_data: dict
    triggered: bool


def compute_volume_spike(
    recent_count: int,
    historical_avg_per_period: Decimal,
) -> VolumeResult:
    """Pure calculation of volume spike signal.

    Parameters
    ----------
    recent_count : transaction count in the most recent 30-day window
    historical_avg_per_period : average transaction count per 30-day period
        over the preceding 90-day window
    """
    if historical_avg_per_period < MIN_AVERAGE_VOLUME:
        return VolumeResult(
            recent_count=recent_count,
            average_count=historical_avg_per_period,
            volume_ratio=None,
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Insufficient historical volume for comparison",
            supporting_data={
                "recent_count": recent_count,
                "historical_avg": str(historical_avg_per_period),
            },
            triggered=False,
        )

    volume_ratio = Decimal(str(recent_count)) / historical_avg_per_period

    if volume_ratio < SPIKE_MULTIPLIER:
        return VolumeResult(
            recent_count=recent_count,
            average_count=historical_avg_per_period,
            volume_ratio=volume_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Volume within normal range",
            supporting_data={
                "recent_count": recent_count,
                "historical_avg": str(historical_avg_per_period),
                "volume_ratio": str(volume_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            },
            triggered=False,
        )

    # Direction is +1 (volume spike could signal turning point in either
    # direction; we flag it as positive because increased interest is notable)
    direction = 1

    # Strength proportional to how far above the threshold we are
    # At 2x -> 0.25 strength, at 4x -> 0.75, at 5x+ -> 1.0
    strength = min((volume_ratio - Decimal("1")) / Decimal("4"), Decimal("1"))
    strength = strength.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Confidence based on absolute counts (more data = higher confidence)
    confidence = min(
        Decimal(str(recent_count)) / Decimal("10"), Decimal("1")
    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    ratio_display = volume_ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    desc = (
        f"Volume spike: {recent_count} transactions in last 30 days "
        f"({ratio_display}x average of {historical_avg_per_period.quantize(Decimal('0.1'))})"
    )

    return VolumeResult(
        recent_count=recent_count,
        average_count=historical_avg_per_period,
        volume_ratio=volume_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        direction=direction,
        strength=strength,
        confidence=confidence,
        description=desc,
        supporting_data={
            "recent_count": recent_count,
            "historical_avg": str(historical_avg_per_period),
            "volume_ratio": str(volume_ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
        },
        triggered=True,
    )


class VolumeSignalGenerator:
    """Generates volume spike signals."""

    def __init__(self, session: AsyncSession):
        self.db = session

    async def generate(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> Optional[Signal]:
        if as_of is None:
            as_of = date.today()

        # Recent 30-day window
        recent_start = as_of - timedelta(days=30)
        recent_count = await self._count_transactions(
            asset_model_id, recent_start, as_of
        )

        # Historical 90-day window (ending where recent starts)
        hist_end = recent_start
        hist_start = hist_end - timedelta(days=90)
        hist_count = await self._count_transactions(
            asset_model_id, hist_start, hist_end
        )

        # Average per 30-day period over the 90-day historical window
        historical_avg = Decimal(str(hist_count)) / Decimal("3")

        result = compute_volume_spike(recent_count, historical_avg)

        if not result.triggered:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            asset_model_id=asset_model_id,
            signal_type=SignalType.VOLUME_SPIKE,
            generated_at=now,
            strength=result.strength,
            direction=result.direction,
            confidence=result.confidence,
            description=result.description,
            supporting_data=result.supporting_data,
            transaction_count=recent_count,
            is_active=True,
            expires_at=now + timedelta(days=7),
        )

    async def _count_transactions(
        self,
        asset_model_id: uuid.UUID,
        window_start: date,
        window_end: date,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Transaction)
            .where(
                and_(
                    Transaction.asset_model_id == asset_model_id,
                    Transaction.transaction_date >= window_start,
                    Transaction.transaction_date <= window_end,
                )
            )
        )
        return (await self.db.execute(stmt)).scalar_one()
