"""Risk engine orchestrator.

Coordinates position-level and portfolio-level risk assessments,
gathers data from the database, calls pure scoring functions, and
persists results.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aatp.core.logging import get_logger
from aatp.db.models import (
    AssetModel,
    AuctionHouse,
    Dealer,
    Manufacturer,
    Position,
    PositionStatus,
    PortfolioRiskSnapshot,
    RiskAssessment,
    Transaction,
    TransactionType,
)
from aatp.risk.portfolio_risk import (
    assess_era_concentration,
    assess_illiquid_exposure,
    assess_manufacturer_concentration,
    assess_type_concentration,
)
from aatp.risk.position_risk import (
    compute_composite_risk,
    score_concentration_risk,
    score_counterparty_risk,
    score_liquidity_risk,
    score_physical_risk,
    score_provenance_risk,
    score_spec_risk,
)
from aatp.risk.scenarios import (
    scenario_market_drop,
    scenario_no_flagship_auction,
    scenario_rate_change,
)

logger = get_logger("risk.engine")


async def assess_position(
    session: AsyncSession,
    position_id: uuid.UUID,
) -> RiskAssessment:
    """Run all 6 risk dimensions for a single position and write to DB.

    Returns
    -------
    The persisted RiskAssessment instance.
    """
    logger.info("position_risk_start", position_id=str(position_id))

    # Load position with related data
    pos_query = await session.execute(
        select(Position)
        .options(selectinload(Position.asset_model).selectinload(AssetModel.manufacturer))
        .where(Position.id == position_id)
    )
    position = pos_query.scalar_one()

    # Gather inputs for each risk dimension
    inputs = await _gather_position_inputs(session, position)

    # 1. Liquidity risk
    liquidity_score, liquidity_explanation = score_liquidity_risk(
        transaction_count_12m=inputs["transaction_count_12m"],
        transaction_count_6m=inputs["transaction_count_6m"],
        days_since_last_sale=inputs["days_since_last_sale"],
        distinct_channels=inputs["distinct_channels"],
    )

    # 2. Concentration risk
    concentration_score, concentration_explanation = score_concentration_risk(
        position_value=inputs["position_value"],
        total_portfolio_value=inputs["total_portfolio_value"],
        manufacturer_count=inputs["total_position_count"],
        same_manufacturer_count=inputs["same_manufacturer_count"],
    )

    # 3. Physical risk
    physical_score, physical_explanation = score_physical_risk(
        has_storage=inputs["has_storage"],
        has_insurance=inputs["has_insurance"],
        storage_quality_score=inputs["storage_quality_score"],
    )

    # 4. Counterparty risk
    counterparty_score, counterparty_explanation = score_counterparty_risk(
        dealer_tier=inputs["dealer_tier"],
        dealer_reliability=inputs["dealer_reliability"],
        auction_house_tier=inputs["auction_house_tier"],
    )

    # 5. Spec risk
    spec_score, spec_explanation = score_spec_risk(
        colour_tier=inputs["colour_tier"],
        has_desirable_options=inputs["has_desirable_options"],
        mileage=inputs["mileage"],
        mileage_ceiling=inputs["mileage_ceiling"],
        has_certification=inputs["has_certification"],
    )

    # 6. Provenance risk
    provenance_score, provenance_explanation = score_provenance_risk(
        has_books=inputs["has_books"],
        has_service_history=inputs["has_service_history"],
        single_owner=inputs["single_owner"],
        has_accident_history=inputs["has_accident_history"],
        ownership_gaps=inputs["ownership_gaps"],
    )

    # Composite
    scores = {
        "liquidity": liquidity_score,
        "concentration": concentration_score,
        "physical": physical_score,
        "counterparty": counterparty_score,
        "spec": spec_score,
        "provenance": provenance_score,
    }
    composite = compute_composite_risk(scores)

    # Build explanation
    explanations = [
        f"Liquidity ({liquidity_score}): {liquidity_explanation}",
        f"Concentration ({concentration_score}): {concentration_explanation}",
        f"Physical ({physical_score}): {physical_explanation}",
        f"Counterparty ({counterparty_score}): {counterparty_explanation}",
        f"Spec ({spec_score}): {spec_explanation}",
        f"Provenance ({provenance_score}): {provenance_explanation}",
    ]
    risk_explanation = " | ".join(explanations)

    # Build risk factors
    risk_factors = {
        dim: {"score": str(s), "explanation": exp}
        for dim, s, exp in [
            ("liquidity", liquidity_score, liquidity_explanation),
            ("concentration", concentration_score, concentration_explanation),
            ("physical", physical_score, physical_explanation),
            ("counterparty", counterparty_score, counterparty_explanation),
            ("spec", spec_score, spec_explanation),
            ("provenance", provenance_score, provenance_explanation),
        ]
    }

    # Build recommendations
    recommendations = _generate_recommendations(scores)

    assessment = RiskAssessment(
        position_id=position_id,
        assessed_at=datetime.now(timezone.utc),
        liquidity_risk_score=liquidity_score,
        concentration_risk_score=concentration_score,
        physical_risk_score=physical_score,
        counterparty_risk_score=counterparty_score,
        spec_risk_score=spec_score,
        provenance_risk_score=provenance_score,
        composite_risk_score=composite,
        risk_explanation=risk_explanation,
        risk_factors=risk_factors,
        recommendations=recommendations,
    )
    session.add(assessment)

    logger.info(
        "position_risk_complete",
        position_id=str(position_id),
        composite_risk=str(composite),
    )

    return assessment


async def assess_portfolio(
    session: AsyncSession,
    snapshot_date: date | None = None,
) -> PortfolioRiskSnapshot:
    """Run portfolio-level risk analysis and write snapshot to DB.

    Returns
    -------
    The persisted PortfolioRiskSnapshot instance.
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    logger.info("portfolio_risk_start", snapshot_date=str(snapshot_date))

    # Load all open positions with manufacturer info
    pos_query = await session.execute(
        select(Position)
        .options(selectinload(Position.asset_model).selectinload(AssetModel.manufacturer))
        .where(Position.status == PositionStatus.OPEN)
    )
    positions = list(pos_query.scalars().all())

    if not positions:
        logger.info("portfolio_risk_empty", snapshot_date=str(snapshot_date))
        snapshot = PortfolioRiskSnapshot(
            snapshot_date=snapshot_date,
            manufacturer_concentration={},
            era_concentration={},
            type_concentration={},
            max_manufacturer_exposure_pct=Decimal("0.00"),
            total_illiquid_90d_pct=Decimal("0.00"),
            scenario_analysis={},
            warnings=[],
            narrative="No open positions in portfolio.",
        )
        session.add(snapshot)
        return snapshot

    # Manufacturer concentration
    mfr_values: dict[str, Decimal] = {}
    for pos in positions:
        mfr_name = pos.asset_model.manufacturer.name
        value = pos.current_fair_value_usd or pos.acquisition_price_usd
        mfr_values[mfr_name] = mfr_values.get(mfr_name, Decimal("0")) + value

    mfr_concentration, mfr_warnings = assess_manufacturer_concentration(mfr_values)

    # Era concentration (by decade)
    era_values: dict[str, Decimal] = {}
    for pos in positions:
        year = pos.year or (pos.asset_model.production_year_start or 2000)
        decade = f"{(year // 10) * 10}s"
        value = pos.current_fair_value_usd or pos.acquisition_price_usd
        era_values[decade] = era_values.get(decade, Decimal("0")) + value

    era_concentration, era_warnings = assess_era_concentration(era_values)

    # Type concentration (coupe vs open-top)
    type_values: dict[str, Decimal] = {}
    for pos in positions:
        asset_type = "open_top" if pos.asset_model.is_open_top else "coupe"
        value = pos.current_fair_value_usd or pos.acquisition_price_usd
        type_values[asset_type] = type_values.get(asset_type, Decimal("0")) + value

    type_concentration, type_warnings = assess_type_concentration(type_values)

    # Max manufacturer exposure
    max_mfr_pct = Decimal("0.00")
    for pct_str in mfr_concentration.values():
        pct_val = Decimal(pct_str)
        if pct_val > max_mfr_pct:
            max_mfr_pct = pct_val

    # Illiquid exposure
    now = datetime.now(timezone.utc)
    positions_with_days: list[tuple[str, int | None]] = []
    for pos in positions:
        last_sale_query = await session.execute(
            select(Transaction.transaction_date)
            .where(
                Transaction.asset_model_id == pos.asset_model_id,
                Transaction.transaction_type.in_([
                    TransactionType.AUCTION_SOLD,
                    TransactionType.DEALER_SOLD,
                    TransactionType.PRIVATE_SALE,
                ]),
            )
            .order_by(Transaction.transaction_date.desc())
            .limit(1)
        )
        row = last_sale_query.one_or_none()
        if row:
            days = (now.date() - row[0]).days
        else:
            days = None
        positions_with_days.append((str(pos.id), days))

    illiquid_pct, illiquid_warnings = assess_illiquid_exposure(positions_with_days)

    # Scenario analysis
    pos_data = [
        {
            "position_id": str(p.id),
            "manufacturer_name": p.asset_model.manufacturer.name,
            "current_fair_value_usd": p.current_fair_value_usd or p.acquisition_price_usd,
            "target_auction_event": (p.notes or ""),  # simplified
        }
        for p in positions
    ]

    # Run scenarios for the top manufacturer
    top_manufacturer = max(mfr_values, key=mfr_values.get) if mfr_values else ""
    scenarios = {}
    if top_manufacturer:
        scenarios["market_drop_20pct"] = scenario_market_drop(
            pos_data, top_manufacturer, Decimal("20"),
        )
    scenarios["rate_rise_200bps"] = scenario_rate_change(
        pos_data, 200, Decimal("0.05"),
    )

    # Aggregate warnings
    all_warnings = mfr_warnings + era_warnings + type_warnings + illiquid_warnings

    # Build narrative
    narrative_parts = [
        f"Portfolio snapshot for {snapshot_date} with {len(positions)} open position(s).",
    ]
    if all_warnings:
        narrative_parts.append(f"{len(all_warnings)} warning(s) detected:")
        for w in all_warnings:
            narrative_parts.append(f"  - {w}")
    else:
        narrative_parts.append("No concentration or liquidity warnings.")
    narrative = " ".join(narrative_parts)

    snapshot = PortfolioRiskSnapshot(
        snapshot_date=snapshot_date,
        manufacturer_concentration=mfr_concentration,
        era_concentration=era_concentration,
        type_concentration=type_concentration,
        max_manufacturer_exposure_pct=max_mfr_pct,
        total_illiquid_90d_pct=illiquid_pct,
        scenario_analysis=scenarios,
        warnings=all_warnings,
        narrative=narrative,
    )
    session.add(snapshot)

    logger.info(
        "portfolio_risk_complete",
        snapshot_date=str(snapshot_date),
        positions=len(positions),
        warnings=len(all_warnings),
        max_mfr_pct=str(max_mfr_pct),
        illiquid_pct=str(illiquid_pct),
    )

    return snapshot


async def run_full_assessment(session: AsyncSession) -> dict:
    """Assess all open positions and generate a portfolio snapshot.

    Returns
    -------
    dict with summary of the assessment run.
    """
    logger.info("full_risk_assessment_start")

    # Assess all open positions
    pos_query = await session.execute(
        select(Position.id).where(Position.status == PositionStatus.OPEN)
    )
    position_ids = [row[0] for row in pos_query.all()]

    results = {
        "positions_assessed": 0,
        "errors": 0,
    }

    for pos_id in position_ids:
        try:
            await assess_position(session, pos_id)
            results["positions_assessed"] += 1
        except Exception:
            logger.exception("position_risk_error", position_id=str(pos_id))
            results["errors"] += 1

    # Portfolio snapshot
    try:
        snapshot = await assess_portfolio(session)
        results["portfolio_snapshot_date"] = str(snapshot.snapshot_date)
        results["portfolio_warnings"] = len(snapshot.warnings or [])
    except Exception:
        logger.exception("portfolio_risk_error")
        results["errors"] += 1
        results["portfolio_snapshot_date"] = None

    await session.commit()

    logger.info("full_risk_assessment_complete", **results)
    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _gather_position_inputs(session: AsyncSession, position: Position) -> dict:
    """Query the database to gather inputs for all six risk scoring functions."""
    inputs: dict = {}
    now = datetime.now(timezone.utc)
    one_year_ago = now - timedelta(days=365)
    six_months_ago = now - timedelta(days=182)

    model_id = position.asset_model_id

    # --- Liquidity data ---
    count_12m = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.asset_model_id == model_id,
            Transaction.transaction_type.in_([
                TransactionType.AUCTION_SOLD,
                TransactionType.DEALER_SOLD,
                TransactionType.PRIVATE_SALE,
            ]),
            Transaction.transaction_date >= one_year_ago.date(),
        )
    )
    inputs["transaction_count_12m"] = count_12m.scalar() or 0

    count_6m = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.asset_model_id == model_id,
            Transaction.transaction_type.in_([
                TransactionType.AUCTION_SOLD,
                TransactionType.DEALER_SOLD,
                TransactionType.PRIVATE_SALE,
            ]),
            Transaction.transaction_date >= six_months_ago.date(),
        )
    )
    inputs["transaction_count_6m"] = count_6m.scalar() or 0

    # Days since last sale
    last_sale_query = await session.execute(
        select(Transaction.transaction_date)
        .where(
            Transaction.asset_model_id == model_id,
            Transaction.transaction_type.in_([
                TransactionType.AUCTION_SOLD,
                TransactionType.DEALER_SOLD,
                TransactionType.PRIVATE_SALE,
            ]),
        )
        .order_by(Transaction.transaction_date.desc())
        .limit(1)
    )
    last_sale_row = last_sale_query.one_or_none()
    if last_sale_row:
        inputs["days_since_last_sale"] = (now.date() - last_sale_row[0]).days
    else:
        inputs["days_since_last_sale"] = None

    # Distinct channels
    channels_query = await session.execute(
        select(func.count(func.distinct(Transaction.source)))
        .where(
            Transaction.asset_model_id == model_id,
            Transaction.transaction_date >= one_year_ago.date(),
        )
    )
    inputs["distinct_channels"] = channels_query.scalar() or 0

    # --- Concentration data ---
    position_value = position.current_fair_value_usd or position.acquisition_price_usd
    inputs["position_value"] = position_value

    total_value_query = await session.execute(
        select(
            func.coalesce(
                func.sum(func.coalesce(Position.current_fair_value_usd, Position.acquisition_price_usd)),
                Decimal("0"),
            )
        )
        .where(Position.status == PositionStatus.OPEN)
    )
    inputs["total_portfolio_value"] = total_value_query.scalar() or Decimal("0")

    total_count_query = await session.execute(
        select(func.count()).select_from(Position).where(Position.status == PositionStatus.OPEN)
    )
    inputs["total_position_count"] = total_count_query.scalar() or 0

    same_mfr_query = await session.execute(
        select(func.count())
        .select_from(Position)
        .join(AssetModel)
        .where(
            Position.status == PositionStatus.OPEN,
            AssetModel.manufacturer_id == position.asset_model.manufacturer_id,
        )
    )
    inputs["same_manufacturer_count"] = same_mfr_query.scalar() or 0

    # --- Physical risk data ---
    inputs["has_storage"] = bool(position.storage_location)
    inputs["has_insurance"] = bool(position.insurance_provider)
    inputs["storage_quality_score"] = None  # Could be enriched from metadata

    # --- Counterparty risk data ---
    inputs["dealer_tier"] = None
    inputs["dealer_reliability"] = None
    inputs["auction_house_tier"] = None

    if position.dealer_id:
        dealer_query = await session.execute(
            select(Dealer).where(Dealer.id == position.dealer_id)
        )
        dealer = dealer_query.scalar_one_or_none()
        if dealer:
            inputs["dealer_tier"] = dealer.tier.value
            inputs["dealer_reliability"] = dealer.reliability_score

    if position.auction_house_id:
        ah_query = await session.execute(
            select(AuctionHouse).where(AuctionHouse.id == position.auction_house_id)
        )
        ah = ah_query.scalar_one_or_none()
        if ah:
            inputs["auction_house_tier"] = ah.tier.value

    # --- Spec risk data ---
    spec = position.spec_details or {}
    inputs["colour_tier"] = spec.get("colour_tier")
    inputs["has_desirable_options"] = spec.get("has_desirable_options", False)
    inputs["mileage"] = position.mileage_at_acquisition
    inputs["mileage_ceiling"] = spec.get("mileage_ceiling")
    inputs["has_certification"] = spec.get("has_certification", False)

    # --- Provenance risk data ---
    prov = position.provenance_dossier or {}
    inputs["has_books"] = prov.get("has_books", False)
    inputs["has_service_history"] = prov.get("has_service_history", False)
    inputs["single_owner"] = prov.get("single_owner", False)
    inputs["has_accident_history"] = prov.get("has_accident_history", False)
    inputs["ownership_gaps"] = prov.get("ownership_gaps", 0)

    return inputs


def _generate_recommendations(scores: dict[str, Decimal]) -> dict:
    """Generate risk mitigation recommendations based on dimension scores."""
    recs: list[dict] = []

    HIGH = Decimal("0.6")
    MODERATE = Decimal("0.4")

    if scores.get("liquidity", Decimal("0")) >= HIGH:
        recs.append({
            "dimension": "liquidity",
            "priority": "high",
            "action": "Consider listing through additional channels to improve exit options.",
        })
    elif scores.get("liquidity", Decimal("0")) >= MODERATE:
        recs.append({
            "dimension": "liquidity",
            "priority": "medium",
            "action": "Monitor market activity; consider pre-marketing to dealers.",
        })

    if scores.get("concentration", Decimal("0")) >= HIGH:
        recs.append({
            "dimension": "concentration",
            "priority": "high",
            "action": "Reduce manufacturer concentration by diversifying future acquisitions.",
        })

    if scores.get("physical", Decimal("0")) >= HIGH:
        recs.append({
            "dimension": "physical",
            "priority": "high",
            "action": "Secure appropriate storage and insurance immediately.",
        })

    if scores.get("counterparty", Decimal("0")) >= HIGH:
        recs.append({
            "dimension": "counterparty",
            "priority": "medium",
            "action": "Consider working with higher-tier dealers or auction houses for exit.",
        })

    if scores.get("spec", Decimal("0")) >= HIGH:
        recs.append({
            "dimension": "spec",
            "priority": "medium",
            "action": "Consider factory certification or detailing to mitigate spec risk.",
        })

    if scores.get("provenance", Decimal("0")) >= HIGH:
        recs.append({
            "dimension": "provenance",
            "priority": "high",
            "action": "Locate missing documentation (books, service records) to improve provenance.",
        })

    return {"recommendations": recs, "count": len(recs)}
