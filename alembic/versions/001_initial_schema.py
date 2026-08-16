"""Initial schema — all 10 modules

Revision ID: 001
Revises: None
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_enum_safe(name: str, values: tuple) -> None:
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(
        f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))


def _create_enums() -> None:
    for name, values in [
        ("assetclass", ("car", "watch", "wine", "whisky", "art")),
        ("transactionsource", ("bring_a_trailer", "rm_sothebys", "gooding", "bonhams", "cars_and_bids", "dealer_listing", "private_sale", "manual_entry")),
        ("transactiontype", ("auction_sold", "auction_not_sold", "dealer_listing", "dealer_sold", "private_sale")),
        ("colourtier", ("1", "2", "3")),
        ("conditiongrade", ("concours", "excellent", "good", "fair", "project")),
        ("signaltype", ("momentum", "dealer_auction_spread", "catalyst", "volume_spike", "comparable_appreciation", "pattern_match")),
        ("consensusmodeltype", ("momentum", "fundamental_value", "liquidity", "sentiment", "macro", "rules")),
        ("opportunitystatus", ("watchlist", "actionable", "acquired", "passed", "expired")),
        ("positionstatus", ("open", "pending_exit", "exited")),
        ("costcategory", ("acquisition_premium", "auction_buyer_premium", "seller_commission", "transport", "insurance", "storage", "import_duty", "tax", "maintenance", "detailing", "photography", "catalogue_fee", "inspection", "documentation", "other")),
        ("alerttype", ("price_movement", "catalyst", "auction_result", "consensus_change", "holding_cost_warning", "hold_period_warning", "liquidity_warning", "reconciliation_divergence")),
        ("alertseverity", ("info", "warning", "critical")),
        ("rulecategory", ("import_eligibility", "tax_treatment", "drive_side", "homologation", "certification", "auction_restriction", "materials_restriction")),
        ("dealertier", ("allocation_access", "secondary_premium", "secondary_standard")),
        ("auctionhousetier", ("major", "mid", "online")),
    ]:
        _create_enum_safe(name, values)


def upgrade() -> None:
    _create_enums()

    # --- Manufacturers ---
    op.create_table(
        "manufacturers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("country", sa.String(100)),
        sa.Column("asset_class", postgresql.ENUM("car", "watch", "wine", "whisky", "art", name="assetclass", create_type=False), nullable=False, server_default="car"),
        sa.Column("prestige_score", sa.Numeric(3, 1)),
        sa.Column("notes", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Asset Models ---
    op.create_table(
        "asset_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manufacturer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manufacturers.id"), nullable=False),
        sa.Column("asset_class", postgresql.ENUM("car", "watch", "wine", "whisky", "art", name="assetclass", create_type=False), nullable=False, server_default="car"),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("variant", sa.String(300)),
        sa.Column("production_year_start", sa.SmallInteger),
        sa.Column("production_year_end", sa.SmallInteger),
        sa.Column("total_produced", sa.Integer),
        sa.Column("estimated_liquid_supply", sa.Integer),
        sa.Column("known_destroyed", sa.Integer, server_default="0"),
        sa.Column("known_museum_held", sa.Integer, server_default="0"),
        sa.Column("is_open_top", sa.Boolean, server_default="false"),
        sa.Column("is_limited_edition", sa.Boolean, server_default="false"),
        sa.Column("is_invitation_only", sa.Boolean, server_default="false"),
        sa.Column("engine_type", sa.String(100)),
        sa.Column("engine_config", sa.String(100)),
        sa.Column("msrp_at_launch", sa.Numeric(14, 2)),
        sa.Column("msrp_currency", sa.String(3)),
        sa.Column("homologation_type", sa.String(100)),
        sa.Column("variant_scarcity_multiplier", sa.Numeric(5, 2), server_default="1.00"),
        sa.Column("appreciation_stage", sa.String(50)),
        sa.Column("notes", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("manufacturer_id", "name", "variant", name="uq_asset_model_identity"),
    )

    # --- Asset Model Relationships ---
    op.create_table(
        "asset_model_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("related_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("correlation_strength", sa.Numeric(4, 3)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_model_id", "related_model_id", name="uq_model_relationship"),
    )

    # --- Colour Specs ---
    op.create_table(
        "colour_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manufacturer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manufacturers.id"), nullable=False),
        sa.Column("colour_name", sa.String(200), nullable=False),
        sa.Column("colour_code", sa.String(50)),
        sa.Column("tier", postgresql.ENUM("1", "2", "3", name="colourtier", create_type=False), nullable=False),
        sa.Column("is_tailor_made", sa.Boolean, server_default="false"),
        sa.Column("liquidity_adjustment_pct", sa.Numeric(5, 2), server_default="0.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("manufacturer_id", "colour_name", name="uq_colour_per_manufacturer"),
    )

    # --- Option Specs ---
    op.create_table(
        "option_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manufacturer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("manufacturers.id"), nullable=False),
        sa.Column("option_name", sa.String(300), nullable=False),
        sa.Column("option_code", sa.String(50)),
        sa.Column("category", sa.String(100)),
        sa.Column("value_impact_pct", sa.Numeric(5, 2), server_default="0.00"),
        sa.Column("is_desirable_for_resale", sa.Boolean, server_default="true"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Data Provenance ---
    op.create_table(
        "data_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", postgresql.ENUM("bring_a_trailer", "rm_sothebys", "gooding", "bonhams", "cars_and_bids", "dealer_listing", "private_sale", "manual_entry", name="transactionsource", create_type=False), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_content_hash", sa.String(64)),
        sa.Column("raw_html_path", sa.Text),
        sa.Column("parsed_content", postgresql.JSONB),
        sa.Column("normalisations_applied", postgresql.JSONB),
        sa.Column("scraper_version", sa.String(50)),
        sa.Column("is_valid", sa.Boolean, server_default="true"),
        sa.Column("validation_errors", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Transactions ---
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_provenance.id"), nullable=False),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("asset_class", postgresql.ENUM("car", "watch", "wine", "whisky", "art", name="assetclass", create_type=False), nullable=False, server_default="car"),
        sa.Column("source", postgresql.ENUM("bring_a_trailer", "rm_sothebys", "gooding", "bonhams", "cars_and_bids", "dealer_listing", "private_sale", "manual_entry", name="transactionsource", create_type=False), nullable=False),
        sa.Column("external_id", sa.String(200)),
        sa.Column("transaction_type", postgresql.ENUM("auction_sold", "auction_not_sold", "dealer_listing", "dealer_sold", "private_sale", name="transactiontype", create_type=False), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("hammer_price", sa.Numeric(14, 2)),
        sa.Column("buyer_premium", sa.Numeric(14, 2)),
        sa.Column("total_price", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("total_price_usd", sa.Numeric(14, 2)),
        sa.Column("exchange_rate_used", sa.Numeric(12, 6)),
        sa.Column("year", sa.SmallInteger),
        sa.Column("mileage", sa.Integer),
        sa.Column("mileage_unit", sa.String(10), server_default="miles"),
        sa.Column("colour_exterior", sa.String(200)),
        sa.Column("colour_interior", sa.String(200)),
        sa.Column("colour_tier", postgresql.ENUM("1", "2", "3", name="colourtier", create_type=False)),
        sa.Column("condition_grade", postgresql.ENUM("concours", "excellent", "good", "fair", "project", name="conditiongrade", create_type=False)),
        sa.Column("drive_side", sa.String(5)),
        sa.Column("vin", sa.String(50)),
        sa.Column("options", postgresql.JSONB),
        sa.Column("has_books", sa.Boolean),
        sa.Column("has_tools", sa.Boolean),
        sa.Column("service_history_complete", sa.Boolean),
        sa.Column("single_owner", sa.Boolean),
        sa.Column("celebrity_provenance", sa.Boolean),
        sa.Column("provenance_notes", sa.Text),
        sa.Column("sale_country", sa.String(100)),
        sa.Column("sale_region", sa.String(100)),
        sa.Column("auction_house", sa.String(200)),
        sa.Column("auction_event", sa.String(300)),
        sa.Column("dealer_name", sa.String(200)),
        sa.Column("normalised_price_usd", sa.Numeric(14, 2)),
        sa.Column("mileage_adjustment_pct", sa.Numeric(6, 3)),
        sa.Column("colour_adjustment_pct", sa.Numeric(6, 3)),
        sa.Column("options_adjustment_pct", sa.Numeric(6, 3)),
        sa.Column("geography_adjustment_pct", sa.Numeric(6, 3)),
        sa.Column("provenance_adjustment_pct", sa.Numeric(6, 3)),
        sa.Column("condition_adjustment_pct", sa.Numeric(6, 3)),
        sa.Column("listing_active", sa.Boolean),
        sa.Column("listing_first_seen", sa.DateTime(timezone=True)),
        sa.Column("listing_last_seen", sa.DateTime(timezone=True)),
        sa.Column("days_on_market", sa.Integer),
        sa.Column("lot_description", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transactions_model_date", "transactions", ["asset_model_id", "transaction_date"])
    op.create_index("ix_transactions_source_ext", "transactions", ["source", "external_id"], unique=True)

    # --- Currency Rates ---
    op.create_table(
        "currency_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rate_date", sa.Date, nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(12, 6), nullable=False),
        sa.Column("source", sa.String(100)),
        sa.UniqueConstraint("rate_date", "base_currency", "quote_currency", name="uq_currency_rate_day"),
    )

    # --- News Articles ---
    op.create_table(
        "news_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provenance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_provenance.id"), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("article_type", sa.String(100)),
        sa.Column("relevant_models", postgresql.JSONB),
        sa.Column("sentiment_score", sa.Numeric(4, 3)),
        sa.Column("is_catalyst", sa.Boolean, server_default="false"),
        sa.Column("catalyst_type", sa.String(100)),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_news_published", "news_articles", ["published_at"])

    # --- Forum Sentiments ---
    op.create_table(
        "forum_sentiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("source_forum", sa.String(200), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("post_count", sa.Integer, nullable=False),
        sa.Column("avg_sentiment", sa.Numeric(4, 3)),
        sa.Column("mention_volume_change_pct", sa.Numeric(6, 2)),
        sa.Column("notable_topics", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_model_id", "source_forum", "period_start", name="uq_forum_sentiment_period"),
    )

    # --- Macro Indicators ---
    op.create_table(
        "macro_indicators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("indicator_name", sa.String(200), nullable=False),
        sa.Column("indicator_date", sa.Date, nullable=False),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(50)),
        sa.Column("source", sa.String(200)),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.UniqueConstraint("indicator_name", "indicator_date", name="uq_macro_indicator_date"),
    )

    # --- Market Rules ---
    op.create_table(
        "market_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", postgresql.ENUM("import_eligibility", "tax_treatment", "drive_side", "homologation", "certification", "auction_restriction", "materials_restriction", name="rulecategory", create_type=False), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("jurisdiction", sa.String(100)),
        sa.Column("effective_date", sa.Date),
        sa.Column("expiry_date", sa.Date),
        sa.Column("rule_logic", postgresql.JSONB, nullable=False),
        sa.Column("impact_description", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Import Eligibility Calendar ---
    op.create_table(
        "import_eligibility_calendar",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=False, server_default="US"),
        sa.Column("manufacture_year", sa.SmallInteger, nullable=False),
        sa.Column("eligible_year", sa.SmallInteger, nullable=False),
        sa.Column("eligible_date", sa.Date, nullable=False),
        sa.Column("rule_reference_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_rules.id")),
        sa.Column("estimated_price_impact_pct", sa.Numeric(5, 2)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_model_id", "jurisdiction", name="uq_import_eligibility_model"),
    )

    # --- Rule Model Flags ---
    op.create_table(
        "rule_model_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("market_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_rules.id"), nullable=False),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("flag_reason", sa.Text, nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_positive", sa.Boolean, nullable=False),
        sa.Column("impact_score", sa.Numeric(4, 2)),
        sa.Column("acknowledged", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_rule_flag_model", "rule_model_flags", ["asset_model_id"])

    # --- Fair Values ---
    op.create_table(
        "fair_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("valuation_date", sa.Date, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("fair_value_low", sa.Numeric(14, 2), nullable=False),
        sa.Column("fair_value_mid", sa.Numeric(14, 2), nullable=False),
        sa.Column("fair_value_high", sa.Numeric(14, 2), nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("comparable_count", sa.Integer, nullable=False),
        sa.Column("comparable_window_months", sa.SmallInteger, nullable=False, server_default="12"),
        sa.Column("appreciation_stage", sa.String(50)),
        sa.Column("appreciation_rate_30d", sa.Numeric(6, 3)),
        sa.Column("appreciation_rate_90d", sa.Numeric(6, 3)),
        sa.Column("appreciation_rate_365d", sa.Numeric(6, 3)),
        sa.Column("methodology", sa.Text),
        sa.Column("comparable_transaction_ids", postgresql.JSONB),
        sa.Column("model_parameters", postgresql.JSONB),
        sa.Column("warnings", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fair_value_model_date", "fair_values", ["asset_model_id", "valuation_date"])

    # --- Mileage Curves ---
    op.create_table(
        "mileage_curves",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("mileage_lower", sa.Integer, nullable=False),
        sa.Column("mileage_upper", sa.Integer, nullable=False),
        sa.Column("adjustment_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("sample_size", sa.Integer),
        sa.Column("last_calibrated", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_model_id", "mileage_lower", name="uq_mileage_band"),
    )

    # --- Cost Models ---
    op.create_table(
        "cost_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("geography", sa.String(100), nullable=False),
        sa.Column("acquisition_channel", sa.String(100), nullable=False),
        sa.Column("exit_channel", sa.String(100), nullable=False),
        sa.Column("buyer_premium_pct", sa.Numeric(5, 3), server_default="12.500"),
        sa.Column("seller_commission_pct", sa.Numeric(5, 3), server_default="10.000"),
        sa.Column("insurance_annual_pct", sa.Numeric(5, 3), server_default="1.250"),
        sa.Column("storage_monthly", sa.Numeric(10, 2), server_default="800.00"),
        sa.Column("transport_estimate", sa.Numeric(10, 2), server_default="3000.00"),
        sa.Column("preparation_estimate", sa.Numeric(10, 2), server_default="5000.00"),
        sa.Column("import_duty_pct", sa.Numeric(5, 3), server_default="0.000"),
        sa.Column("vat_pct", sa.Numeric(5, 3), server_default="0.000"),
        sa.Column("other_costs", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Signals ---
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("signal_type", postgresql.ENUM("momentum", "dealer_auction_spread", "catalyst", "volume_spike", "comparable_appreciation", "pattern_match", name="signaltype", create_type=False), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("strength", sa.Numeric(5, 3), nullable=False),
        sa.Column("direction", sa.SmallInteger, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("supporting_data", postgresql.JSONB, nullable=False),
        sa.Column("transaction_count", sa.Integer),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_signals_model_type_date", "signals", ["asset_model_id", "signal_type", "generated_at"])

    # --- Opportunity Scores ---
    op.create_table(
        "opportunity_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("composite_score", sa.Numeric(6, 3), nullable=False),
        sa.Column("signal_count", sa.Integer, nullable=False),
        sa.Column("signal_breakdown", postgresql.JSONB, nullable=False),
        sa.Column("liquidity_score", sa.Numeric(4, 3)),
        sa.Column("cost_adjusted_return_pct", sa.Numeric(6, 3)),
        sa.Column("time_to_catalyst_days", sa.Integer),
        sa.Column("rule_flags", postgresql.JSONB),
        sa.Column("status", postgresql.ENUM("watchlist", "actionable", "acquired", "passed", "expired", name="opportunitystatus", create_type=False), nullable=False, server_default="watchlist"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_opp_score_model_date", "opportunity_scores", ["asset_model_id", "scored_at"])

    # --- Consensus Scores ---
    op.create_table(
        "consensus_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("aggregate_score", sa.SmallInteger, nullable=False),
        sa.Column("has_veto", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("veto_model", sa.String(50)),
        sa.Column("veto_reason", sa.Text),
        sa.Column("status", postgresql.ENUM("watchlist", "actionable", "acquired", "passed", "expired", name="opportunitystatus", create_type=False), nullable=False),
        sa.Column("disagreement_summary", sa.Text),
        sa.Column("actionable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consensus_model_date", "consensus_scores", ["asset_model_id", "scored_at"])

    # --- Consensus Model Scores ---
    op.create_table(
        "consensus_model_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consensus_score_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consensus_scores.id"), nullable=False),
        sa.Column("model_type", postgresql.ENUM("momentum", "fundamental_value", "liquidity", "sentiment", "macro", "rules", name="consensusmodeltype", create_type=False), nullable=False),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("supporting_data", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("score >= -2 AND score <= 2", name="ck_consensus_score_range"),
    )
    op.create_index("ix_consensus_model_scored", "consensus_model_scores", ["consensus_score_id", "model_type"])

    # --- Dealers ---
    op.create_table(
        "dealers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("tier", postgresql.ENUM("allocation_access", "secondary_premium", "secondary_standard", name="dealertier", create_type=False), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("specialisation", sa.String(300)),
        sa.Column("typical_margin_pct", sa.Numeric(5, 2)),
        sa.Column("has_allocation_access", sa.Boolean, server_default="false"),
        sa.Column("allocation_brands", postgresql.JSONB),
        sa.Column("contact_info", postgresql.JSONB),
        sa.Column("relationship_notes", sa.Text),
        sa.Column("reliability_score", sa.Numeric(3, 2)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Auction Houses ---
    op.create_table(
        "auction_houses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("tier", postgresql.ENUM("major", "mid", "online", name="auctionhousetier", create_type=False), nullable=False),
        sa.Column("buyer_premium_pct", sa.Numeric(5, 3), nullable=False),
        sa.Column("seller_commission_pct", sa.Numeric(5, 3)),
        sa.Column("catalogue_fee", sa.Numeric(10, 2)),
        sa.Column("geographic_reach", postgresql.JSONB),
        sa.Column("specialisation", sa.String(300)),
        sa.Column("contact_info", postgresql.JSONB),
        sa.Column("notes", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Auction Events ---
    op.create_table(
        "auction_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("auction_house_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auction_houses.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("event_end_date", sa.Date),
        sa.Column("location", sa.String(300)),
        sa.Column("is_flagship", sa.Boolean, server_default="false"),
        sa.Column("consignment_deadline", sa.Date),
        sa.Column("estimated_lots", sa.Integer),
        sa.Column("notes", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auction_event_date", "auction_events", ["event_date"])

    # --- Spec Guides ---
    op.create_table(
        "spec_guides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("recommended_colours", postgresql.JSONB, nullable=False),
        sa.Column("recommended_options", postgresql.JSONB, nullable=False),
        sa.Column("avoid_options", postgresql.JSONB),
        sa.Column("mileage_ceiling", sa.Integer),
        sa.Column("drive_side_preference", sa.String(5)),
        sa.Column("certification_required", sa.Boolean, server_default="false"),
        sa.Column("certification_type", sa.String(200)),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Positions ---
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("asset_class", postgresql.ENUM("car", "watch", "wine", "whisky", "art", name="assetclass", create_type=False), nullable=False, server_default="car"),
        sa.Column("status", postgresql.ENUM("open", "pending_exit", "exited", name="positionstatus", create_type=False), nullable=False, server_default="open"),
        sa.Column("identifier", sa.String(100)),
        sa.Column("year", sa.SmallInteger),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("colour_exterior", sa.String(200)),
        sa.Column("colour_interior", sa.String(200)),
        sa.Column("mileage_at_acquisition", sa.Integer),
        sa.Column("spec_details", postgresql.JSONB),
        sa.Column("provenance_dossier", postgresql.JSONB),
        sa.Column("acquisition_date", sa.Date, nullable=False),
        sa.Column("acquisition_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("acquisition_currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("acquisition_price_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("acquisition_channel", sa.String(200), nullable=False),
        sa.Column("acquisition_counterparty", sa.String(300)),
        sa.Column("dealer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dealers.id")),
        sa.Column("auction_house_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auction_houses.id")),
        sa.Column("exit_date", sa.Date),
        sa.Column("exit_price", sa.Numeric(14, 2)),
        sa.Column("exit_currency", sa.String(3)),
        sa.Column("exit_price_usd", sa.Numeric(14, 2)),
        sa.Column("exit_channel", sa.String(200)),
        sa.Column("exit_counterparty", sa.String(300)),
        sa.Column("exit_hammer_price", sa.Numeric(14, 2)),
        sa.Column("exit_buyer_premium", sa.Numeric(14, 2)),
        sa.Column("current_fair_value_usd", sa.Numeric(14, 2)),
        sa.Column("fair_value_date", sa.Date),
        sa.Column("total_acquisition_costs", sa.Numeric(14, 2)),
        sa.Column("total_holding_costs", sa.Numeric(14, 2)),
        sa.Column("total_exit_costs", sa.Numeric(14, 2)),
        sa.Column("total_cost_basis", sa.Numeric(14, 2)),
        sa.Column("unrealised_pnl", sa.Numeric(14, 2)),
        sa.Column("realised_pnl", sa.Numeric(14, 2)),
        sa.Column("irr", sa.Numeric(8, 4)),
        sa.Column("storage_location", sa.String(300)),
        sa.Column("insurance_provider", sa.String(200)),
        sa.Column("insurance_policy_number", sa.String(100)),
        sa.Column("target_exit_date", sa.Date),
        sa.Column("target_exit_price_usd", sa.Numeric(14, 2)),
        sa.Column("target_auction_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auction_events.id")),
        sa.Column("notes", sa.Text),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_positions_status", "positions", ["status"])

    # --- Cost Entries ---
    op.create_table(
        "cost_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("cost_category", postgresql.ENUM("acquisition_premium", "auction_buyer_premium", "seller_commission", "transport", "insurance", "storage", "import_duty", "tax", "maintenance", "detailing", "photography", "catalogue_fee", "inspection", "documentation", "other", name="costcategory", create_type=False), nullable=False),
        sa.Column("cost_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("amount_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("vendor", sa.String(300)),
        sa.Column("invoice_reference", sa.String(200)),
        sa.Column("is_recurring", sa.Boolean, server_default="false"),
        sa.Column("recurrence_months", sa.SmallInteger),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cost_entries_position", "cost_entries", ["position_id", "cost_date"])

    # --- Ledger Entries (immutable) ---
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("entry_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("entry_type", sa.String(100), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("amount_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("corrects_entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ledger_entries.id")),
        sa.Column("is_correction", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(200)),
        sa.Column("metadata", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_ledger_position_date", "ledger_entries", ["position_id", "entry_date"])

    # --- Portfolio Snapshots ---
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("total_market_value_usd", sa.Numeric(16, 2), nullable=False),
        sa.Column("total_cost_basis_usd", sa.Numeric(16, 2), nullable=False),
        sa.Column("total_unrealised_pnl_usd", sa.Numeric(16, 2), nullable=False),
        sa.Column("total_realised_pnl_usd", sa.Numeric(16, 2), nullable=False),
        sa.Column("portfolio_irr", sa.Numeric(8, 4)),
        sa.Column("open_positions_count", sa.Integer, nullable=False),
        sa.Column("capital_deployed_usd", sa.Numeric(16, 2), nullable=False),
        sa.Column("available_capital_usd", sa.Numeric(16, 2)),
        sa.Column("position_breakdown", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("snapshot_date", name="uq_portfolio_snapshot_date"),
    )

    # --- Risk Assessments ---
    op.create_table(
        "risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("liquidity_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("concentration_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("physical_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("counterparty_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("spec_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("provenance_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("composite_risk_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("risk_explanation", sa.Text, nullable=False),
        sa.Column("risk_factors", postgresql.JSONB, nullable=False),
        sa.Column("recommendations", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_risk_position_date", "risk_assessments", ["position_id", "assessed_at"])

    # --- Portfolio Risk Snapshots ---
    op.create_table(
        "portfolio_risk_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("manufacturer_concentration", postgresql.JSONB, nullable=False),
        sa.Column("era_concentration", postgresql.JSONB, nullable=False),
        sa.Column("type_concentration", postgresql.JSONB, nullable=False),
        sa.Column("max_manufacturer_exposure_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("total_illiquid_90d_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("scenario_analysis", postgresql.JSONB, nullable=False),
        sa.Column("warnings", postgresql.JSONB),
        sa.Column("narrative", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Reconciliation Runs ---
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("run_type", sa.String(100), nullable=False),
        sa.Column("positions_checked", sa.Integer, nullable=False),
        sa.Column("divergences_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("alerts_generated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("details", postgresql.JSONB, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # --- Alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_type", postgresql.ENUM("price_movement", "catalyst", "auction_result", "consensus_change", "holding_cost_warning", "hold_period_warning", "liquidity_warning", "reconciliation_divergence", name="alerttype", create_type=False), nullable=False),
        sa.Column("severity", postgresql.ENUM("info", "warning", "critical", name="alertseverity", create_type=False), nullable=False),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id")),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("data", postgresql.JSONB),
        sa.Column("is_read", sa.Boolean, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("is_emailed", sa.Boolean, server_default="false"),
        sa.Column("emailed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alerts_type_created", "alerts", ["alert_type", "created_at"])
    op.create_index("ix_alerts_unread", "alerts", ["is_read", "created_at"])

    # --- Backtest Runs ---
    op.create_table(
        "backtest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("parameters", postgresql.JSONB, nullable=False),
        sa.Column("model_versions", postgresql.JSONB, nullable=False),
        sa.Column("total_opportunities_flagged", sa.Integer),
        sa.Column("actionable_opportunities", sa.Integer),
        sa.Column("signal_accuracy_rate", sa.Numeric(5, 3)),
        sa.Column("avg_return_pct", sa.Numeric(6, 3)),
        sa.Column("median_return_pct", sa.Numeric(6, 3)),
        sa.Column("false_positive_rate", sa.Numeric(5, 3)),
        sa.Column("sharpe_ratio", sa.Numeric(6, 3)),
        sa.Column("max_drawdown_pct", sa.Numeric(6, 3)),
        sa.Column("return_distribution", postgresql.JSONB),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Backtest Signals ---
    op.create_table(
        "backtest_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("backtest_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id"), nullable=False),
        sa.Column("signal_date", sa.Date, nullable=False),
        sa.Column("signal_type", postgresql.ENUM("momentum", "dealer_auction_spread", "catalyst", "volume_spike", "comparable_appreciation", "pattern_match", name="signaltype", create_type=False), nullable=False),
        sa.Column("predicted_direction", sa.SmallInteger, nullable=False),
        sa.Column("predicted_return_pct", sa.Numeric(6, 3)),
        sa.Column("consensus_score", sa.SmallInteger),
        sa.Column("opportunity_status", postgresql.ENUM("watchlist", "actionable", "acquired", "passed", "expired", name="opportunitystatus", create_type=False)),
        sa.Column("actual_return_6m_pct", sa.Numeric(6, 3)),
        sa.Column("actual_return_12m_pct", sa.Numeric(6, 3)),
        sa.Column("actual_return_24m_pct", sa.Numeric(6, 3)),
        sa.Column("was_correct", sa.Boolean),
        sa.Column("signal_data", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_backtest_signal_run", "backtest_signals", ["backtest_run_id", "signal_date"])

    # --- Backtest Model Validations ---
    op.create_table(
        "backtest_model_validations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("backtest_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("model_type", postgresql.ENUM("momentum", "fundamental_value", "liquidity", "sentiment", "macro", "rules", name="consensusmodeltype", create_type=False), nullable=False),
        sa.Column("accuracy_rate", sa.Numeric(5, 3)),
        sa.Column("precision", sa.Numeric(5, 3)),
        sa.Column("recall", sa.Numeric(5, 3)),
        sa.Column("f1_score", sa.Numeric(5, 3)),
        sa.Column("correlation_with_other_models", postgresql.JSONB),
        sa.Column("optimal_weight", sa.Numeric(4, 3)),
        sa.Column("notes", sa.Text),
        sa.UniqueConstraint("backtest_run_id", "model_type", name="uq_backtest_model_validation"),
    )

    # --- Scraper Runs ---
    op.create_table(
        "scraper_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scraper_name", sa.String(200), nullable=False),
        sa.Column("source", postgresql.ENUM("bring_a_trailer", "rm_sothebys", "gooding", "bonhams", "cars_and_bids", "dealer_listing", "private_sale", "manual_entry", name="transactionsource", create_type=False), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("items_collected", sa.Integer, server_default="0"),
        sa.Column("items_parsed", sa.Integer, server_default="0"),
        sa.Column("items_normalised", sa.Integer, server_default="0"),
        sa.Column("errors", postgresql.JSONB),
        sa.Column("config_used", postgresql.JSONB),
    )


def downgrade() -> None:
    tables = [
        "scraper_runs", "backtest_model_validations", "backtest_signals", "backtest_runs",
        "alerts", "reconciliation_runs", "portfolio_risk_snapshots", "risk_assessments",
        "portfolio_snapshots", "ledger_entries", "cost_entries", "positions",
        "spec_guides", "auction_events", "auction_houses", "dealers",
        "consensus_model_scores", "consensus_scores", "opportunity_scores", "signals",
        "cost_models", "mileage_curves", "fair_values",
        "rule_model_flags", "import_eligibility_calendar", "market_rules",
        "macro_indicators", "forum_sentiments", "news_articles",
        "currency_rates", "transactions", "data_provenance",
        "option_specs", "colour_specs", "asset_model_relationships", "asset_models", "manufacturers",
    ]
    for table in tables:
        op.drop_table(table)

    enums = [
        "auctionhousetier", "dealertier", "rulecategory", "alertseverity", "alerttype",
        "costcategory", "positionstatus", "opportunitystatus", "consensusmodeltype",
        "signaltype", "conditiongrade", "colourtier", "transactiontype", "transactionsource", "assetclass",
    ]
    for name in enums:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
