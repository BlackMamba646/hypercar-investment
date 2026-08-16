from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.ledger import (
    PortfolioSnapshotResponse,
    PositionCreateRequest,
    PositionResponse,
)
from aatp.core.logging import get_logger
from aatp.db.models import AssetClass, Position, PortfolioSnapshot, PositionStatus
from aatp.db.session import get_session
from aatp.ledger.position_service import OpenPositionData, open_position

logger = get_logger("api.ledger")

router = APIRouter(prefix="/api/v1", tags=["ledger"])


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PositionResponse]:
    query = select(Position)

    if status is not None:
        query = query.where(Position.status == PositionStatus(status))

    result = await session.execute(
        query.order_by(desc(Position.created_at)).offset(skip).limit(limit)
    )
    return [PositionResponse.model_validate(p) for p in result.scalars().all()]


@router.post("/positions", response_model=PositionResponse, status_code=201)
async def create_position(
    body: PositionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PositionResponse:
    data = OpenPositionData(
        asset_model_id=body.asset_model_id,
        description=body.description,
        acquisition_date=body.acquisition_date,
        acquisition_price=body.acquisition_price,
        acquisition_price_usd=body.acquisition_price_usd,
        acquisition_channel=body.acquisition_channel,
        acquisition_currency=body.acquisition_currency,
        asset_class=AssetClass(body.asset_class),
        identifier=body.identifier,
        year=body.year,
        colour_exterior=body.colour_exterior,
        colour_interior=body.colour_interior,
        mileage_at_acquisition=body.mileage_at_acquisition,
        notes=body.notes,
    )
    position = await open_position(session, data)
    await session.commit()
    return PositionResponse.model_validate(position)


@router.get("/positions/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PositionResponse:
    result = await session.execute(
        select(Position).where(Position.id == position_id)
    )
    position = result.scalar_one_or_none()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return PositionResponse.model_validate(position)


@router.get("/pnl", response_model=PortfolioSnapshotResponse)
async def get_portfolio_pnl(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PortfolioSnapshotResponse:
    result = await session.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No portfolio snapshot found")
    return PortfolioSnapshotResponse.model_validate(snapshot)
