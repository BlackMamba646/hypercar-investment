"""
Celery tasks for reconciliation and system health monitoring.

Runs daily reconciliation checks and hourly health monitoring,
recording results and generating alerts as needed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aatp.core.celery_app import app
from aatp.core.logging import get_logger
from aatp.db.session import async_session_factory

logger = get_logger("reconciliation.tasks")


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(
    bind=True,
    name="aatp.reconciliation.tasks.run_daily_reconciliation",
    max_retries=1,
)
def run_daily_reconciliation(self):
    """Run all reconciliation checks — price, ledger, and cost-basis integrity."""

    async def _run():
        from decimal import Decimal

        from sqlalchemy import func, select

        from aatp.db.models import (
            Alert,
            AlertSeverity,
            AlertType,
            CostEntry,
            LedgerEntry,
            Position,
            PositionStatus,
            ReconciliationRun,
            Transaction,
        )
        from aatp.reconciliation.alert_service import classify_alert_severity
        from aatp.reconciliation.ledger_recon import (
            LedgerReconciliationResult,
            check_cost_basis_integrity,
            check_ledger_balance,
            check_pnl_integrity,
        )
        from aatp.reconciliation.price_recon import (
            PriceReconciliationResult,
            check_price_divergence,
        )

        async with async_session_factory() as session:
            now = datetime.now(timezone.utc)
            price_result = PriceReconciliationResult()
            ledger_result = LedgerReconciliationResult()
            alerts_generated = 0

            # --- Price reconciliation ---
            tx_query = select(Transaction).where(
                Transaction.normalised_price_usd.isnot(None)
            ).limit(1000)
            rows = await session.execute(tx_query)
            transactions = list(rows.scalars().all())
            price_result.transactions_checked = len(transactions)

            for tx in transactions:
                if tx.total_price_usd and tx.normalised_price_usd:
                    has_div, div_pct, desc = check_price_divergence(
                        tx.normalised_price_usd, tx.total_price_usd
                    )
                    if has_div:
                        price_result.add_divergence(
                            str(tx.id), tx.normalised_price_usd,
                            tx.total_price_usd, div_pct, desc,
                        )

            # --- Ledger reconciliation ---
            pos_query = select(Position).where(
                Position.status == PositionStatus.OPEN
            )
            rows = await session.execute(pos_query)
            positions = list(rows.scalars().all())
            ledger_result.positions_checked = len(positions)

            for pos in positions:
                # Cost basis check
                cost_query = select(func.coalesce(func.sum(CostEntry.amount_usd), Decimal("0"))).where(
                    CostEntry.position_id == pos.id
                )
                cost_sum_row = await session.execute(cost_query)
                cost_sum = cost_sum_row.scalar() or Decimal("0")

                if pos.total_cost_basis is not None:
                    has_div, div_amt, desc = check_cost_basis_integrity(
                        pos.acquisition_price_usd, cost_sum, pos.total_cost_basis,
                    )
                    if has_div:
                        ledger_result.cost_basis_divergences += 1
                        ledger_result.add_divergence(str(pos.id), "cost_basis", div_amt, desc)

                # Ledger balance check
                ledger_query = select(func.coalesce(func.sum(LedgerEntry.amount_usd), Decimal("0"))).where(
                    LedgerEntry.position_id == pos.id
                )
                ledger_sum_row = await session.execute(ledger_query)
                ledger_sum = ledger_sum_row.scalar() or Decimal("0")

                if pos.total_cost_basis is not None:
                    has_div, div_amt, desc = check_ledger_balance(ledger_sum, pos.total_cost_basis)
                    if has_div:
                        ledger_result.ledger_balance_divergences += 1
                        ledger_result.add_divergence(str(pos.id), "ledger_balance", div_amt, desc)

                # P&L integrity check
                if pos.current_fair_value_usd is not None and pos.total_cost_basis is not None and pos.unrealised_pnl is not None:
                    has_div, div_amt, desc = check_pnl_integrity(
                        pos.current_fair_value_usd, pos.total_cost_basis, pos.unrealised_pnl,
                    )
                    if has_div:
                        ledger_result.pnl_divergences += 1
                        ledger_result.add_divergence(str(pos.id), "pnl_integrity", div_amt, desc)

            # Generate alerts for divergences
            total_divergences = price_result.divergences_found + ledger_result.total_divergences
            if total_divergences > 0:
                severity = classify_alert_severity(
                    Decimal(str(min(total_divergences * 5, 100)))
                )
                alert = Alert(
                    alert_type=AlertType.RECONCILIATION_DIVERGENCE,
                    severity=severity,
                    title=f"Reconciliation found {total_divergences} divergence(s)",
                    message=(
                        f"Daily reconciliation detected {price_result.divergences_found} "
                        f"price divergences and {ledger_result.total_divergences} "
                        f"ledger divergences."
                    ),
                    data={
                        "price_recon": price_result.to_dict(),
                        "ledger_recon": ledger_result.to_dict(),
                    },
                )
                session.add(alert)
                alerts_generated = 1

            # Record reconciliation run
            recon_run = ReconciliationRun(
                run_type="daily_full",
                positions_checked=ledger_result.positions_checked,
                divergences_found=total_divergences,
                alerts_generated=alerts_generated,
                details={
                    "price_recon": price_result.to_dict(),
                    "ledger_recon": ledger_result.to_dict(),
                },
                completed_at=datetime.now(timezone.utc),
            )
            session.add(recon_run)
            await session.commit()

            logger.info(
                "daily_reconciliation_complete",
                positions_checked=ledger_result.positions_checked,
                transactions_checked=price_result.transactions_checked,
                total_divergences=total_divergences,
                alerts_generated=alerts_generated,
            )

            return {
                "positions_checked": ledger_result.positions_checked,
                "transactions_checked": price_result.transactions_checked,
                "total_divergences": total_divergences,
                "alerts_generated": alerts_generated,
            }

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("daily_reconciliation_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=600)


@app.task(
    bind=True,
    name="aatp.reconciliation.tasks.run_health_check",
    max_retries=1,
)
def run_health_check(self):
    """Run system health monitoring checks."""

    async def _run():
        from datetime import timedelta

        from sqlalchemy import func, select

        from aatp.db.models import (
            AssetModel,
            FairValue,
            ScraperRun,
            Signal,
            Transaction,
        )
        from aatp.reconciliation.health_check import (
            SystemHealthReport,
            check_fair_value_coverage,
            check_normalisation_coverage,
            check_scraper_health,
            check_signal_freshness,
        )

        async with async_session_factory() as session:
            now = datetime.now(timezone.utc)

            # Scraper health
            cutoff = now - timedelta(days=7)
            scraper_query = select(ScraperRun).where(ScraperRun.started_at >= cutoff)
            rows = await session.execute(scraper_query)
            scraper_runs_raw = list(rows.scalars().all())

            scraper_runs = [
                {
                    "name": r.scraper_name,
                    "status": r.status,
                    "items_collected": r.items_collected,
                    "started_at": r.started_at,
                }
                for r in scraper_runs_raw
            ]
            scraper_health = check_scraper_health(scraper_runs)

            # Normalisation coverage
            total_tx_row = await session.execute(select(func.count(Transaction.id)))
            total_tx = total_tx_row.scalar() or 0
            normalised_row = await session.execute(
                select(func.count(Transaction.id)).where(
                    Transaction.normalised_price_usd.isnot(None)
                )
            )
            normalised_count = normalised_row.scalar() or 0
            norm_pct, norm_desc = check_normalisation_coverage(total_tx, normalised_count)

            # Fair value coverage
            total_models_row = await session.execute(select(func.count(AssetModel.id)))
            total_models = total_models_row.scalar() or 0
            valued_row = await session.execute(
                select(func.count(func.distinct(FairValue.asset_model_id)))
            )
            valued_count = valued_row.scalar() or 0
            fv_pct, fv_desc = check_fair_value_coverage(total_models, valued_count)

            # Signal freshness
            latest_signal_row = await session.execute(
                select(func.max(Signal.generated_at))
            )
            latest_signal = latest_signal_row.scalar()
            freshness_hours, freshness_desc = check_signal_freshness(latest_signal, now)

            report = SystemHealthReport(
                scraper_health=scraper_health,
                normalisation_coverage_pct=norm_pct,
                normalisation_description=norm_desc,
                fair_value_coverage_pct=fv_pct,
                fair_value_description=fv_desc,
                signal_freshness_hours=freshness_hours,
                signal_freshness_description=freshness_desc,
            )

            logger.info(
                "health_check_complete",
                overall_status=report.overall_status,
                normalisation_pct=str(norm_pct),
                fair_value_pct=str(fv_pct),
                signal_freshness_hours=freshness_hours,
            )

            return report.to_dict()

    try:
        return _run_async(_run())
    except Exception as exc:
        logger.error("health_check_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=120)
