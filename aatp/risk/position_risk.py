"""Position-level risk assessment -- six risk dimensions scored 0.0 to 1.0.

Each scoring function is pure (no DB access) and returns a tuple of
(score, explanation) where score is a Decimal in [0, 1] and explanation
is a human-readable string describing the risk level.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("risk.position_risk")

# ---------------------------------------------------------------------------
# Constants / thresholds
# ---------------------------------------------------------------------------

# Liquidity
LIQUID_TX_12M = 6          # >= 6 sales in 12 months is highly liquid
ILLIQUID_DAYS = 365        # No sale in 365 days = max illiquidity
MODERATE_DAYS = 180        # 180+ days since last sale = moderate concern

# Concentration
HIGH_POSITION_PCT = Decimal("0.20")    # >20% portfolio in one position
HIGH_MANUFACTURER_PCT = Decimal("0.40")  # >40% in one manufacturer

# Physical
GOOD_STORAGE_SCORE = Decimal("0.8")

# Counterparty
TIER_RISK = {
    "allocation_access": Decimal("0.1"),
    "secondary_premium": Decimal("0.3"),
    "secondary_standard": Decimal("0.5"),
    "major": Decimal("0.1"),
    "mid": Decimal("0.3"),
    "online": Decimal("0.5"),
}

# Spec
MILEAGE_LOW_RISK = 5000
COLOUR_TIER_RISK = {
    1: Decimal("0.1"),
    2: Decimal("0.3"),
    3: Decimal("0.7"),
}

# Default composite weights (equal)
DEFAULT_WEIGHTS = {
    "liquidity": Decimal("1"),
    "concentration": Decimal("1"),
    "physical": Decimal("1"),
    "counterparty": Decimal("1"),
    "spec": Decimal("1"),
    "provenance": Decimal("1"),
}

_ONE = Decimal("1.000")
_ZERO = Decimal("0.000")
_QUANTIZE = Decimal("0.001")


def _clamp(value: Decimal) -> Decimal:
    """Clamp a Decimal to [0.000, 1.000] and quantize to 3 decimal places."""
    clamped = max(_ZERO, min(_ONE, value))
    return clamped.quantize(_QUANTIZE, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Individual risk dimension scorers
# ---------------------------------------------------------------------------

def score_liquidity_risk(
    transaction_count_12m: int,
    transaction_count_6m: int,
    days_since_last_sale: Optional[int],
    distinct_channels: int,
) -> tuple[Decimal, str]:
    """Score liquidity risk based on market activity.

    0.0 = highly liquid (frequent sales, multiple channels)
    1.0 = illiquid (no recent sales, single channel)
    """
    factors: list[Decimal] = []

    # Transaction frequency (12m)
    if transaction_count_12m >= LIQUID_TX_12M:
        factors.append(Decimal("0.0"))
    elif transaction_count_12m >= 3:
        factors.append(Decimal("0.3"))
    elif transaction_count_12m >= 1:
        factors.append(Decimal("0.6"))
    else:
        factors.append(Decimal("1.0"))

    # Recency of last sale
    if days_since_last_sale is None or days_since_last_sale >= ILLIQUID_DAYS:
        factors.append(Decimal("1.0"))
    elif days_since_last_sale >= MODERATE_DAYS:
        factors.append(Decimal("0.6"))
    elif days_since_last_sale >= 90:
        factors.append(Decimal("0.3"))
    else:
        factors.append(Decimal("0.1"))

    # Channel diversity
    if distinct_channels >= 3:
        factors.append(Decimal("0.0"))
    elif distinct_channels >= 2:
        factors.append(Decimal("0.3"))
    else:
        factors.append(Decimal("0.6"))

    # Recent momentum (6m vs 12m)
    if transaction_count_12m > 0:
        recent_ratio = Decimal(str(transaction_count_6m)) / Decimal(str(max(transaction_count_12m, 1)))
        if recent_ratio >= Decimal("0.5"):
            factors.append(Decimal("0.1"))
        elif recent_ratio >= Decimal("0.25"):
            factors.append(Decimal("0.4"))
        else:
            factors.append(Decimal("0.7"))
    else:
        factors.append(Decimal("0.8"))

    score = _clamp(sum(factors) / Decimal(str(len(factors))))

    # Build explanation
    parts = []
    if transaction_count_12m == 0:
        parts.append("No sales recorded in 12 months")
    else:
        parts.append(f"{transaction_count_12m} sales in 12 months")
    if days_since_last_sale is not None:
        parts.append(f"last sale {days_since_last_sale} days ago")
    else:
        parts.append("no known last sale date")
    parts.append(f"{distinct_channels} distinct channel(s)")
    explanation = "; ".join(parts)

    return score, explanation


def score_concentration_risk(
    position_value: Decimal,
    total_portfolio_value: Decimal,
    manufacturer_count: int,
    same_manufacturer_count: int,
) -> tuple[Decimal, str]:
    """Score concentration risk for a single position.

    0.0 = well-diversified
    1.0 = dangerously concentrated
    """
    factors: list[Decimal] = []
    parts: list[str] = []

    # Position as % of portfolio
    if total_portfolio_value > 0:
        position_pct = position_value / total_portfolio_value
        if position_pct > Decimal("0.40"):
            factors.append(Decimal("1.0"))
            parts.append(f"Position is {position_pct * 100:.1f}% of portfolio (>40%)")
        elif position_pct > HIGH_POSITION_PCT:
            factors.append(Decimal("0.7"))
            parts.append(f"Position is {position_pct * 100:.1f}% of portfolio (>20%)")
        elif position_pct > Decimal("0.10"):
            factors.append(Decimal("0.3"))
            parts.append(f"Position is {position_pct * 100:.1f}% of portfolio")
        else:
            factors.append(Decimal("0.1"))
            parts.append(f"Position is {position_pct * 100:.1f}% of portfolio")
    else:
        factors.append(Decimal("1.0"))
        parts.append("Cannot determine portfolio percentage")

    # Manufacturer concentration
    total_positions = max(manufacturer_count, 1)
    if total_positions > 0:
        mfr_pct = Decimal(str(same_manufacturer_count)) / Decimal(str(total_positions))
        if mfr_pct > HIGH_MANUFACTURER_PCT:
            factors.append(Decimal("0.9"))
            parts.append(f"Manufacturer concentration {mfr_pct * 100:.0f}% (>40%)")
        elif mfr_pct > Decimal("0.25"):
            factors.append(Decimal("0.5"))
            parts.append(f"Manufacturer concentration {mfr_pct * 100:.0f}%")
        else:
            factors.append(Decimal("0.2"))
            parts.append(f"Manufacturer concentration {mfr_pct * 100:.0f}%")

    score = _clamp(sum(factors) / Decimal(str(len(factors))))
    return score, "; ".join(parts)


def score_physical_risk(
    has_storage: bool,
    has_insurance: bool,
    storage_quality_score: Optional[Decimal],
) -> tuple[Decimal, str]:
    """Score physical risk from storage and insurance gaps.

    0.0 = fully covered (climate-controlled, insured)
    1.0 = high risk (no storage info, no insurance)
    """
    factors: list[Decimal] = []
    parts: list[str] = []

    if not has_storage:
        factors.append(Decimal("0.8"))
        parts.append("No storage location recorded")
    else:
        if storage_quality_score is not None and storage_quality_score >= GOOD_STORAGE_SCORE:
            factors.append(Decimal("0.1"))
            parts.append("High-quality storage")
        elif storage_quality_score is not None:
            factors.append(Decimal("0.4"))
            parts.append(f"Storage quality score: {storage_quality_score}")
        else:
            factors.append(Decimal("0.3"))
            parts.append("Storage location known, quality unscored")

    if not has_insurance:
        factors.append(Decimal("0.9"))
        parts.append("No insurance on record")
    else:
        factors.append(Decimal("0.1"))
        parts.append("Insurance active")

    score = _clamp(sum(factors) / Decimal(str(len(factors))))
    return score, "; ".join(parts)


def score_counterparty_risk(
    dealer_tier: Optional[str],
    dealer_reliability: Optional[Decimal],
    auction_house_tier: Optional[str],
) -> tuple[Decimal, str]:
    """Score counterparty risk from dealer and auction house quality.

    0.0 = top-tier counterparty
    1.0 = unknown or unreliable counterparty
    """
    factors: list[Decimal] = []
    parts: list[str] = []

    if dealer_tier is not None:
        tier_risk = TIER_RISK.get(dealer_tier, Decimal("0.5"))
        factors.append(tier_risk)
        parts.append(f"Dealer tier: {dealer_tier}")

        if dealer_reliability is not None:
            # reliability_score is 0-1, higher = more reliable -> invert for risk
            reliability_risk = _ONE - dealer_reliability
            factors.append(_clamp(reliability_risk))
            parts.append(f"Dealer reliability: {dealer_reliability}")
        else:
            factors.append(Decimal("0.5"))
            parts.append("Dealer reliability unknown")
    elif auction_house_tier is not None:
        tier_risk = TIER_RISK.get(auction_house_tier, Decimal("0.5"))
        factors.append(tier_risk)
        parts.append(f"Auction house tier: {auction_house_tier}")
    else:
        factors.append(Decimal("0.7"))
        parts.append("No counterparty information available")

    score = _clamp(sum(factors) / Decimal(str(len(factors))))
    return score, "; ".join(parts)


def score_spec_risk(
    colour_tier: Optional[int],
    has_desirable_options: bool,
    mileage: Optional[int],
    mileage_ceiling: Optional[int],
    has_certification: bool,
) -> tuple[Decimal, str]:
    """Score spec risk from colour, options, mileage, and certification.

    0.0 = perfect spec (desirable colour, low miles, certified)
    1.0 = undesirable spec
    """
    factors: list[Decimal] = []
    parts: list[str] = []

    # Colour tier
    if colour_tier is not None:
        colour_risk = COLOUR_TIER_RISK.get(colour_tier, Decimal("0.5"))
        factors.append(colour_risk)
        parts.append(f"Colour tier {colour_tier}")
    else:
        factors.append(Decimal("0.4"))
        parts.append("Colour tier unknown")

    # Desirable options
    if has_desirable_options:
        factors.append(Decimal("0.1"))
        parts.append("Has desirable options")
    else:
        factors.append(Decimal("0.6"))
        parts.append("Missing desirable options")

    # Mileage relative to ceiling
    if mileage is not None and mileage_ceiling is not None and mileage_ceiling > 0:
        mileage_ratio = Decimal(str(mileage)) / Decimal(str(mileage_ceiling))
        if mileage_ratio > Decimal("1.0"):
            factors.append(Decimal("0.9"))
            parts.append(f"Mileage {mileage} exceeds ceiling {mileage_ceiling}")
        elif mileage_ratio > Decimal("0.75"):
            factors.append(Decimal("0.6"))
            parts.append(f"Mileage {mileage} approaching ceiling {mileage_ceiling}")
        elif mileage_ratio > Decimal("0.5"):
            factors.append(Decimal("0.3"))
            parts.append(f"Mileage {mileage} moderate vs ceiling {mileage_ceiling}")
        else:
            factors.append(Decimal("0.1"))
            parts.append(f"Mileage {mileage} well below ceiling {mileage_ceiling}")
    elif mileage is not None:
        if mileage <= MILEAGE_LOW_RISK:
            factors.append(Decimal("0.1"))
            parts.append(f"Low mileage: {mileage}")
        elif mileage <= 20000:
            factors.append(Decimal("0.3"))
            parts.append(f"Moderate mileage: {mileage}")
        else:
            factors.append(Decimal("0.6"))
            parts.append(f"High mileage: {mileage}")
    else:
        factors.append(Decimal("0.5"))
        parts.append("Mileage unknown")

    # Certification
    if has_certification:
        factors.append(Decimal("0.05"))
        parts.append("Factory certified")
    else:
        factors.append(Decimal("0.4"))
        parts.append("Not factory certified")

    score = _clamp(sum(factors) / Decimal(str(len(factors))))
    return score, "; ".join(parts)


def score_provenance_risk(
    has_books: bool,
    has_service_history: bool,
    single_owner: bool,
    has_accident_history: bool,
    ownership_gaps: int,
) -> tuple[Decimal, str]:
    """Score provenance risk from documentation completeness.

    0.0 = full documentation, single owner, no accidents
    1.0 = major documentation gaps, accidents, many owners
    """
    factors: list[Decimal] = []
    parts: list[str] = []

    if has_books:
        factors.append(Decimal("0.05"))
        parts.append("Books/tools present")
    else:
        factors.append(Decimal("0.6"))
        parts.append("Books/tools missing")

    if has_service_history:
        factors.append(Decimal("0.05"))
        parts.append("Complete service history")
    else:
        factors.append(Decimal("0.7"))
        parts.append("Incomplete service history")

    if single_owner:
        factors.append(Decimal("0.05"))
        parts.append("Single-owner history")
    else:
        factors.append(Decimal("0.3"))
        parts.append("Multiple owners")

    if has_accident_history:
        factors.append(Decimal("0.8"))
        parts.append("Known accident history")
    else:
        factors.append(Decimal("0.05"))
        parts.append("No accident history")

    # Ownership gaps
    if ownership_gaps == 0:
        factors.append(Decimal("0.05"))
        parts.append("No ownership gaps")
    elif ownership_gaps <= 2:
        factors.append(Decimal("0.4"))
        parts.append(f"{ownership_gaps} ownership gap(s)")
    else:
        factors.append(Decimal("0.8"))
        parts.append(f"{ownership_gaps} ownership gaps")

    score = _clamp(sum(factors) / Decimal(str(len(factors))))
    return score, "; ".join(parts)


# ---------------------------------------------------------------------------
# Composite risk
# ---------------------------------------------------------------------------

def compute_composite_risk(
    scores: dict[str, Decimal],
    weights: Optional[dict[str, Decimal]] = None,
) -> Decimal:
    """Compute weighted average composite risk score.

    Parameters
    ----------
    scores : dict mapping dimension name to score (0-1)
    weights : optional dict mapping dimension name to weight.
              Defaults to equal weights across all dimensions.

    Returns
    -------
    Decimal composite score in [0, 1], quantized to 3 decimal places.
    """
    if not scores:
        return _ZERO

    w = weights or DEFAULT_WEIGHTS

    total_weight = _ZERO
    weighted_sum = _ZERO

    for dimension, score in scores.items():
        dim_weight = w.get(dimension, Decimal("1"))
        weighted_sum += score * dim_weight
        total_weight += dim_weight

    if total_weight == _ZERO:
        return _ZERO

    return _clamp(weighted_sum / total_weight)
