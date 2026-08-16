"""
Walk-forward validation for backtesting -- Module 10.

All functions are pure (no DB, no I/O).  The module splits a date range
into overlapping train/test windows and evaluates whether model weights
remain stable across those windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from dateutil.relativedelta import relativedelta

from aatp.core.logging import get_logger
from aatp.research.metrics import accuracy_rate

logger = get_logger("research.walk_forward")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class DateRange:
    """Inclusive date range."""

    start: date
    end: date


@dataclass
class WindowResult:
    """Per-window evaluation result."""

    window_index: int
    train_range: DateRange
    test_range: DateRange
    train_accuracy: Decimal
    test_accuracy: Decimal
    optimal_weights: dict[str, Decimal]


@dataclass
class WalkForwardResult:
    """Aggregate walk-forward result."""

    windows: list[WindowResult]
    per_window_accuracy: list[Decimal]
    weight_stability_score: Decimal
    recommended_weights: dict[str, Decimal]


# ---------------------------------------------------------------------------
# Window generation
# ---------------------------------------------------------------------------

def generate_windows(
    start_date: date,
    end_date: date,
    train_months: int = 12,
    test_months: int = 6,
) -> list[tuple[DateRange, DateRange]]:
    """Split ``[start_date, end_date]`` into sliding train/test windows.

    The first training window starts at *start_date* and spans
    *train_months*.  The test window immediately follows for
    *test_months*.  The next window slides forward by *test_months*.

    Returns a list of ``(train_range, test_range)`` tuples.  Windows whose
    test period would exceed *end_date* are dropped.
    """
    if train_months <= 0 or test_months <= 0:
        return []

    windows: list[tuple[DateRange, DateRange]] = []
    cursor = start_date

    while True:
        train_start = cursor
        train_end = train_start + relativedelta(months=train_months) - relativedelta(days=1)
        test_start = train_end + relativedelta(days=1)
        test_end = test_start + relativedelta(months=test_months) - relativedelta(days=1)

        if test_end > end_date:
            break

        windows.append((
            DateRange(start=train_start, end=train_end),
            DateRange(start=test_start, end=test_end),
        ))

        cursor = cursor + relativedelta(months=test_months)

    return windows


# ---------------------------------------------------------------------------
# Window evaluation
# ---------------------------------------------------------------------------

def evaluate_window(
    train_predictions: list[tuple[int, int]],
    test_predictions: list[tuple[int, int]],
) -> dict:
    """Compare accuracy between training and test sets for one window.

    Each prediction is ``(predicted_direction, actual_direction)``.

    Returns a dict with ``train_accuracy``, ``test_accuracy``, and
    ``overfit_gap`` (train - test).
    """
    train_preds = [p for p, _ in train_predictions]
    train_acts = [a for _, a in train_predictions]
    test_preds = [p for p, _ in test_predictions]
    test_acts = [a for _, a in test_predictions]

    train_acc = accuracy_rate(train_preds, train_acts)
    test_acc = accuracy_rate(test_preds, test_acts)

    return {
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "overfit_gap": train_acc - test_acc,
    }


# ---------------------------------------------------------------------------
# Weight stability
# ---------------------------------------------------------------------------

def assess_weight_stability(
    window_results: Sequence[dict[str, Decimal]],
) -> dict:
    """Assess how stable optimal weights are across walk-forward windows.

    *window_results* is a list of dicts mapping model-type strings to their
    optimal weight ``Decimal`` for that window.

    Returns:
        ``stability_score`` in [0, 1] (higher = more stable),
        ``mean_weights``, ``weight_std``, and ``is_stable`` (score >= 0.7).
    """
    if not window_results:
        return {
            "stability_score": Decimal("0"),
            "mean_weights": {},
            "weight_std": {},
            "is_stable": False,
        }

    # Gather all model types across all windows.
    all_keys: set[str] = set()
    for w in window_results:
        all_keys.update(w.keys())

    mean_weights: dict[str, Decimal] = {}
    weight_std: dict[str, Decimal] = {}

    for key in sorted(all_keys):
        values = [w.get(key, Decimal("0")) for w in window_results]
        n = Decimal(len(values))
        mean = sum(values) / n
        mean_weights[key] = mean.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        if len(values) > 1:
            var = sum((v - mean) ** 2 for v in values) / (n - Decimal("1"))
            std = var.sqrt()
        else:
            std = Decimal("0")
        weight_std[key] = std.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # Stability score: 1 - mean(std / mean) where mean != 0,
    # else 1 - std  (penalise any variation from zero).
    cvs: list[Decimal] = []
    for key in sorted(all_keys):
        m = mean_weights[key]
        s = weight_std[key]
        if m != 0:
            cvs.append(abs(s / m))
        else:
            cvs.append(s)

    if cvs:
        avg_cv = sum(cvs) / Decimal(len(cvs))
        stability = max(Decimal("0"), Decimal("1") - avg_cv)
    else:
        stability = Decimal("0")

    stability = stability.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    return {
        "stability_score": stability,
        "mean_weights": mean_weights,
        "weight_std": weight_std,
        "is_stable": stability >= Decimal("0.700"),
    }
