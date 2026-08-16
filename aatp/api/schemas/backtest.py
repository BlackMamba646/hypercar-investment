from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BacktestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    start_date: date
    end_date: date
    parameters: dict
    model_versions: dict
    total_opportunities_flagged: Optional[int]
    actionable_opportunities: Optional[int]
    signal_accuracy_rate: Optional[Decimal]
    avg_return_pct: Optional[Decimal]
    median_return_pct: Optional[Decimal]
    false_positive_rate: Optional[Decimal]
    sharpe_ratio: Optional[Decimal]
    max_drawdown_pct: Optional[Decimal]
    return_distribution: Optional[dict]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class BacktestCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    parameters: dict
    model_versions: dict
