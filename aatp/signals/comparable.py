"""
Comparable appreciation signal generator.

Uses asset_model_relationships to check if related models appreciated
significantly. If a related model appreciated >10%, generates a signal
for the source model, weighted by correlation_strength.
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
    AssetModelRelationship,
    FairValue,
    Signal,
    SignalType,
)

logger = get_logger("signals.comparable")

# Minimum appreciation in a related model to trigger the signal
MIN_APPRECIATION_PCT = Decimal("0.10")  # 10%


@dataclass
class ComparableResult:
    """Pure data result from comparable appreciation calculation."""

    related_appreciations: list  # list of dicts with model info
    best_appreciation_pct: Optional[Decimal]
    correlation_strength: Optional[Decimal]
    direction: int
    strength: Decimal
    confidence: Decimal
    description: str
    supporting_data: dict
    triggered: bool


def compute_comparable_appreciation(
    related_appreciations: list[dict],
) -> ComparableResult:
    """Pure calculation of comparable appreciation signal.

    Parameters
    ----------
    related_appreciations : list of dicts, each with:
        - related_model_id: str
        - appreciation_rate_90d: Decimal or None
        - correlation_strength: Decimal or None
        - relationship_type: str
    """
    significant = []
    for rel in related_appreciations:
        rate = rel.get("appreciation_rate_90d")
        corr = rel.get("correlation_strength") or Decimal("0.5")
        if rate is not None and rate >= MIN_APPRECIATION_PCT:
            significant.append({
                **rel,
                "correlation_strength": corr,
                "weighted_signal": (rate * corr).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
            })

    if not significant:
        return ComparableResult(
            related_appreciations=related_appreciations,
            best_appreciation_pct=None,
            correlation_strength=None,
            direction=0,
            strength=Decimal("0"),
            confidence=Decimal("0"),
            description="No significant comparable appreciation detected",
            supporting_data={},
            triggered=False,
        )

    # Use the strongest weighted signal
    best = max(significant, key=lambda s: s["weighted_signal"])
    best_rate = best["appreciation_rate_90d"]
    best_corr = best["correlation_strength"]
    weighted = best["weighted_signal"]

    # Strength from weighted signal, capped at 1.0
    strength = min(weighted / Decimal("0.15"), Decimal("1"))
    strength = strength.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Confidence driven by correlation strength
    confidence = best_corr.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    rate_display = (best_rate * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    desc = (
        f"Related model appreciated {rate_display}% over 90 days "
        f"(correlation: {best_corr})"
    )

    supporting = {
        "significant_comparables": [
            {k: (str(v) if isinstance(v, Decimal) else v) for k, v in s.items()}
            for s in significant
        ],
        "best_related_model_id": best.get("related_model_id"),
        "best_appreciation_pct": str(best_rate),
        "correlation_strength": str(best_corr),
    }

    return ComparableResult(
        related_appreciations=related_appreciations,
        best_appreciation_pct=best_rate,
        correlation_strength=best_corr,
        direction=1,
        strength=strength,
        confidence=confidence,
        description=desc,
        supporting_data=supporting,
        triggered=True,
    )


class ComparableSignalGenerator:
    """Generates comparable appreciation signals."""

    def __init__(self, session: AsyncSession):
        self.db = session

    async def generate(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> Optional[Signal]:
        if as_of is None:
            as_of = date.today()

        relationships = await self._get_relationships(asset_model_id)
        if not relationships:
            return None

        related_data = []
        for rel in relationships:
            fv = await self._latest_fair_value(rel.related_model_id, as_of)
            rate_90d = fv.appreciation_rate_90d if fv else None
            related_data.append({
                "related_model_id": str(rel.related_model_id),
                "appreciation_rate_90d": rate_90d,
                "correlation_strength": rel.correlation_strength,
                "relationship_type": rel.relationship_type,
            })

        result = compute_comparable_appreciation(related_data)

        if not result.triggered:
            return None

        now = datetime.now(timezone.utc)
        return Signal(
            asset_model_id=asset_model_id,
            signal_type=SignalType.COMPARABLE_APPRECIATION,
            generated_at=now,
            strength=result.strength,
            direction=result.direction,
            confidence=result.confidence,
            description=result.description,
            supporting_data=result.supporting_data,
            is_active=True,
            expires_at=now + timedelta(days=14),
        )

    async def _get_relationships(
        self, asset_model_id: uuid.UUID
    ) -> list[AssetModelRelationship]:
        stmt = (
            select(AssetModelRelationship)
            .where(AssetModelRelationship.source_model_id == asset_model_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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
