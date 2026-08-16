"""
Dealer-auction spread signal generator.

Compares dealer listing prices vs recent auction results for the same model.
A large spread indicates an arbitrage opportunity.
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
from aatp.db.models import Signal, SignalType, Transaction, TransactionType

logger = get_logger("signals.spread")

# Minimum spread percentage to trigger a signal
MIN_SPREAD_PCT = Decimal("0.10")  # 10%


@dataclass
class SpreadResult:
    """Pure data result from spread calculation."""

    avg_dealer_price: Optional[Decimal]
    avg_auction_price: Optional[Decimal]
    spread_pct: Optional[Decimal]
    direction: int
    strength: Decimal
    confidence: Decimal
    description: str
    supporting_data: dict
    triggered: bool


def compute_spread(
    avg_dealer_price: Optional[Decimal],
    avg_auction_price: Optional[Decimal],
    dealer_count: int,
    auction_count: int,
) -> SpreadResult:
    """Pure calculation of dealer-auction spread signal.

    Parameters
    ----------
    avg_dealer_price : average normalised dealer listing price
    avg_auction_price : average normalised auction sold price
    dealer_count : number of dealer listings in the window
    auction_count : number of auction results in the window
    """
    if (
        avg_dealer_price is None
        or avg_auction_price is None
        or avg_auction_price == 0
        or dealer_count == 0
        or auction_count == 0
    ):
        return SpreadResult(
            avg_dealer_price=avg_dealer_price,
            avg_auction_price=avg_auction_price,
            spread_pct=None,
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Insufficient data for spread calculation",
            supporting_data={},
            triggered=False,
        )

    spread_pct = (avg_dealer_price - avg_auction_price) / avg_auction_price
    abs_spread = abs(spread_pct)

    if abs_spread < MIN_SPREAD_PCT:
        return SpreadResult(
            avg_dealer_price=avg_dealer_price,
            avg_auction_price=avg_auction_price,
            spread_pct=spread_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Dealer-auction spread within normal range",
            supporting_data={
                "avg_dealer_price": str(avg_dealer_price),
                "avg_auction_price": str(avg_auction_price),
                "spread_pct": str(spread_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            },
            triggered=False,
        )

    # Positive spread (dealer > auction) means buy at auction is arbitrage
    direction = 1 if spread_pct > 0 else -1

    # Strength proportional to spread size, capped at 1.0
    strength = min(abs_spread / Decimal("0.40"), Decimal("1"))
    strength = strength.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Confidence based on sample sizes
    sample_factor = min(Decimal(str(dealer_count + auction_count)) / Decimal("10"), Decimal("1"))
    confidence = sample_factor.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    spread_display = (abs_spread * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if direction == 1:
        desc = (
            f"Dealer listings {spread_display}% above auction results "
            f"-- potential auction arbitrage"
        )
    else:
        desc = (
            f"Auction results {spread_display}% above dealer listings "
            f"-- dealers may be underpricing"
        )

    return SpreadResult(
        avg_dealer_price=avg_dealer_price,
        avg_auction_price=avg_auction_price,
        spread_pct=spread_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        direction=direction,
        strength=strength,
        confidence=confidence,
        description=desc,
        supporting_data={
            "avg_dealer_price": str(avg_dealer_price),
            "avg_auction_price": str(avg_auction_price),
            "spread_pct": str(spread_pct.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            "dealer_count": dealer_count,
            "auction_count": auction_count,
        },
        triggered=True,
    )


class SpreadSignalGenerator:
    """Generates dealer-auction spread signals."""

    def __init__(self, session: AsyncSession, lookback_days: int = 180):
        self.db = session
        self.lookback_days = lookback_days

    async def generate(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> Optional[Signal]:
        if as_of is None:
            as_of = date.today()

        window_start = as_of - timedelta(days=self.lookback_days)

        avg_dealer, dealer_count = await self._avg_price(
            asset_model_id,
            window_start,
            as_of,
            [TransactionType.DEALER_LISTING, TransactionType.DEALER_SOLD],
        )
        avg_auction, auction_count = await self._avg_price(
            asset_model_id,
            window_start,
            as_of,
            [TransactionType.AUCTION_SOLD],
        )

        result = compute_spread(avg_dealer, avg_auction, dealer_count, auction_count)

        if not result.triggered:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            asset_model_id=asset_model_id,
            signal_type=SignalType.DEALER_AUCTION_SPREAD,
            generated_at=now,
            strength=result.strength,
            direction=result.direction,
            confidence=result.confidence,
            description=result.description,
            supporting_data=result.supporting_data,
            transaction_count=dealer_count + auction_count,
            is_active=True,
            expires_at=now + timedelta(days=14),
        )

    async def _avg_price(
        self,
        asset_model_id: uuid.UUID,
        window_start: date,
        window_end: date,
        transaction_types: list,
    ) -> tuple[Optional[Decimal], int]:
        stmt = (
            select(
                func.avg(Transaction.normalised_price_usd),
                func.count(),
            )
            .where(
                and_(
                    Transaction.asset_model_id == asset_model_id,
                    Transaction.normalised_price_usd.isnot(None),
                    Transaction.transaction_type.in_(transaction_types),
                    Transaction.transaction_date >= window_start,
                    Transaction.transaction_date <= window_end,
                )
            )
        )
        row = (await self.db.execute(stmt)).one()
        return row[0], row[1]
