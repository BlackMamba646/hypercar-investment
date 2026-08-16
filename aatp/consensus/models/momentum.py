"""Momentum consensus model.

Scores an asset -2 to +2 based on price trend and acceleration
derived from FairValue appreciation rates and Signal data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("consensus.momentum")

# Annualised appreciation thresholds
STRONG_UPTREND_PCT = Decimal("0.20")   # >20% annualised => +2
MODERATE_UPTREND_PCT = Decimal("0.05")  # >5% annualised => +1
MODERATE_DECLINE_PCT = Decimal("-0.05")  # <-5% annualised => -1
CRASH_PCT = Decimal("-0.20")            # <-20% annualised => -2


def score_momentum(
    appreciation_rate_90d: Optional[Decimal],
    appreciation_rate_365d: Optional[Decimal],
    has_momentum_signal: bool,
    signal_direction: Optional[int],
) -> tuple[int, str, dict]:
    """Score an asset's price momentum from -2 to +2.

    Parameters
    ----------
    appreciation_rate_90d : 90-day annualised appreciation rate (e.g. 0.15 = 15%).
    appreciation_rate_365d : 365-day annualised appreciation rate.
    has_momentum_signal : Whether the signal engine has flagged a momentum signal.
    signal_direction : Direction of the momentum signal (-1, 0, +1).

    Returns
    -------
    tuple of (score, rationale, supporting_data)
    """
    supporting_data: dict = {
        "appreciation_rate_90d": str(appreciation_rate_90d) if appreciation_rate_90d is not None else None,
        "appreciation_rate_365d": str(appreciation_rate_365d) if appreciation_rate_365d is not None else None,
        "has_momentum_signal": has_momentum_signal,
        "signal_direction": signal_direction,
    }

    # If we have no appreciation data, score neutral
    if appreciation_rate_90d is None and appreciation_rate_365d is None:
        return 0, "Insufficient data to assess momentum", supporting_data

    # Use 365d as primary, 90d as secondary/confirmation
    primary = appreciation_rate_365d if appreciation_rate_365d is not None else appreciation_rate_90d
    secondary = appreciation_rate_90d if appreciation_rate_365d is not None else None

    score = 0

    # Primary trend classification
    if primary >= STRONG_UPTREND_PCT:
        score = 2
        rationale = f"Strong uptrend: {_pct(primary)} annualised appreciation"
    elif primary >= MODERATE_UPTREND_PCT:
        score = 1
        rationale = f"Moderate uptrend: {_pct(primary)} annualised appreciation"
    elif primary > MODERATE_DECLINE_PCT:
        score = 0
        rationale = f"Flat trend: {_pct(primary)} annualised appreciation"
    elif primary > CRASH_PCT:
        score = -1
        rationale = f"Declining trend: {_pct(primary)} annualised appreciation"
    else:
        score = -2
        rationale = f"Crash-level decline: {_pct(primary)} annualised appreciation"

    # Momentum signal can nudge score by 1 in either direction (clamped to -2..+2)
    if has_momentum_signal and signal_direction is not None and signal_direction != 0:
        # Only nudge if signal confirms or contradicts trend
        if signal_direction > 0 and score < 2:
            score += 1
            rationale += "; momentum signal confirms upward trend"
        elif signal_direction < 0 and score > -2:
            score -= 1
            rationale += "; momentum signal confirms downward trend"

    # Acceleration check: if 90d is significantly different from 365d, note it
    if secondary is not None and primary is not None and primary != Decimal("0"):
        acceleration = secondary - primary
        supporting_data["acceleration"] = str(acceleration)
        if acceleration > Decimal("0.10"):
            rationale += "; accelerating appreciation in recent quarter"
        elif acceleration < Decimal("-0.10"):
            rationale += "; decelerating appreciation in recent quarter"

    # Clamp to valid range
    score = max(-2, min(2, score))

    return score, rationale, supporting_data


def _pct(value: Decimal) -> str:
    """Format a decimal as a percentage string."""
    return f"{float(value) * 100:.1f}%"
