from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import Transaction, TransactionType

logger = get_logger("valuation.comparable")

SOLD_TYPES = {
    TransactionType.AUCTION_SOLD,
    TransactionType.DEALER_SOLD,
    TransactionType.PRIVATE_SALE,
}


@dataclass
class ComparableResult:
    fair_value_low: Decimal
    fair_value_mid: Decimal
    fair_value_high: Decimal
    confidence_score: Decimal
    comparable_count: int
    comparable_window_months: int
    comparable_transaction_ids: list[str]
    warnings: list[str] = field(default_factory=list)


class ComparableTransactionModel:

    def __init__(
        self,
        session: AsyncSession,
        lookback_months: int = 12,
        half_life_days: int = 90,
        min_comparables: int = 3,
    ):
        self.db = session
        self.lookback_months = lookback_months
        self.half_life_days = half_life_days
        self.min_comparables = min_comparables

    async def compute(
        self,
        asset_model_id: uuid.UUID,
        valuation_date: date,
    ) -> Optional[ComparableResult]:
        window_months = self.lookback_months
        transactions = await self._fetch_comparables(
            asset_model_id, valuation_date, window_months
        )

        if len(transactions) < self.min_comparables:
            wider = window_months * 2
            transactions = await self._fetch_comparables(
                asset_model_id, valuation_date, wider
            )
            window_months = wider

        if len(transactions) < self.min_comparables:
            return None

        prices, weights = self._build_weighted_arrays(transactions, valuation_date)
        low, mid, high = weighted_percentiles(prices, weights, [25, 50, 75])
        confidence = self._confidence_score(prices, weights, transactions, valuation_date)
        warnings = self._generate_warnings(prices, transactions, window_months)

        tx_ids = [str(tx.id) for tx in transactions]

        return ComparableResult(
            fair_value_low=Decimal(str(round(low, 2))),
            fair_value_mid=Decimal(str(round(mid, 2))),
            fair_value_high=Decimal(str(round(high, 2))),
            confidence_score=Decimal(str(round(confidence, 3))),
            comparable_count=len(transactions),
            comparable_window_months=window_months,
            comparable_transaction_ids=tx_ids,
            warnings=warnings,
        )

    async def _fetch_comparables(
        self,
        asset_model_id: uuid.UUID,
        valuation_date: date,
        window_months: int,
    ) -> list[Transaction]:
        cutoff = valuation_date - timedelta(days=window_months * 30)
        stmt = (
            select(Transaction)
            .where(
                and_(
                    Transaction.asset_model_id == asset_model_id,
                    Transaction.transaction_type.in_(SOLD_TYPES),
                    Transaction.normalised_price_usd.isnot(None),
                    Transaction.transaction_date >= cutoff,
                    Transaction.transaction_date <= valuation_date,
                )
            )
            .order_by(Transaction.transaction_date.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _build_weighted_arrays(
        self, transactions: list[Transaction], valuation_date: date
    ) -> tuple[np.ndarray, np.ndarray]:
        prices = []
        weights = []
        decay = math.log(2) / self.half_life_days

        for tx in transactions:
            prices.append(float(tx.normalised_price_usd))
            days_ago = (valuation_date - tx.transaction_date).days
            weights.append(math.exp(-decay * days_ago))

        return np.array(prices), np.array(weights)

    def _confidence_score(
        self,
        prices: np.ndarray,
        weights: np.ndarray,
        transactions: list[Transaction],
        valuation_date: date,
    ) -> float:
        count_score = min(len(prices) / 10.0, 1.0)

        days = [(valuation_date - tx.transaction_date).days for tx in transactions]
        most_recent = min(days) if days else 365
        recency_score = max(0, 1.0 - most_recent / 180.0)

        mean = float(np.average(prices, weights=weights))
        if mean > 0:
            std = float(np.sqrt(np.average((prices - mean) ** 2, weights=weights)))
            cv = std / mean
        else:
            cv = 1.0
        dispersion_score = max(0, 1.0 - cv)

        sources = {tx.source for tx in transactions}
        source_diversity = min(len(sources) / 2.0, 1.0)

        confidence = (
            count_score * 0.35
            + recency_score * 0.25
            + dispersion_score * 0.25
            + source_diversity * 0.15
        )
        return max(0.0, min(1.0, confidence))

    def _generate_warnings(
        self,
        prices: np.ndarray,
        transactions: list[Transaction],
        window_months: int,
    ) -> list[str]:
        warnings = []

        if len(prices) < 5:
            warnings.append(
                f"Only {len(prices)} comparables in {window_months} months"
            )

        if window_months > 12:
            warnings.append(
                f"Window widened to {window_months} months due to insufficient data"
            )

        mean = float(np.mean(prices))
        if mean > 0:
            cv = float(np.std(prices) / mean)
            if cv > 0.30:
                warnings.append(
                    f"Price dispersion {cv:.0%} — consider spec-specific valuation"
                )

        sources = {tx.source for tx in transactions}
        if len(sources) == 1:
            warnings.append(
                f"All comparables from single source: {sources.pop().value}"
            )

        return warnings


def weighted_percentiles(
    values: np.ndarray,
    weights: np.ndarray,
    percentiles: list[float],
) -> list[float]:
    sort_idx = np.argsort(values)
    sorted_vals = values[sort_idx]
    sorted_weights = weights[sort_idx]

    cum_weights = np.cumsum(sorted_weights)
    total = cum_weights[-1]

    results = []
    for p in percentiles:
        threshold = p / 100.0 * total
        idx = np.searchsorted(cum_weights, threshold)
        idx = min(idx, len(sorted_vals) - 1)
        results.append(float(sorted_vals[idx]))

    return results
