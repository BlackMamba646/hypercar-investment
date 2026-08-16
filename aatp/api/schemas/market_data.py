from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provenance_id: uuid.UUID
    asset_model_id: uuid.UUID
    asset_class: str
    source: str
    external_id: Optional[str]
    transaction_type: str
    transaction_date: date
    hammer_price: Optional[Decimal]
    buyer_premium: Optional[Decimal]
    total_price: Optional[Decimal]
    currency: str
    total_price_usd: Optional[Decimal]
    year: Optional[int]
    mileage: Optional[int]
    mileage_unit: Optional[str]
    colour_exterior: Optional[str]
    colour_interior: Optional[str]
    colour_tier: Optional[int]
    condition_grade: Optional[str]
    normalised_price_usd: Optional[Decimal]
    sale_country: Optional[str]
    auction_house: Optional[str]
    dealer_name: Optional[str]
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
