from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aatp.api.schemas.common import MessageResponse
from aatp.api.schemas.consensus import ConsensusScoreResponse
from aatp.core.logging import get_logger
from aatp.db.models import ConsensusScore
from aatp.db.session import get_session

logger = get_logger("api.consensus")

router = APIRouter(prefix="/api/v1", tags=["consensus"])


@router.get("/consensus/{model_id}", response_model=ConsensusScoreResponse)
async def get_latest_consensus(
    model_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConsensusScoreResponse:
    result = await session.execute(
        select(ConsensusScore)
        .where(ConsensusScore.asset_model_id == model_id)
        .options(selectinload(ConsensusScore.model_scores))
        .order_by(ConsensusScore.scored_at.desc())
        .limit(1)
    )
    consensus = result.scalar_one_or_none()
    if consensus is None:
        raise HTTPException(status_code=404, detail="No consensus score found for this model")
    return ConsensusScoreResponse.model_validate(consensus)


@router.post("/consensus/run", response_model=MessageResponse, status_code=202)
async def run_consensus() -> MessageResponse:
    from aatp.consensus.tasks import run_consensus_scan

    run_consensus_scan.delay()
    return MessageResponse(message="Consensus scan queued")
