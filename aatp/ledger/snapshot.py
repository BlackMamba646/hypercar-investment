from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import PortfolioSnapshot, Position, PositionStatus

logger = get_logger("ledger.snapshot")


async def generate_daily_snapshot(
    session: AsyncSession,
    snapshot_date: date,
) -> PortfolioSnapshot:
    """Aggregate all open positions into a daily portfolio snapshot.

    If a snapshot for *snapshot_date* already exists it is returned as-is
    (idempotent).
    """
    # Check for existing snapshot
    existing = await session.execute(
        select(PortfolioSnapshot).where(
            PortfolioSnapshot.snapshot_date == snapshot_date
        )
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        logger.info("snapshot_already_exists", snapshot_date=str(snapshot_date))
        return found

    # Fetch all open positions
    result = await session.execute(
        select(Position).where(Position.status == PositionStatus.OPEN)
    )
    positions: List[Position] = list(result.scalars().all())

    total_market_value = Decimal("0")
    total_cost_basis = Decimal("0")
    total_unrealised = Decimal("0")
    capital_deployed = Decimal("0")
    breakdown: List[Dict[str, Any]] = []

    for pos in positions:
        fv = pos.current_fair_value_usd or pos.acquisition_price_usd
        cb = pos.total_cost_basis or pos.acquisition_price_usd
        upnl = pos.unrealised_pnl or Decimal("0")

        total_market_value += fv
        total_cost_basis += cb
        total_unrealised += upnl
        capital_deployed += pos.acquisition_price_usd

        breakdown.append({
            "position_id": str(pos.id),
            "description": pos.description,
            "acquisition_price_usd": str(pos.acquisition_price_usd),
            "current_fair_value_usd": str(fv),
            "total_cost_basis": str(cb),
            "unrealised_pnl": str(upnl),
            "status": pos.status.value,
        })

    # Sum realised P&L across exited positions
    exited_result = await session.execute(
        select(Position).where(Position.status == PositionStatus.EXITED)
    )
    exited_positions = exited_result.scalars().all()
    total_realised = sum(
        (p.realised_pnl or Decimal("0")) for p in exited_positions
    )

    snapshot = PortfolioSnapshot(
        snapshot_date=snapshot_date,
        total_market_value_usd=total_market_value,
        total_cost_basis_usd=total_cost_basis,
        total_unrealised_pnl_usd=total_unrealised,
        total_realised_pnl_usd=total_realised,
        open_positions_count=len(positions),
        capital_deployed_usd=capital_deployed,
        position_breakdown={"positions": breakdown},
    )
    session.add(snapshot)
    await session.flush()

    logger.info(
        "snapshot_generated",
        snapshot_date=str(snapshot_date),
        open_positions=len(positions),
        total_market_value_usd=str(total_market_value),
        total_unrealised_pnl_usd=str(total_unrealised),
    )
    return snapshot
