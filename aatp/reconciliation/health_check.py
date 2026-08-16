"""
System health monitoring — scraper status, data-pipeline coverage,
and signal freshness checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from aatp.core.logging import get_logger

logger = get_logger("reconciliation.health_check")

TWO_PLACES = Decimal("0.01")

# Coverage thresholds
COVERAGE_WARNING_PCT = Decimal("80.00")
COVERAGE_CRITICAL_PCT = Decimal("50.00")

# Signal freshness thresholds (hours)
SIGNAL_WARNING_HOURS = 24
SIGNAL_CRITICAL_HOURS = 72

# Scraper health thresholds
ITEM_COUNT_DROP_PCT = Decimal("20.0")


def check_scraper_health(scraper_runs: list[dict]) -> dict:
    """Analyse recent scraper runs for failures, declining item counts, and gaps.

    Each dict in *scraper_runs* must contain:
        name (str), status (str), items_collected (int), started_at (datetime)

    Returns a dict with overall_status, issues (list[str]), and per-scraper details.
    """
    if not scraper_runs:
        return {
            "overall_status": "unknown",
            "issues": ["No scraper runs found to analyse."],
            "scrapers": {},
        }

    # Group runs by scraper name, most recent first
    by_scraper: dict[str, list[dict]] = {}
    for run in scraper_runs:
        name = run["name"]
        by_scraper.setdefault(name, []).append(run)

    issues: list[str] = []
    scrapers: dict[str, dict] = {}

    for name, runs in by_scraper.items():
        sorted_runs = sorted(runs, key=lambda r: r["started_at"], reverse=True)
        latest = sorted_runs[0]
        scraper_info: dict = {
            "latest_status": latest["status"],
            "latest_items": latest["items_collected"],
            "latest_started_at": str(latest["started_at"]),
            "issues": [],
        }

        # Check 1: Latest run failure
        if latest["status"] != "completed":
            issue = f"Scraper '{name}' latest run status: {latest['status']}."
            scraper_info["issues"].append(issue)
            issues.append(issue)

        # Check 2: Declining item counts (need at least 2 runs)
        if len(sorted_runs) >= 2:
            previous = sorted_runs[1]
            prev_items = previous["items_collected"]
            curr_items = latest["items_collected"]

            if prev_items > 0:
                drop_pct = (
                    Decimal(str(prev_items - curr_items))
                    / Decimal(str(prev_items))
                    * Decimal("100")
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                if drop_pct > ITEM_COUNT_DROP_PCT:
                    issue = (
                        f"Scraper '{name}' item count dropped {drop_pct}% "
                        f"({prev_items} -> {curr_items})."
                    )
                    scraper_info["issues"].append(issue)
                    issues.append(issue)

        # Check 3: Missed schedules (gap > expected interval * 2)
        if len(sorted_runs) >= 2:
            # Estimate expected interval from the two most recent consecutive runs
            intervals = []
            for i in range(len(sorted_runs) - 1):
                gap = sorted_runs[i]["started_at"] - sorted_runs[i + 1]["started_at"]
                intervals.append(gap)
                if len(intervals) >= 3:
                    break

            if len(intervals) >= 2:
                avg_interval = sum(intervals, timedelta()) / len(intervals)
                latest_gap = intervals[0]
                if avg_interval > timedelta(0) and latest_gap > avg_interval * 2:
                    issue = (
                        f"Scraper '{name}' may have missed a schedule: "
                        f"latest gap={latest_gap}, expected ~{avg_interval}."
                    )
                    scraper_info["issues"].append(issue)
                    issues.append(issue)

        scrapers[name] = scraper_info

    overall = "healthy" if not issues else "degraded"
    return {
        "overall_status": overall,
        "issues": issues,
        "scrapers": scrapers,
    }


def check_normalisation_coverage(
    total_transactions: int,
    normalised_count: int,
) -> tuple[Decimal, str]:
    """Return the percentage of transactions that have been normalised.

    Returns
    -------
    (coverage_pct, description)
    """
    if total_transactions == 0:
        return (Decimal("100.00"), "No transactions to normalise.")

    coverage = (
        Decimal(str(normalised_count)) / Decimal(str(total_transactions)) * Decimal("100")
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if coverage < COVERAGE_CRITICAL_PCT:
        desc = f"CRITICAL: Only {coverage}% of {total_transactions} transactions normalised."
    elif coverage < COVERAGE_WARNING_PCT:
        desc = f"WARNING: {coverage}% of {total_transactions} transactions normalised."
    else:
        desc = f"OK: {coverage}% of {total_transactions} transactions normalised."

    return (coverage, desc)


def check_fair_value_coverage(
    total_models: int,
    valued_count: int,
) -> tuple[Decimal, str]:
    """Return the percentage of asset models with a current fair value.

    Returns
    -------
    (coverage_pct, description)
    """
    if total_models == 0:
        return (Decimal("100.00"), "No models to value.")

    coverage = (
        Decimal(str(valued_count)) / Decimal(str(total_models)) * Decimal("100")
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if coverage < COVERAGE_CRITICAL_PCT:
        desc = f"CRITICAL: Only {coverage}% of {total_models} models have fair values."
    elif coverage < COVERAGE_WARNING_PCT:
        desc = f"WARNING: {coverage}% of {total_models} models have fair values."
    else:
        desc = f"OK: {coverage}% of {total_models} models have fair values."

    return (coverage, desc)


def check_signal_freshness(
    latest_signal_date: datetime | None,
    current_date: datetime,
) -> tuple[int, str]:
    """Return the number of hours since the latest signal was generated.

    Returns
    -------
    (hours_since_last, description)
    """
    if latest_signal_date is None:
        return (
            -1,
            "CRITICAL: No signals found in the system.",
        )

    delta = current_date - latest_signal_date
    hours = int(delta.total_seconds() // 3600)

    if hours > SIGNAL_CRITICAL_HOURS:
        desc = f"CRITICAL: Last signal was {hours}h ago (threshold: {SIGNAL_CRITICAL_HOURS}h)."
    elif hours > SIGNAL_WARNING_HOURS:
        desc = f"WARNING: Last signal was {hours}h ago (threshold: {SIGNAL_WARNING_HOURS}h)."
    else:
        desc = f"OK: Last signal was {hours}h ago."

    return (hours, desc)


@dataclass
class SystemHealthReport:
    """Aggregated system health report."""

    scraper_health: dict = field(default_factory=dict)
    normalisation_coverage_pct: Decimal = Decimal("0.00")
    normalisation_description: str = ""
    fair_value_coverage_pct: Decimal = Decimal("0.00")
    fair_value_description: str = ""
    signal_freshness_hours: int = 0
    signal_freshness_description: str = ""

    @property
    def overall_status(self) -> str:
        """Derive overall status from component checks."""
        if (
            self.normalisation_coverage_pct < COVERAGE_CRITICAL_PCT
            or self.fair_value_coverage_pct < COVERAGE_CRITICAL_PCT
            or self.signal_freshness_hours > SIGNAL_CRITICAL_HOURS
            or self.signal_freshness_hours == -1
            or self.scraper_health.get("overall_status") == "degraded"
        ):
            return "critical"

        if (
            self.normalisation_coverage_pct < COVERAGE_WARNING_PCT
            or self.fair_value_coverage_pct < COVERAGE_WARNING_PCT
            or self.signal_freshness_hours > SIGNAL_WARNING_HOURS
        ):
            return "warning"

        return "healthy"

    def to_dict(self) -> dict:
        return {
            "overall_status": self.overall_status,
            "scraper_health": self.scraper_health,
            "normalisation_coverage_pct": str(self.normalisation_coverage_pct),
            "normalisation_description": self.normalisation_description,
            "fair_value_coverage_pct": str(self.fair_value_coverage_pct),
            "fair_value_description": self.fair_value_description,
            "signal_freshness_hours": self.signal_freshness_hours,
            "signal_freshness_description": self.signal_freshness_description,
        }
