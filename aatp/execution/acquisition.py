from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from aatp.core.logging import get_logger

logger = get_logger("execution.acquisition")

# ---------------------------------------------------------------------------
# Fee schedules
# ---------------------------------------------------------------------------

# BaT: 5% buyer premium, capped at $5,000
BAT_PREMIUM_PCT = Decimal("5")
BAT_PREMIUM_CAP = Decimal("5000")

# RM Sotheby's: tiered buyer premium
RM_TIER_1_LIMIT = Decimal("250000")
RM_TIER_1_PCT = Decimal("12.5")
RM_TIER_2_LIMIT = Decimal("1000000")
RM_TIER_2_PCT = Decimal("12")
RM_TIER_3_PCT = Decimal("10")

# Dealer: typical margin 5-10%
DEALER_MARGIN_LOW = Decimal("5")
DEALER_MARGIN_HIGH = Decimal("10")

# Private sale: minimal transaction fees (legal, escrow)
PRIVATE_SALE_FLAT_FEE = Decimal("2500")


@dataclass
class AcquisitionChannel:
    """Scored acquisition channel recommendation."""

    channel_name: str
    estimated_total_cost: Decimal
    buyer_premium_estimate: Decimal
    pros: List[str]
    cons: List[str]
    score: Decimal  # 0-100, higher is better


def _calculate_bat_premium(asset_value: Decimal) -> Decimal:
    """BaT buyer premium: 5% capped at $5,000."""
    premium = (asset_value * BAT_PREMIUM_PCT / 100).quantize(Decimal("0.01"))
    return min(premium, BAT_PREMIUM_CAP)


def _calculate_rm_premium(asset_value: Decimal) -> Decimal:
    """RM Sotheby's tiered buyer premium."""
    if asset_value <= RM_TIER_1_LIMIT:
        return (asset_value * RM_TIER_1_PCT / 100).quantize(Decimal("0.01"))

    premium = (RM_TIER_1_LIMIT * RM_TIER_1_PCT / 100).quantize(Decimal("0.01"))
    remaining = asset_value - RM_TIER_1_LIMIT

    if remaining <= (RM_TIER_2_LIMIT - RM_TIER_1_LIMIT):
        premium += (remaining * RM_TIER_2_PCT / 100).quantize(Decimal("0.01"))
        return premium

    premium += (
        (RM_TIER_2_LIMIT - RM_TIER_1_LIMIT) * RM_TIER_2_PCT / 100
    ).quantize(Decimal("0.01"))
    over_1m = asset_value - RM_TIER_2_LIMIT
    premium += (over_1m * RM_TIER_3_PCT / 100).quantize(Decimal("0.01"))
    return premium


def _calculate_dealer_premium(asset_value: Decimal) -> Decimal:
    """Dealer margin estimate: midpoint of 5-10%."""
    midpoint = (DEALER_MARGIN_LOW + DEALER_MARGIN_HIGH) / 2
    return (asset_value * midpoint / 100).quantize(Decimal("0.01"))


def _score_channel(
    total_cost: Decimal,
    price_discovery: Decimal,
    speed: Decimal,
    risk: Decimal,
) -> Decimal:
    """Weighted composite score (0-100).

    Weights: cost 40%, price_discovery 25%, speed 20%, risk 15%.
    Each input is 0-100 where 100 is best.
    """
    weighted = (
        total_cost * Decimal("0.40")
        + price_discovery * Decimal("0.25")
        + speed * Decimal("0.20")
        + risk * Decimal("0.15")
    )
    return weighted.quantize(Decimal("0.01"))


def recommend_acquisition_channel(
    asset_value: Decimal,
    geography: str,
    available_channels: Optional[List[str]] = None,
) -> List[AcquisitionChannel]:
    """Recommend ranked acquisition channels for a given asset value.

    Pure function -- no database access.  Returns a list of
    ``AcquisitionChannel`` sorted best-first by composite score.

    Parameters
    ----------
    asset_value:
        Estimated market value of the target asset in USD.
    geography:
        Geography string (e.g. ``"US"``, ``"EU"``, ``"UK"``).
    available_channels:
        Optional whitelist of channel names to consider.  When *None*,
        all four built-in channels are evaluated.
    """
    if asset_value <= 0:
        return []

    all_channels = {
        "bat_auction": _build_bat_channel,
        "rm_sothebys": _build_rm_channel,
        "dealer": _build_dealer_channel,
        "private_sale": _build_private_channel,
    }

    if available_channels is not None:
        filtered = {
            k: v for k, v in all_channels.items() if k in available_channels
        }
    else:
        filtered = all_channels

    results: List[AcquisitionChannel] = []
    for builder in filtered.values():
        results.append(builder(asset_value, geography))

    results.sort(key=lambda ch: ch.score, reverse=True)

    logger.info(
        "acquisition_channels_scored",
        asset_value=str(asset_value),
        geography=geography,
        top_channel=results[0].channel_name if results else None,
        channel_count=len(results),
    )
    return results


# ---------------------------------------------------------------------------
# Channel builders
# ---------------------------------------------------------------------------


def _build_bat_channel(
    asset_value: Decimal, geography: str
) -> AcquisitionChannel:
    premium = _calculate_bat_premium(asset_value)
    total = asset_value + premium

    # Cost score: BaT has low fees -- great for sub-$100k
    cost_ratio = premium / asset_value * 100
    cost_score = max(Decimal("0"), Decimal("100") - cost_ratio * 5)

    # Price discovery: good community, but ceiling limited
    if asset_value > Decimal("500000"):
        pd_score = Decimal("30")
    elif asset_value > Decimal("200000"):
        pd_score = Decimal("55")
    else:
        pd_score = Decimal("80")

    speed_score = Decimal("70")  # ~7-day auction format
    risk_score = Decimal("75")  # transparent, but online-only

    score = _score_channel(cost_score, pd_score, speed_score, risk_score)

    pros = [
        "Low buyer premium (5% capped at $5,000)",
        "Transparent bidding history",
        "Large enthusiast audience",
    ]
    cons = []
    if asset_value > Decimal("200000"):
        cons.append("Price ceiling limited for high-value assets")
    if geography != "US":
        cons.append("Primarily US-focused platform")
    if not cons:
        cons.append("Online-only, no physical preview")

    return AcquisitionChannel(
        channel_name="bat_auction",
        estimated_total_cost=total,
        buyer_premium_estimate=premium,
        pros=pros,
        cons=cons,
        score=score,
    )


def _build_rm_channel(
    asset_value: Decimal, geography: str
) -> AcquisitionChannel:
    premium = _calculate_rm_premium(asset_value)
    total = asset_value + premium

    cost_ratio = premium / asset_value * 100
    cost_score = max(Decimal("0"), Decimal("100") - cost_ratio * 3)

    # Price discovery: best for high-value assets
    if asset_value >= Decimal("500000"):
        pd_score = Decimal("95")
    elif asset_value >= Decimal("100000"):
        pd_score = Decimal("80")
    else:
        pd_score = Decimal("60")

    speed_score = Decimal("40")  # need to wait for flagship events
    risk_score = Decimal("85")  # established, global reach

    score = _score_channel(cost_score, pd_score, speed_score, risk_score)

    pros = [
        "Global reach and prestige",
        "Best price discovery for high-value assets",
        "Expert cataloguing and provenance verification",
    ]
    cons = ["Higher buyer premium (12.5% tiered)", "Must align with auction calendar"]
    if asset_value < Decimal("100000"):
        cons.append("May not attract top bidders for sub-$100k assets")

    return AcquisitionChannel(
        channel_name="rm_sothebys",
        estimated_total_cost=total,
        buyer_premium_estimate=premium,
        pros=pros,
        cons=cons,
        score=score,
    )


def _build_dealer_channel(
    asset_value: Decimal, geography: str
) -> AcquisitionChannel:
    premium = _calculate_dealer_premium(asset_value)
    total = asset_value + premium

    cost_ratio = premium / asset_value * 100
    cost_score = max(Decimal("0"), Decimal("100") - cost_ratio * 4)

    pd_score = Decimal("65")  # negotiable but less transparent
    speed_score = Decimal("85")  # can transact immediately
    risk_score = Decimal("70")  # depends on dealer reputation

    score = _score_channel(cost_score, pd_score, speed_score, risk_score)

    pros = [
        "Negotiable pricing",
        "Immediate availability",
        "Pre-purchase inspection possible",
        "Relationship-based, can access allocation",
    ]
    cons = [
        "Dealer margin embedded in price (5-10%)",
        "Less price transparency than auction",
    ]

    return AcquisitionChannel(
        channel_name="dealer",
        estimated_total_cost=total,
        buyer_premium_estimate=premium,
        pros=pros,
        cons=cons,
        score=score,
    )


def _build_private_channel(
    asset_value: Decimal, geography: str
) -> AcquisitionChannel:
    premium = PRIVATE_SALE_FLAT_FEE
    total = asset_value + premium

    cost_ratio = premium / asset_value * 100
    cost_score = max(Decimal("0"), Decimal("100") - cost_ratio * 5)

    pd_score = Decimal("40")  # no competitive bidding
    speed_score = Decimal("90")  # direct negotiation
    risk_score = Decimal("50")  # higher counterparty risk

    score = _score_channel(cost_score, pd_score, speed_score, risk_score)

    pros = [
        "Lowest transaction costs",
        "Direct negotiation",
        "No auction timeline constraints",
    ]
    cons = [
        "No price discovery from competitive bidding",
        "Higher counterparty risk",
        "Due diligence burden on buyer",
    ]

    return AcquisitionChannel(
        channel_name="private_sale",
        estimated_total_cost=total,
        buyer_premium_estimate=premium,
        pros=pros,
        cons=cons,
        score=score,
    )
