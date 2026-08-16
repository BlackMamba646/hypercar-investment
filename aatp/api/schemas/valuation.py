from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FairValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_model_id: uuid.UUID
    valuation_date: date
    currency: str
    fair_value_low: Decimal
    fair_value_mid: Decimal
    fair_value_high: Decimal
    confidence_score: Decimal
    comparable_count: int
    comparable_window_months: int
    appreciation_stage: Optional[str]
    appreciation_rate_30d: Optional[Decimal]
    appreciation_rate_90d: Optional[Decimal]
    appreciation_rate_365d: Optional[Decimal]
    methodology: Optional[str]
    warnings: Optional[dict]
    created_at: datetime
    updated_at: datetime
