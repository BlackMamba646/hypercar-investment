"""Multi-model consensus engine.

Orchestrates all six consensus models, aggregates scores, applies veto
logic, and persists results to the database.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.consensus.models.fundamental import score_fundamental
from aatp.consensus.models.liquidity import score_liquidity
from aatp.consensus.models.macro import score_macro
from aatp.consensus.models.momentum import score_momentum
from aatp.consensus.models.rules import score_rules
from aatp.consensus.models.sentiment import score_sentiment
from aatp.core.logging import get_logger
from aatp.db.models import (
    AssetModel,
    ConsensusModelScore,
    ConsensusModelType,
    ConsensusScore,
    FairValue,
    ForumSentiment,
    ImportEligibilityCalendar,
    MacroIndicator,
    OpportunityStatus,
    RuleModelFlag,
    Signal,
    SignalType,
    Transaction,
    TransactionType,
)

logger = get_logger("consensus.engine")

# Classification thresholds
ACTIONABLE_THRESHOLD = 4
WATCHLIST_THRESHOLD = 2

# Disagreement detection: flag if max - min spread exceeds this
DISAGREEMENT_SPREAD_THRESHOLD = 3

# Veto score
VETO_SCORE = -2


async def run_consensus(session: AsyncSession, asset_model_id: uuid.UUID) -> dict:
    """Run the full consensus engine for a single asset model.

    Executes all six scoring models, aggregates results, applies veto
    logic, and writes to the database.

    Returns
    -------
    dict with keys: asset_model_id, aggregate_score, status, has_veto, actionable
    """
    logger.info("consensus_start", asset_model_id=str(asset_model_id))

    # Gather data for all models
    model_inputs = await _gather_model_inputs(session, asset_model_id)

    # Run all six scoring models
    scores = _run_all_scoring_models(model_inputs)

    # Aggregate and classify
    result = _aggregate_scores(scores)

    # Persist to database
    consensus_score = ConsensusScore(
        asset_model_id=asset_model_id,
        scored_at=datetime.now(timezone.utc),
        aggregate_score=result["aggregate_score"],
        has_veto=result["has_veto"],
        veto_model=result.get("veto_model"),
        veto_reason=result.get("veto_reason"),
        status=result["status"],
        disagreement_summary=result.get("disagreement_summary"),
        actionable=result["actionable"],
    )
    session.add(consensus_score)
    await session.flush()  # Get the ID

    # Write individual model scores
    for model_type, (score, confidence, rationale, supporting_data) in scores.items():
        model_score = ConsensusModelScore(
            consensus_score_id=consensus_score.id,
            model_type=model_type,
            score=score,
            confidence=confidence,
            rationale=rationale,
            supporting_data=supporting_data,
        )
        session.add(model_score)

    await session.commit()

    logger.info(
        "consensus_complete",
        asset_model_id=str(asset_model_id),
        aggregate_score=result["aggregate_score"],
        status=result["status"].value,
        has_veto=result["has_veto"],
        actionable=result["actionable"],
    )

    return {
        "asset_model_id": str(asset_model_id),
        "aggregate_score": result["aggregate_score"],
        "status": result["status"].value,
        "has_veto": result["has_veto"],
        "actionable": result["actionable"],
    }


async def run_all_models(session: AsyncSession) -> dict:
    """Run consensus engine across all asset models.

    Returns
    -------
    dict with summary statistics.
    """
    logger.info("consensus_scan_start")

    result_query = await session.execute(select(AssetModel.id))
    model_ids = [row[0] for row in result_query.all()]

    results = {
        "models_scanned": 0,
        "actionable": 0,
        "watchlist": 0,
        "passed": 0,
        "vetoed": 0,
        "errors": 0,
    }

    for model_id in model_ids:
        try:
            outcome = await run_consensus(session, model_id)
            results["models_scanned"] += 1
            if outcome["has_veto"]:
                results["vetoed"] += 1
            if outcome["status"] == OpportunityStatus.ACTIONABLE.value:
                results["actionable"] += 1
            elif outcome["status"] == OpportunityStatus.WATCHLIST.value:
                results["watchlist"] += 1
            else:
                results["passed"] += 1
        except Exception:
            logger.exception("consensus_model_error", asset_model_id=str(model_id))
            results["errors"] += 1

    logger.info("consensus_scan_complete", **results)
    return results


def _run_all_scoring_models(
    inputs: dict,
) -> dict[ConsensusModelType, tuple[int, Decimal, str, dict]]:
    """Run all six pure scoring functions and return structured results.

    Returns dict mapping model type to (score, confidence, rationale, supporting_data).
    """
    results: dict[ConsensusModelType, tuple[int, Decimal, str, dict]] = {}

    # 1. Momentum
    score, rationale, data = score_momentum(
        appreciation_rate_90d=inputs.get("appreciation_rate_90d"),
        appreciation_rate_365d=inputs.get("appreciation_rate_365d"),
        has_momentum_signal=inputs.get("has_momentum_signal", False),
        signal_direction=inputs.get("signal_direction"),
    )
    confidence = _compute_confidence(score, inputs.get("appreciation_rate_90d") is not None)
    results[ConsensusModelType.MOMENTUM] = (score, confidence, rationale, data)

    # 2. Fundamental
    score, rationale, data = score_fundamental(
        fair_value_mid=inputs.get("fair_value_mid"),
        latest_transaction_price=inputs.get("latest_transaction_price"),
        confidence=inputs.get("fair_value_confidence"),
    )
    confidence = _compute_confidence(score, inputs.get("fair_value_mid") is not None)
    results[ConsensusModelType.FUNDAMENTAL_VALUE] = (score, confidence, rationale, data)

    # 3. Liquidity
    score, rationale, data = score_liquidity(
        transaction_count_12m=inputs.get("transaction_count_12m", 0),
        transaction_count_6m=inputs.get("transaction_count_6m", 0),
        distinct_sources=inputs.get("distinct_sources", 0),
        avg_days_on_market=inputs.get("avg_days_on_market"),
    )
    confidence = _compute_confidence(score, inputs.get("transaction_count_12m", 0) > 0)
    results[ConsensusModelType.LIQUIDITY] = (score, confidence, rationale, data)

    # 4. Sentiment
    score, rationale, data = score_sentiment(
        avg_sentiment=inputs.get("avg_sentiment"),
        mention_volume_change_pct=inputs.get("mention_volume_change_pct"),
        news_sentiment_avg=inputs.get("news_sentiment_avg"),
        has_negative_catalyst=inputs.get("has_negative_catalyst", False),
    )
    confidence = _compute_confidence(score, inputs.get("avg_sentiment") is not None)
    results[ConsensusModelType.SENTIMENT] = (score, confidence, rationale, data)

    # 5. Macro
    score, rationale, data = score_macro(
        luxury_index_trend=inputs.get("luxury_index_trend"),
        interest_rate_trend=inputs.get("interest_rate_trend"),
        wealth_indicator_trend=inputs.get("wealth_indicator_trend"),
    )
    confidence = _compute_confidence(score, inputs.get("luxury_index_trend") is not None)
    results[ConsensusModelType.MACRO] = (score, confidence, rationale, data)

    # 6. Rules
    score, rationale, data = score_rules(
        active_rule_flags=inputs.get("active_rule_flags", 0),
        positive_flag_count=inputs.get("positive_flag_count", 0),
        negative_flag_count=inputs.get("negative_flag_count", 0),
        has_import_eligibility_soon=inputs.get("has_import_eligibility_soon", False),
    )
    confidence = _compute_confidence(score, inputs.get("active_rule_flags", 0) > 0 or inputs.get("has_import_eligibility_soon", False))
    results[ConsensusModelType.RULES] = (score, confidence, rationale, data)

    return results


def _aggregate_scores(
    scores: dict[ConsensusModelType, tuple[int, Decimal, str, dict]],
) -> dict:
    """Aggregate individual model scores, apply veto logic, classify.

    Returns
    -------
    dict with aggregate_score, has_veto, veto_model, veto_reason,
    status, actionable, disagreement_summary.
    """
    score_values = [s[0] for s in scores.values()]
    aggregate = sum(score_values)

    # Veto logic: ANY score of -2 kills the opportunity
    has_veto = False
    veto_model: Optional[str] = None
    veto_reason: Optional[str] = None

    for model_type, (score, _conf, rationale, _data) in scores.items():
        if score == VETO_SCORE:
            has_veto = True
            veto_model = model_type.value
            veto_reason = rationale
            break  # First veto found is sufficient

    # Disagreement detection
    disagreement_summary: Optional[str] = None
    if score_values:
        spread = max(score_values) - min(score_values)
        if spread > DISAGREEMENT_SPREAD_THRESHOLD:
            high_models = [
                mt.value for mt, (s, _, _, _) in scores.items() if s == max(score_values)
            ]
            low_models = [
                mt.value for mt, (s, _, _, _) in scores.items() if s == min(score_values)
            ]
            disagreement_summary = (
                f"Spread of {spread} detected. "
                f"Highest: {', '.join(high_models)} ({max(score_values)}). "
                f"Lowest: {', '.join(low_models)} ({min(score_values)}). "
                f"Manual review recommended."
            )

    # Classification
    if has_veto:
        status = OpportunityStatus.PASSED
        actionable = False
    elif aggregate >= ACTIONABLE_THRESHOLD:
        status = OpportunityStatus.ACTIONABLE
        actionable = True
    elif aggregate >= WATCHLIST_THRESHOLD:
        status = OpportunityStatus.WATCHLIST
        actionable = False
    else:
        status = OpportunityStatus.PASSED
        actionable = False

    return {
        "aggregate_score": aggregate,
        "has_veto": has_veto,
        "veto_model": veto_model,
        "veto_reason": veto_reason,
        "status": status,
        "actionable": actionable,
        "disagreement_summary": disagreement_summary,
    }


def _compute_confidence(score: int, has_data: bool) -> Decimal:
    """Compute a confidence value for a model score.

    Higher confidence when data is available and score is non-zero.
    """
    if not has_data:
        return Decimal("0.300")
    if score == 0:
        return Decimal("0.500")
    return Decimal("0.800")


async def _gather_model_inputs(
    session: AsyncSession, asset_model_id: uuid.UUID
) -> dict:
    """Query the database to gather inputs for all six scoring models."""
    inputs: dict = {}
    now = datetime.now(timezone.utc)
    one_year_ago = now - timedelta(days=365)
    six_months_ago = now - timedelta(days=182)

    # --- Fair Value data (for momentum + fundamental) ---
    fv_query = await session.execute(
        select(FairValue)
        .where(FairValue.asset_model_id == asset_model_id)
        .order_by(FairValue.valuation_date.desc())
        .limit(1)
    )
    latest_fv = fv_query.scalar_one_or_none()

    if latest_fv:
        inputs["appreciation_rate_90d"] = latest_fv.appreciation_rate_90d
        inputs["appreciation_rate_365d"] = latest_fv.appreciation_rate_365d
        inputs["fair_value_mid"] = latest_fv.fair_value_mid
        inputs["fair_value_confidence"] = latest_fv.confidence_score

    # --- Momentum signal ---
    signal_query = await session.execute(
        select(Signal)
        .where(
            Signal.asset_model_id == asset_model_id,
            Signal.signal_type == SignalType.MOMENTUM,
            Signal.is_active.is_(True),
        )
        .order_by(Signal.generated_at.desc())
        .limit(1)
    )
    momentum_signal = signal_query.scalar_one_or_none()
    inputs["has_momentum_signal"] = momentum_signal is not None
    inputs["signal_direction"] = momentum_signal.direction if momentum_signal else None

    # --- Latest transaction price (for fundamental) ---
    tx_query = await session.execute(
        select(Transaction.normalised_price_usd)
        .where(
            Transaction.asset_model_id == asset_model_id,
            Transaction.transaction_type.in_([
                TransactionType.AUCTION_SOLD,
                TransactionType.DEALER_SOLD,
                TransactionType.PRIVATE_SALE,
            ]),
            Transaction.normalised_price_usd.isnot(None),
        )
        .order_by(Transaction.transaction_date.desc())
        .limit(1)
    )
    latest_price_row = tx_query.one_or_none()
    inputs["latest_transaction_price"] = latest_price_row[0] if latest_price_row else None

    # --- Liquidity data ---
    count_12m_query = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.asset_model_id == asset_model_id,
            Transaction.transaction_date >= one_year_ago.date(),
        )
    )
    inputs["transaction_count_12m"] = count_12m_query.scalar() or 0

    count_6m_query = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.asset_model_id == asset_model_id,
            Transaction.transaction_date >= six_months_ago.date(),
        )
    )
    inputs["transaction_count_6m"] = count_6m_query.scalar() or 0

    sources_query = await session.execute(
        select(func.count(func.distinct(Transaction.source)))
        .where(
            Transaction.asset_model_id == asset_model_id,
            Transaction.transaction_date >= one_year_ago.date(),
        )
    )
    inputs["distinct_sources"] = sources_query.scalar() or 0

    dom_query = await session.execute(
        select(func.avg(Transaction.days_on_market))
        .where(
            Transaction.asset_model_id == asset_model_id,
            Transaction.days_on_market.isnot(None),
            Transaction.transaction_date >= one_year_ago.date(),
        )
    )
    avg_dom = dom_query.scalar()
    inputs["avg_days_on_market"] = int(avg_dom) if avg_dom is not None else None

    # --- Sentiment data ---
    sentiment_query = await session.execute(
        select(
            func.avg(ForumSentiment.avg_sentiment),
            func.avg(ForumSentiment.mention_volume_change_pct),
        )
        .where(
            ForumSentiment.asset_model_id == asset_model_id,
            ForumSentiment.period_start >= six_months_ago.date(),
        )
    )
    sentiment_row = sentiment_query.one_or_none()
    if sentiment_row and sentiment_row[0] is not None:
        inputs["avg_sentiment"] = sentiment_row[0]
        inputs["mention_volume_change_pct"] = sentiment_row[1]
    else:
        inputs["avg_sentiment"] = None
        inputs["mention_volume_change_pct"] = None

    # News sentiment: check for negative catalyst signals
    catalyst_query = await session.execute(
        select(Signal)
        .where(
            Signal.asset_model_id == asset_model_id,
            Signal.signal_type == SignalType.CATALYST,
            Signal.is_active.is_(True),
            Signal.direction == -1,
        )
        .limit(1)
    )
    inputs["has_negative_catalyst"] = catalyst_query.scalar_one_or_none() is not None
    inputs["news_sentiment_avg"] = None  # Populated by news pipeline if available

    # --- Macro data ---
    for indicator_name, key in [
        ("luxury_index", "luxury_index_trend"),
        ("interest_rate", "interest_rate_trend"),
        ("wealth_indicator", "wealth_indicator_trend"),
    ]:
        macro_query = await session.execute(
            select(MacroIndicator.value)
            .where(MacroIndicator.indicator_name == indicator_name)
            .order_by(MacroIndicator.indicator_date.desc())
            .limit(2)
        )
        rows = macro_query.all()
        if len(rows) >= 2 and rows[1][0] != Decimal("0"):
            trend = (rows[0][0] - rows[1][0]) / rows[1][0]
            inputs[key] = trend
        else:
            inputs[key] = None

    # --- Rules data ---
    rule_flags_query = await session.execute(
        select(
            func.count(),
            func.count().filter(RuleModelFlag.is_positive.is_(True)),
            func.count().filter(RuleModelFlag.is_positive.is_(False)),
        )
        .where(RuleModelFlag.asset_model_id == asset_model_id)
    )
    rule_row = rule_flags_query.one()
    inputs["active_rule_flags"] = rule_row[0] or 0
    inputs["positive_flag_count"] = rule_row[1] or 0
    inputs["negative_flag_count"] = rule_row[2] or 0

    # Import eligibility within next 24 months
    two_years_from_now = date.today() + timedelta(days=730)
    eligibility_query = await session.execute(
        select(ImportEligibilityCalendar)
        .where(
            ImportEligibilityCalendar.asset_model_id == asset_model_id,
            ImportEligibilityCalendar.eligible_date <= two_years_from_now,
            ImportEligibilityCalendar.eligible_date >= date.today(),
        )
        .limit(1)
    )
    inputs["has_import_eligibility_soon"] = eligibility_query.scalar_one_or_none() is not None

    return inputs
