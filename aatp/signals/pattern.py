"""
Pattern match signal generator.

Detects known pricing patterns based on heuristics:
- Spider/open-top variant appreciates 12-18 months after coupe peaks
- Open-top variants lagging their coupe counterparts
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
    AssetModel,
    AssetModelRelationship,
    FairValue,
    Signal,
    SignalType,
)

logger = get_logger("signals.pattern")

# The lag percentage threshold: open-top should be at least 15% behind coupe
OPEN_TOP_LAG_THRESHOLD = Decimal("0.15")

# Coupe must have appreciated at least 10% in 365d to qualify as "peaked"
COUPE_APPRECIATION_THRESHOLD = Decimal("0.10")


@dataclass
class PatternResult:
    """Pure data result from pattern detection."""

    pattern_name: str
    direction: int
    strength: Decimal
    confidence: Decimal
    description: str
    supporting_data: dict
    triggered: bool


def compute_open_top_lag(
    source_is_open_top: bool,
    source_appreciation_90d: Optional[Decimal],
    coupe_appreciation_90d: Optional[Decimal],
    coupe_appreciation_365d: Optional[Decimal],
    source_fair_value: Optional[Decimal],
    coupe_fair_value: Optional[Decimal],
) -> PatternResult:
    """Detect whether an open-top variant lags its coupe counterpart.

    The heuristic: if the coupe has appreciated significantly (>10% in 365d)
    and the open-top variant is lagging (fair value > 15% below coupe), the
    open-top is likely to follow.

    Parameters
    ----------
    source_is_open_top : whether the source model is an open-top variant
    source_appreciation_90d : source model's 90-day appreciation rate
    coupe_appreciation_90d : related coupe's 90-day appreciation rate
    coupe_appreciation_365d : related coupe's 365-day appreciation rate
    source_fair_value : source model's fair value midpoint
    coupe_fair_value : coupe model's fair value midpoint
    """
    if not source_is_open_top:
        return PatternResult(
            pattern_name="open_top_lag",
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Model is not an open-top variant",
            supporting_data={},
            triggered=False,
        )

    if (
        coupe_appreciation_365d is None
        or source_fair_value is None
        or coupe_fair_value is None
        or coupe_fair_value == 0
    ):
        return PatternResult(
            pattern_name="open_top_lag",
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Insufficient data for open-top lag pattern",
            supporting_data={},
            triggered=False,
        )

    # Check if coupe has appreciated significantly
    if coupe_appreciation_365d < COUPE_APPRECIATION_THRESHOLD:
        return PatternResult(
            pattern_name="open_top_lag",
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Coupe appreciation below threshold for pattern detection",
            supporting_data={
                "coupe_appreciation_365d": str(coupe_appreciation_365d),
                "threshold": str(COUPE_APPRECIATION_THRESHOLD),
            },
            triggered=False,
        )

    # Compute how far the open-top lags behind the coupe
    value_gap = (coupe_fair_value - source_fair_value) / coupe_fair_value

    if value_gap < OPEN_TOP_LAG_THRESHOLD:
        return PatternResult(
            pattern_name="open_top_lag",
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="Open-top not sufficiently lagging coupe",
            supporting_data={
                "value_gap_pct": str(value_gap.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
                "threshold": str(OPEN_TOP_LAG_THRESHOLD),
            },
            triggered=False,
        )

    # Signal triggered: open-top is lagging a coupe that has appreciated
    strength = min(value_gap / Decimal("0.40"), Decimal("1"))
    strength = strength.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Confidence based on coupe appreciation strength
    confidence = min(coupe_appreciation_365d / Decimal("0.20"), Decimal("1"))
    confidence = confidence.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    gap_display = (value_gap * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    coupe_display = (coupe_appreciation_365d * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    desc = (
        f"Open-top variant lagging coupe by {gap_display}% "
        f"while coupe appreciated {coupe_display}% over 365 days"
    )

    return PatternResult(
        pattern_name="open_top_lag",
        direction=1,
        strength=strength,
        confidence=confidence,
        description=desc,
        supporting_data={
            "value_gap_pct": str(value_gap.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)),
            "coupe_appreciation_365d": str(coupe_appreciation_365d),
            "source_fair_value": str(source_fair_value),
            "coupe_fair_value": str(coupe_fair_value),
            "source_appreciation_90d": str(source_appreciation_90d) if source_appreciation_90d else None,
            "coupe_appreciation_90d": str(coupe_appreciation_90d) if coupe_appreciation_90d else None,
        },
        triggered=True,
    )


class PatternSignalGenerator:
    """Generates pattern match signals using heuristic-based detection."""

    def __init__(self, session: AsyncSession):
        self.db = session

    async def generate(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> Optional[Signal]:
        if as_of is None:
            as_of = date.today()

        model = await self._get_model(asset_model_id)
        if model is None:
            return None

        # Only check open-top lag pattern if the model is an open-top variant
        if not model.is_open_top:
            return None

        # Find related coupe models
        coupe_rel = await self._find_coupe_relationship(asset_model_id)
        if coupe_rel is None:
            return None

        source_fv = await self._latest_fair_value(asset_model_id, as_of)
        coupe_fv = await self._latest_fair_value(coupe_rel.related_model_id, as_of)

        result = compute_open_top_lag(
            source_is_open_top=model.is_open_top,
            source_appreciation_90d=source_fv.appreciation_rate_90d if source_fv else None,
            coupe_appreciation_90d=coupe_fv.appreciation_rate_90d if coupe_fv else None,
            coupe_appreciation_365d=coupe_fv.appreciation_rate_365d if coupe_fv else None,
            source_fair_value=source_fv.fair_value_mid if source_fv else None,
            coupe_fair_value=coupe_fv.fair_value_mid if coupe_fv else None,
        )

        if not result.triggered:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            asset_model_id=asset_model_id,
            signal_type=SignalType.PATTERN_MATCH,
            generated_at=now,
            strength=result.strength,
            direction=result.direction,
            confidence=result.confidence,
            description=result.description,
            supporting_data=result.supporting_data,
            is_active=True,
            expires_at=now + timedelta(days=30),
        )

    async def _get_model(self, asset_model_id: uuid.UUID) -> Optional[AssetModel]:
        stmt = select(AssetModel).where(AssetModel.id == asset_model_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _find_coupe_relationship(
        self, asset_model_id: uuid.UUID
    ) -> Optional[AssetModelRelationship]:
        """Find a relationship where the source is open-top and related is coupe."""
        stmt = (
            select(AssetModelRelationship)
            .where(
                and_(
                    AssetModelRelationship.source_model_id == asset_model_id,
                    AssetModelRelationship.relationship_type.in_(
                        ["coupe_variant", "closed_variant", "hardtop_variant"]
                    ),
                )
            )
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

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
        return (await self.db.execute(stmt)).scalar_one_or_none()
