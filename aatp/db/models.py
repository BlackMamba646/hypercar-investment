"""
Complete database models for the Alternative Asset Trading Platform.

Schema covers all 10 modules and is asset-class agnostic — cars are the first
implementation but the same tables support watches, wine, whisky, art.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aatp.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AssetClass(str, enum.Enum):
    CAR = "car"
    WATCH = "watch"
    WINE = "wine"
    WHISKY = "whisky"
    ART = "art"


class TransactionSource(str, enum.Enum):
    BRING_A_TRAILER = "bring_a_trailer"
    RM_SOTHEBYS = "rm_sothebys"
    GOODING = "gooding"
    BONHAMS = "bonhams"
    CARS_AND_BIDS = "cars_and_bids"
    DEALER_LISTING = "dealer_listing"
    PRIVATE_SALE = "private_sale"
    MANUAL_ENTRY = "manual_entry"


class TransactionType(str, enum.Enum):
    AUCTION_SOLD = "auction_sold"
    AUCTION_NOT_SOLD = "auction_not_sold"
    DEALER_LISTING = "dealer_listing"
    DEALER_SOLD = "dealer_sold"
    PRIVATE_SALE = "private_sale"


class ColourTier(int, enum.Enum):
    TIER_1 = 1  # Rosso Corsa, Nero, standard blues — max liquidity
    TIER_2 = 2  # Giallo, other factory standard colours
    TIER_3 = 3  # Tailor Made / unusual colours — hurts liquidity


class ConditionGrade(str, enum.Enum):
    CONCOURS = "concours"
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    PROJECT = "project"


class SignalType(str, enum.Enum):
    MOMENTUM = "momentum"
    DEALER_AUCTION_SPREAD = "dealer_auction_spread"
    CATALYST = "catalyst"
    VOLUME_SPIKE = "volume_spike"
    COMPARABLE_APPRECIATION = "comparable_appreciation"
    PATTERN_MATCH = "pattern_match"


class ConsensusModelType(str, enum.Enum):
    MOMENTUM = "momentum"
    FUNDAMENTAL_VALUE = "fundamental_value"
    LIQUIDITY = "liquidity"
    SENTIMENT = "sentiment"
    MACRO = "macro"
    RULES = "rules"


class OpportunityStatus(str, enum.Enum):
    WATCHLIST = "watchlist"
    ACTIONABLE = "actionable"
    ACQUIRED = "acquired"
    PASSED = "passed"
    EXPIRED = "expired"


class PositionStatus(str, enum.Enum):
    OPEN = "open"
    PENDING_EXIT = "pending_exit"
    EXITED = "exited"


class CostCategory(str, enum.Enum):
    ACQUISITION_PREMIUM = "acquisition_premium"
    AUCTION_BUYER_PREMIUM = "auction_buyer_premium"
    SELLER_COMMISSION = "seller_commission"
    TRANSPORT = "transport"
    INSURANCE = "insurance"
    STORAGE = "storage"
    IMPORT_DUTY = "import_duty"
    TAX = "tax"
    MAINTENANCE = "maintenance"
    DETAILING = "detailing"
    PHOTOGRAPHY = "photography"
    CATALOGUE_FEE = "catalogue_fee"
    INSPECTION = "inspection"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class AlertType(str, enum.Enum):
    PRICE_MOVEMENT = "price_movement"
    CATALYST = "catalyst"
    AUCTION_RESULT = "auction_result"
    CONSENSUS_CHANGE = "consensus_change"
    HOLDING_COST_WARNING = "holding_cost_warning"
    HOLD_PERIOD_WARNING = "hold_period_warning"
    LIQUIDITY_WARNING = "liquidity_warning"
    RECONCILIATION_DIVERGENCE = "reconciliation_divergence"


class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RuleCategory(str, enum.Enum):
    IMPORT_ELIGIBILITY = "import_eligibility"
    TAX_TREATMENT = "tax_treatment"
    DRIVE_SIDE = "drive_side"
    HOMOLOGATION = "homologation"
    CERTIFICATION = "certification"
    AUCTION_RESTRICTION = "auction_restriction"
    MATERIALS_RESTRICTION = "materials_restriction"


class DealerTier(str, enum.Enum):
    ALLOCATION_ACCESS = "allocation_access"
    SECONDARY_PREMIUM = "secondary_premium"
    SECONDARY_STANDARD = "secondary_standard"


class AuctionHouseTier(str, enum.Enum):
    MAJOR = "major"      # RM Sotheby's, Gooding — highest hammer, highest fees
    MID = "mid"          # Bonhams
    ONLINE = "online"    # BaT, Cars and Bids — lower fee, lower ceiling


# ---------------------------------------------------------------------------
# MODULE 1: Asset Catalog & Market Data
# ---------------------------------------------------------------------------

class Manufacturer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manufacturers"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    country: Mapped[Optional[str]] = mapped_column(String(100))
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass), nullable=False, default=AssetClass.CAR)
    prestige_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 1))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    models: Mapped[list["AssetModel"]] = relationship(back_populates="manufacturer")


class AssetModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_models"
    __table_args__ = (
        UniqueConstraint("manufacturer_id", "name", "variant", name="uq_asset_model_identity"),
    )

    manufacturer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manufacturers.id"), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass), nullable=False, default=AssetClass.CAR)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    variant: Mapped[Optional[str]] = mapped_column(String(300))

    production_year_start: Mapped[Optional[int]] = mapped_column(SmallInteger)
    production_year_end: Mapped[Optional[int]] = mapped_column(SmallInteger)
    total_produced: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_liquid_supply: Mapped[Optional[int]] = mapped_column(Integer)
    known_destroyed: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    known_museum_held: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    is_open_top: Mapped[bool] = mapped_column(Boolean, default=False)
    is_limited_edition: Mapped[bool] = mapped_column(Boolean, default=False)
    is_invitation_only: Mapped[bool] = mapped_column(Boolean, default=False)
    engine_type: Mapped[Optional[str]] = mapped_column(String(100))
    engine_config: Mapped[Optional[str]] = mapped_column(String(100))
    msrp_at_launch: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    msrp_currency: Mapped[Optional[str]] = mapped_column(String(3))
    homologation_type: Mapped[Optional[str]] = mapped_column(String(100))

    variant_scarcity_multiplier: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), default=Decimal("1.00"))

    appreciation_stage: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    manufacturer: Mapped["Manufacturer"] = relationship(back_populates="models")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="asset_model")
    fair_values: Mapped[list["FairValue"]] = relationship(back_populates="asset_model")
    signals: Mapped[list["Signal"]] = relationship(back_populates="asset_model")
    consensus_scores: Mapped[list["ConsensusScore"]] = relationship(back_populates="asset_model")
    model_relationships: Mapped[list["AssetModelRelationship"]] = relationship(
        back_populates="source_model", foreign_keys="AssetModelRelationship.source_model_id"
    )


class AssetModelRelationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks relationships between models for comparable appreciation signals.
    e.g. F40 -> F50, 812 Superfast -> 812 GTS"""
    __tablename__ = "asset_model_relationships"
    __table_args__ = (
        UniqueConstraint("source_model_id", "related_model_id", name="uq_model_relationship"),
    )

    source_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    related_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_strength: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    source_model: Mapped["AssetModel"] = relationship(foreign_keys=[source_model_id], back_populates="model_relationships")
    related_model: Mapped["AssetModel"] = relationship(foreign_keys=[related_model_id])


class ColourSpec(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Colour classification and liquidity tier per manufacturer."""
    __tablename__ = "colour_specs"
    __table_args__ = (
        UniqueConstraint("manufacturer_id", "colour_name", name="uq_colour_per_manufacturer"),
    )

    manufacturer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manufacturers.id"), nullable=False)
    colour_name: Mapped[str] = mapped_column(String(200), nullable=False)
    colour_code: Mapped[Optional[str]] = mapped_column(String(50))
    tier: Mapped[ColourTier] = mapped_column(Enum(ColourTier), nullable=False)
    is_tailor_made: Mapped[bool] = mapped_column(Boolean, default=False)
    liquidity_adjustment_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))


class OptionSpec(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Factory options and their estimated value impact."""
    __tablename__ = "option_specs"

    manufacturer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manufacturers.id"), nullable=False)
    option_name: Mapped[str] = mapped_column(String(300), nullable=False)
    option_code: Mapped[Optional[str]] = mapped_column(String(50))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    value_impact_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    is_desirable_for_resale: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# MODULE 1: Transactions (scraped and normalised market data)
# ---------------------------------------------------------------------------

class DataProvenance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Full provenance record for every piece of collected data."""
    __tablename__ = "data_provenance"

    source: Mapped[TransactionSource] = mapped_column(Enum(TransactionSource), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    raw_content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    raw_html_path: Mapped[Optional[str]] = mapped_column(Text)
    parsed_content: Mapped[Optional[dict]] = mapped_column(JSONB)
    normalisations_applied: Mapped[Optional[dict]] = mapped_column(JSONB)
    scraper_version: Mapped[Optional[str]] = mapped_column(String(50))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_errors: Mapped[Optional[dict]] = mapped_column(JSONB)


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every observed market transaction — auction result, dealer listing, private sale."""
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_model_date", "asset_model_id", "transaction_date"),
        Index("ix_transactions_source_ext", "source", "external_id", unique=True),
    )

    provenance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("data_provenance.id"), nullable=False)
    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass), nullable=False, default=AssetClass.CAR)

    source: Mapped[TransactionSource] = mapped_column(Enum(TransactionSource), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(200))
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Raw price data
    hammer_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    buyer_premium: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    exchange_rate_used: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6))

    # Asset specifics (car-oriented but extensible via metadata)
    year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    mileage: Mapped[Optional[int]] = mapped_column(Integer)
    mileage_unit: Mapped[Optional[str]] = mapped_column(String(10), default="miles")
    colour_exterior: Mapped[Optional[str]] = mapped_column(String(200))
    colour_interior: Mapped[Optional[str]] = mapped_column(String(200))
    colour_tier: Mapped[Optional[ColourTier]] = mapped_column(Enum(ColourTier))
    condition_grade: Mapped[Optional[ConditionGrade]] = mapped_column(Enum(ConditionGrade))
    drive_side: Mapped[Optional[str]] = mapped_column(String(5))
    vin: Mapped[Optional[str]] = mapped_column(String(50))

    # Options and provenance
    options: Mapped[Optional[dict]] = mapped_column(JSONB)
    has_books: Mapped[Optional[bool]] = mapped_column(Boolean)
    has_tools: Mapped[Optional[bool]] = mapped_column(Boolean)
    service_history_complete: Mapped[Optional[bool]] = mapped_column(Boolean)
    single_owner: Mapped[Optional[bool]] = mapped_column(Boolean)
    celebrity_provenance: Mapped[Optional[bool]] = mapped_column(Boolean)
    provenance_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Geography
    sale_country: Mapped[Optional[str]] = mapped_column(String(100))
    sale_region: Mapped[Optional[str]] = mapped_column(String(100))
    auction_house: Mapped[Optional[str]] = mapped_column(String(200))
    auction_event: Mapped[Optional[str]] = mapped_column(String(300))
    dealer_name: Mapped[Optional[str]] = mapped_column(String(200))

    # Normalised price
    normalised_price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    mileage_adjustment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    colour_adjustment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    options_adjustment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    geography_adjustment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    provenance_adjustment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    condition_adjustment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))

    # Listing-specific (for dealer listings)
    listing_active: Mapped[Optional[bool]] = mapped_column(Boolean)
    listing_first_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    listing_last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    days_on_market: Mapped[Optional[int]] = mapped_column(Integer)

    lot_description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    asset_model: Mapped["AssetModel"] = relationship(back_populates="transactions")
    provenance: Mapped["DataProvenance"] = relationship()


class CurrencyRate(UUIDPrimaryKeyMixin, Base):
    """Daily currency exchange rates for cross-geography normalisation."""
    __tablename__ = "currency_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_currency_rate_day"),
    )

    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(100))


class NewsArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Editorial and manufacturer news relevant to asset pricing."""
    __tablename__ = "news_articles"
    __table_args__ = (
        Index("ix_news_published", "published_at"),
    )

    provenance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("data_provenance.id"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    article_type: Mapped[Optional[str]] = mapped_column(String(100))
    relevant_models: Mapped[Optional[dict]] = mapped_column(JSONB)
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    is_catalyst: Mapped[bool] = mapped_column(Boolean, default=False)
    catalyst_type: Mapped[Optional[str]] = mapped_column(String(100))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)


class ForumSentiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Aggregated forum/community sentiment per model per period."""
    __tablename__ = "forum_sentiments"
    __table_args__ = (
        UniqueConstraint("asset_model_id", "source_forum", "period_start", name="uq_forum_sentiment_period"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    source_forum: Mapped[str] = mapped_column(String(200), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    post_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_sentiment: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    mention_volume_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    notable_topics: Mapped[Optional[dict]] = mapped_column(JSONB)


class MacroIndicator(UUIDPrimaryKeyMixin, Base):
    """External macro data — luxury indices, art market, wealth data."""
    __tablename__ = "macro_indicators"
    __table_args__ = (
        UniqueConstraint("indicator_name", "indicator_date", name="uq_macro_indicator_date"),
    )

    indicator_name: Mapped[str] = mapped_column(String(200), nullable=False)
    indicator_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    source: Mapped[Optional[str]] = mapped_column(String(200))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)


# ---------------------------------------------------------------------------
# MODULE 2: Market Rules
# ---------------------------------------------------------------------------

class MarketRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structural rules that affect pricing, eligibility, and buyer pools."""
    __tablename__ = "market_rules"

    category: Mapped[RuleCategory] = mapped_column(Enum(RuleCategory), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(100))
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    rule_logic: Mapped[dict] = mapped_column(JSONB, nullable=False)
    impact_description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ImportEligibilityCalendar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """US 25-year import rule calendar — which models become eligible when."""
    __tablename__ = "import_eligibility_calendar"
    __table_args__ = (
        UniqueConstraint("asset_model_id", "jurisdiction", name="uq_import_eligibility_model"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False, default="US")
    manufacture_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    eligible_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    eligible_date: Mapped[date] = mapped_column(Date, nullable=False)
    rule_reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("market_rules.id"))
    estimated_price_impact_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)


class RuleModelFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a market rule to a specific model when the rule becomes relevant."""
    __tablename__ = "rule_model_flags"
    __table_args__ = (
        Index("ix_rule_flag_model", "asset_model_id"),
    )

    market_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("market_rules.id"), nullable=False)
    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    flag_reason: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    impact_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# MODULE 3: Fair Value Engine
# ---------------------------------------------------------------------------

class FairValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Point-in-time fair value estimate for a model."""
    __tablename__ = "fair_values"
    __table_args__ = (
        Index("ix_fair_value_model_date", "asset_model_id", "valuation_date"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    fair_value_low: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fair_value_mid: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fair_value_high: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    confidence_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    comparable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    comparable_window_months: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=12)

    appreciation_stage: Mapped[Optional[str]] = mapped_column(String(50))
    appreciation_rate_30d: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    appreciation_rate_90d: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    appreciation_rate_365d: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))

    methodology: Mapped[Optional[str]] = mapped_column(Text)
    comparable_transaction_ids: Mapped[Optional[dict]] = mapped_column(JSONB)
    model_parameters: Mapped[Optional[dict]] = mapped_column(JSONB)
    warnings: Mapped[Optional[dict]] = mapped_column(JSONB)

    asset_model: Mapped["AssetModel"] = relationship(back_populates="fair_values")


class MileageCurve(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mileage adjustment curves per model — maps mileage bands to price adjustments."""
    __tablename__ = "mileage_curves"
    __table_args__ = (
        UniqueConstraint("asset_model_id", "mileage_lower", name="uq_mileage_band"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    mileage_lower: Mapped[int] = mapped_column(Integer, nullable=False)
    mileage_upper: Mapped[int] = mapped_column(Integer, nullable=False)
    adjustment_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer)
    last_calibrated: Mapped[Optional[date]] = mapped_column(Date)


class CostModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Template cost assumptions for return modelling per geography/channel."""
    __tablename__ = "cost_models"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    geography: Mapped[str] = mapped_column(String(100), nullable=False)
    acquisition_channel: Mapped[str] = mapped_column(String(100), nullable=False)
    exit_channel: Mapped[str] = mapped_column(String(100), nullable=False)

    buyer_premium_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("12.500"))
    seller_commission_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("10.000"))
    insurance_annual_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("1.250"))
    storage_monthly: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("800.00"))
    transport_estimate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("3000.00"))
    preparation_estimate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("5000.00"))
    import_duty_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0.000"))
    vat_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0.000"))
    other_costs: Mapped[Optional[dict]] = mapped_column(JSONB)


# ---------------------------------------------------------------------------
# MODULE 4: Signal Engine
# ---------------------------------------------------------------------------

class Signal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Individual signals generated by the signal engine."""
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_model_type_date", "asset_model_id", "signal_type", "generated_at"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    strength: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    direction: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # -1, 0, +1
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    transaction_count: Mapped[Optional[int]] = mapped_column(Integer)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    asset_model: Mapped["AssetModel"] = relationship(back_populates="signals")


class OpportunityScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Composite opportunity score combining all active signals for a model."""
    __tablename__ = "opportunity_scores"
    __table_args__ = (
        Index("ix_opp_score_model_date", "asset_model_id", "scored_at"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    composite_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)

    liquidity_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    cost_adjusted_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    time_to_catalyst_days: Mapped[Optional[int]] = mapped_column(Integer)
    rule_flags: Mapped[Optional[dict]] = mapped_column(JSONB)

    status: Mapped[OpportunityStatus] = mapped_column(Enum(OpportunityStatus), nullable=False, default=OpportunityStatus.WATCHLIST)


# ---------------------------------------------------------------------------
# MODULE 5: Multi-Model Consensus Engine
# ---------------------------------------------------------------------------

class ConsensusModelScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Individual model score within the consensus engine."""
    __tablename__ = "consensus_model_scores"
    __table_args__ = (
        Index("ix_consensus_model_scored", "consensus_score_id", "model_type"),
    )

    consensus_score_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("consensus_scores.id"), nullable=False)
    model_type: Mapped[ConsensusModelType] = mapped_column(Enum(ConsensusModelType), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # -2 to +2
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        CheckConstraint("score >= -2 AND score <= 2", name="ck_consensus_score_range"),
        Index("ix_consensus_model_scored", "consensus_score_id", "model_type"),
    )

    consensus: Mapped["ConsensusScore"] = relationship(back_populates="model_scores")


class ConsensusScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Aggregated consensus across all six models for an asset model."""
    __tablename__ = "consensus_scores"
    __table_args__ = (
        Index("ix_consensus_model_date", "asset_model_id", "scored_at"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    aggregate_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    has_veto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    veto_model: Mapped[Optional[str]] = mapped_column(String(50))
    veto_reason: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[OpportunityStatus] = mapped_column(Enum(OpportunityStatus), nullable=False)
    disagreement_summary: Mapped[Optional[str]] = mapped_column(Text)
    actionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    model_scores: Mapped[list["ConsensusModelScore"]] = relationship(back_populates="consensus")
    asset_model: Mapped["AssetModel"] = relationship(back_populates="consensus_scores")


# ---------------------------------------------------------------------------
# MODULE 6: Risk Engine
# ---------------------------------------------------------------------------

class RiskAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Position-level risk assessment."""
    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("ix_risk_position_date", "position_id", "assessed_at"),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    liquidity_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    concentration_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    physical_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    counterparty_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    spec_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    provenance_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)

    composite_risk_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    risk_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_factors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recommendations: Mapped[Optional[dict]] = mapped_column(JSONB)

    position: Mapped["Position"] = relationship(back_populates="risk_assessments")


class PortfolioRiskSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Portfolio-level risk assessment at a point in time."""
    __tablename__ = "portfolio_risk_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    manufacturer_concentration: Mapped[dict] = mapped_column(JSONB, nullable=False)
    era_concentration: Mapped[dict] = mapped_column(JSONB, nullable=False)
    type_concentration: Mapped[dict] = mapped_column(JSONB, nullable=False)

    max_manufacturer_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    total_illiquid_90d_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    scenario_analysis: Mapped[dict] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[Optional[dict]] = mapped_column(JSONB)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# MODULE 7: Execution Engine
# ---------------------------------------------------------------------------

class Dealer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dealer and auction house registry."""
    __tablename__ = "dealers"

    name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    tier: Mapped[DealerTier] = mapped_column(Enum(DealerTier), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(100))
    specialisation: Mapped[Optional[str]] = mapped_column(String(300))
    typical_margin_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    has_allocation_access: Mapped[bool] = mapped_column(Boolean, default=False)
    allocation_brands: Mapped[Optional[dict]] = mapped_column(JSONB)
    contact_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    relationship_notes: Mapped[Optional[str]] = mapped_column(Text)
    reliability_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuctionHouse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Auction house registry with fee structures and event calendars."""
    __tablename__ = "auction_houses"

    name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    tier: Mapped[AuctionHouseTier] = mapped_column(Enum(AuctionHouseTier), nullable=False)
    buyer_premium_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    seller_commission_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    catalogue_fee: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    geographic_reach: Mapped[Optional[dict]] = mapped_column(JSONB)
    specialisation: Mapped[Optional[str]] = mapped_column(String(300))
    contact_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuctionEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Known upcoming and historical auction events."""
    __tablename__ = "auction_events"
    __table_args__ = (
        Index("ix_auction_event_date", "event_date"),
    )

    auction_house_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auction_houses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_end_date: Mapped[Optional[date]] = mapped_column(Date)
    location: Mapped[Optional[str]] = mapped_column(String(300))
    is_flagship: Mapped[bool] = mapped_column(Boolean, default=False)
    consignment_deadline: Mapped[Optional[date]] = mapped_column(Date)
    estimated_lots: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)


class SpecGuide(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Optimal spec recommendations per model for maximum resale value."""
    __tablename__ = "spec_guides"

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    recommended_colours: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recommended_options: Mapped[dict] = mapped_column(JSONB, nullable=False)
    avoid_options: Mapped[Optional[dict]] = mapped_column(JSONB)
    mileage_ceiling: Mapped[Optional[int]] = mapped_column(Integer)
    drive_side_preference: Mapped[Optional[str]] = mapped_column(String(5))
    certification_required: Mapped[bool] = mapped_column(Boolean, default=False)
    certification_type: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# MODULE 8: Trading Ledger
# ---------------------------------------------------------------------------

class Position(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A car (or other asset) held in the portfolio."""
    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_status", "status"),
    )

    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass), nullable=False, default=AssetClass.CAR)
    status: Mapped[PositionStatus] = mapped_column(Enum(PositionStatus), nullable=False, default=PositionStatus.OPEN)

    # Asset identification
    identifier: Mapped[Optional[str]] = mapped_column(String(100))  # VIN, serial number, etc.
    year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    colour_exterior: Mapped[Optional[str]] = mapped_column(String(200))
    colour_interior: Mapped[Optional[str]] = mapped_column(String(200))
    mileage_at_acquisition: Mapped[Optional[int]] = mapped_column(Integer)
    spec_details: Mapped[Optional[dict]] = mapped_column(JSONB)
    provenance_dossier: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Acquisition
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    acquisition_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    acquisition_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    acquisition_price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    acquisition_channel: Mapped[str] = mapped_column(String(200), nullable=False)
    acquisition_counterparty: Mapped[Optional[str]] = mapped_column(String(300))
    dealer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("dealers.id"))
    auction_house_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("auction_houses.id"))

    # Exit
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    exit_currency: Mapped[Optional[str]] = mapped_column(String(3))
    exit_price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    exit_channel: Mapped[Optional[str]] = mapped_column(String(200))
    exit_counterparty: Mapped[Optional[str]] = mapped_column(String(300))
    exit_hammer_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    exit_buyer_premium: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))

    # Current valuation
    current_fair_value_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    fair_value_date: Mapped[Optional[date]] = mapped_column(Date)

    # Computed P&L (denormalised for query performance, recalculated by reconciliation)
    total_acquisition_costs: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    total_holding_costs: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    total_exit_costs: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    total_cost_basis: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    unrealised_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    realised_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    irr: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))

    # Storage and insurance
    storage_location: Mapped[Optional[str]] = mapped_column(String(300))
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(200))
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100))

    # Target exit
    target_exit_date: Mapped[Optional[date]] = mapped_column(Date)
    target_exit_price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    target_auction_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("auction_events.id"))

    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    asset_model: Mapped["AssetModel"] = relationship()
    cost_entries: Mapped[list["CostEntry"]] = relationship(back_populates="position")
    risk_assessments: Mapped[list["RiskAssessment"]] = relationship(back_populates="position")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="position")


class CostEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Itemised cost against a position — every financial event recorded."""
    __tablename__ = "cost_entries"
    __table_args__ = (
        Index("ix_cost_entries_position", "position_id", "cost_date"),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=False)
    cost_category: Mapped[CostCategory] = mapped_column(Enum(CostCategory), nullable=False)
    cost_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    vendor: Mapped[Optional[str]] = mapped_column(String(300))
    invoice_reference: Mapped[Optional[str]] = mapped_column(String(200))
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_months: Mapped[Optional[int]] = mapped_column(SmallInteger)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    position: Mapped["Position"] = relationship(back_populates="cost_entries")


class LedgerEntry(UUIDPrimaryKeyMixin, Base):
    """Immutable audit log — every financial event. Cannot be edited, only corrected."""
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_position_date", "position_id", "entry_date"),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    entry_type: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    corrects_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ledger_entries.id"))
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(String(200))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    position: Mapped["Position"] = relationship(back_populates="ledger_entries")


class PortfolioSnapshot(UUIDPrimaryKeyMixin, Base):
    """Daily portfolio-level performance snapshot."""
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", name="uq_portfolio_snapshot_date"),
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_market_value_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    total_cost_basis_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    total_unrealised_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    total_realised_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    portfolio_irr: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    open_positions_count: Mapped[int] = mapped_column(Integer, nullable=False)
    capital_deployed_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    available_capital_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2))
    position_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# MODULE 9: Reconciliation & Monitoring
# ---------------------------------------------------------------------------

class ReconciliationRun(UUIDPrimaryKeyMixin, Base):
    """Record of each reconciliation job execution."""
    __tablename__ = "reconciliation_runs"

    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    run_type: Mapped[str] = mapped_column(String(100), nullable=False)
    positions_checked: Mapped[int] = mapped_column(Integer, nullable=False)
    divergences_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alerts_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """All platform alerts — price movements, catalysts, reconciliation issues."""
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_type_created", "alert_type", "created_at"),
        Index("ix_alerts_unread", "is_read", "created_at"),
    )

    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), nullable=False)
    asset_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"))
    position_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("positions.id"))

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSONB)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    emailed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# MODULE 10: Backtesting
# ---------------------------------------------------------------------------

class BacktestRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A complete backtest simulation run."""
    __tablename__ = "backtest_runs"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_versions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Aggregate results
    total_opportunities_flagged: Mapped[Optional[int]] = mapped_column(Integer)
    actionable_opportunities: Mapped[Optional[int]] = mapped_column(Integer)
    signal_accuracy_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    avg_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    median_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    false_positive_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    sharpe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    max_drawdown_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    return_distribution: Mapped[Optional[dict]] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class BacktestSignal(UUIDPrimaryKeyMixin, Base):
    """Individual signal generated during a backtest — with actual outcome attached."""
    __tablename__ = "backtest_signals"
    __table_args__ = (
        Index("ix_backtest_signal_run", "backtest_run_id", "signal_date"),
    )

    backtest_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False)
    asset_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("asset_models.id"), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType), nullable=False)

    predicted_direction: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    predicted_return_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    consensus_score: Mapped[Optional[int]] = mapped_column(SmallInteger)
    opportunity_status: Mapped[Optional[OpportunityStatus]] = mapped_column(Enum(OpportunityStatus))

    actual_return_6m_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    actual_return_12m_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    actual_return_24m_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    was_correct: Mapped[Optional[bool]] = mapped_column(Boolean)

    signal_data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class BacktestModelValidation(UUIDPrimaryKeyMixin, Base):
    """Per-model validation results from a backtest run."""
    __tablename__ = "backtest_model_validations"
    __table_args__ = (
        UniqueConstraint("backtest_run_id", "model_type", name="uq_backtest_model_validation"),
    )

    backtest_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("backtest_runs.id"), nullable=False)
    model_type: Mapped[ConsensusModelType] = mapped_column(Enum(ConsensusModelType), nullable=False)

    accuracy_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    precision: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    recall: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    f1_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 3))
    correlation_with_other_models: Mapped[Optional[dict]] = mapped_column(JSONB)
    optimal_weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# System / Scraper Management
# ---------------------------------------------------------------------------

class ScraperRun(UUIDPrimaryKeyMixin, Base):
    """Log of every scraper execution for monitoring and debugging."""
    __tablename__ = "scraper_runs"

    scraper_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[TransactionSource] = mapped_column(Enum(TransactionSource), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="running")
    items_collected: Mapped[int] = mapped_column(Integer, default=0)
    items_parsed: Mapped[int] = mapped_column(Integer, default=0)
    items_normalised: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[dict]] = mapped_column(JSONB)
    config_used: Mapped[Optional[dict]] = mapped_column(JSONB)
