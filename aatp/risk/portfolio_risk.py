"""Portfolio-level risk analysis -- concentration and illiquidity assessment.

Pure functions operating on pre-aggregated data. No database access.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from aatp.core.logging import get_logger

logger = get_logger("risk.portfolio_risk")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MAX_MANUFACTURER_PCT = Decimal("40.00")
MAX_ERA_PCT = Decimal("60.00")
MAX_TYPE_PCT = Decimal("70.00")
MAX_ILLIQUID_PCT = Decimal("30.00")

_QUANTIZE_2 = Decimal("0.01")


def _pct(value: Decimal, total: Decimal) -> Decimal:
    """Compute percentage and quantize to 2 decimal places."""
    if total <= 0:
        return Decimal("0.00")
    return ((value / total) * Decimal("100")).quantize(_QUANTIZE_2, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Concentration assessments
# ---------------------------------------------------------------------------

def assess_manufacturer_concentration(
    positions_by_manufacturer: dict[str, Decimal],
) -> tuple[dict, list[str]]:
    """Assess portfolio concentration by manufacturer.

    Parameters
    ----------
    positions_by_manufacturer : dict mapping manufacturer name to total value

    Returns
    -------
    (concentration_map, warnings)
    concentration_map: dict of manufacturer -> percentage of portfolio
    warnings: list of warning strings for any manufacturer exceeding 40%
    """
    total = sum(positions_by_manufacturer.values())
    concentration: dict[str, str] = {}
    warnings: list[str] = []

    if total <= 0:
        return concentration, warnings

    for manufacturer, value in sorted(
        positions_by_manufacturer.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        pct = _pct(value, total)
        concentration[manufacturer] = str(pct)

        if pct > MAX_MANUFACTURER_PCT:
            warnings.append(
                f"Manufacturer '{manufacturer}' represents {pct}% of portfolio "
                f"(threshold: {MAX_MANUFACTURER_PCT}%)"
            )

    return concentration, warnings


def assess_era_concentration(
    positions_by_decade: dict[str, Decimal],
) -> tuple[dict, list[str]]:
    """Assess portfolio concentration by production era / decade.

    Parameters
    ----------
    positions_by_decade : dict mapping decade label (e.g. "1990s") to total value

    Returns
    -------
    (concentration_map, warnings)
    concentration_map: dict of decade -> percentage of portfolio
    warnings: list of warning strings for any decade exceeding 60%
    """
    total = sum(positions_by_decade.values())
    concentration: dict[str, str] = {}
    warnings: list[str] = []

    if total <= 0:
        return concentration, warnings

    for decade, value in sorted(
        positions_by_decade.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        pct = _pct(value, total)
        concentration[decade] = str(pct)

        if pct > MAX_ERA_PCT:
            warnings.append(
                f"Era '{decade}' represents {pct}% of portfolio "
                f"(threshold: {MAX_ERA_PCT}%)"
            )

    return concentration, warnings


def assess_type_concentration(
    positions_by_type: dict[str, Decimal],
) -> tuple[dict, list[str]]:
    """Assess portfolio concentration by asset type (e.g. coupe, convertible).

    Parameters
    ----------
    positions_by_type : dict mapping type label to total value

    Returns
    -------
    (concentration_map, warnings)
    concentration_map: dict of type -> percentage of portfolio
    warnings: list of warning strings for any type exceeding 70%
    """
    total = sum(positions_by_type.values())
    concentration: dict[str, str] = {}
    warnings: list[str] = []

    if total <= 0:
        return concentration, warnings

    for asset_type, value in sorted(
        positions_by_type.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        pct = _pct(value, total)
        concentration[asset_type] = str(pct)

        if pct > MAX_TYPE_PCT:
            warnings.append(
                f"Type '{asset_type}' represents {pct}% of portfolio "
                f"(threshold: {MAX_TYPE_PCT}%)"
            )

    return concentration, warnings


def assess_illiquid_exposure(
    positions_with_last_sale_days: list[tuple[str, int | None]],
) -> tuple[Decimal, list[str]]:
    """Assess what percentage of positions are illiquid (no sale in 90 days).

    Parameters
    ----------
    positions_with_last_sale_days : list of (position_id, days_since_last_sale)
        where days_since_last_sale is None if no sale is known.

    Returns
    -------
    (illiquid_pct, warnings)
    illiquid_pct: percentage of positions with no sale in 90+ days
    warnings: list of warning strings if exposure exceeds 30%
    """
    if not positions_with_last_sale_days:
        return Decimal("0.00"), []

    total = len(positions_with_last_sale_days)
    illiquid_count = sum(
        1
        for _, days in positions_with_last_sale_days
        if days is None or days >= 90
    )

    illiquid_pct = _pct(Decimal(str(illiquid_count)), Decimal(str(total)))

    warnings: list[str] = []
    if illiquid_pct > MAX_ILLIQUID_PCT:
        warnings.append(
            f"{illiquid_pct}% of positions are illiquid (no sale in 90+ days); "
            f"threshold is {MAX_ILLIQUID_PCT}%"
        )

    return illiquid_pct, warnings
