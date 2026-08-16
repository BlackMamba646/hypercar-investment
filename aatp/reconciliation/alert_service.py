"""
Alert generation and management — severity classification, formatting,
and database persistence for platform-wide alerts.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from aatp.core.logging import get_logger
from aatp.db.models import AlertSeverity, AlertType

logger = get_logger("reconciliation.alert_service")

TWO_PLACES = Decimal("0.01")

# Severity thresholds (percentage)
SEVERITY_WARNING_PCT = Decimal("5.0")
SEVERITY_CRITICAL_PCT = Decimal("15.0")


def should_generate_alert(
    alert_type: AlertType,
    severity: AlertSeverity,
    value: Decimal,
    threshold: Decimal,
) -> bool:
    """Decide whether an alert should be generated based on value vs threshold.

    An alert is generated when *value* exceeds *threshold*.
    """
    return value > threshold


def classify_alert_severity(divergence_pct: Decimal) -> AlertSeverity:
    """Classify alert severity based on divergence percentage.

    - < 5%  -> INFO
    - 5-15% -> WARNING
    - > 15% -> CRITICAL
    """
    if divergence_pct > SEVERITY_CRITICAL_PCT:
        return AlertSeverity.CRITICAL
    if divergence_pct >= SEVERITY_WARNING_PCT:
        return AlertSeverity.WARNING
    return AlertSeverity.INFO


def format_price_movement_alert(
    model_name: str,
    old_price: Decimal,
    new_price: Decimal,
    change_pct: Decimal,
) -> tuple[str, str]:
    """Format a price-movement alert.

    Returns
    -------
    (title, message)
    """
    direction = "increased" if new_price > old_price else "decreased"
    title = f"Price {direction} {abs(change_pct)}% for {model_name}"
    message = (
        f"The fair value for {model_name} has {direction} by {abs(change_pct)}% "
        f"from ${old_price:,.2f} to ${new_price:,.2f}."
    )
    return (title, message)


def format_hold_period_alert(
    position_description: str,
    months_held: int,
    max_months: int,
) -> tuple[str, str]:
    """Format a hold-period warning alert.

    Returns
    -------
    (title, message)
    """
    title = f"Hold period warning: {position_description}"
    message = (
        f"Position '{position_description}' has been held for {months_held} months, "
        f"exceeding the target maximum of {max_months} months. "
        f"Review exit strategy."
    )
    return (title, message)
