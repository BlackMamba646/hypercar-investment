from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import LedgerEntry

logger = get_logger("ledger.ledger_service")


async def record_entry(
    session: AsyncSession,
    position_id: uuid.UUID,
    entry_type: str,
    amount: Decimal,
    description: str,
    currency: str = "USD",
    amount_usd: Optional[Decimal] = None,
    created_by: Optional[str] = None,
) -> LedgerEntry:
    """Create an immutable ledger entry.

    If *amount_usd* is not supplied it defaults to *amount* (assumes USD).
    """
    entry = LedgerEntry(
        position_id=position_id,
        entry_date=datetime.now(timezone.utc),
        entry_type=entry_type,
        amount=amount,
        currency=currency,
        amount_usd=amount_usd if amount_usd is not None else amount,
        description=description,
        is_correction=False,
        created_by=created_by,
    )
    session.add(entry)
    await session.flush()
    logger.info(
        "ledger_entry_recorded",
        entry_id=str(entry.id),
        position_id=str(position_id),
        entry_type=entry_type,
        amount_usd=str(entry.amount_usd),
    )
    return entry


async def correct_entry(
    session: AsyncSession,
    original_entry_id: uuid.UUID,
    corrected_amount: Decimal,
    reason: str,
    currency: str = "USD",
    corrected_amount_usd: Optional[Decimal] = None,
    created_by: Optional[str] = None,
) -> LedgerEntry:
    """Create a correction entry that references the original.

    The correction entry records the *corrected_amount* (typically the
    negative/reversed value) and links back via ``corrects_entry_id``.
    """
    result = await session.execute(
        select(LedgerEntry).where(LedgerEntry.id == original_entry_id)
    )
    original = result.scalar_one()

    correction = LedgerEntry(
        position_id=original.position_id,
        entry_date=datetime.now(timezone.utc),
        entry_type=f"correction:{original.entry_type}",
        amount=corrected_amount,
        currency=currency,
        amount_usd=corrected_amount_usd if corrected_amount_usd is not None else corrected_amount,
        description=reason,
        corrects_entry_id=original_entry_id,
        is_correction=True,
        created_by=created_by,
    )
    session.add(correction)
    await session.flush()
    logger.info(
        "ledger_entry_corrected",
        correction_id=str(correction.id),
        original_id=str(original_entry_id),
        corrected_amount_usd=str(correction.amount_usd),
    )
    return correction


async def get_position_ledger(
    session: AsyncSession,
    position_id: uuid.UUID,
) -> List[LedgerEntry]:
    """Return all effective ledger entries for a position.

    Entries that have been superseded by a correction are excluded.
    Correction entries themselves are included so the audit trail is visible.
    """
    # First find entry IDs that have been corrected
    corrected_subq = (
        select(LedgerEntry.corrects_entry_id)
        .where(
            LedgerEntry.position_id == position_id,
            LedgerEntry.is_correction.is_(True),
            LedgerEntry.corrects_entry_id.isnot(None),
        )
        .scalar_subquery()
    )

    result = await session.execute(
        select(LedgerEntry)
        .where(
            LedgerEntry.position_id == position_id,
            LedgerEntry.id.notin_(corrected_subq),
        )
        .order_by(LedgerEntry.entry_date)
    )
    return list(result.scalars().all())
