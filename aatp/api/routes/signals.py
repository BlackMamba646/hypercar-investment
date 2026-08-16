from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.signals import OpportunityScoreResponse, SignalResponse
from aatp.core.logging import get_logger
from aatp.db.models import OpportunityScore, Signal
from aatp.db.session import get_session

logger = get_logger("api.signals")

router = APIRouter(prefix="/api/v1", tags=["signals"])


@router.get("/signals/{model_id}", response_model=list[SignalResponse])
async def get_active_signals(
    model_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SignalResponse]:
    result = await session.execute(
        select(Signal)
        .where(Signal.asset_model_id == model_id, Signal.is_active == True)
        .order_by(Signal.generated_at.desc())
    )
    return [SignalResponse.model_validate(s) for s in result.scalars().all()]


@router.get("/opportunities", response_model=list[OpportunityScoreResponse])
async def list_opportunities(
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[OpportunityScoreResponse]:
    result = await session.execute(
        select(OpportunityScore)
        .order_by(desc(OpportunityScore.composite_score))
        .offset(skip)
        .limit(limit)
    )
    return [OpportunityScoreResponse.model_validate(o) for o in result.scalars().all()]
