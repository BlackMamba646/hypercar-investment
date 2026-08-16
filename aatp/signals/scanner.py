"""
Opportunity scanner -- orchestrator for all signal generators.

Runs all signal generators for all models, computes composite opportunity
scores, and writes results to the signals and opportunity_scores tables.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import (
    AssetModel,
    OpportunityScore,
    OpportunityStatus,
    RuleModelFlag,
    Signal,
    SignalType,
)
from aatp.signals.catalyst import CatalystSignalGenerator
from aatp.signals.comparable import ComparableSignalGenerator
from aatp.signals.momentum import MomentumSignalGenerator
from aatp.signals.pattern import PatternSignalGenerator
from aatp.signals.spread import SpreadSignalGenerator
from aatp.signals.volume import VolumeSignalGenerator

logger = get_logger("signals.scanner")


# Signal type weights for composite scoring
SIGNAL_WEIGHTS: dict[str, Decimal] = {
    SignalType.MOMENTUM.value: Decimal("0.25"),
    SignalType.DEALER_AUCTION_SPREAD.value: Decimal("0.20"),
    SignalType.CATALYST.value: Decimal("0.20"),
    SignalType.VOLUME_SPIKE.value: Decimal("0.10"),
    SignalType.COMPARABLE_APPRECIATION.value: Decimal("0.15"),
    SignalType.PATTERN_MATCH.value: Decimal("0.10"),
}

# Status thresholds
ACTIONABLE_THRESHOLD = Decimal("4.0")
WATCHLIST_THRESHOLD = Decimal("2.0")


@dataclass
class ScoringInput:
    """Input for the pure composite scoring function."""

    signal_type: str
    strength: Decimal
    direction: int
    confidence: Decimal


@dataclass
class CompositeScoreResult:
    """Result from composite scoring."""

    composite_score: Decimal
    signal_count: int
    signal_breakdown: dict
    status: str


def compute_composite_score(
    signals: list[ScoringInput],
) -> CompositeScoreResult:
    """Pure calculation of composite opportunity score.

    Each signal contributes: weight * strength * direction * confidence * 10
    (the 10x scaling puts the score in a 0-10 range for thresholding).

    Parameters
    ----------
    signals : list of ScoringInput with type, strength, direction, confidence

    Returns
    -------
    CompositeScoreResult with composite_score, breakdown, and status.
    """
    if not signals:
        return CompositeScoreResult(
            composite_score=Decimal("0"),
            signal_count=0,
            signal_breakdown={},
            status=OpportunityStatus.EXPIRED.value,
        )

    breakdown: dict[str, dict] = {}
    total_score = Decimal("0")

    for sig in signals:
        weight = SIGNAL_WEIGHTS.get(sig.signal_type, Decimal("0.10"))
        contribution = weight * sig.strength * Decimal(str(sig.direction)) * sig.confidence * Decimal("10")
        contribution = contribution.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        total_score += contribution
        breakdown[sig.signal_type] = {
            "weight": str(weight),
            "strength": str(sig.strength),
            "direction": sig.direction,
            "confidence": str(sig.confidence),
            "contribution": str(contribution),
        }

    composite = total_score.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    if composite >= ACTIONABLE_THRESHOLD:
        status = OpportunityStatus.ACTIONABLE.value
    elif composite >= WATCHLIST_THRESHOLD:
        status = OpportunityStatus.WATCHLIST.value
    else:
        status = OpportunityStatus.PASSED.value

    return CompositeScoreResult(
        composite_score=composite,
        signal_count=len(signals),
        signal_breakdown=breakdown,
        status=status,
    )


@dataclass
class ScanResult:
    """Summary result from a full scan."""

    models_scanned: int = 0
    signals_generated: int = 0
    opportunities_scored: int = 0
    actionable_count: int = 0
    watchlist_count: int = 0
    errors: int = 0


class OpportunityScanner:
    """Orchestrates all signal generators and computes composite scores."""

    def __init__(self, session: AsyncSession):
        self.db = session
        self.momentum_gen = MomentumSignalGenerator(session)
        self.spread_gen = SpreadSignalGenerator(session)
        self.catalyst_gen = CatalystSignalGenerator(session)
        self.volume_gen = VolumeSignalGenerator(session)
        self.comparable_gen = ComparableSignalGenerator(session)
        self.pattern_gen = PatternSignalGenerator(session)

    async def scan_all(self, as_of: Optional[date] = None) -> ScanResult:
        """Run signal scan across all asset models."""
        if as_of is None:
            as_of = date.today()

        result = ScanResult()

        model_ids = await self._get_all_model_ids()
        result.models_scanned = len(model_ids)

        for model_id in model_ids:
            try:
                scan_outcome = await self.scan_model(model_id, as_of)
                result.signals_generated += scan_outcome["signals_generated"]
                result.opportunities_scored += 1
                if scan_outcome["status"] == OpportunityStatus.ACTIONABLE.value:
                    result.actionable_count += 1
                elif scan_outcome["status"] == OpportunityStatus.WATCHLIST.value:
                    result.watchlist_count += 1
            except Exception as exc:
                logger.error(
                    "scan_model_failed",
                    asset_model_id=str(model_id),
                    error=str(exc),
                )
                result.errors += 1

        await self.db.commit()

        logger.info(
            "scan_complete",
            models_scanned=result.models_scanned,
            signals_generated=result.signals_generated,
            actionable=result.actionable_count,
            watchlist=result.watchlist_count,
            errors=result.errors,
        )
        return result

    async def scan_model(
        self,
        asset_model_id: uuid.UUID,
        as_of: Optional[date] = None,
    ) -> dict:
        """Run all signal generators for a single model and compute score."""
        if as_of is None:
            as_of = date.today()

        # Deactivate previous signals for this model
        await self._deactivate_old_signals(asset_model_id)

        # Run all generators
        generators = [
            self.momentum_gen,
            self.spread_gen,
            self.catalyst_gen,
            self.volume_gen,
            self.comparable_gen,
            self.pattern_gen,
        ]

        signals: list[Signal] = []
        for gen in generators:
            try:
                signal = await gen.generate(asset_model_id, as_of)
                if signal is not None:
                    signals.append(signal)
                    self.db.add(signal)
            except Exception as exc:
                logger.warning(
                    "generator_failed",
                    generator=gen.__class__.__name__,
                    asset_model_id=str(asset_model_id),
                    error=str(exc),
                )

        # Build scoring inputs
        scoring_inputs = [
            ScoringInput(
                signal_type=s.signal_type.value if isinstance(s.signal_type, SignalType) else s.signal_type,
                strength=s.strength,
                direction=s.direction,
                confidence=s.confidence,
            )
            for s in signals
        ]

        score_result = compute_composite_score(scoring_inputs)

        # Fetch rule flags for this model
        rule_flags = await self._get_rule_flags(asset_model_id)

        # Find time to nearest catalyst
        time_to_catalyst = None
        for s in signals:
            st = s.signal_type.value if isinstance(s.signal_type, SignalType) else s.signal_type
            if st == SignalType.CATALYST.value:
                catalysts = s.supporting_data.get("catalysts", [])
                if catalysts:
                    days_list = [c.get("days_until") for c in catalysts if c.get("days_until") is not None]
                    if days_list:
                        time_to_catalyst = min(days_list)

        # Create opportunity score record
        now = datetime.now(timezone.utc)
        opp_score = OpportunityScore(
            asset_model_id=asset_model_id,
            scored_at=now,
            composite_score=score_result.composite_score,
            signal_count=score_result.signal_count,
            signal_breakdown=score_result.signal_breakdown,
            time_to_catalyst_days=time_to_catalyst,
            rule_flags=rule_flags,
            status=OpportunityStatus(score_result.status),
        )
        self.db.add(opp_score)

        return {
            "signals_generated": len(signals),
            "composite_score": str(score_result.composite_score),
            "status": score_result.status,
        }

    async def _get_all_model_ids(self) -> list[uuid.UUID]:
        stmt = select(AssetModel.id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _deactivate_old_signals(self, asset_model_id: uuid.UUID) -> None:
        """Mark previous active signals for this model as inactive."""
        from sqlalchemy import update

        stmt = (
            update(Signal)
            .where(
                and_(
                    Signal.asset_model_id == asset_model_id,
                    Signal.is_active.is_(True),
                )
            )
            .values(is_active=False)
        )
        await self.db.execute(stmt)

    async def _get_rule_flags(self, asset_model_id: uuid.UUID) -> Optional[dict]:
        """Get active rule flags for this model."""
        stmt = (
            select(RuleModelFlag)
            .where(RuleModelFlag.asset_model_id == asset_model_id)
        )
        result = await self.db.execute(stmt)
        flags = list(result.scalars().all())
        if not flags:
            return None
        return {
            "flags": [
                {
                    "rule_id": str(f.market_rule_id),
                    "reason": f.flag_reason,
                    "is_positive": f.is_positive,
                    "impact_score": str(f.impact_score) if f.impact_score else None,
                }
                for f in flags
            ]
        }
