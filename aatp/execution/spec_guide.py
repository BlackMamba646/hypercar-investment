from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from aatp.core.logging import get_logger

logger = get_logger("execution.spec_guide")

# ---------------------------------------------------------------------------
# Scoring weights and thresholds
# ---------------------------------------------------------------------------

COLOUR_WEIGHT = Decimal("30")
OPTIONS_WEIGHT = Decimal("30")
MILEAGE_WEIGHT = Decimal("25")
CERTIFICATION_WEIGHT = Decimal("15")

# Mileage deduction tiers (per 1,000 miles over ceiling)
MILEAGE_DEDUCTION_PER_1K = Decimal("3")
# Maximum mileage deduction
MAX_MILEAGE_DEDUCTION = Decimal("25")

# Drive side mismatch penalty
DRIVE_SIDE_PENALTY = Decimal("10")

# Option scoring
AVOID_OPTION_PENALTY = Decimal("5")
MAX_AVOID_PENALTY = Decimal("20")


@dataclass
class RecommendedSpec:
    """Recommended specification for optimal resale value.

    Mirrors the data stored in the ``SpecGuide`` DB model but is a
    plain dataclass so pure functions can accept it without importing
    SQLAlchemy.
    """

    recommended_colours: List[str]
    recommended_options: List[str]
    avoid_options: List[str]
    mileage_ceiling: Optional[int]
    drive_side_preference: Optional[str]
    certification_required: bool
    certification_type: Optional[str] = None


@dataclass
class SpecScore:
    """Result of scoring a specific asset against its recommended spec."""

    total_score: Decimal
    colour_score: Decimal
    options_score: Decimal
    mileage_score: Decimal
    certification_score: Decimal
    deductions: List[str]


def _score_colour(
    colour_exterior: Optional[str],
    colour_interior: Optional[str],
    recommended_colours: List[str],
) -> tuple[Decimal, List[str]]:
    """Score exterior/interior colour against recommended list.

    Returns (score_0_to_100, deductions).
    """
    if not recommended_colours:
        return Decimal("100"), []

    deductions: List[str] = []
    score = Decimal("100")

    # Normalise for comparison
    rec_lower = [c.lower().strip() for c in recommended_colours]

    ext_match = False
    if colour_exterior:
        if colour_exterior.lower().strip() in rec_lower:
            ext_match = True

    if not ext_match and colour_exterior:
        score -= Decimal("50")
        deductions.append(
            f"Exterior colour '{colour_exterior}' not in recommended list"
        )
    elif not colour_exterior:
        score -= Decimal("25")
        deductions.append("Exterior colour not specified")

    # Interior is a softer factor
    if colour_interior and rec_lower:
        if colour_interior.lower().strip() not in rec_lower:
            score -= Decimal("15")
            deductions.append(
                f"Interior colour '{colour_interior}' not in recommended list"
            )

    return max(score, Decimal("0")), deductions


def _score_options(
    options: Optional[List[str]],
    recommended_options: List[str],
    avoid_options: List[str],
) -> tuple[Decimal, List[str]]:
    """Score options against recommended and avoid lists.

    Returns (score_0_to_100, deductions).
    """
    deductions: List[str] = []
    score = Decimal("100")

    if not options:
        if recommended_options:
            score -= Decimal("20")
            deductions.append("No options data provided for comparison")
        return max(score, Decimal("0")), deductions

    opt_lower = [o.lower().strip() for o in options]

    # Penalise avoided options
    avoid_lower = [a.lower().strip() for a in avoid_options]
    penalty = Decimal("0")
    for opt in opt_lower:
        if opt in avoid_lower:
            penalty += AVOID_OPTION_PENALTY
            deductions.append(f"Has avoided option: '{opt}'")
    penalty = min(penalty, MAX_AVOID_PENALTY)
    score -= penalty

    # Reward recommended options (partial credit)
    if recommended_options:
        rec_lower = [r.lower().strip() for r in recommended_options]
        matched = sum(1 for r in rec_lower if r in opt_lower)
        coverage = Decimal(str(matched)) / Decimal(str(len(rec_lower)))
        missing_penalty = (Decimal("1") - coverage) * Decimal("30")
        score -= missing_penalty
        if matched < len(rec_lower):
            missing = [r for r in recommended_options if r.lower().strip() not in opt_lower]
            deductions.append(
                f"Missing {len(missing)} recommended option(s): {', '.join(missing[:3])}"
            )

    return max(score, Decimal("0")).quantize(Decimal("0.01")), deductions


def _score_mileage(
    mileage: Optional[int],
    mileage_ceiling: Optional[int],
) -> tuple[Decimal, List[str]]:
    """Score mileage against ceiling.

    Returns (score_0_to_100, deductions).
    """
    if mileage is None:
        return Decimal("80"), ["Mileage not specified"]

    if mileage_ceiling is None:
        # No ceiling defined -- give full marks for low mileage
        if mileage <= 5000:
            return Decimal("100"), []
        if mileage <= 15000:
            return Decimal("85"), []
        return Decimal("60"), [f"Mileage {mileage:,} is moderate (no ceiling defined)"]

    if mileage <= mileage_ceiling:
        # Under ceiling: proportional score
        if mileage_ceiling > 0:
            ratio = Decimal(str(mileage)) / Decimal(str(mileage_ceiling))
            score = Decimal("100") - ratio * Decimal("20")  # up to 20pt penalty at ceiling
        else:
            score = Decimal("100")
        return score.quantize(Decimal("0.01")), []

    # Over ceiling: deductions per 1,000 miles over
    over = mileage - mileage_ceiling
    over_thousands = Decimal(str(over)) / Decimal("1000")
    deduction = min(
        (over_thousands * MILEAGE_DEDUCTION_PER_1K).quantize(Decimal("0.01")),
        MAX_MILEAGE_DEDUCTION,
    )
    score = max(Decimal("100") - Decimal("20") - deduction, Decimal("0"))
    deductions = [
        f"Mileage {mileage:,} exceeds ceiling of {mileage_ceiling:,} by {over:,}"
    ]
    return score.quantize(Decimal("0.01")), deductions


def _score_certification(
    has_certification: bool,
    certification_required: bool,
) -> tuple[Decimal, List[str]]:
    """Score certification status.

    Returns (score_0_to_100, deductions).
    """
    if not certification_required:
        if has_certification:
            return Decimal("100"), []
        return Decimal("80"), []

    if has_certification:
        return Decimal("100"), []

    return Decimal("0"), ["Missing required certification"]


def score_spec(
    colour_exterior: Optional[str],
    colour_interior: Optional[str],
    options: Optional[List[str]],
    mileage: Optional[int],
    drive_side: Optional[str],
    has_certification: bool,
    recommended_spec: RecommendedSpec,
) -> SpecScore:
    """Score an asset's specification against recommended spec.

    Pure function -- no database access.  Returns a ``SpecScore`` with
    a total score 0-100 and itemised deductions.

    Parameters
    ----------
    colour_exterior:
        Exterior colour of the asset.
    colour_interior:
        Interior colour of the asset.
    options:
        List of option names/codes on the asset.
    mileage:
        Current mileage reading.
    drive_side:
        ``"LHD"`` or ``"RHD"``.
    has_certification:
        Whether the asset has manufacturer certification.
    recommended_spec:
        The ideal specification to compare against.
    """
    all_deductions: List[str] = []

    colour_raw, colour_ded = _score_colour(
        colour_exterior, colour_interior, recommended_spec.recommended_colours
    )
    all_deductions.extend(colour_ded)

    options_raw, options_ded = _score_options(
        options,
        recommended_spec.recommended_options,
        recommended_spec.avoid_options,
    )
    all_deductions.extend(options_ded)

    mileage_raw, mileage_ded = _score_mileage(
        mileage, recommended_spec.mileage_ceiling
    )
    all_deductions.extend(mileage_ded)

    cert_raw, cert_ded = _score_certification(
        has_certification, recommended_spec.certification_required
    )
    all_deductions.extend(cert_ded)

    # Drive-side mismatch penalty applied to total
    drive_penalty = Decimal("0")
    if (
        drive_side
        and recommended_spec.drive_side_preference
        and drive_side.upper() != recommended_spec.drive_side_preference.upper()
    ):
        drive_penalty = DRIVE_SIDE_PENALTY
        all_deductions.append(
            f"Drive side '{drive_side}' does not match preference "
            f"'{recommended_spec.drive_side_preference}'"
        )

    # Weighted total
    total = (
        colour_raw * COLOUR_WEIGHT / 100
        + options_raw * OPTIONS_WEIGHT / 100
        + mileage_raw * MILEAGE_WEIGHT / 100
        + cert_raw * CERTIFICATION_WEIGHT / 100
        - drive_penalty
    ).quantize(Decimal("0.01"))
    total = max(total, Decimal("0"))
    total = min(total, Decimal("100"))

    result = SpecScore(
        total_score=total,
        colour_score=colour_raw.quantize(Decimal("0.01")),
        options_score=options_raw.quantize(Decimal("0.01")),
        mileage_score=mileage_raw.quantize(Decimal("0.01")),
        certification_score=cert_raw.quantize(Decimal("0.01")),
        deductions=all_deductions,
    )

    logger.info(
        "spec_scored",
        total_score=str(result.total_score),
        colour_score=str(result.colour_score),
        options_score=str(result.options_score),
        mileage_score=str(result.mileage_score),
        deductions_count=len(all_deductions),
    )
    return result
