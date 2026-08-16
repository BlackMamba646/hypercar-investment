from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.api.schemas.catalog import (
    AssetModelListResponse,
    AssetModelResponse,
    ManufacturerResponse,
)
from aatp.core.logging import get_logger
from aatp.db.models import AssetModel, Manufacturer
from aatp.db.session import get_session

logger = get_logger("api.catalog")

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/manufacturers", response_model=list[ManufacturerResponse])
async def list_manufacturers(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ManufacturerResponse]:
    result = await session.execute(
        select(Manufacturer).order_by(Manufacturer.name)
    )
    return [ManufacturerResponse.model_validate(m) for m in result.scalars().all()]


@router.get("/models", response_model=AssetModelListResponse)
async def list_models(
    session: Annotated[AsyncSession, Depends(get_session)],
    manufacturer_id: uuid.UUID | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> AssetModelListResponse:
    query = select(AssetModel)
    count_query = select(func.count()).select_from(AssetModel)

    if manufacturer_id is not None:
        query = query.where(AssetModel.manufacturer_id == manufacturer_id)
        count_query = count_query.where(AssetModel.manufacturer_id == manufacturer_id)

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    result = await session.execute(query.offset(skip).limit(limit))
    items = [AssetModelResponse.model_validate(m) for m in result.scalars().all()]

    return AssetModelListResponse(items=items, total=total)


@router.get("/models/{model_id}", response_model=AssetModelResponse)
async def get_model(
    model_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssetModelResponse:
    result = await session.execute(
        select(AssetModel).where(AssetModel.id == model_id)
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return AssetModelResponse.model_validate(model)
