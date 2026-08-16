from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ConsensusModelScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    consensus_score_id: uuid.UUID
    model_type: str
    score: int
    confidence: Decimal
    rationale: str
    supporting_data: dict
    created_at: datetime
    updated_at: datetime


class ConsensusScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_model_id: uuid.UUID
    scored_at: datetime
    aggregate_score: int
    has_veto: bool
    veto_model: Optional[str]
    veto_reason: Optional[str]
    status: str
    disagreement_summary: Optional[str]
    actionable: bool
    model_scores: list[ConsensusModelScoreResponse]
    created_at: datetime
    updated_at: datetime
