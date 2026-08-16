"""
Catalyst signal generator.

Detects upcoming events that could move prices:
- Auction events within 90 days
- Import eligibility calendar milestones
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import (
    AuctionEvent,
    ImportEligibilityCalendar,
    Signal,
    SignalType,
)

logger = get_logger("signals.catalyst")

# Look-ahead window for catalyst events
CATALYST_WINDOW_DAYS = 90


@dataclass
class CatalystResult:
    """Pure data result from catalyst detection."""

    catalyst_type: str  # "auction_event" | "import_eligibility" | "none"
    days_until: Optional[int]
    direction: int  # always +1 for positive catalysts, 0 if none
    strength: Decimal
    confidence: Decimal
    description: str
    supporting_data: dict
    triggered: bool


def compute_catalyst(
    has_upcoming_auction: bool,
    days_to_auction: Optional[int],
    auction_name: Optional[str],
    is_flagship_auction: bool,
    has_import_eligibility: bool,
    days_to_eligibility: Optional[int],
    estimated_price_impact_pct: Optional[Decimal],
) -> CatalystResult:
    """Pure calculation of catalyst signal.

    Parameters
    ----------
    has_upcoming_auction : whether there is an auction within the window
    days_to_auction : days until the nearest auction event
    auction_name : name of the upcoming auction
    is_flagship_auction : whether the auction is a flagship event
    has_import_eligibility : whether import eligibility is approaching
    days_to_eligibility : days until eligibility date
    estimated_price_impact_pct : estimated price impact from eligibility
    """
    catalysts = []

    if has_upcoming_auction and days_to_auction is not None:
        # Closer events are stronger signals
        time_factor = max(Decimal("0"), Decimal("1") - Decimal(str(days_to_auction)) / Decimal(str(CATALYST_WINDOW_DAYS)))
        auction_strength = time_factor * (Decimal("0.8") if is_flagship_auction else Decimal("0.5"))
        auction_strength = min(auction_strength, Decimal("1"))
        catalysts.append({
            "type": "auction_event",
            "days_until": days_to_auction,
            "strength": auction_strength,
            "name": auction_name or "Upcoming auction",
            "is_flagship": is_flagship_auction,
        })

    if has_import_eligibility and days_to_eligibility is not None:
        time_factor = max(Decimal("0"), Decimal("1") - Decimal(str(days_to_eligibility)) / Decimal(str(CATALYST_WINDOW_DAYS)))
        impact = estimated_price_impact_pct or Decimal("10")
        elig_strength = time_factor * min(impact / Decimal("20"), Decimal("1"))
        elig_strength = min(elig_strength, Decimal("1"))
        catalysts.append({
            "type": "import_eligibility",
            "days_until": days_to_eligibility,
            "strength": elig_strength,
            "estimated_impact_pct": str(impact),
        })

    if not catalysts:
        return CatalystResult(
            catalyst_type="none",
            days_until=None,
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="No upcoming catalysts detected",
            supporting_data={},
            triggered=False,
        )

    # Pick the strongest catalyst
    best = max(catalysts, key=lambda c: c["strength"])
    strength = best["strength"].quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Confidence is high for known calendar events
    confidence = Decimal("0.800")

    days_until = best["days_until"]
    catalyst_type = best["type"]

    if catalyst_type == "auction_event":
        flag_label = " (flagship)" if best.get("is_flagship") else ""
        desc = f"Upcoming auction{flag_label}: {best['name']} in {days_until} days"
    else:
        desc = f"Import eligibility in {days_until} days -- est. {best.get('estimated_impact_pct', '?')}% price impact"

    supporting = {
        "catalysts": [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in c.items()}
            for c in catalysts
        ],
    }

    return CatalystResult(
        catalyst_type=catalyst_type,
        days_until=days_until,
        direction=1,  # catalysts are always positive direction
        strength=strength,
        confidence=confidence,
        description=desc,
        supporting_data=supporting,
        triggered=True,
    )


class CatalystSignalGenerator:
    """Generates catalyst signals from upcoming events."""

    def __init__(self, session: AsyncSession):
        self.db = session

    async def generate(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> Optional[Signal]:
        if as_of is None:
            as_of = date.today()

        window_end = as_of + timedelta(days=CATALYST_WINDOW_DAYS)

        # Check upcoming auctions
        auction = await self._nearest_auction(as_of, window_end)
        has_auction = auction is not None
        days_to_auction = (auction.event_date - as_of).days if auction else None
        auction_name = auction.name if auction else None
        is_flagship = auction.is_flagship if auction else False

        # Check import eligibility
        elig = await self._import_eligibility(asset_model_id, as_of, window_end)
        has_elig = elig is not None
        days_to_elig = (elig.eligible_date - as_of).days if elig else None
        impact_pct = elig.estimated_price_impact_pct if elig else None

        result = compute_catalyst(
            has_upcoming_auction=has_auction,
            days_to_auction=days_to_auction,
            auction_name=auction_name,
            is_flagship_auction=is_flagship,
            has_import_eligibility=has_elig,
            days_to_eligibility=days_to_elig,
            estimated_price_impact_pct=impact_pct,
        )

        if not result.triggered:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            asset_model_id=asset_model_id,
            signal_type=SignalType.CATALYST,
            generated_at=now,
            strength=result.strength,
            direction=result.direction,
            confidence=result.confidence,
            description=result.description,
            supporting_data=result.supporting_data,
            is_active=True,
            expires_at=now + timedelta(days=result.days_until or 30),
        )

    async def _nearest_auction(
        self, window_start: date, window_end: date
    ) -> Optional[AuctionEvent]:
        stmt = (
            select(AuctionEvent)
            .where(
                and_(
                    AuctionEvent.event_date >= window_start,
                    AuctionEvent.event_date <= window_end,
                )
            )
            .order_by(AuctionEvent.event_date.asc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _import_eligibility(
        self,
        asset_model_id: uuid.UUID,
        window_start: date,
        window_end: date,
    ) -> Optional[ImportEligibilityCalendar]:
        stmt = (
            select(ImportEligibilityCalendar)
            .where(
                and_(
                    ImportEligibilityCalendar.asset_model_id == asset_model_id,
                    ImportEligibilityCalendar.eligible_date >= window_start,
                    ImportEligibilityCalendar.eligible_date <= window_end,
                )
            )
            .order_by(ImportEligibilityCalendar.eligible_date.asc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
