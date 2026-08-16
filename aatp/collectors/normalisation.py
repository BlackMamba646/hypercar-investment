"""
Price normalisation pipeline.

Takes raw transaction data and applies systematic adjustments to produce
normalised_price_usd — a comparable value that accounts for:
1. Mileage (low mileage premium, high mileage discount)
2. Colour tier (Tier 1 neutral, Tier 2/3 discounted)
3. Options (desirable options add value)
4. Geography and currency
5. Provenance (books, tools, single owner, celebrity)
6. Condition (from NLP grading of auction descriptions)

Each adjustment is stored as a percentage on the transaction record so the
full breakdown is always visible and auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aatp.core.logging import get_logger
from aatp.db.models import (
    ColourSpec,
    ColourTier,
    ConditionGrade,
    CurrencyRate,
    MileageCurve,
    Transaction,
)

logger = get_logger("collectors.normalisation")


@dataclass
class NormalisationResult:
    normalised_price_usd: Decimal
    mileage_adjustment_pct: Decimal
    colour_adjustment_pct: Decimal
    options_adjustment_pct: Decimal
    geography_adjustment_pct: Decimal
    provenance_adjustment_pct: Decimal
    condition_adjustment_pct: Decimal


# -----------------------------------------------------------------------
# Default adjustment tables (used when model-specific curves aren't available)
# -----------------------------------------------------------------------

DEFAULT_MILEAGE_BANDS = [
    (0, 500, Decimal("5.0")),         # Delivery miles — premium
    (500, 1000, Decimal("3.0")),      # Sub-1k — strong premium
    (1000, 3000, Decimal("1.0")),     # Low mileage — slight premium
    (3000, 5000, Decimal("0.0")),     # Baseline
    (5000, 10000, Decimal("-2.0")),   # Moderate use
    (10000, 20000, Decimal("-5.0")),  # Higher mileage for a hypercar
    (20000, 50000, Decimal("-10.0")), # Very high
    (50000, 999999, Decimal("-15.0")),
]

COLOUR_TIER_ADJUSTMENTS = {
    ColourTier.TIER_1: Decimal("0.0"),
    ColourTier.TIER_2: Decimal("-3.0"),
    ColourTier.TIER_3: Decimal("-8.0"),
}

CONDITION_ADJUSTMENTS = {
    ConditionGrade.CONCOURS: Decimal("8.0"),
    ConditionGrade.EXCELLENT: Decimal("3.0"),
    ConditionGrade.GOOD: Decimal("0.0"),
    ConditionGrade.FAIR: Decimal("-8.0"),
    ConditionGrade.PROJECT: Decimal("-25.0"),
}

CONDITION_KEYWORDS = {
    ConditionGrade.CONCOURS: [
        "concours", "show quality", "museum quality", "best in class",
        "award winning", "pebble beach", "concorso",
    ],
    ConditionGrade.EXCELLENT: [
        "excellent condition", "exceptional", "pristine",
        "immaculate", "flawless", "perfect", "like new",
        "recently serviced", "fresh service", "just serviced",
    ],
    ConditionGrade.GOOD: [
        "good condition", "well maintained", "well kept",
        "nice example", "solid example", "presentable",
    ],
    ConditionGrade.FAIR: [
        "fair condition", "needs attention", "some wear",
        "driver quality", "patina", "used regularly",
        "minor issues", "cosmetic wear",
    ],
    ConditionGrade.PROJECT: [
        "project", "barn find", "needs restoration",
        "non running", "not running", "incomplete",
        "accident", "damage", "salvage",
    ],
}


class NormalisationPipeline:
    """Applies all normalisation adjustments to transactions."""

    def __init__(self, session: AsyncSession):
        self.db = session
        self._colour_cache: dict[str, ColourTier] = {}

    async def normalise_transaction(self, tx: Transaction) -> NormalisationResult:
        """Apply all adjustments to a single transaction."""
        if tx.total_price_usd is None and tx.total_price is None:
            raise ValueError(f"Transaction {tx.id} has no price data")

        base_price_usd = tx.total_price_usd
        if base_price_usd is None:
            base_price_usd = await self._convert_to_usd(
                tx.total_price, tx.currency, tx.transaction_date
            )
            tx.total_price_usd = base_price_usd
            tx.exchange_rate_used = (
                base_price_usd / tx.total_price if tx.total_price else None
            )

        mileage_adj = await self._mileage_adjustment(tx)
        colour_adj = await self._colour_adjustment(tx)
        options_adj = self._options_adjustment(tx)
        geo_adj = self._geography_adjustment(tx)
        prov_adj = self._provenance_adjustment(tx)
        condition_adj = self._condition_adjustment(tx)

        total_adj = (
            mileage_adj + colour_adj + options_adj +
            geo_adj + prov_adj + condition_adj
        )

        # Normalised price = base price adjusted back to "standard spec"
        # If a car has low mileage (+5%), the normalised price removes that premium
        # so all cars are comparable at the same baseline
        normalised = base_price_usd / (Decimal("1") + total_adj / Decimal("100"))

        result = NormalisationResult(
            normalised_price_usd=normalised.quantize(Decimal("0.01")),
            mileage_adjustment_pct=mileage_adj,
            colour_adjustment_pct=colour_adj,
            options_adjustment_pct=options_adj,
            geography_adjustment_pct=geo_adj,
            provenance_adjustment_pct=prov_adj,
            condition_adjustment_pct=condition_adj,
        )

        # Write results back to the transaction
        tx.normalised_price_usd = result.normalised_price_usd
        tx.mileage_adjustment_pct = result.mileage_adjustment_pct
        tx.colour_adjustment_pct = result.colour_adjustment_pct
        tx.options_adjustment_pct = result.options_adjustment_pct
        tx.geography_adjustment_pct = result.geography_adjustment_pct
        tx.provenance_adjustment_pct = result.provenance_adjustment_pct
        tx.condition_adjustment_pct = result.condition_adjustment_pct

        return result

    async def normalise_batch(self, transactions: list[Transaction]) -> int:
        """Normalise a batch of transactions. Returns count of successfully normalised."""
        normalised_count = 0
        for tx in transactions:
            try:
                await self.normalise_transaction(tx)
                normalised_count += 1
            except Exception as e:
                logger.warning("normalisation_failed", tx_id=str(tx.id), error=str(e))
        return normalised_count

    # -------------------------------------------------------------------
    # Individual adjustments
    # -------------------------------------------------------------------

    async def _mileage_adjustment(self, tx: Transaction) -> Decimal:
        """Mileage adjustment: low mileage = premium, high = discount."""
        if tx.mileage is None:
            return Decimal("0")

        mileage = tx.mileage
        if tx.mileage_unit == "km":
            mileage = int(mileage * 0.621371)

        # Try model-specific curves first
        result = await self.db.execute(
            select(MileageCurve).where(
                MileageCurve.asset_model_id == tx.asset_model_id,
                MileageCurve.mileage_lower <= mileage,
                MileageCurve.mileage_upper > mileage,
            ).limit(1)
        )
        curve = result.scalar_one_or_none()
        if curve:
            return curve.adjustment_pct

        # Fall back to defaults
        for lower, upper, adj in DEFAULT_MILEAGE_BANDS:
            if lower <= mileage < upper:
                return adj

        return Decimal("-15.0")

    async def _colour_adjustment(self, tx: Transaction) -> Decimal:
        """Colour tier adjustment based on exterior colour."""
        if tx.colour_tier is not None:
            return COLOUR_TIER_ADJUSTMENTS.get(tx.colour_tier, Decimal("0"))

        if tx.colour_exterior is None:
            return Decimal("0")

        tier = await self._lookup_colour_tier(tx.colour_exterior, tx.asset_model_id)
        if tier is not None:
            tx.colour_tier = tier
            return COLOUR_TIER_ADJUSTMENTS.get(tier, Decimal("0"))

        # Heuristic fallback
        colour_lower = tx.colour_exterior.lower()
        tier_1_patterns = ["rosso", "nero", "black", "red", "grigio", "silver", "blu", "blue"]
        tier_3_patterns = ["tailor made", "custom", "matte", "satin"]

        for pattern in tier_3_patterns:
            if pattern in colour_lower:
                tx.colour_tier = ColourTier.TIER_3
                return Decimal("-8.0")

        for pattern in tier_1_patterns:
            if pattern in colour_lower:
                tx.colour_tier = ColourTier.TIER_1
                return Decimal("0.0")

        tx.colour_tier = ColourTier.TIER_2
        return Decimal("-3.0")

    async def _lookup_colour_tier(self, colour_name: str, model_id) -> ColourTier | None:
        """Look up colour tier from the colour_specs table."""
        cache_key = colour_name.lower().strip()
        if cache_key in self._colour_cache:
            return self._colour_cache[cache_key]

        from aatp.db.models import AssetModel
        model_result = await self.db.execute(
            select(AssetModel.manufacturer_id).where(AssetModel.id == model_id)
        )
        manufacturer_id = model_result.scalar_one_or_none()
        if manufacturer_id is None:
            return None

        result = await self.db.execute(
            select(ColourSpec.tier).where(
                ColourSpec.manufacturer_id == manufacturer_id,
                ColourSpec.colour_name.ilike(f"%{colour_name}%"),
            ).limit(1)
        )
        tier = result.scalar_one_or_none()
        if tier:
            self._colour_cache[cache_key] = tier
        return tier

    def _options_adjustment(self, tx: Transaction) -> Decimal:
        """Options adjustment based on desirable equipment."""
        if not tx.options:
            return Decimal("0")

        adj = Decimal("0")
        options_text = str(tx.options).lower()

        desirable = {
            "racing seat": Decimal("1.5"),
            "sport seat": Decimal("1.0"),
            "carbon fibre": Decimal("1.0"),
            "carbon fiber": Decimal("1.0"),
            "carbon ceramic": Decimal("1.5"),
            "lift system": Decimal("0.5"),
            "front lift": Decimal("0.5"),
            "camera": Decimal("0.3"),
            "telemetry": Decimal("0.5"),
            "stripe": Decimal("0.5"),
            "alcantara": Decimal("0.3"),
            "scuderia shields": Decimal("0.5"),
        }

        undesirable = {
            "aftermarket": Decimal("-2.0"),
            "modified": Decimal("-3.0"),
            "wrap": Decimal("-1.0"),
            "repaint": Decimal("-2.0"),
            "rebuilt": Decimal("-5.0"),
        }

        for keyword, value in desirable.items():
            if keyword in options_text:
                adj += value

        for keyword, value in undesirable.items():
            if keyword in options_text:
                adj += value

        return min(adj, Decimal("5.0"))

    def _geography_adjustment(self, tx: Transaction) -> Decimal:
        """Geography adjustment for regional price differentials."""
        if tx.sale_country is None:
            return Decimal("0")

        # US is baseline (0%), other markets adjust
        adjustments = {
            "US": Decimal("0"),
            "UK": Decimal("-2.0"),
            "AE": Decimal("-3.0"),    # UAE — no VAT but smaller buyer pool
            "DE": Decimal("-1.0"),
            "FR": Decimal("-1.0"),
            "IT": Decimal("-1.0"),
            "CH": Decimal("1.0"),     # Switzerland — strong prices
            "JP": Decimal("-2.0"),
            "AU": Decimal("-3.0"),
        }

        country = tx.sale_country.upper()
        if len(country) > 2:
            country_map = {
                "UNITED STATES": "US", "USA": "US",
                "UNITED KINGDOM": "UK", "ENGLAND": "UK",
                "UNITED ARAB EMIRATES": "AE", "UAE": "AE", "DUBAI": "AE",
                "GERMANY": "DE", "FRANCE": "FR", "ITALY": "IT",
                "SWITZERLAND": "CH", "JAPAN": "JP", "AUSTRALIA": "AU",
            }
            country = country_map.get(country, country)

        # RHD discount in LHD markets
        rhd_discount = Decimal("0")
        if tx.drive_side and tx.drive_side.upper() == "RHD":
            if country in ("US", "DE", "FR", "IT", "AE"):
                rhd_discount = Decimal("-7.0")

        return adjustments.get(country, Decimal("0")) + rhd_discount

    def _provenance_adjustment(self, tx: Transaction) -> Decimal:
        """Provenance adjustment for documentation, ownership history."""
        adj = Decimal("0")

        if tx.has_books is True:
            adj += Decimal("2.0")
        elif tx.has_books is False:
            adj -= Decimal("3.0")

        if tx.has_tools is True:
            adj += Decimal("0.5")

        if tx.service_history_complete is True:
            adj += Decimal("2.0")
        elif tx.service_history_complete is False:
            adj -= Decimal("4.0")

        if tx.single_owner is True:
            adj += Decimal("2.0")

        if tx.celebrity_provenance is True:
            adj += Decimal("5.0")

        # Check description for provenance keywords
        desc = (tx.lot_description or "").lower()
        if "classiche" in desc or "red book" in desc:
            adj += Decimal("3.0")
        if "matching numbers" in desc:
            adj += Decimal("2.0")
        if "accident" in desc or "damage history" in desc:
            adj -= Decimal("10.0")

        return adj

    def _condition_adjustment(self, tx: Transaction) -> Decimal:
        """Condition adjustment — grade from explicit field or NLP on description."""
        if tx.condition_grade is not None:
            return CONDITION_ADJUSTMENTS.get(tx.condition_grade, Decimal("0"))

        # NLP grading from lot description
        desc = (tx.lot_description or "").lower()
        if not desc:
            return Decimal("0")

        grade = _grade_condition_from_text(desc)
        if grade:
            tx.condition_grade = grade
            return CONDITION_ADJUSTMENTS.get(grade, Decimal("0"))

        return Decimal("0")

    async def _convert_to_usd(
        self, amount: Decimal, currency: str, tx_date: date
    ) -> Decimal:
        """Convert amount to USD using stored exchange rates."""
        if currency == "USD":
            return amount

        result = await self.db.execute(
            select(CurrencyRate.rate).where(
                CurrencyRate.base_currency == currency,
                CurrencyRate.quote_currency == "USD",
                CurrencyRate.rate_date <= tx_date,
            ).order_by(CurrencyRate.rate_date.desc()).limit(1)
        )
        rate = result.scalar_one_or_none()

        if rate is None:
            # Fallback rates — better than nothing but should be flagged
            fallback_rates = {
                "EUR": Decimal("1.08"),
                "GBP": Decimal("1.27"),
                "AED": Decimal("0.2723"),
                "CHF": Decimal("1.13"),
                "JPY": Decimal("0.0067"),
                "AUD": Decimal("0.66"),
            }
            rate = fallback_rates.get(currency)
            if rate is None:
                logger.warning("no_exchange_rate", currency=currency, date=str(tx_date))
                return amount

            logger.debug("using_fallback_rate", currency=currency, rate=str(rate))

        return (amount * rate).quantize(Decimal("0.01"))


def _grade_condition_from_text(text: str) -> ConditionGrade | None:
    """Simple keyword-based condition grading from descriptions."""
    # Check from worst to best — first match wins among negative grades,
    # but for positive grades we want the highest applicable
    for grade in [ConditionGrade.PROJECT, ConditionGrade.FAIR]:
        for keyword in CONDITION_KEYWORDS[grade]:
            if keyword in text:
                return grade

    for grade in [ConditionGrade.CONCOURS, ConditionGrade.EXCELLENT]:
        for keyword in CONDITION_KEYWORDS[grade]:
            if keyword in text:
                return grade

    for keyword in CONDITION_KEYWORDS[ConditionGrade.GOOD]:
        if keyword in text:
            return ConditionGrade.GOOD

    return None
