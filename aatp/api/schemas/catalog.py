from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ManufacturerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: Optional[str]
    asset_class: str
    prestige_score: Optional[Decimal]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class AssetModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    manufacturer_id: uuid.UUID
    asset_class: str
    name: str
    variant: Optional[str]
    production_year_start: Optional[int]
    production_year_end: Optional[int]
    total_produced: Optional[int]
    estimated_liquid_supply: Optional[int]
    known_destroyed: Optional[int]
    known_museum_held: Optional[int]
    is_open_top: bool
    is_limited_edition: bool
    is_invitation_only: bool
    engine_type: Optional[str]
    engine_config: Optional[str]
    msrp_at_launch: Optional[Decimal]
    msrp_currency: Optional[str]
    homologation_type: Optional[str]
    variant_scarcity_multiplier: Optional[Decimal]
    appreciation_stage: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class AssetModelListResponse(BaseModel):
    items: list[AssetModelResponse]
    total: int
