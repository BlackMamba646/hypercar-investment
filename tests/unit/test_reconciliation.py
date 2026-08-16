"""Tests for Module 9 — Reconciliation & Monitoring pure-function logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from aatp.reconciliation.price_recon import (
    PriceReconciliationResult,
    check_price_divergence,
)
from aatp.reconciliation.ledger_recon import (
    LedgerReconciliationResult,
    check_cost_basis_integrity,
    check_ledger_balance,
    check_pnl_integrity,
)
from aatp.reconciliation.health_check import (
    COVERAGE_CRITICAL_PCT,
    COVERAGE_WARNING_PCT,
    SIGNAL_CRITICAL_HOURS,
    SIGNAL_WARNING_HOURS,
    SystemHealthReport,
    check_fair_value_coverage,
    check_normalisation_coverage,
    check_scraper_health,
    check_signal_freshness,
)
from aatp.reconciliation.alert_service import (
    classify_alert_severity,
    format_hold_period_alert,
    format_price_movement_alert,
    should_generate_alert,
)
from aatp.db.models import AlertSeverity, AlertType


# ===========================================================================
# Helpers
# ===========================================================================

def _d(value) -> Decimal:
    return Decimal(str(value))


# ===========================================================================
# Price Divergence
# ===========================================================================

class TestCheckPriceDivergence:
    def test_no_divergence_within_threshold(self):
        has_div, pct, desc = check_price_divergence(_d(100000), _d(100500))
        assert not has_div
        assert pct <= _d("1.0")
        assert "within tolerance" in desc

    def test_divergence_above_threshold(self):
        has_div, pct, desc = check_price_divergence(_d(100000), _d(105000))
        assert has_div
        assert pct == _d("5.0000")
        assert "divergence" in desc.lower()

    def test_exact_match_no_divergence(self):
        has_div, pct, desc = check_price_divergence(_d(500000), _d(500000))
        assert not has_div
        assert pct == _d("0.0000")

    def test_custom_threshold(self):
        # 2% divergence with 3% threshold -> no alert
        has_div, pct, desc = check_price_divergence(
            _d(100000), _d(102000), threshold_pct=_d("3.0")
        )
        assert not has_div

    def test_custom_threshold_exceeded(self):
        # 2% divergence with 1.5% threshold -> alert
        has_div, pct, desc = check_price_divergence(
            _d(100000), _d(102000), threshold_pct=_d("1.5")
        )
        assert has_div

    def test_both_zero_no_divergence(self):
        has_div, pct, desc = check_price_divergence(_d(0), _d(0))
        assert not has_div
        assert "zero" in desc.lower()

    def test_stored_zero_recalculated_nonzero(self):
        has_div, pct, desc = check_price_divergence(_d(0), _d(50000))
        assert has_div
        assert pct == _d("100.00")

    def test_boundary_exactly_at_threshold(self):
        # Exactly at 1% -> not divergent (must exceed, not equal)
        has_div, pct, desc = check_price_divergence(_d(100000), _d(101000))
        assert not has_div
        assert pct == _d("1.0000")

    def test_large_divergence(self):
        has_div, pct, desc = check_price_divergence(_d(100000), _d(200000))
        assert has_div
        assert pct == _d("100.0000")

    def test_negative_direction_divergence(self):
        # Recalculated lower than stored
        has_div, pct, desc = check_price_divergence(_d(100000), _d(90000))
        assert has_div
        assert pct == _d("10.0000")


class TestPriceReconciliationResult:
    def test_empty_result(self):
        result = PriceReconciliationResult()
        assert result.transactions_checked == 0
        assert result.divergences_found == 0
        assert result.divergences == []

    def test_add_divergence(self):
        result = PriceReconciliationResult(transactions_checked=10)
        result.add_divergence("tx-1", _d(100000), _d(110000), _d("10.0"), "big drift")
        assert result.divergences_found == 1
        assert result.divergences[0]["transaction_id"] == "tx-1"

    def test_to_dict(self):
        result = PriceReconciliationResult(transactions_checked=5, divergences_found=1)
        d = result.to_dict()
        assert d["transactions_checked"] == 5
        assert d["divergences_found"] == 1


# ===========================================================================
# Cost Basis Integrity
# ===========================================================================

class TestCheckCostBasisIntegrity:
    def test_matching_cost_basis(self):
        has_div, amt, desc = check_cost_basis_integrity(
            _d(1000000), _d(50000), _d(1050000)
        )
        assert not has_div
        assert amt == _d("0.00")

    def test_mismatched_cost_basis(self):
        has_div, amt, desc = check_cost_basis_integrity(
            _d(1000000), _d(50000), _d(1060000)
        )
        assert has_div
        assert amt == _d("10000.00")
        assert "mismatch" in desc.lower()

    def test_zero_costs(self):
        has_div, amt, desc = check_cost_basis_integrity(
            _d(500000), _d(0), _d(500000)
        )
        assert not has_div

    def test_small_rounding_difference(self):
        # Rounding should resolve sub-cent differences
        has_div, amt, desc = check_cost_basis_integrity(
            _d("1000000.004"), _d("50000.003"), _d("1050000.01")
        )
        assert not has_div


# ===========================================================================
# Ledger Balance
# ===========================================================================

class TestCheckLedgerBalance:
    def test_balanced_ledger(self):
        has_div, amt, desc = check_ledger_balance(_d(250000), _d(250000))
        assert not has_div
        assert amt == _d("0.00")

    def test_unbalanced_ledger(self):
        has_div, amt, desc = check_ledger_balance(_d(250000), _d(260000))
        assert has_div
        assert amt == _d("10000.00")

    def test_zero_balance(self):
        has_div, amt, desc = check_ledger_balance(_d(0), _d(0))
        assert not has_div


# ===========================================================================
# P&L Integrity
# ===========================================================================

class TestCheckPnlIntegrity:
    def test_correct_pnl(self):
        has_div, amt, desc = check_pnl_integrity(
            _d(1500000), _d(1200000), _d(300000)
        )
        assert not has_div
        assert amt == _d("0.00")

    def test_incorrect_pnl(self):
        has_div, amt, desc = check_pnl_integrity(
            _d(1500000), _d(1200000), _d(250000)
        )
        assert has_div
        assert amt == _d("50000.00")

    def test_negative_pnl_correct(self):
        has_div, amt, desc = check_pnl_integrity(
            _d(900000), _d(1200000), _d(-300000)
        )
        assert not has_div

    def test_negative_pnl_incorrect(self):
        has_div, amt, desc = check_pnl_integrity(
            _d(900000), _d(1200000), _d(-200000)
        )
        assert has_div
        assert amt == _d("100000.00")

    def test_zero_pnl(self):
        has_div, amt, desc = check_pnl_integrity(
            _d(1000000), _d(1000000), _d(0)
        )
        assert not has_div


class TestLedgerReconciliationResult:
    def test_total_divergences(self):
        result = LedgerReconciliationResult(
            cost_basis_divergences=2,
            ledger_balance_divergences=1,
            pnl_divergences=3,
        )
        assert result.total_divergences == 6

    def test_to_dict_keys(self):
        result = LedgerReconciliationResult()
        d = result.to_dict()
        assert "positions_checked" in d
        assert "total_divergences" in d
        assert "divergences" in d


# ===========================================================================
# Scraper Health
# ===========================================================================

class TestCheckScraperHealth:
    def test_empty_runs(self):
        result = check_scraper_health([])
        assert result["overall_status"] == "unknown"
        assert len(result["issues"]) == 1

    def test_healthy_scraper(self):
        now = datetime.now(timezone.utc)
        runs = [
            {"name": "bat", "status": "completed", "items_collected": 50, "started_at": now},
            {"name": "bat", "status": "completed", "items_collected": 48, "started_at": now - timedelta(days=1)},
        ]
        result = check_scraper_health(runs)
        assert result["overall_status"] == "healthy"
        assert len(result["issues"]) == 0

    def test_failed_scraper(self):
        now = datetime.now(timezone.utc)
        runs = [
            {"name": "bat", "status": "failed", "items_collected": 0, "started_at": now},
        ]
        result = check_scraper_health(runs)
        assert result["overall_status"] == "degraded"
        assert any("failed" in issue for issue in result["issues"])

    def test_declining_item_count(self):
        now = datetime.now(timezone.utc)
        runs = [
            {"name": "bat", "status": "completed", "items_collected": 30, "started_at": now},
            {"name": "bat", "status": "completed", "items_collected": 50, "started_at": now - timedelta(days=1)},
        ]
        result = check_scraper_health(runs)
        assert result["overall_status"] == "degraded"
        assert any("dropped" in issue for issue in result["issues"])

    def test_multiple_scrapers_mixed(self):
        now = datetime.now(timezone.utc)
        runs = [
            {"name": "bat", "status": "completed", "items_collected": 50, "started_at": now},
            {"name": "bat", "status": "completed", "items_collected": 48, "started_at": now - timedelta(days=1)},
            {"name": "rm", "status": "failed", "items_collected": 0, "started_at": now},
        ]
        result = check_scraper_health(runs)
        assert result["overall_status"] == "degraded"
        assert "bat" in result["scrapers"]
        assert "rm" in result["scrapers"]

    def test_item_count_drop_below_threshold(self):
        """A drop of exactly 20% should NOT trigger (must exceed)."""
        now = datetime.now(timezone.utc)
        runs = [
            {"name": "bat", "status": "completed", "items_collected": 40, "started_at": now},
            {"name": "bat", "status": "completed", "items_collected": 50, "started_at": now - timedelta(days=1)},
        ]
        result = check_scraper_health(runs)
        assert result["overall_status"] == "healthy"


# ===========================================================================
# Normalisation Coverage
# ===========================================================================

class TestCheckNormalisationCoverage:
    def test_full_coverage(self):
        pct, desc = check_normalisation_coverage(100, 100)
        assert pct == _d("100.00")
        assert "OK" in desc

    def test_warning_coverage(self):
        pct, desc = check_normalisation_coverage(100, 70)
        assert pct == _d("70.00")
        assert "WARNING" in desc

    def test_critical_coverage(self):
        pct, desc = check_normalisation_coverage(100, 40)
        assert pct == _d("40.00")
        assert "CRITICAL" in desc

    def test_zero_transactions(self):
        pct, desc = check_normalisation_coverage(0, 0)
        assert pct == _d("100.00")
        assert "No transactions" in desc

    def test_boundary_80_percent(self):
        pct, desc = check_normalisation_coverage(100, 80)
        assert pct == _d("80.00")
        assert "OK" in desc

    def test_boundary_just_below_80(self):
        pct, desc = check_normalisation_coverage(100, 79)
        assert pct == _d("79.00")
        assert "WARNING" in desc


# ===========================================================================
# Fair Value Coverage
# ===========================================================================

class TestCheckFairValueCoverage:
    def test_full_coverage(self):
        pct, desc = check_fair_value_coverage(50, 50)
        assert pct == _d("100.00")
        assert "OK" in desc

    def test_critical_coverage(self):
        pct, desc = check_fair_value_coverage(100, 30)
        assert pct == _d("30.00")
        assert "CRITICAL" in desc

    def test_zero_models(self):
        pct, desc = check_fair_value_coverage(0, 0)
        assert pct == _d("100.00")


# ===========================================================================
# Signal Freshness
# ===========================================================================

class TestCheckSignalFreshness:
    def test_fresh_signal(self):
        now = datetime.now(timezone.utc)
        latest = now - timedelta(hours=2)
        hours, desc = check_signal_freshness(latest, now)
        assert hours == 2
        assert "OK" in desc

    def test_stale_warning(self):
        now = datetime.now(timezone.utc)
        latest = now - timedelta(hours=30)
        hours, desc = check_signal_freshness(latest, now)
        assert hours == 30
        assert "WARNING" in desc

    def test_stale_critical(self):
        now = datetime.now(timezone.utc)
        latest = now - timedelta(hours=80)
        hours, desc = check_signal_freshness(latest, now)
        assert hours == 80
        assert "CRITICAL" in desc

    def test_no_signals(self):
        now = datetime.now(timezone.utc)
        hours, desc = check_signal_freshness(None, now)
        assert hours == -1
        assert "CRITICAL" in desc

    def test_boundary_24h(self):
        now = datetime.now(timezone.utc)
        latest = now - timedelta(hours=24)
        hours, desc = check_signal_freshness(latest, now)
        assert hours == 24
        assert "OK" in desc  # must exceed, not equal

    def test_boundary_just_over_24h(self):
        now = datetime.now(timezone.utc)
        latest = now - timedelta(hours=25)
        hours, desc = check_signal_freshness(latest, now)
        assert hours == 25
        assert "WARNING" in desc


# ===========================================================================
# SystemHealthReport
# ===========================================================================

class TestSystemHealthReport:
    def test_healthy_report(self):
        report = SystemHealthReport(
            scraper_health={"overall_status": "healthy", "issues": []},
            normalisation_coverage_pct=_d("95.00"),
            fair_value_coverage_pct=_d("90.00"),
            signal_freshness_hours=5,
        )
        assert report.overall_status == "healthy"

    def test_warning_from_coverage(self):
        report = SystemHealthReport(
            scraper_health={"overall_status": "healthy", "issues": []},
            normalisation_coverage_pct=_d("75.00"),
            fair_value_coverage_pct=_d("90.00"),
            signal_freshness_hours=5,
        )
        assert report.overall_status == "warning"

    def test_critical_from_signals(self):
        report = SystemHealthReport(
            scraper_health={"overall_status": "healthy", "issues": []},
            normalisation_coverage_pct=_d("95.00"),
            fair_value_coverage_pct=_d("90.00"),
            signal_freshness_hours=80,
        )
        assert report.overall_status == "critical"

    def test_critical_from_scraper(self):
        report = SystemHealthReport(
            scraper_health={"overall_status": "degraded", "issues": ["fail"]},
            normalisation_coverage_pct=_d("95.00"),
            fair_value_coverage_pct=_d("90.00"),
            signal_freshness_hours=5,
        )
        assert report.overall_status == "critical"

    def test_to_dict_has_all_keys(self):
        report = SystemHealthReport()
        d = report.to_dict()
        expected_keys = {
            "overall_status", "scraper_health",
            "normalisation_coverage_pct", "normalisation_description",
            "fair_value_coverage_pct", "fair_value_description",
            "signal_freshness_hours", "signal_freshness_description",
        }
        assert expected_keys == set(d.keys())


# ===========================================================================
# Alert Severity Classification
# ===========================================================================

class TestClassifyAlertSeverity:
    def test_info_low_divergence(self):
        assert classify_alert_severity(_d("2.0")) == AlertSeverity.INFO

    def test_warning_medium_divergence(self):
        assert classify_alert_severity(_d("5.0")) == AlertSeverity.WARNING

    def test_warning_mid_range(self):
        assert classify_alert_severity(_d("10.0")) == AlertSeverity.WARNING

    def test_critical_high_divergence(self):
        assert classify_alert_severity(_d("20.0")) == AlertSeverity.CRITICAL

    def test_boundary_just_below_5(self):
        assert classify_alert_severity(_d("4.99")) == AlertSeverity.INFO

    def test_boundary_exactly_15(self):
        assert classify_alert_severity(_d("15.0")) == AlertSeverity.WARNING

    def test_boundary_just_above_15(self):
        assert classify_alert_severity(_d("15.01")) == AlertSeverity.CRITICAL

    def test_zero_divergence(self):
        assert classify_alert_severity(_d("0")) == AlertSeverity.INFO


# ===========================================================================
# should_generate_alert
# ===========================================================================

class TestShouldGenerateAlert:
    def test_above_threshold(self):
        assert should_generate_alert(
            AlertType.PRICE_MOVEMENT, AlertSeverity.WARNING, _d("10"), _d("5")
        ) is True

    def test_below_threshold(self):
        assert should_generate_alert(
            AlertType.PRICE_MOVEMENT, AlertSeverity.INFO, _d("3"), _d("5")
        ) is False

    def test_exactly_at_threshold(self):
        assert should_generate_alert(
            AlertType.RECONCILIATION_DIVERGENCE, AlertSeverity.WARNING, _d("5"), _d("5")
        ) is False


# ===========================================================================
# Alert Formatting
# ===========================================================================

class TestFormatPriceMovementAlert:
    def test_price_increase(self):
        title, message = format_price_movement_alert(
            "Ferrari F40", _d(1500000), _d(1650000), _d("10.0")
        )
        assert "increased" in title
        assert "Ferrari F40" in title
        assert "$1,500,000" in message
        assert "$1,650,000" in message

    def test_price_decrease(self):
        title, message = format_price_movement_alert(
            "Porsche 911 GT3", _d(300000), _d(270000), _d("10.0")
        )
        assert "decreased" in title
        assert "Porsche 911 GT3" in title


class TestFormatHoldPeriodAlert:
    def test_hold_period_warning(self):
        title, message = format_hold_period_alert(
            "2020 Ferrari SF90 Stradale", 18, 12
        )
        assert "2020 Ferrari SF90 Stradale" in title
        assert "18 months" in message
        assert "12 months" in message
        assert "exit strategy" in message.lower()

    def test_hold_period_at_limit(self):
        title, message = format_hold_period_alert("1995 McLaren F1", 24, 24)
        assert "24 months" in message
