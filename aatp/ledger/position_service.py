from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import (
    AssetClass,
    CostCategory,
    Position,
    PositionStatus,
)
from aatp.ledger.cost_service import add_cost
from aatp.ledger.ledger_service import record_entry
from aatp.ledger.pnl import (
    MonthlyHoldingCost,
    calculate_holding_period_months,
    calculate_irr,
    calculate_realised_pnl,
    calculate_total_cost_basis,
    calculate_unrealised_pnl,
)

logger = get_logger("ledger.position_service")


@dataclass
class InitialCost:
    """A cost to record at acquisition time."""
    category: CostCategory
    amount: Decimal
    description: str
    currency: str = "USD"
    amount_usd: Optional[Decimal] = None
    vendor: Optional[str] = None
    invoice_reference: Optional[str] = None


@dataclass
class OpenPositionData:
    """Data required to open a new position."""
    asset_model_id: uuid.UUID
    description: str
    acquisition_date: date
    acquisition_price: Decimal
    acquisition_price_usd: Decimal
    acquisition_channel: str
    acquisition_currency: str = "USD"
    asset_class: AssetClass = AssetClass.CAR
    identifier: Optional[str] = None
    year: Optional[int] = None
    colour_exterior: Optional[str] = None
    colour_interior: Optional[str] = None
    mileage_at_acquisition: Optional[int] = None
    spec_details: Optional[dict] = None
    provenance_dossier: Optional[dict] = None
    acquisition_counterparty: Optional[str] = None
    dealer_id: Optional[uuid.UUID] = None
    auction_house_id: Optional[uuid.UUID] = None
    storage_location: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_policy_number: Optional[str] = None
    notes: Optional[str] = None
    initial_costs: List[InitialCost] = field(default_factory=list)


@dataclass
class ExitData:
    """Data required to close a position."""
    exit_date: date
    exit_price: Decimal
    exit_price_usd: Decimal
    exit_channel: str
    exit_currency: str = "USD"
    exit_counterparty: Optional[str] = None
    exit_hammer_price: Optional[Decimal] = None
    exit_buyer_premium: Optional[Decimal] = None
    exit_costs: List[InitialCost] = field(default_factory=list)


async def open_position(
    session: AsyncSession,
    data: OpenPositionData,
) -> Position:
    """Create a new position with acquisition details, costs, and ledger entry."""
    position = Position(
        asset_model_id=data.asset_model_id,
        asset_class=data.asset_class,
        status=PositionStatus.OPEN,
        identifier=data.identifier,
        year=data.year,
        description=data.description,
        colour_exterior=data.colour_exterior,
        colour_interior=data.colour_interior,
        mileage_at_acquisition=data.mileage_at_acquisition,
        spec_details=data.spec_details,
        provenance_dossier=data.provenance_dossier,
        acquisition_date=data.acquisition_date,
        acquisition_price=data.acquisition_price,
        acquisition_currency=data.acquisition_currency,
        acquisition_price_usd=data.acquisition_price_usd,
        acquisition_channel=data.acquisition_channel,
        acquisition_counterparty=data.acquisition_counterparty,
        dealer_id=data.dealer_id,
        auction_house_id=data.auction_house_id,
        storage_location=data.storage_location,
        insurance_provider=data.insurance_provider,
        insurance_policy_number=data.insurance_policy_number,
        notes=data.notes,
        current_fair_value_usd=data.acquisition_price_usd,
        fair_value_date=data.acquisition_date,
        total_acquisition_costs=Decimal("0"),
        total_holding_costs=Decimal("0"),
        total_exit_costs=Decimal("0"),
        total_cost_basis=data.acquisition_price_usd,
        unrealised_pnl=Decimal("0"),
    )
    session.add(position)
    await session.flush()

    # Record acquisition ledger entry
    await record_entry(
        session,
        position_id=position.id,
        entry_type="acquisition",
        amount=data.acquisition_price,
        description=f"Acquisition: {data.description}",
        currency=data.acquisition_currency,
        amount_usd=data.acquisition_price_usd,
    )

    # Record initial costs (buyer premium, transport, etc.)
    for ic in data.initial_costs:
        await add_cost(
            session,
            position_id=position.id,
            category=ic.category,
            amount=ic.amount,
            cost_date=data.acquisition_date,
            description=ic.description,
            currency=ic.currency,
            amount_usd=ic.amount_usd,
            vendor=ic.vendor,
            invoice_reference=ic.invoice_reference,
        )

    # Refresh to pick up denormalised cost totals
    await session.refresh(position)

    logger.info(
        "position_opened",
        position_id=str(position.id),
        description=data.description,
        acquisition_price_usd=str(data.acquisition_price_usd),
    )
    return position


async def close_position(
    session: AsyncSession,
    position_id: uuid.UUID,
    exit_data: ExitData,
) -> Position:
    """Close a position: record exit details, costs, P&L, and IRR."""
    result = await session.execute(
        select(Position).where(Position.id == position_id)
    )
    position = result.scalar_one()

    # Record exit costs first
    for ec in exit_data.exit_costs:
        await add_cost(
            session,
            position_id=position_id,
            category=ec.category,
            amount=ec.amount,
            cost_date=exit_data.exit_date,
            description=ec.description,
            currency=ec.currency,
            amount_usd=ec.amount_usd,
            vendor=ec.vendor,
            invoice_reference=ec.invoice_reference,
        )

    # Update exit fields
    position.exit_date = exit_data.exit_date
    position.exit_price = exit_data.exit_price
    position.exit_currency = exit_data.exit_currency
    position.exit_price_usd = exit_data.exit_price_usd
    position.exit_channel = exit_data.exit_channel
    position.exit_counterparty = exit_data.exit_counterparty
    position.exit_hammer_price = exit_data.exit_hammer_price
    position.exit_buyer_premium = exit_data.exit_buyer_premium
    position.status = PositionStatus.EXITED

    await session.flush()
    await session.refresh(position)

    # Calculate realised P&L
    total_cost_basis = position.total_cost_basis or position.acquisition_price_usd
    realised = calculate_realised_pnl(exit_data.exit_price_usd, total_cost_basis)
    position.realised_pnl = realised
    position.unrealised_pnl = Decimal("0")
    position.current_fair_value_usd = exit_data.exit_price_usd
    position.fair_value_date = exit_data.exit_date

    # Calculate IRR
    hold_months = calculate_holding_period_months(
        position.acquisition_date, exit_data.exit_date
    )
    monthly_holding = (
        Decimal("0") if hold_months == 0
        else (position.total_holding_costs or Decimal("0")) / hold_months
    )
    holding_costs = [
        MonthlyHoldingCost(month_offset=m, amount=monthly_holding)
        for m in range(1, hold_months + 1)
    ]
    acquisition_cost = position.acquisition_price_usd + (
        position.total_acquisition_costs or Decimal("0")
    )
    exit_proceeds = exit_data.exit_price_usd - (
        position.total_exit_costs or Decimal("0")
    )
    irr = calculate_irr(
        acquisition_date=position.acquisition_date,
        acquisition_cost=acquisition_cost,
        holding_costs_by_month=holding_costs,
        exit_date=exit_data.exit_date,
        exit_proceeds=exit_proceeds,
    )
    position.irr = irr

    await session.flush()

    # Record exit ledger entry
    await record_entry(
        session,
        position_id=position_id,
        entry_type="exit",
        amount=exit_data.exit_price,
        description=f"Exit: {position.description} via {exit_data.exit_channel}",
        currency=exit_data.exit_currency,
        amount_usd=exit_data.exit_price_usd,
    )

    logger.info(
        "position_closed",
        position_id=str(position_id),
        realised_pnl=str(realised),
        irr=str(irr),
        hold_months=hold_months,
    )
    return position


async def update_fair_value(
    session: AsyncSession,
    position_id: uuid.UUID,
    fair_value_usd: Decimal,
    valuation_date: date,
) -> Position:
    """Update the current fair value and recalculate unrealised P&L."""
    result = await session.execute(
        select(Position).where(Position.id == position_id)
    )
    position = result.scalar_one()

    position.current_fair_value_usd = fair_value_usd
    position.fair_value_date = valuation_date

    cost_basis = position.total_cost_basis or position.acquisition_price_usd
    position.unrealised_pnl = calculate_unrealised_pnl(fair_value_usd, cost_basis)

    await session.flush()

    logger.info(
        "fair_value_updated",
        position_id=str(position_id),
        fair_value_usd=str(fair_value_usd),
        unrealised_pnl=str(position.unrealised_pnl),
    )
    return position
