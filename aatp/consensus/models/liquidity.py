"""Liquidity consensus model.

Scores an asset -2 to +2 based on ability to exit within target timeframe.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("consensus.liquidity")

# Thresholds
HIGH_TRANSACTION_COUNT_12M = 10    # 10+ transactions in 12 months => very liquid
MODERATE_TRANSACTION_COUNT_12M = 5  # 5+ => moderate
LOW_TRANSACTION_COUNT_12M = 2      # 2+ => thin
MULTI_SOURCE_THRESHOLD = 3         # 3+ distinct sources => diversified exit channels
FAST_DAYS_ON_MARKET = 30           # Average < 30 days => quick turnover
SLOW_DAYS_ON_MARKET = 180          # Average > 180 days => illiquid


def score_liquidity(
    transaction_count_12m: int,
    transaction_count_6m: int,
    distinct_sources: int,
    avg_days_on_market: Optional[int],
) -> tuple[int, str, dict]:
    """Score liquidity from -2 to +2.

    Parameters
    ----------
    transaction_count_12m : Number of comparable transactions in the last 12 months.
    transaction_count_6m : Number of comparable transactions in the last 6 months.
    distinct_sources : Number of distinct sale sources/channels observed.
    avg_days_on_market : Average days on market for dealer listings (None if no data).

    Returns
    -------
    tuple of (score, rationale, supporting_data)
    """
    supporting_data: dict = {
        "transaction_count_12m": transaction_count_12m,
        "transaction_count_6m": transaction_count_6m,
        "distinct_sources": distinct_sources,
        "avg_days_on_market": avg_days_on_market,
    }

    # No transactions in 12 months => illiquid
    if transaction_count_12m == 0:
        return -2, "No comparable transactions in 12 months; exit risk is extreme", supporting_data

    reasons: list[str] = []
    points = 0

    # Volume assessment (up to 2 points)
    if transaction_count_12m >= HIGH_TRANSACTION_COUNT_12M:
        points += 2
        reasons.append(f"high volume ({transaction_count_12m} transactions in 12m)")
    elif transaction_count_12m >= MODERATE_TRANSACTION_COUNT_12M:
        points += 1
        reasons.append(f"moderate volume ({transaction_count_12m} transactions in 12m)")
    elif transaction_count_12m >= LOW_TRANSACTION_COUNT_12M:
        points += 0
        reasons.append(f"thin volume ({transaction_count_12m} transactions in 12m)")
    else:
        points -= 1
        reasons.append(f"very thin volume (only {transaction_count_12m} transaction in 12m)")

    # Recent velocity: compare 6m to 12m
    if transaction_count_12m > 0:
        recent_ratio = transaction_count_6m / transaction_count_12m
        supporting_data["recent_velocity_ratio"] = round(recent_ratio, 2)
        if recent_ratio > 0.6:
            points += 1
            reasons.append("accelerating recent activity")
        elif recent_ratio < 0.3 and transaction_count_12m >= MODERATE_TRANSACTION_COUNT_12M:
            points -= 1
            reasons.append("declining recent activity")

    # Exit channel diversity
    if distinct_sources >= MULTI_SOURCE_THRESHOLD:
        points += 1
        reasons.append(f"multiple exit channels ({distinct_sources} sources)")
    elif distinct_sources <= 1:
        points -= 1
        reasons.append("limited exit channels (single source)")

    # Days on market
    if avg_days_on_market is not None:
        if avg_days_on_market <= FAST_DAYS_ON_MARKET:
            points += 1
            reasons.append(f"quick turnover (avg {avg_days_on_market} days on market)")
        elif avg_days_on_market >= SLOW_DAYS_ON_MARKET:
            points -= 1
            reasons.append(f"slow turnover (avg {avg_days_on_market} days on market)")

    # Clamp to -2..+2
    score = max(-2, min(2, points))
    rationale = "Liquidity: " + "; ".join(reasons)

    return score, rationale, supporting_data
