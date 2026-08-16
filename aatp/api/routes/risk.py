from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.risk import PortfolioRiskSnapshotResponse, RiskAssessmentResponse
from aatp.core.logging import get_logger
from aatp.db.models import PortfolioRiskSnapshot, RiskAssessment
from aatp.db.session import get_session

logger = get_logger("api.risk")

router = APIRouter(prefix="/api/v1", tags=["risk"])


@router.get("/risk/positions/{position_id}", response_model=RiskAssessmentResponse)
async def get_position_risk(
    position_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RiskAssessmentResponse:
    result = await session.execute(
        select(RiskAssessment)
        .where(RiskAssessment.position_id == position_id)
        .order_by(RiskAssessment.assessed_at.desc())
        .limit(1)
    )
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=404, detail="No risk assessment found for this position")
    return RiskAssessmentResponse.model_validate(assessment)


@router.get("/risk/portfolio", response_model=PortfolioRiskSnapshotResponse)
async def get_portfolio_risk(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PortfolioRiskSnapshotResponse:
    result = await session.execute(
        select(PortfolioRiskSnapshot)
        .order_by(PortfolioRiskSnapshot.snapshot_date.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No portfolio risk snapshot found")
    return PortfolioRiskSnapshotResponse.model_validate(snapshot)
