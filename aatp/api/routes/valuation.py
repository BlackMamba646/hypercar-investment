from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.common import MessageResponse
from aatp.api.schemas.valuation import FairValueResponse
from aatp.core.logging import get_logger
from aatp.db.models import FairValue
from aatp.db.session import get_session

logger = get_logger("api.valuation")

router = APIRouter(prefix="/api/v1", tags=["valuation"])


@router.get("/fair-values/{model_id}", response_model=FairValueResponse)
async def get_latest_fair_value(
    model_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FairValueResponse:
    result = await session.execute(
        select(FairValue)
        .where(FairValue.asset_model_id == model_id)
        .order_by(FairValue.valuation_date.desc())
        .limit(1)
    )
    fair_value = result.scalar_one_or_none()
    if fair_value is None:
        raise HTTPException(status_code=404, detail="No fair value found for this model")
    return FairValueResponse.model_validate(fair_value)


@router.post("/fair-values/refresh", response_model=MessageResponse, status_code=202)
async def refresh_fair_values() -> MessageResponse:
    from aatp.valuation.tasks import run_valuation

    run_valuation.delay()
    return MessageResponse(message="Valuation refresh queued")
