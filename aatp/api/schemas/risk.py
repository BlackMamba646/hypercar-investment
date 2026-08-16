from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RiskAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position_id: uuid.UUID
    assessed_at: datetime
    liquidity_risk_score: Decimal
    concentration_risk_score: Decimal
    physical_risk_score: Decimal
    counterparty_risk_score: Decimal
    spec_risk_score: Decimal
    provenance_risk_score: Decimal
    composite_risk_score: Decimal
    risk_explanation: str
    risk_factors: dict
    recommendations: Optional[dict]
    created_at: datetime
    updated_at: datetime


class PortfolioRiskSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    snapshot_date: date
    manufacturer_concentration: dict
    era_concentration: dict
    type_concentration: dict
    max_manufacturer_exposure_pct: Decimal
    total_illiquid_90d_pct: Decimal
    scenario_analysis: dict
    warnings: Optional[dict]
    narrative: str
    created_at: datetime
    updated_at: datetime
