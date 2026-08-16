"""
Core backtest simulation runner -- Module 10.

Provides the ``BacktestRunner`` class that orchestrates a historical
simulation, and pure helper functions for signal-accuracy checking,
return-metric computation, and look-ahead-bias detection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import (
    AssetModel,
    BacktestModelValidation,
    BacktestRun,
    BacktestSignal,
    ConsensusModelType,
    FairValue,
    OpportunityStatus,
    Signal,
    SignalType,
    Transaction,
)
from aatp.research.metrics import (
    accuracy_rate,
    f1_score,
    false_positive_rate,
    max_drawdown,
    per_model_validation,
    precision,
    recall,
    sharpe_ratio,
)

logger = get_logger("research.backtest_runner")


# ---------------------------------------------------------------------------
# Parameters dataclass
# ---------------------------------------------------------------------------

@dataclass
class BacktestParams:
    """User-supplied parameters for a backtest run."""

    name: str
    start_date: date
    end_date: date
    step_months: int = 1
    model_ids: list[uuid.UUID] = field(default_factory=list)
    signal_weights: dict[str, Decimal] = field(default_factory=dict)
    consensus_threshold: int = 4
    description: str = ""


# ---------------------------------------------------------------------------
# Pure helper functions (no DB)
# ---------------------------------------------------------------------------

def compute_signal_accuracy(
    predictions: list[dict],
) -> dict:
    """Compare predicted vs actual direction across a list of signal dicts.

    Each dict must contain ``predicted_direction`` and ``was_correct``
    (bool or None).  Returns counts and an accuracy ``Decimal``.
    """
    evaluated = [p for p in predictions if p.get("was_correct") is not None]
    if not evaluated:
        return {
            "total": len(predictions),
            "evaluated": 0,
            "correct": 0,
            "incorrect": 0,
            "accuracy": Decimal("0"),
        }

    correct = sum(1 for p in evaluated if p["was_correct"])
    incorrect = len(evaluated) - correct

    return {
        "total": len(predictions),
        "evaluated": len(evaluated),
        "correct": correct,
        "incorrect": incorrect,
        "accuracy": (
            Decimal(correct) / Decimal(len(evaluated))
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
    }


def compute_return_metrics(
    returns: Sequence[Decimal],
) -> dict:
    """Descriptive statistics for a sequence of return percentages.

    Returns avg, median, std, min, max as ``Decimal`` values.
    """
    if not returns:
        return {
            "avg": Decimal("0"),
            "median": Decimal("0"),
            "std": Decimal("0"),
            "min": Decimal("0"),
            "max": Decimal("0"),
            "count": 0,
        }

    n = Decimal(len(returns))
    avg = sum(returns) / n

    sorted_rets = sorted(returns)
    mid = len(sorted_rets) // 2
    if len(sorted_rets) % 2 == 0:
        median = (sorted_rets[mid - 1] + sorted_rets[mid]) / Decimal("2")
    else:
        median = sorted_rets[mid]

    if len(returns) > 1:
        variance = sum((r - avg) ** 2 for r in returns) / (n - Decimal("1"))
        std = variance.sqrt()
    else:
        std = Decimal("0")

    return {
        "avg": avg.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "median": median.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "std": std.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "min": min(returns).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "max": max(returns).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        "count": len(returns),
    }


def check_look_ahead_bias(
    signal_date: date,
    data_dates: Sequence[date],
) -> bool:
    """Return ``True`` if any date in *data_dates* is **after** *signal_date*.

    This is a safety check to confirm that no future data leaked into a
    signal generated on *signal_date*.
    """
    return any(d > signal_date for d in data_dates)


# ---------------------------------------------------------------------------
# BacktestRunner (DB-aware orchestrator)
# ---------------------------------------------------------------------------

class BacktestRunner:
    """Run a historical backtest simulation.

    Usage::

        runner = BacktestRunner()
        result = await runner.run(session, params)
    """

    async def run(
        self,
        session: AsyncSession,
        params: BacktestParams,
    ) -> BacktestRun:
        """Execute the backtest and persist results.

        1. Create ``BacktestRun`` record (status=running).
        2. Step through time, generating signals at each step using only
           data available up to that date.
        3. Attach actual outcomes (6m, 12m, 24m returns).
        4. Compute aggregate metrics and update the run record.
        """
        run = BacktestRun(
            name=params.name,
            description=params.description,
            start_date=params.start_date,
            end_date=params.end_date,
            parameters={
                "step_months": params.step_months,
                "model_ids": [str(m) for m in params.model_ids],
                "signal_weights": {k: str(v) for k, v in params.signal_weights.items()},
                "consensus_threshold": params.consensus_threshold,
            },
            model_versions={},
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.flush()

        logger.info(
            "backtest_started",
            run_id=str(run.id),
            start=str(params.start_date),
            end=str(params.end_date),
        )

        try:
            signals = await self._simulate(session, run, params)
            await self._attach_outcomes(session, run, signals, params)
            await self._compute_aggregates(session, run, signals)
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            logger.error("backtest_failed", run_id=str(run.id), error=str(exc))
            raise
        finally:
            await session.flush()

        logger.info(
            "backtest_completed",
            run_id=str(run.id),
            signals=len(signals),
            accuracy=str(run.signal_accuracy_rate),
        )
        return run

    # ----- internal methods -------------------------------------------------

    async def _simulate(
        self,
        session: AsyncSession,
        run: BacktestRun,
        params: BacktestParams,
    ) -> list[BacktestSignal]:
        """Step through the date range and generate signals."""
        all_signals: list[BacktestSignal] = []
        current = params.start_date

        # Resolve target models once.
        if params.model_ids:
            stmt = select(AssetModel).where(AssetModel.id.in_(params.model_ids))
        else:
            stmt = select(AssetModel)
        result = await session.execute(stmt)
        models = list(result.scalars().all())

        while current <= params.end_date:
            for model in models:
                signal = await self._generate_signal_at_date(
                    session, run, model, current, params,
                )
                if signal is not None:
                    session.add(signal)
                    all_signals.append(signal)
            current = current + relativedelta(months=params.step_months)

        await session.flush()
        return all_signals

    async def _generate_signal_at_date(
        self,
        session: AsyncSession,
        run: BacktestRun,
        model: AssetModel,
        sim_date: date,
        params: BacktestParams,
    ) -> Optional[BacktestSignal]:
        """Generate a single signal for *model* at *sim_date*.

        Only data with dates <= *sim_date* is queried (no look-ahead bias).
        """
        # Fetch the most recent fair value on or before sim_date.
        fv_stmt = (
            select(FairValue)
            .where(
                and_(
                    FairValue.asset_model_id == model.id,
                    FairValue.valuation_date <= sim_date,
                ),
            )
            .order_by(FairValue.valuation_date.desc())
            .limit(1)
        )
        fv_result = await session.execute(fv_stmt)
        fair_value = fv_result.scalar_one_or_none()

        # Fetch transactions up to sim_date for price trend.
        txn_stmt = (
            select(Transaction)
            .where(
                and_(
                    Transaction.asset_model_id == model.id,
                    Transaction.transaction_date <= sim_date,
                ),
            )
            .order_by(Transaction.transaction_date.desc())
            .limit(24)
        )
        txn_result = await session.execute(txn_stmt)
        transactions = list(txn_result.scalars().all())

        if not fair_value and not transactions:
            return None

        # Verify no look-ahead bias.
        data_dates = [t.transaction_date for t in transactions]
        if fair_value:
            data_dates.append(fair_value.valuation_date)
        if check_look_ahead_bias(sim_date, data_dates):
            logger.warning(
                "look_ahead_bias_detected",
                model_id=str(model.id),
                sim_date=str(sim_date),
            )
            return None

        # Simple momentum-based signal: compare latest transaction price
        # to fair value mid.
        predicted_direction = 0
        predicted_return_pct = Decimal("0")

        if fair_value and transactions:
            latest_price = transactions[0].normalised_price_usd or transactions[0].total_price_usd
            if latest_price and fair_value.fair_value_mid and fair_value.fair_value_mid > 0:
                spread = (fair_value.fair_value_mid - latest_price) / fair_value.fair_value_mid
                predicted_return_pct = spread.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                if spread > Decimal("0.05"):
                    predicted_direction = 1  # undervalued -> buy
                elif spread < Decimal("-0.05"):
                    predicted_direction = -1  # overvalued -> sell
        elif transactions and len(transactions) >= 2:
            p_new = transactions[0].normalised_price_usd or transactions[0].total_price_usd
            p_old = transactions[1].normalised_price_usd or transactions[1].total_price_usd
            if p_new and p_old and p_old > 0:
                change = (p_new - p_old) / p_old
                predicted_return_pct = change.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                if change > Decimal("0.05"):
                    predicted_direction = 1
                elif change < Decimal("-0.05"):
                    predicted_direction = -1

        return BacktestSignal(
            backtest_run_id=run.id,
            asset_model_id=model.id,
            signal_date=sim_date,
            signal_type=SignalType.MOMENTUM,
            predicted_direction=predicted_direction,
            predicted_return_pct=predicted_return_pct,
            consensus_score=None,
            opportunity_status=None,
            signal_data={
                "fair_value_mid": str(fair_value.fair_value_mid) if fair_value else None,
                "latest_price": str(
                    transactions[0].normalised_price_usd or transactions[0].total_price_usd
                ) if transactions else None,
                "transaction_count": len(transactions),
            },
        )

    async def _attach_outcomes(
        self,
        session: AsyncSession,
        run: BacktestRun,
        signals: list[BacktestSignal],
        params: BacktestParams,
    ) -> None:
        """Attach actual 6m/12m/24m returns to each signal."""
        for signal in signals:
            for months, attr in [
                (6, "actual_return_6m_pct"),
                (12, "actual_return_12m_pct"),
                (24, "actual_return_24m_pct"),
            ]:
                future_date = signal.signal_date + relativedelta(months=months)
                fv_stmt = (
                    select(FairValue)
                    .where(
                        and_(
                            FairValue.asset_model_id == signal.asset_model_id,
                            FairValue.valuation_date <= future_date,
                        ),
                    )
                    .order_by(FairValue.valuation_date.desc())
                    .limit(1)
                )
                fv_result = await session.execute(fv_stmt)
                future_fv = fv_result.scalar_one_or_none()

                if future_fv and signal.signal_data.get("fair_value_mid"):
                    try:
                        base = Decimal(signal.signal_data["fair_value_mid"])
                        if base > 0:
                            ret = (
                                (future_fv.fair_value_mid - base) / base
                            ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                            setattr(signal, attr, ret)
                    except Exception:
                        pass

            # Determine correctness based on 12-month return.
            if signal.actual_return_12m_pct is not None:
                actual_dir = (
                    1 if signal.actual_return_12m_pct > 0
                    else (-1 if signal.actual_return_12m_pct < 0 else 0)
                )
                signal.was_correct = signal.predicted_direction == actual_dir

    async def _compute_aggregates(
        self,
        session: AsyncSession,
        run: BacktestRun,
        signals: list[BacktestSignal],
    ) -> None:
        """Compute and set aggregate metrics on the BacktestRun."""
        predictions = [
            {
                "predicted_direction": s.predicted_direction,
                "was_correct": s.was_correct,
            }
            for s in signals
        ]
        accuracy_result = compute_signal_accuracy(predictions)

        run.total_opportunities_flagged = len(signals)
        run.actionable_opportunities = sum(
            1 for s in signals if s.predicted_direction != 0
        )
        run.signal_accuracy_rate = accuracy_result["accuracy"]

        returns_12m = [
            s.actual_return_12m_pct
            for s in signals
            if s.actual_return_12m_pct is not None
        ]

        if returns_12m:
            ret_metrics = compute_return_metrics(returns_12m)
            run.avg_return_pct = ret_metrics["avg"]
            run.median_return_pct = ret_metrics["median"]

            # Sharpe on monthly-equivalent returns (approximate).
            run.sharpe_ratio = sharpe_ratio(returns_12m)

            # Max drawdown from cumulative returns.
            cum = []
            running = Decimal("1")
            for r in returns_12m:
                running = running * (Decimal("1") + r)
                cum.append(running)
            run.max_drawdown_pct = max_drawdown(cum)

            run.return_distribution = {
                "min": str(ret_metrics["min"]),
                "max": str(ret_metrics["max"]),
                "std": str(ret_metrics["std"]),
                "count": ret_metrics["count"],
            }

        # False positive rate.
        evaluated = [s for s in signals if s.was_correct is not None]
        fp = sum(
            1 for s in evaluated
            if s.predicted_direction != 0 and not s.was_correct
        )
        tn = sum(
            1 for s in evaluated
            if s.predicted_direction == 0 and (s.was_correct or s.was_correct is None)
        )
        run.false_positive_rate = false_positive_rate(fp, tn)
