from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional

from aatp.core.logging import get_logger

logger = get_logger("execution.exit_strategy")

# ---------------------------------------------------------------------------
# Seller commission / fee schedules per exit channel
# ---------------------------------------------------------------------------

# RM Sotheby's: 10% seller commission for standard consignments
RM_SELLER_COMMISSION_PCT = Decimal("10")
# Bonhams: 10% seller commission
BONHAMS_SELLER_COMMISSION_PCT = Decimal("10")
# BaT: no seller commission (listing fee only)
BAT_LISTING_FEE = Decimal("99")
BAT_SUCCESS_FEE_PCT = Decimal("5")
BAT_SUCCESS_FEE_CAP = Decimal("5000")
# Private sale: minimal costs
PRIVATE_SALE_FEE = Decimal("2500")
# Dealer consignment: 5-8% commission
DEALER_CONSIGNMENT_PCT = Decimal("6.5")

# Value tier thresholds
HIGH_VALUE_THRESHOLD = Decimal("500000")
MID_VALUE_UPPER = Decimal("500000")
MID_VALUE_LOWER = Decimal("100000")


@dataclass
class ExitStrategy:
    """Recommended exit channel with estimated net proceeds."""

    channel: str
    estimated_net_proceeds: Decimal
    fees: Decimal
    preparation_checklist: List[str]
    timing_notes: str


@dataclass
class UpcomingEvent:
    """Simplified representation of an auction event for exit planning."""

    name: str
    event_date: date
    is_flagship: bool
    auction_house: str
    consignment_deadline: Optional[date] = None


def _calculate_rm_exit_fees(exit_price: Decimal) -> Decimal:
    """RM Sotheby's seller commission."""
    return (exit_price * RM_SELLER_COMMISSION_PCT / 100).quantize(Decimal("0.01"))


def _calculate_bonhams_exit_fees(exit_price: Decimal) -> Decimal:
    """Bonhams seller commission."""
    return (exit_price * BONHAMS_SELLER_COMMISSION_PCT / 100).quantize(
        Decimal("0.01")
    )


def _calculate_bat_exit_fees(exit_price: Decimal) -> Decimal:
    """BaT seller fees: listing fee + 5% success fee capped at $5,000."""
    success_fee = (exit_price * BAT_SUCCESS_FEE_PCT / 100).quantize(Decimal("0.01"))
    success_fee = min(success_fee, BAT_SUCCESS_FEE_CAP)
    return BAT_LISTING_FEE + success_fee


def _calculate_private_exit_fees(exit_price: Decimal) -> Decimal:
    """Private sale: flat legal/escrow fee."""
    return PRIVATE_SALE_FEE


def _calculate_dealer_exit_fees(exit_price: Decimal) -> Decimal:
    """Dealer consignment commission."""
    return (exit_price * DEALER_CONSIGNMENT_PCT / 100).quantize(Decimal("0.01"))


def generate_preparation_checklist(
    needs_certification: bool,
    needs_detailing: bool,
) -> List[str]:
    """Return a list of preparation steps for exit.

    Pure function -- no database access.
    """
    steps: List[str] = []

    # Always required
    steps.append("Commission professional photography (exterior, interior, engine bay, underside)")
    steps.append("Compile complete service history and ownership documentation")
    steps.append("Verify VIN plate and chassis numbers match documentation")

    if needs_certification:
        steps.append("Obtain manufacturer certification (e.g. Ferrari Classiche)")
        steps.append("Allow 3-6 months lead time for certification process")

    if needs_detailing:
        steps.append("Professional paint correction and ceramic coating")
        steps.append("Interior deep clean and leather conditioning")
        steps.append("Engine bay detailing")

    steps.append("Pre-sale mechanical inspection by marque specialist")
    steps.append("Address any outstanding maintenance items")
    steps.append("Prepare window sticker, books, tools, and accessories for presentation")

    return steps


def _find_upcoming_flagship(
    upcoming_events: List[UpcomingEvent],
    auction_house: str,
) -> Optional[UpcomingEvent]:
    """Find the next flagship event for a given auction house."""
    flagships = [
        e
        for e in upcoming_events
        if e.is_flagship and e.auction_house == auction_house
    ]
    if not flagships:
        return None
    return min(flagships, key=lambda e: e.event_date)


def _build_exit_strategy(
    channel: str,
    exit_price: Decimal,
    fees: Decimal,
    timing_notes: str,
    needs_certification: bool,
    needs_detailing: bool,
) -> ExitStrategy:
    net_proceeds = exit_price - fees
    checklist = generate_preparation_checklist(needs_certification, needs_detailing)
    return ExitStrategy(
        channel=channel,
        estimated_net_proceeds=net_proceeds,
        fees=fees,
        preparation_checklist=checklist,
        timing_notes=timing_notes,
    )


def recommend_exit_channel(
    asset_value: Decimal,
    hold_months: int,
    geography: str,
    upcoming_events: Optional[List[UpcomingEvent]] = None,
    needs_certification: bool = False,
    needs_detailing: bool = True,
) -> List[ExitStrategy]:
    """Recommend ranked exit strategies for a given asset.

    Pure function -- no database access.  Returns strategies sorted by
    estimated net proceeds (highest first).

    Parameters
    ----------
    asset_value:
        Estimated exit/sale price in USD.
    hold_months:
        How many months the asset has been (or will be) held.
    geography:
        Geography string (e.g. ``"US"``, ``"EU"``, ``"UK"``).
    upcoming_events:
        Optional list of upcoming auction events to consider for timing.
    needs_certification:
        Whether the asset requires manufacturer certification.
    needs_detailing:
        Whether pre-sale detailing is recommended.
    """
    if asset_value <= 0:
        return []

    events = upcoming_events or []
    strategies: List[ExitStrategy] = []

    # --- High value (>$500k): RM Sotheby's flagship preferred ---
    if asset_value >= HIGH_VALUE_THRESHOLD:
        rm_fees = _calculate_rm_exit_fees(asset_value)
        flagship = _find_upcoming_flagship(events, "RM Sotheby's")
        if flagship:
            timing = (
                f"Target {flagship.name} on {flagship.event_date.isoformat()}. "
                f"Consignment deadline: {flagship.consignment_deadline.isoformat() if flagship.consignment_deadline else 'TBC'}."
            )
        else:
            timing = (
                "Target next RM Sotheby's flagship event (Monterey Aug, "
                "Paris Feb, or London Oct). Contact consignment department "
                "6+ months in advance."
            )
        strategies.append(
            _build_exit_strategy(
                "rm_sothebys_flagship",
                asset_value,
                rm_fees,
                timing,
                needs_certification,
                needs_detailing,
            )
        )

    # --- Mid value ($100k-$500k): BaT or Bonhams ---
    if MID_VALUE_LOWER <= asset_value < MID_VALUE_UPPER:
        bat_fees = _calculate_bat_exit_fees(asset_value)
        strategies.append(
            _build_exit_strategy(
                "bat_auction",
                asset_value,
                bat_fees,
                "BaT auctions run 7 days. Best results with strong photography "
                "and detailed descriptions. Consider timing around peak "
                "enthusiasm (spring/early summer).",
                needs_certification,
                needs_detailing,
            )
        )

        bonhams_fees = _calculate_bonhams_exit_fees(asset_value)
        flagship = _find_upcoming_flagship(events, "Bonhams")
        if flagship:
            timing = f"Target {flagship.name} on {flagship.event_date.isoformat()}."
        else:
            timing = (
                "Target Bonhams scheduled sale. Contact consignment "
                "department 3+ months in advance."
            )
        strategies.append(
            _build_exit_strategy(
                "bonhams",
                asset_value,
                bonhams_fees,
                timing,
                needs_certification,
                needs_detailing,
            )
        )

    # --- Also offer RM for mid-value if not already added ---
    if MID_VALUE_LOWER <= asset_value < HIGH_VALUE_THRESHOLD:
        rm_fees = _calculate_rm_exit_fees(asset_value)
        strategies.append(
            _build_exit_strategy(
                "rm_sothebys",
                asset_value,
                rm_fees,
                "RM Sotheby's can handle mid-value lots but prioritise "
                "flagships for high-value consignments.",
                needs_certification,
                needs_detailing,
            )
        )

    # --- Sub-$100k: BaT primary ---
    if asset_value < MID_VALUE_LOWER:
        bat_fees = _calculate_bat_exit_fees(asset_value)
        strategies.append(
            _build_exit_strategy(
                "bat_auction",
                asset_value,
                bat_fees,
                "BaT is the premier online platform for sub-$100k collector "
                "cars. Strong results with good photography and documentation.",
                needs_certification,
                needs_detailing,
            )
        )

    # --- Always offer dealer consignment and private sale ---
    dealer_fees = _calculate_dealer_exit_fees(asset_value)
    strategies.append(
        _build_exit_strategy(
            "dealer_consignment",
            asset_value,
            dealer_fees,
            "Dealer handles marketing and sale. Typical 60-90 day consignment "
            "period. Best for assets needing expert presentation.",
            needs_certification,
            needs_detailing,
        )
    )

    private_fees = _calculate_private_exit_fees(asset_value)
    strategies.append(
        _build_exit_strategy(
            "private_sale",
            asset_value,
            private_fees,
            "Direct sale to known buyer or through collector network. "
            "Lowest fees but requires finding qualified buyer.",
            needs_certification,
            needs_detailing,
        )
    )

    # Hold period warnings
    if hold_months > 24:
        for s in strategies:
            s.timing_notes += (
                f" WARNING: Hold period ({hold_months} months) exceeds "
                f"24-month target -- consider accelerating exit."
            )

    # Sort by estimated net proceeds (highest first)
    strategies.sort(key=lambda s: s.estimated_net_proceeds, reverse=True)

    logger.info(
        "exit_strategies_scored",
        asset_value=str(asset_value),
        hold_months=hold_months,
        geography=geography,
        top_channel=strategies[0].channel if strategies else None,
        strategy_count=len(strategies),
    )
    return strategies
