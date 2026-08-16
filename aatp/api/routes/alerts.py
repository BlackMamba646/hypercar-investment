from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.alerts import AlertResponse
from aatp.core.logging import get_logger
from aatp.db.models import Alert, AlertSeverity, AlertType
from aatp.db.session import get_session

logger = get_logger("api.alerts")

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    session: Annotated[AsyncSession, Depends(get_session)],
    alert_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    is_read: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertResponse]:
    query = select(Alert)

    if alert_type is not None:
        query = query.where(Alert.alert_type == AlertType(alert_type))
    if severity is not None:
        query = query.where(Alert.severity == AlertSeverity(severity))
    if is_read is not None:
        query = query.where(Alert.is_read == is_read)

    result = await session.execute(
        query.order_by(desc(Alert.created_at)).offset(skip).limit(limit)
    )
    return [AlertResponse.model_validate(a) for a in result.scalars().all()]


@router.patch("/alerts/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertResponse:
    result = await session.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_read = True
    alert.read_at = datetime.now(timezone.utc)
    await session.commit()
    return AlertResponse.model_validate(alert)
