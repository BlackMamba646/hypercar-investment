"""Macro consensus model.

Scores -2 to +2 based on macroeconomic indicators relevant to
the luxury collectible asset market.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("consensus.macro")

# Trend values: positive = up, negative = down (percentage change over period)
STRONG_POSITIVE_TREND = Decimal("0.05")   # >5% growth
MILD_POSITIVE_TREND = Decimal("0.01")     # >1% growth
MILD_NEGATIVE_TREND = Decimal("-0.01")    # <-1% decline
STRONG_NEGATIVE_TREND = Decimal("-0.05")  # <-5% decline


def score_macro(
    luxury_index_trend: Optional[Decimal],
    interest_rate_trend: Optional[Decimal],
    wealth_indicator_trend: Optional[Decimal],
) -> tuple[int, str, dict]:
    """Score macro environment from -2 to +2.

    Parameters
    ----------
    luxury_index_trend : Trend of the luxury/collectible index (e.g. +0.08 = 8% up).
    interest_rate_trend : Trend of interest rates (positive = rates rising, bad for assets).
    wealth_indicator_trend : Trend of wealth/HNWI indicator (positive = growing wealth).

    Returns
    -------
    tuple of (score, rationale, supporting_data)
    """
    supporting_data: dict = {
        "luxury_index_trend": str(luxury_index_trend) if luxury_index_trend is not None else None,
        "interest_rate_trend": str(interest_rate_trend) if interest_rate_trend is not None else None,
        "wealth_indicator_trend": str(wealth_indicator_trend) if wealth_indicator_trend is not None else None,
    }

    # If no macro data, score neutral
    if luxury_index_trend is None and interest_rate_trend is None and wealth_indicator_trend is None:
        return 0, "Insufficient macro data", supporting_data

    reasons: list[str] = []
    points = 0

    # Luxury index trend (primary indicator)
    if luxury_index_trend is not None:
        if luxury_index_trend >= STRONG_POSITIVE_TREND:
            points += 2
            reasons.append(f"luxury index strongly up ({_pct(luxury_index_trend)})")
        elif luxury_index_trend >= MILD_POSITIVE_TREND:
            points += 1
            reasons.append(f"luxury index up ({_pct(luxury_index_trend)})")
        elif luxury_index_trend <= STRONG_NEGATIVE_TREND:
            points -= 2
            reasons.append(f"luxury index sharply down ({_pct(luxury_index_trend)})")
        elif luxury_index_trend <= MILD_NEGATIVE_TREND:
            points -= 1
            reasons.append(f"luxury index down ({_pct(luxury_index_trend)})")
        else:
            reasons.append(f"luxury index flat ({_pct(luxury_index_trend)})")

    # Interest rate trend (inverted: rising rates = negative for asset prices)
    if interest_rate_trend is not None:
        if interest_rate_trend <= STRONG_NEGATIVE_TREND:
            points += 1
            reasons.append(f"rates falling sharply ({_pct(interest_rate_trend)}), tailwind")
        elif interest_rate_trend <= MILD_NEGATIVE_TREND:
            points += 1
            reasons.append(f"rates falling ({_pct(interest_rate_trend)}), mild tailwind")
        elif interest_rate_trend >= STRONG_POSITIVE_TREND:
            points -= 1
            reasons.append(f"rates rising sharply ({_pct(interest_rate_trend)}), headwind")
        elif interest_rate_trend >= MILD_POSITIVE_TREND:
            points -= 1
            reasons.append(f"rates rising ({_pct(interest_rate_trend)}), mild headwind")
        else:
            reasons.append("rates stable")

    # Wealth indicator trend
    if wealth_indicator_trend is not None:
        if wealth_indicator_trend >= STRONG_POSITIVE_TREND:
            points += 1
            reasons.append(f"wealth indicator strongly up ({_pct(wealth_indicator_trend)})")
        elif wealth_indicator_trend >= MILD_POSITIVE_TREND:
            # Mild positive wealth doesn't add a point but is noted
            reasons.append(f"wealth indicator up ({_pct(wealth_indicator_trend)})")
        elif wealth_indicator_trend <= STRONG_NEGATIVE_TREND:
            points -= 1
            reasons.append(f"wealth indicator sharply down ({_pct(wealth_indicator_trend)})")
        elif wealth_indicator_trend <= MILD_NEGATIVE_TREND:
            reasons.append(f"wealth indicator down ({_pct(wealth_indicator_trend)})")

    # Clamp to -2..+2
    score = max(-2, min(2, points))
    rationale = "Macro: " + "; ".join(reasons) if reasons else "Macro: neutral"

    return score, rationale, supporting_data


def _pct(value: Decimal) -> str:
    """Format a decimal as a percentage string."""
    return f"{float(value) * 100:.1f}%"
