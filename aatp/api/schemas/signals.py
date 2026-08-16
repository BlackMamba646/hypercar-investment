from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_model_id: uuid.UUID
    signal_type: str
    generated_at: datetime
    strength: Decimal
    direction: int
    confidence: Decimal
    description: str
    supporting_data: dict
    transaction_count: Optional[int]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class OpportunityScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_model_id: uuid.UUID
    scored_at: datetime
    composite_score: Decimal
    signal_count: int
    signal_breakdown: dict
    liquidity_score: Optional[Decimal]
    cost_adjusted_return_pct: Optional[Decimal]
    time_to_catalyst_days: Optional[int]
    rule_flags: Optional[dict]
    status: str
    created_at: datetime
    updated_at: datetime
