"""
Price reconciliation — compare stored normalised prices against
re-running normalisation to detect drift and data-integrity issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from aatp.core.logging import get_logger

logger = get_logger("reconciliation.price_recon")

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def check_price_divergence(
    stored_price: Decimal,
    recalculated_price: Decimal,
    threshold_pct: Decimal = Decimal("1.0"),
) -> tuple[bool, Decimal, str]:
    """Compare a stored normalised price against its recalculated value.

    Returns
    -------
    (has_divergence, divergence_pct, description)
        *has_divergence* is True when the absolute percentage difference
        exceeds *threshold_pct*.
    """
    if stored_price == Decimal("0") and recalculated_price == Decimal("0"):
        return (False, Decimal("0.00"), "Both prices are zero — no divergence.")

    if stored_price == Decimal("0"):
        return (
            True,
            Decimal("100.00"),
            f"Stored price is zero but recalculated price is {recalculated_price}.",
        )

    divergence_pct = (
        abs(recalculated_price - stored_price) / abs(stored_price) * Decimal("100")
    ).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

    has_divergence = divergence_pct > threshold_pct

    if has_divergence:
        description = (
            f"Price divergence of {divergence_pct}% detected "
            f"(stored={stored_price}, recalculated={recalculated_price}, "
            f"threshold={threshold_pct}%)."
        )
    else:
        description = (
            f"Price within tolerance ({divergence_pct}% vs {threshold_pct}% threshold)."
        )

    return (has_divergence, divergence_pct, description)


@dataclass
class PriceReconciliationResult:
    """Aggregated result of a price-reconciliation run."""

    transactions_checked: int = 0
    divergences_found: int = 0
    divergences: list[dict] = field(default_factory=list)

    def add_divergence(
        self,
        transaction_id: str,
        stored_price: Decimal,
        recalculated_price: Decimal,
        divergence_pct: Decimal,
        description: str,
    ) -> None:
        self.divergences.append(
            {
                "transaction_id": transaction_id,
                "stored_price": str(stored_price),
                "recalculated_price": str(recalculated_price),
                "divergence_pct": str(divergence_pct),
                "description": description,
            }
        )
        self.divergences_found += 1

    def to_dict(self) -> dict:
        return {
            "transactions_checked": self.transactions_checked,
            "divergences_found": self.divergences_found,
            "divergences": self.divergences,
        }
