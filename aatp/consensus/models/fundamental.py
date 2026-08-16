"""Fundamental value consensus model.

Scores an asset -2 to +2 based on fair value vs current market price.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("consensus.fundamental")

# Undervaluation / overvaluation thresholds
STRONG_UNDERVALUED_PCT = Decimal("0.15")   # >15% undervalued => +2
MODERATE_UNDERVALUED_PCT = Decimal("0.05")  # 5-15% undervalued => +1
MODERATE_OVERVALUED_PCT = Decimal("-0.05")  # 5-15% overvalued => -1
STRONG_OVERVALUED_PCT = Decimal("-0.15")   # >15% overvalued => -2


def score_fundamental(
    fair_value_mid: Optional[Decimal],
    latest_transaction_price: Optional[Decimal],
    confidence: Optional[Decimal],
) -> tuple[int, str, dict]:
    """Score fundamental value from -2 to +2.

    Parameters
    ----------
    fair_value_mid : Mid-point fair value estimate in USD.
    latest_transaction_price : Most recent comparable transaction price in USD.
    confidence : Confidence score of the fair value estimate (0-1).

    Returns
    -------
    tuple of (score, rationale, supporting_data)
    """
    supporting_data: dict = {
        "fair_value_mid": str(fair_value_mid) if fair_value_mid is not None else None,
        "latest_transaction_price": str(latest_transaction_price) if latest_transaction_price is not None else None,
        "confidence": str(confidence) if confidence is not None else None,
    }

    if fair_value_mid is None or latest_transaction_price is None:
        return 0, "Insufficient data for fundamental valuation", supporting_data

    if fair_value_mid <= Decimal("0") or latest_transaction_price <= Decimal("0"):
        return 0, "Invalid price data for fundamental valuation", supporting_data

    # discount_pct > 0 means undervalued (price below fair value)
    discount_pct = (fair_value_mid - latest_transaction_price) / fair_value_mid
    supporting_data["discount_pct"] = str(discount_pct)

    if discount_pct > STRONG_UNDERVALUED_PCT:
        score = 2
        rationale = f"Strongly undervalued: market price {_pct(discount_pct)} below fair value"
    elif discount_pct > MODERATE_UNDERVALUED_PCT:
        score = 1
        rationale = f"Moderately undervalued: market price {_pct(discount_pct)} below fair value"
    elif discount_pct >= MODERATE_OVERVALUED_PCT:
        score = 0
        rationale = f"Fairly valued: market price within {_pct(abs(discount_pct))} of fair value"
    elif discount_pct >= STRONG_OVERVALUED_PCT:
        score = -1
        rationale = f"Moderately overvalued: market price {_pct(abs(discount_pct))} above fair value"
    else:
        score = -2
        rationale = f"Strongly overvalued: market price {_pct(abs(discount_pct))} above fair value"

    # Low confidence degrades the score toward neutral
    if confidence is not None and confidence < Decimal("0.5"):
        supporting_data["confidence_adjustment"] = True
        if score > 0:
            score -= 1
            rationale += f"; score reduced due to low confidence ({_pct(confidence)})"
        elif score < 0:
            score += 1
            rationale += f"; score moved toward neutral due to low confidence ({_pct(confidence)})"

    return score, rationale, supporting_data


def _pct(value: Decimal) -> str:
    """Format a decimal as a percentage string."""
    return f"{float(value) * 100:.1f}%"
