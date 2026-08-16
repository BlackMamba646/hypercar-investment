from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_type: str
    severity: str
    asset_model_id: Optional[uuid.UUID]
    position_id: Optional[uuid.UUID]
    title: str
    message: str
    data: Optional[dict]
    is_read: bool
    read_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AlertUpdateRequest(BaseModel):
    is_read: bool
