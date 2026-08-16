"""
Ledger reconciliation — verify cost-basis integrity, ledger balances,
and P&L calculations against their constituent parts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from aatp.core.logging import get_logger

logger = get_logger("reconciliation.ledger_recon")

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def check_cost_basis_integrity(
    position_acquisition_price: Decimal,
    sum_of_cost_entries: Decimal,
    stored_total_cost_basis: Decimal,
) -> tuple[bool, Decimal, str]:
    """Verify that cost entries sum matches the stored total cost basis.

    Expected total = acquisition_price + sum_of_cost_entries.

    Returns
    -------
    (has_divergence, divergence_amount, description)
    """
    expected = (position_acquisition_price + sum_of_cost_entries).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    stored = stored_total_cost_basis.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    divergence = abs(expected - stored).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if divergence == Decimal("0.00"):
        return (
            False,
            Decimal("0.00"),
            f"Cost basis matches: expected={expected}, stored={stored}.",
        )

    return (
        True,
        divergence,
        f"Cost basis mismatch of ${divergence}: "
        f"expected={expected} (acquisition={position_acquisition_price} + "
        f"costs={sum_of_cost_entries}), stored={stored}.",
    )


def check_ledger_balance(
    ledger_entries_sum: Decimal,
    expected_total: Decimal,
) -> tuple[bool, Decimal, str]:
    """Verify that ledger entries sum to the expected total.

    Returns
    -------
    (has_divergence, divergence_amount, description)
    """
    actual = ledger_entries_sum.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    expected = expected_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    divergence = abs(actual - expected).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if divergence == Decimal("0.00"):
        return (
            False,
            Decimal("0.00"),
            f"Ledger balance matches: sum={actual}, expected={expected}.",
        )

    return (
        True,
        divergence,
        f"Ledger balance mismatch of ${divergence}: "
        f"sum={actual}, expected={expected}.",
    )


def check_pnl_integrity(
    fair_value: Decimal,
    cost_basis: Decimal,
    stored_unrealised_pnl: Decimal,
) -> tuple[bool, Decimal, str]:
    """Verify that stored unrealised P&L matches fair_value - cost_basis.

    Returns
    -------
    (has_divergence, divergence_amount, description)
    """
    expected_pnl = (fair_value - cost_basis).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    stored = stored_unrealised_pnl.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    divergence = abs(expected_pnl - stored).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if divergence == Decimal("0.00"):
        return (
            False,
            Decimal("0.00"),
            f"P&L matches: expected={expected_pnl}, stored={stored}.",
        )

    return (
        True,
        divergence,
        f"P&L mismatch of ${divergence}: "
        f"expected={expected_pnl} (fair_value={fair_value} - cost_basis={cost_basis}), "
        f"stored={stored}.",
    )


@dataclass
class LedgerReconciliationResult:
    """Aggregated result of a ledger-reconciliation run."""

    positions_checked: int = 0
    cost_basis_divergences: int = 0
    ledger_balance_divergences: int = 0
    pnl_divergences: int = 0
    divergences: list[dict] = field(default_factory=list)

    @property
    def total_divergences(self) -> int:
        return (
            self.cost_basis_divergences
            + self.ledger_balance_divergences
            + self.pnl_divergences
        )

    def add_divergence(
        self,
        position_id: str,
        check_type: str,
        divergence_amount: Decimal,
        description: str,
    ) -> None:
        self.divergences.append(
            {
                "position_id": position_id,
                "check_type": check_type,
                "divergence_amount": str(divergence_amount),
                "description": description,
            }
        )

    def to_dict(self) -> dict:
        return {
            "positions_checked": self.positions_checked,
            "cost_basis_divergences": self.cost_basis_divergences,
            "ledger_balance_divergences": self.ledger_balance_divergences,
            "pnl_divergences": self.pnl_divergences,
            "total_divergences": self.total_divergences,
            "divergences": self.divergences,
        }
