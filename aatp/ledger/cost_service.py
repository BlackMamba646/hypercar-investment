from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import CostCategory, CostEntry, Position, PositionStatus
from aatp.ledger.ledger_service import record_entry

logger = get_logger("ledger.cost_service")


async def add_cost(
    session: AsyncSession,
    position_id: uuid.UUID,
    category: CostCategory,
    amount: Decimal,
    cost_date: date,
    description: str,
    currency: str = "USD",
    amount_usd: Optional[Decimal] = None,
    vendor: Optional[str] = None,
    invoice_reference: Optional[str] = None,
    is_recurring: bool = False,
    recurrence_months: Optional[int] = None,
) -> CostEntry:
    """Record a cost entry and its corresponding ledger entry."""
    resolved_usd = amount_usd if amount_usd is not None else amount

    cost = CostEntry(
        position_id=position_id,
        cost_category=category,
        cost_date=cost_date,
        amount=amount,
        currency=currency,
        amount_usd=resolved_usd,
        description=description,
        vendor=vendor,
        invoice_reference=invoice_reference,
        is_recurring=is_recurring,
        recurrence_months=recurrence_months,
    )
    session.add(cost)
    await session.flush()

    # Mirror as immutable ledger entry
    await record_entry(
        session,
        position_id=position_id,
        entry_type=f"cost:{category.value}",
        amount=amount,
        description=description,
        currency=currency,
        amount_usd=resolved_usd,
    )

    # Update denormalised cost totals on position
    await _refresh_position_costs(session, position_id)

    logger.info(
        "cost_added",
        cost_id=str(cost.id),
        position_id=str(position_id),
        category=category.value,
        amount_usd=str(resolved_usd),
    )
    return cost


async def generate_recurring_costs(session: AsyncSession) -> int:
    """Auto-generate monthly recurring costs for all open positions.

    For each open position, finds recurring cost entries and creates new
    entries for the current month if one does not already exist.

    Returns the number of new cost entries created.
    """
    today = date.today()

    result = await session.execute(
        select(Position).where(Position.status == PositionStatus.OPEN)
    )
    positions = result.scalars().all()

    generated = 0
    for position in positions:
        recurring_result = await session.execute(
            select(CostEntry).where(
                CostEntry.position_id == position.id,
                CostEntry.is_recurring.is_(True),
            )
        )
        recurring_costs = recurring_result.scalars().all()

        for rc in recurring_costs:
            # Check whether this recurring cost has already been generated
            # for the current month.
            existing = await session.execute(
                select(func.count()).select_from(CostEntry).where(
                    CostEntry.position_id == position.id,
                    CostEntry.cost_category == rc.cost_category,
                    func.extract("year", CostEntry.cost_date) == today.year,
                    func.extract("month", CostEntry.cost_date) == today.month,
                    CostEntry.is_recurring.is_(True),
                    CostEntry.id != rc.id,
                )
            )
            if existing.scalar_one() > 0:
                continue

            # Also skip if the template itself is from the current month
            if rc.cost_date.year == today.year and rc.cost_date.month == today.month:
                continue

            await add_cost(
                session,
                position_id=position.id,
                category=rc.cost_category,
                amount=rc.amount,
                cost_date=today,
                description=f"{rc.description} (recurring)",
                currency=rc.currency,
                amount_usd=rc.amount_usd,
                vendor=rc.vendor,
                is_recurring=True,
                recurrence_months=rc.recurrence_months,
            )
            generated += 1

    logger.info("recurring_costs_generated", count=generated)
    return generated


async def get_cost_summary(
    session: AsyncSession,
    position_id: uuid.UUID,
) -> Dict[str, Decimal]:
    """Sum costs by category for a position.

    Returns a dict mapping ``CostCategory.value`` strings to total USD amounts,
    plus a ``"total"`` key.
    """
    result = await session.execute(
        select(CostEntry.cost_category, func.sum(CostEntry.amount_usd))
        .where(CostEntry.position_id == position_id)
        .group_by(CostEntry.cost_category)
    )

    summary: Dict[str, Decimal] = {}
    total = Decimal("0")
    for category, amount in result.all():
        cat_value = category.value if hasattr(category, "value") else str(category)
        summary[cat_value] = amount
        total += amount

    summary["total"] = total
    return summary


# ---- Internal helpers -------------------------------------------------------

_ACQUISITION_CATEGORIES = frozenset({
    CostCategory.ACQUISITION_PREMIUM,
    CostCategory.AUCTION_BUYER_PREMIUM,
    CostCategory.IMPORT_DUTY,
    CostCategory.TAX,
    CostCategory.TRANSPORT,
    CostCategory.INSPECTION,
    CostCategory.DOCUMENTATION,
})

_HOLDING_CATEGORIES = frozenset({
    CostCategory.INSURANCE,
    CostCategory.STORAGE,
    CostCategory.MAINTENANCE,
    CostCategory.DETAILING,
    CostCategory.PHOTOGRAPHY,
    CostCategory.CATALOGUE_FEE,
})

_EXIT_CATEGORIES = frozenset({
    CostCategory.SELLER_COMMISSION,
})


async def _refresh_position_costs(
    session: AsyncSession,
    position_id: uuid.UUID,
) -> None:
    """Recalculate denormalised cost totals on the Position record."""
    result = await session.execute(
        select(CostEntry.cost_category, func.sum(CostEntry.amount_usd))
        .where(CostEntry.position_id == position_id)
        .group_by(CostEntry.cost_category)
    )
    rows = result.all()

    acquisition = Decimal("0")
    holding = Decimal("0")
    exit_ = Decimal("0")

    for category, amount in rows:
        if category in _ACQUISITION_CATEGORIES:
            acquisition += amount
        elif category in _HOLDING_CATEGORIES:
            holding += amount
        elif category in _EXIT_CATEGORIES:
            exit_ += amount
        else:
            # OTHER category — attribute to holding by default
            holding += amount

    position_result = await session.execute(
        select(Position).where(Position.id == position_id)
    )
    position = position_result.scalar_one()

    position.total_acquisition_costs = acquisition
    position.total_holding_costs = holding
    position.total_exit_costs = exit_
    position.total_cost_basis = position.acquisition_price_usd + acquisition + holding + exit_

    await session.flush()
