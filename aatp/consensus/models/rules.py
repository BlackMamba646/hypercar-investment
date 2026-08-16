"""Rules / regulatory consensus model.

Scores an asset -2 to +2 based on import eligibility,
regulatory considerations, and rule model flags.
"""

from __future__ import annotations

from aatp.core.logging import get_logger

logger = get_logger("consensus.rules")


def score_rules(
    active_rule_flags: int,
    positive_flag_count: int,
    negative_flag_count: int,
    has_import_eligibility_soon: bool,
) -> tuple[int, str, dict]:
    """Score rules/regulatory environment from -2 to +2.

    Parameters
    ----------
    active_rule_flags : Total number of active rule flags for this asset.
    positive_flag_count : Number of positive rule flags (e.g. becoming eligible).
    negative_flag_count : Number of negative rule flags (e.g. regulatory blockers).
    has_import_eligibility_soon : Whether the asset will become import-eligible
        within the next 24 months (US 25-year rule).

    Returns
    -------
    tuple of (score, rationale, supporting_data)
    """
    supporting_data: dict = {
        "active_rule_flags": active_rule_flags,
        "positive_flag_count": positive_flag_count,
        "negative_flag_count": negative_flag_count,
        "has_import_eligibility_soon": has_import_eligibility_soon,
    }

    # No flags at all => neutral
    if active_rule_flags == 0 and not has_import_eligibility_soon:
        return 0, "No active regulatory flags", supporting_data

    reasons: list[str] = []
    points = 0

    # Negative flags are more impactful
    if negative_flag_count >= 2:
        points -= 2
        reasons.append(f"{negative_flag_count} negative regulatory flags (potential blockers)")
    elif negative_flag_count == 1:
        points -= 1
        reasons.append("1 negative regulatory flag")

    # Positive flags
    if positive_flag_count >= 2:
        points += 1
        reasons.append(f"{positive_flag_count} positive regulatory flags")
    elif positive_flag_count == 1:
        points += 1
        reasons.append("1 positive regulatory flag")

    # Import eligibility is a strong positive catalyst
    if has_import_eligibility_soon:
        points += 2
        reasons.append("25-year import eligibility approaching (strong catalyst)")

    # Clamp to -2..+2
    score = max(-2, min(2, points))
    rationale = "Rules: " + "; ".join(reasons) if reasons else "Rules: neutral"

    return score, rationale, supporting_data
