from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.backtest import BacktestCreateRequest, BacktestRunResponse
from aatp.core.logging import get_logger
from aatp.db.models import BacktestRun
from aatp.db.session import get_session

logger = get_logger("api.backtest")

router = APIRouter(prefix="/api/v1", tags=["backtest"])


@router.post("/backtest", response_model=BacktestRunResponse, status_code=201)
async def create_backtest(
    body: BacktestCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BacktestRunResponse:
    run = BacktestRun(
        name=body.name,
        description=body.description,
        start_date=body.start_date,
        end_date=body.end_date,
        parameters=body.parameters,
        model_versions=body.model_versions,
        status="pending",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return BacktestRunResponse.model_validate(run)


@router.get("/backtest/{run_id}", response_model=BacktestRunResponse)
async def get_backtest_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BacktestRunResponse:
    result = await session.execute(
        select(BacktestRun).where(BacktestRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return BacktestRunResponse.model_validate(run)
