from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.market_data import TransactionListResponse, TransactionResponse
from aatp.core.logging import get_logger
from aatp.db.models import Transaction
from aatp.db.session import get_session

logger = get_logger("api.market_data")

router = APIRouter(prefix="/api/v1", tags=["market_data"])


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    session: Annotated[AsyncSession, Depends(get_session)],
    model_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> TransactionListResponse:
    query = select(Transaction)
    count_query = select(func.count()).select_from(Transaction)

    if model_id is not None:
        query = query.where(Transaction.asset_model_id == model_id)
        count_query = count_query.where(Transaction.asset_model_id == model_id)

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    result = await session.execute(
        query.order_by(desc(Transaction.transaction_date)).offset(skip).limit(limit)
    )
    items = [TransactionResponse.model_validate(t) for t in result.scalars().all()]

    return TransactionListResponse(items=items, total=total)


@router.get("/transactions/{model_id}", response_model=list[TransactionResponse])
async def get_transactions_for_model(
    model_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[TransactionResponse]:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.asset_model_id == model_id)
        .order_by(desc(Transaction.transaction_date))
        .offset(skip)
        .limit(limit)
    )
    return [TransactionResponse.model_validate(t) for t in result.scalars().all()]
