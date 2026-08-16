from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("execution.cost_calculator")

# ---------------------------------------------------------------------------
# Default cost assumptions (used when no explicit override is given)
# ---------------------------------------------------------------------------

DEFAULT_TRANSPORT = Decimal("3000.00")
DEFAULT_INSURANCE_ANNUAL_PCT = Decimal("1.25")
DEFAULT_STORAGE_MONTHLY = Decimal("800.00")
DEFAULT_PREPARATION = Decimal("5000.00")
DEFAULT_IMPORT_DUTY_PCT = Decimal("0")
DEFAULT_VAT_PCT = Decimal("0")

# Geography-specific import duty / VAT defaults
GEO_OVERRIDES: dict[str, dict[str, Decimal]] = {
    "US": {"import_duty_pct": Decimal("2.5"), "vat_pct": Decimal("0")},
    "UK": {"import_duty_pct": Decimal("6.5"), "vat_pct": Decimal("20")},
    "EU": {"import_duty_pct": Decimal("6.5"), "vat_pct": Decimal("19")},
    "JP": {"import_duty_pct": Decimal("0"), "vat_pct": Decimal("10")},
}


@dataclass
class AcquisitionCostBreakdown:
    """Itemised acquisition costs."""

    purchase_price: Decimal
    buyer_premium: Decimal
    transport: Decimal
    import_duty: Decimal
    vat: Decimal
    total: Decimal


@dataclass
class ExitCostBreakdown:
    """Itemised exit costs."""

    sale_price: Decimal
    seller_commission: Decimal
    preparation: Decimal
    total_fees: Decimal
    net_proceeds: Decimal


@dataclass
class RoundTripCost:
    """Full round-trip cost breakdown."""

    acquisition_price: Decimal
    exit_price: Decimal

    # Acquisition costs
    buyer_premium: Decimal
    transport: Decimal
    import_duty: Decimal
    vat: Decimal
    total_acquisition_costs: Decimal

    # Holding costs
    insurance_total: Decimal
    storage_total: Decimal
    total_holding_costs: Decimal
    hold_months: int

    # Exit costs
    seller_commission: Decimal
    preparation: Decimal
    total_exit_costs: Decimal

    # Totals
    total_all_costs: Decimal
    net_proceeds: Decimal
    gross_profit: Decimal
    net_profit: Decimal
    net_return_pct: Decimal


# ---------------------------------------------------------------------------
# Buyer premium calculators (per channel)
# ---------------------------------------------------------------------------


def _bat_buyer_premium(price: Decimal) -> Decimal:
    """BaT: 5% capped at $5,000."""
    premium = (price * Decimal("5") / 100).quantize(Decimal("0.01"))
    return min(premium, Decimal("5000"))


def _rm_buyer_premium(price: Decimal) -> Decimal:
    """RM Sotheby's: tiered -- 12.5% first $250k, 12% $250k-$1M, 10% above $1M."""
    tier_1_limit = Decimal("250000")
    tier_2_limit = Decimal("1000000")

    if price <= tier_1_limit:
        return (price * Decimal("12.5") / 100).quantize(Decimal("0.01"))

    premium = (tier_1_limit * Decimal("12.5") / 100).quantize(Decimal("0.01"))
    remaining = price - tier_1_limit

    if remaining <= (tier_2_limit - tier_1_limit):
        premium += (remaining * Decimal("12") / 100).quantize(Decimal("0.01"))
        return premium

    premium += (
        (tier_2_limit - tier_1_limit) * Decimal("12") / 100
    ).quantize(Decimal("0.01"))
    over_1m = price - tier_2_limit
    premium += (over_1m * Decimal("10") / 100).quantize(Decimal("0.01"))
    return premium


def _dealer_buyer_premium(price: Decimal) -> Decimal:
    """Dealer: average 7.5% margin already in price (estimate)."""
    return (price * Decimal("7.5") / 100).quantize(Decimal("0.01"))


def _private_buyer_premium(price: Decimal) -> Decimal:
    """Private sale: flat escrow/legal fee."""
    return Decimal("2500.00")


_BUYER_PREMIUM_FN = {
    "bat_auction": _bat_buyer_premium,
    "rm_sothebys": _rm_buyer_premium,
    "dealer": _dealer_buyer_premium,
    "private_sale": _private_buyer_premium,
}

# ---------------------------------------------------------------------------
# Seller commission calculators (per channel)
# ---------------------------------------------------------------------------


def _bat_seller_commission(price: Decimal) -> Decimal:
    """BaT seller: listing fee $99 + 5% success fee capped at $5,000."""
    success = (price * Decimal("5") / 100).quantize(Decimal("0.01"))
    return Decimal("99") + min(success, Decimal("5000"))


def _rm_seller_commission(price: Decimal) -> Decimal:
    """RM Sotheby's: 10% seller commission."""
    return (price * Decimal("10") / 100).quantize(Decimal("0.01"))


def _dealer_seller_commission(price: Decimal) -> Decimal:
    """Dealer consignment: 6.5%."""
    return (price * Decimal("6.5") / 100).quantize(Decimal("0.01"))


def _private_seller_commission(price: Decimal) -> Decimal:
    """Private sale: flat fee."""
    return Decimal("2500.00")


_SELLER_COMMISSION_FN = {
    "bat_auction": _bat_seller_commission,
    "rm_sothebys": _rm_seller_commission,
    "dealer": _dealer_seller_commission,
    "private_sale": _private_seller_commission,
}


# ---------------------------------------------------------------------------
# Public pure functions
# ---------------------------------------------------------------------------


def calculate_acquisition_cost(
    price: Decimal,
    channel: str,
    geography: str = "US",
    transport: Optional[Decimal] = None,
    import_duty_pct: Optional[Decimal] = None,
    vat_pct: Optional[Decimal] = None,
) -> AcquisitionCostBreakdown:
    """Calculate total cost to acquire an asset.

    Pure function -- no database access.
    """
    premium_fn = _BUYER_PREMIUM_FN.get(channel, _private_buyer_premium)
    buyer_premium = premium_fn(price)

    transport_cost = transport if transport is not None else DEFAULT_TRANSPORT

    geo = GEO_OVERRIDES.get(geography, {})
    duty_pct = (
        import_duty_pct
        if import_duty_pct is not None
        else geo.get("import_duty_pct", DEFAULT_IMPORT_DUTY_PCT)
    )
    _vat_pct = (
        vat_pct
        if vat_pct is not None
        else geo.get("vat_pct", DEFAULT_VAT_PCT)
    )

    import_duty = (price * duty_pct / 100).quantize(Decimal("0.01"))
    vat_amount = (price * _vat_pct / 100).quantize(Decimal("0.01"))

    total = price + buyer_premium + transport_cost + import_duty + vat_amount

    return AcquisitionCostBreakdown(
        purchase_price=price,
        buyer_premium=buyer_premium,
        transport=transport_cost,
        import_duty=import_duty,
        vat=vat_amount,
        total=total,
    )


def calculate_exit_cost(
    price: Decimal,
    channel: str,
    preparation: Optional[Decimal] = None,
) -> ExitCostBreakdown:
    """Calculate net proceeds from selling an asset.

    Pure function -- no database access.
    """
    commission_fn = _SELLER_COMMISSION_FN.get(channel, _private_seller_commission)
    seller_commission = commission_fn(price)

    prep = preparation if preparation is not None else DEFAULT_PREPARATION

    total_fees = seller_commission + prep
    net_proceeds = price - total_fees

    return ExitCostBreakdown(
        sale_price=price,
        seller_commission=seller_commission,
        preparation=prep,
        total_fees=total_fees,
        net_proceeds=net_proceeds,
    )


def calculate_round_trip_cost(
    acquisition_price: Decimal,
    exit_price: Decimal,
    hold_months: int,
    channel_in: str,
    channel_out: str,
    geography: str = "US",
    transport: Optional[Decimal] = None,
    insurance_annual_pct: Optional[Decimal] = None,
    storage_monthly: Optional[Decimal] = None,
    preparation: Optional[Decimal] = None,
    import_duty_pct: Optional[Decimal] = None,
    vat_pct: Optional[Decimal] = None,
) -> RoundTripCost:
    """Calculate complete round-trip cost of buying, holding, and selling.

    Pure function -- no database access.
    """
    # Acquisition
    acq = calculate_acquisition_cost(
        acquisition_price,
        channel_in,
        geography,
        transport=transport,
        import_duty_pct=import_duty_pct,
        vat_pct=vat_pct,
    )

    # Holding costs
    ins_pct = (
        insurance_annual_pct
        if insurance_annual_pct is not None
        else DEFAULT_INSURANCE_ANNUAL_PCT
    )
    stor_monthly = (
        storage_monthly if storage_monthly is not None else DEFAULT_STORAGE_MONTHLY
    )

    insurance_total = (
        acquisition_price * ins_pct / 100 * hold_months / 12
    ).quantize(Decimal("0.01"))
    storage_total = (stor_monthly * hold_months).quantize(Decimal("0.01"))
    total_holding = insurance_total + storage_total

    # Exit
    ext = calculate_exit_cost(exit_price, channel_out, preparation=preparation)

    # Aggregate
    total_acq_costs = acq.buyer_premium + acq.transport + acq.import_duty + acq.vat
    total_exit_costs = ext.seller_commission + ext.preparation
    total_all = total_acq_costs + total_holding + total_exit_costs

    gross_profit = exit_price - acquisition_price
    net_proceeds = exit_price - ext.seller_commission - ext.preparation
    net_profit = net_proceeds - acquisition_price - total_acq_costs - total_holding

    if acquisition_price + total_acq_costs + total_holding > 0:
        cost_basis = acquisition_price + total_acq_costs + total_holding
        net_return_pct = (net_profit / cost_basis * 100).quantize(Decimal("0.01"))
    else:
        net_return_pct = Decimal("0")

    result = RoundTripCost(
        acquisition_price=acquisition_price,
        exit_price=exit_price,
        buyer_premium=acq.buyer_premium,
        transport=acq.transport,
        import_duty=acq.import_duty,
        vat=acq.vat,
        total_acquisition_costs=total_acq_costs,
        insurance_total=insurance_total,
        storage_total=storage_total,
        total_holding_costs=total_holding,
        hold_months=hold_months,
        seller_commission=ext.seller_commission,
        preparation=ext.preparation,
        total_exit_costs=total_exit_costs,
        total_all_costs=total_all,
        net_proceeds=net_proceeds,
        gross_profit=gross_profit,
        net_profit=net_profit,
        net_return_pct=net_return_pct,
    )

    logger.info(
        "round_trip_cost_calculated",
        acquisition_price=str(acquisition_price),
        exit_price=str(exit_price),
        hold_months=hold_months,
        total_costs=str(total_all),
        net_return_pct=str(net_return_pct),
    )
    return result
