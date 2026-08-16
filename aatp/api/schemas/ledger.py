from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_model_id: uuid.UUID
    asset_class: str
    status: str
    identifier: Optional[str]
    year: Optional[int]
    description: str
    colour_exterior: Optional[str]
    colour_interior: Optional[str]
    mileage_at_acquisition: Optional[int]
    acquisition_date: date
    acquisition_price: Decimal
    acquisition_currency: str
    acquisition_price_usd: Decimal
    acquisition_channel: str
    exit_date: Optional[date]
    exit_price: Optional[Decimal]
    exit_price_usd: Optional[Decimal]
    exit_channel: Optional[str]
    current_fair_value_usd: Optional[Decimal]
    fair_value_date: Optional[date]
    total_cost_basis: Optional[Decimal]
    unrealised_pnl: Optional[Decimal]
    realised_pnl: Optional[Decimal]
    irr: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class PositionCreateRequest(BaseModel):
    asset_model_id: uuid.UUID
    description: str
    acquisition_date: date
    acquisition_price: Decimal
    acquisition_price_usd: Decimal
    acquisition_channel: str
    acquisition_currency: str = "USD"
    asset_class: str = "car"
    identifier: Optional[str] = None
    year: Optional[int] = None
    colour_exterior: Optional[str] = None
    colour_interior: Optional[str] = None
    mileage_at_acquisition: Optional[int] = None
    notes: Optional[str] = None


class PositionExitRequest(BaseModel):
    exit_date: date
    exit_price: Decimal
    exit_price_usd: Decimal
    exit_channel: str
    exit_currency: str = "USD"


class CostEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position_id: uuid.UUID
    cost_category: str
    cost_date: date
    amount: Decimal
    currency: str
    amount_usd: Decimal
    description: str
    vendor: Optional[str]
    invoice_reference: Optional[str]
    is_recurring: bool
    created_at: datetime
    updated_at: datetime


class PortfolioSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    snapshot_date: date
    total_market_value_usd: Decimal
    total_cost_basis_usd: Decimal
    total_unrealised_pnl_usd: Decimal
    total_realised_pnl_usd: Decimal
    portfolio_irr: Optional[Decimal]
    open_positions_count: int
    capital_deployed_usd: Decimal
    available_capital_usd: Optional[Decimal]
    position_breakdown: dict
    created_at: datetime
