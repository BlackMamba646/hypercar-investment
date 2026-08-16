"""
Backtest performance metrics -- Module 10.

All functions are pure (no DB, no I/O).  Every percentage and ratio is
returned as ``Decimal`` for consistency with the rest of the platform.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Sequence

from aatp.core.logging import get_logger

logger = get_logger("research.metrics")

# Annualisation factor: sqrt(12) for monthly returns.
_SQRT_12 = Decimal(str(math.sqrt(12)))


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def accuracy_rate(
    predictions: Sequence[int],
    actuals: Sequence[int],
) -> Decimal:
    """Percentage of predictions whose direction matched the actual direction.

    Both *predictions* and *actuals* are sequences of ``-1 | 0 | 1``.
    Returns a ``Decimal`` in [0, 1].
    """
    if not predictions or not actuals or len(predictions) != len(actuals):
        return Decimal("0")
    correct = sum(1 for p, a in zip(predictions, actuals) if p == a)
    return (Decimal(correct) / Decimal(len(predictions))).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP,
    )


def precision(true_positives: int, false_positives: int) -> Decimal:
    """Precision = TP / (TP + FP).  Returns 0 when denominator is zero."""
    denom = true_positives + false_positives
    if denom == 0:
        return Decimal("0")
    return (Decimal(true_positives) / Decimal(denom)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP,
    )


def recall(true_positives: int, false_negatives: int) -> Decimal:
    """Recall = TP / (TP + FN).  Returns 0 when denominator is zero."""
    denom = true_positives + false_negatives
    if denom == 0:
        return Decimal("0")
    return (Decimal(true_positives) / Decimal(denom)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP,
    )


def f1_score(prec: Decimal, rec: Decimal) -> Decimal:
    """Harmonic mean of precision and recall.  Returns 0 when both are 0."""
    denom = prec + rec
    if denom == 0:
        return Decimal("0")
    return (Decimal("2") * prec * rec / denom).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP,
    )


def false_positive_rate(false_positives: int, true_negatives: int) -> Decimal:
    """FPR = FP / (FP + TN).  Returns 0 when denominator is zero."""
    denom = false_positives + true_negatives
    if denom == 0:
        return Decimal("0")
    return (Decimal(false_positives) / Decimal(denom)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP,
    )


# ---------------------------------------------------------------------------
# Return / risk metrics
# ---------------------------------------------------------------------------

def sharpe_ratio(
    returns: Sequence[Decimal],
    risk_free_rate: Decimal = Decimal("0.04"),
) -> Decimal:
    """Annualised Sharpe ratio for *monthly* returns.

    Formula: ``(mean_return - rf_monthly) / std_return * sqrt(12)``

    Returns ``Decimal("0")`` when the standard deviation is zero or when
    fewer than two data points are provided.
    """
    if len(returns) < 2:
        return Decimal("0")

    n = Decimal(len(returns))
    mean_ret = sum(returns) / n
    rf_monthly = risk_free_rate / Decimal("12")

    variance = sum((r - mean_ret) ** 2 for r in returns) / (n - Decimal("1"))
    try:
        std_ret = variance.sqrt()
    except (InvalidOperation, ValueError):
        return Decimal("0")

    if std_ret == 0:
        return Decimal("0")

    ratio = (mean_ret - rf_monthly) / std_ret * _SQRT_12
    return ratio.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def max_drawdown(cumulative_returns: Sequence[Decimal]) -> Decimal:
    """Largest peak-to-trough decline in *cumulative_returns*.

    Returns a **positive** ``Decimal`` representing the magnitude of the
    worst drawdown (e.g. ``Decimal("0.150")`` means -15%).  Returns 0 when
    there is no drawdown.
    """
    if not cumulative_returns:
        return Decimal("0")

    peak = cumulative_returns[0]
    worst = Decimal("0")

    for value in cumulative_returns:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak
            if dd > worst:
                worst = dd

    return worst.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def information_ratio(
    active_returns: Sequence[Decimal],
    tracking_error: Decimal,
) -> Decimal:
    """Information ratio = mean(active_returns) / tracking_error.

    Returns 0 when tracking error is zero or no data is supplied.
    """
    if not active_returns or tracking_error == 0:
        return Decimal("0")

    mean_active = sum(active_returns) / Decimal(len(active_returns))
    return (mean_active / tracking_error).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP,
    )


# ---------------------------------------------------------------------------
# Per-model validation
# ---------------------------------------------------------------------------

def per_model_validation(
    model_predictions: dict[str, list[tuple[int, int]]],
) -> dict[str, dict[str, Decimal]]:
    """Compute accuracy, precision, recall, and F1 per consensus model type.

    *model_predictions* maps a model-type string (e.g. ``"momentum"``) to a
    list of ``(predicted_direction, actual_direction)`` tuples where
    directions are ``-1 | 0 | 1``.

    Returns a dict keyed by model type with metric sub-dicts.
    """
    results: dict[str, dict[str, Decimal]] = {}

    for model_type, pairs in model_predictions.items():
        if not pairs:
            results[model_type] = {
                "accuracy": Decimal("0"),
                "precision": Decimal("0"),
                "recall": Decimal("0"),
                "f1": Decimal("0"),
            }
            continue

        preds = [p for p, _ in pairs]
        acts = [a for _, a in pairs]

        # For binary classification: positive = direction 1
        tp = sum(1 for p, a in pairs if p == 1 and a == 1)
        fp = sum(1 for p, a in pairs if p == 1 and a != 1)
        fn = sum(1 for p, a in pairs if p != 1 and a == 1)

        prec = precision(tp, fp)
        rec = recall(tp, fn)

        results[model_type] = {
            "accuracy": accuracy_rate(preds, acts),
            "precision": prec,
            "recall": rec,
            "f1": f1_score(prec, rec),
        }

    return results
