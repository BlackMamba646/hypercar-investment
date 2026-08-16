"""Scenario analysis -- pure functions for stress-testing the portfolio.

Each scenario function takes position data and a stress parameter, and
returns a dict describing the impact: affected positions, estimated
dollar impact, percentage impact, and a narrative explanation.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from aatp.core.logging import get_logger

logger = get_logger("risk.scenarios")

_QUANTIZE_2 = Decimal("0.01")


def scenario_market_drop(
    positions: list[dict],
    manufacturer: str,
    drop_pct: Decimal,
) -> dict:
    """Model the impact of a market drop for a specific manufacturer.

    "What if the Ferrari market drops 20%?"

    Parameters
    ----------
    positions : list of dicts with keys:
        position_id, manufacturer_name, current_fair_value_usd
    manufacturer : manufacturer name to stress
    drop_pct : percentage drop as Decimal (e.g. Decimal("20") for 20%)

    Returns
    -------
    dict with: affected_positions, estimated_impact_usd, impact_pct, narrative
    """
    drop_factor = drop_pct / Decimal("100")
    affected = []
    total_impact = Decimal("0")
    total_portfolio_value = Decimal("0")

    for pos in positions:
        value = pos.get("current_fair_value_usd") or Decimal("0")
        total_portfolio_value += value

        if pos.get("manufacturer_name", "").lower() == manufacturer.lower():
            impact = (value * drop_factor).quantize(_QUANTIZE_2, rounding=ROUND_HALF_UP)
            affected.append({
                "position_id": pos["position_id"],
                "current_value": str(value),
                "estimated_loss": str(impact),
                "post_stress_value": str((value - impact).quantize(_QUANTIZE_2)),
            })
            total_impact += impact

    impact_pct = Decimal("0.00")
    if total_portfolio_value > 0:
        impact_pct = ((total_impact / total_portfolio_value) * Decimal("100")).quantize(
            _QUANTIZE_2, rounding=ROUND_HALF_UP
        )

    narrative = (
        f"If the {manufacturer} market drops {drop_pct}%, "
        f"{len(affected)} position(s) would be affected. "
        f"Estimated portfolio impact: ${total_impact:,.2f} ({impact_pct}% of total value)."
    )

    return {
        "scenario": "market_drop",
        "parameters": {"manufacturer": manufacturer, "drop_pct": str(drop_pct)},
        "affected_positions": affected,
        "affected_count": len(affected),
        "estimated_impact_usd": str(total_impact.quantize(_QUANTIZE_2)),
        "impact_pct": str(impact_pct),
        "narrative": narrative,
    }


def scenario_rate_change(
    positions: list[dict],
    rate_change_bps: int,
    sensitivity: Decimal = Decimal("0.05"),
) -> dict:
    """Model the impact of an interest rate change on portfolio values.

    Higher rates reduce the value of illiquid luxury assets as opportunity
    cost increases and financing becomes more expensive.

    Parameters
    ----------
    positions : list of dicts with keys:
        position_id, current_fair_value_usd, manufacturer_name
    rate_change_bps : basis point change (e.g. 200 = 2% rise)
    sensitivity : value impact per 100bps (default 5%)

    Returns
    -------
    dict with: affected_positions, estimated_impact_usd, impact_pct, narrative
    """
    rate_change_pct = Decimal(str(rate_change_bps)) / Decimal("10000")
    impact_factor = rate_change_pct * (sensitivity / Decimal("0.01")) * Decimal("100")
    # impact_factor gives the percentage of value lost/gained per position

    affected = []
    total_impact = Decimal("0")
    total_portfolio_value = Decimal("0")

    for pos in positions:
        value = pos.get("current_fair_value_usd") or Decimal("0")
        total_portfolio_value += value

        if value > 0:
            impact = (value * impact_factor / Decimal("100")).quantize(
                _QUANTIZE_2, rounding=ROUND_HALF_UP
            )
            affected.append({
                "position_id": pos["position_id"],
                "current_value": str(value),
                "estimated_impact": str(impact),
                "post_stress_value": str((value - impact).quantize(_QUANTIZE_2)),
            })
            total_impact += impact

    impact_pct = Decimal("0.00")
    if total_portfolio_value > 0:
        impact_pct = ((total_impact / total_portfolio_value) * Decimal("100")).quantize(
            _QUANTIZE_2, rounding=ROUND_HALF_UP
        )

    direction = "rise" if rate_change_bps > 0 else "fall"
    narrative = (
        f"If interest rates {direction} by {abs(rate_change_bps)}bps, "
        f"all {len(affected)} position(s) would be affected "
        f"(sensitivity: {sensitivity * 100}% per 100bps). "
        f"Estimated portfolio impact: ${total_impact:,.2f} ({impact_pct}% of total value)."
    )

    return {
        "scenario": "rate_change",
        "parameters": {
            "rate_change_bps": rate_change_bps,
            "sensitivity": str(sensitivity),
        },
        "affected_positions": affected,
        "affected_count": len(affected),
        "estimated_impact_usd": str(total_impact.quantize(_QUANTIZE_2)),
        "impact_pct": str(impact_pct),
        "narrative": narrative,
    }


def scenario_no_flagship_auction(
    positions: list[dict],
    expected_exit_events: list[str],
) -> dict:
    """Model the impact of losing a flagship auction event (e.g. Monterey week).

    Positions targeting one of the expected exit events would lose their
    planned exit opportunity, forcing alternative (potentially lower-value)
    exits.

    Parameters
    ----------
    positions : list of dicts with keys:
        position_id, current_fair_value_usd, target_auction_event,
        manufacturer_name
    expected_exit_events : list of event names that would be cancelled

    Returns
    -------
    dict with: affected_positions, estimated_impact_usd, impact_pct, narrative
    """
    # Assume a 10-15% haircut for positions forced to alternative exit channels
    ALTERNATIVE_EXIT_DISCOUNT = Decimal("0.10")

    normalised_events = {e.lower().strip() for e in expected_exit_events}

    affected = []
    total_impact = Decimal("0")
    total_portfolio_value = Decimal("0")

    for pos in positions:
        value = pos.get("current_fair_value_usd") or Decimal("0")
        total_portfolio_value += value

        target_event = (pos.get("target_auction_event") or "").lower().strip()
        if target_event and target_event in normalised_events:
            impact = (value * ALTERNATIVE_EXIT_DISCOUNT).quantize(
                _QUANTIZE_2, rounding=ROUND_HALF_UP
            )
            affected.append({
                "position_id": pos["position_id"],
                "current_value": str(value),
                "target_event": pos.get("target_auction_event", ""),
                "estimated_loss": str(impact),
                "post_stress_value": str((value - impact).quantize(_QUANTIZE_2)),
            })
            total_impact += impact

    impact_pct = Decimal("0.00")
    if total_portfolio_value > 0:
        impact_pct = ((total_impact / total_portfolio_value) * Decimal("100")).quantize(
            _QUANTIZE_2, rounding=ROUND_HALF_UP
        )

    event_names = ", ".join(expected_exit_events)
    narrative = (
        f"If flagship auction event(s) ({event_names}) are cancelled, "
        f"{len(affected)} position(s) targeting those events would need "
        f"alternative exit channels. "
        f"Estimated portfolio impact: ${total_impact:,.2f} ({impact_pct}% of total value) "
        f"assuming {ALTERNATIVE_EXIT_DISCOUNT * 100}% alternative exit discount."
    )

    return {
        "scenario": "no_flagship_auction",
        "parameters": {"expected_exit_events": expected_exit_events},
        "affected_positions": affected,
        "affected_count": len(affected),
        "estimated_impact_usd": str(total_impact.quantize(_QUANTIZE_2)),
        "impact_pct": str(impact_pct),
        "narrative": narrative,
    }
