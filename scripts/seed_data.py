"""
Seed the database with foundational reference data:
- Manufacturers
- Key asset models (hypercars specified in the investment thesis)
- Colour specs (Ferrari tier system)
- Model relationships (comparable appreciation pairs)
- Dealers and auction houses
- Market rules (US 25-year import rule)
- Cost model templates
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aatp.core.config import settings
from aatp.db.base import Base
from aatp.db.models import (
    AssetClass,
    AssetModel,
    AssetModelRelationship,
    AuctionHouse,
    AuctionHouseTier,
    ColourSpec,
    ColourTier,
    CostModel,
    Dealer,
    DealerTier,
    ImportEligibilityCalendar,
    Manufacturer,
    MarketRule,
    RuleCategory,
)


def seed(session: Session) -> None:
    # -----------------------------------------------------------------------
    # Manufacturers
    # -----------------------------------------------------------------------
    ferrari = Manufacturer(name="Ferrari", country="Italy", prestige_score=Decimal("9.5"))
    bugatti = Manufacturer(name="Bugatti", country="France", prestige_score=Decimal("9.0"))
    mclaren = Manufacturer(name="McLaren", country="United Kingdom", prestige_score=Decimal("8.5"))
    lamborghini = Manufacturer(name="Lamborghini", country="Italy", prestige_score=Decimal("8.5"))
    porsche = Manufacturer(name="Porsche", country="Germany", prestige_score=Decimal("8.0"))
    pagani = Manufacturer(name="Pagani", country="Italy", prestige_score=Decimal("9.0"))
    koenigsegg = Manufacturer(name="Koenigsegg", country="Sweden", prestige_score=Decimal("9.0"))
    aston_martin = Manufacturer(name="Aston Martin", country="United Kingdom", prestige_score=Decimal("7.5"))
    mercedes = Manufacturer(name="Mercedes-AMG", country="Germany", prestige_score=Decimal("7.5"))

    session.add_all([ferrari, bugatti, mclaren, lamborghini, porsche, pagani, koenigsegg, aston_martin, mercedes])
    session.flush()

    # -----------------------------------------------------------------------
    # Ferrari Models
    # -----------------------------------------------------------------------
    sp3_monza = AssetModel(
        manufacturer_id=ferrari.id, name="SP3 Monza", variant=None,
        production_year_start=2018, production_year_end=2020,
        total_produced=499, estimated_liquid_supply=80, known_destroyed=0, known_museum_held=5,
        is_open_top=True, is_limited_edition=True, is_invitation_only=True,
        engine_type="V12", engine_config="6.5L naturally aspirated",
        msrp_at_launch=Decimal("1750000"), msrp_currency="EUR",
        variant_scarcity_multiplier=Decimal("3.00"),
        appreciation_stage="maturity",
        notes="Icona series. No windscreen. Sold at Sotheby's for $16M. Benchmark case study.",
    )

    sf_coupe = AssetModel(
        manufacturer_id=ferrari.id, name="812 Superfast", variant=None,
        production_year_start=2017, production_year_end=2022,
        total_produced=2500, estimated_liquid_supply=800,
        is_open_top=False, is_limited_edition=False,
        engine_type="V12", engine_config="6.5L naturally aspirated",
        msrp_at_launch=Decimal("335000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("1.00"),
        appreciation_stage="early_appreciation",
    )

    sf_gts = AssetModel(
        manufacturer_id=ferrari.id, name="812 Superfast", variant="GTS",
        production_year_start=2019, production_year_end=2022,
        total_produced=812, estimated_liquid_supply=350,
        is_open_top=True, is_limited_edition=False,
        engine_type="V12", engine_config="6.5L naturally aspirated",
        msrp_at_launch=Decimal("365000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("1.80"),
        appreciation_stage="early_appreciation",
        notes="V12 NA convertible. Far fewer produced than coupe. 20-30% appreciation in 6-12 months. Active opportunity.",
    )

    sf_competizione = AssetModel(
        manufacturer_id=ferrari.id, name="812 Competizione", variant=None,
        production_year_start=2021, production_year_end=2022,
        total_produced=999, estimated_liquid_supply=250,
        is_open_top=False, is_limited_edition=True, is_invitation_only=True,
        engine_type="V12", engine_config="6.5L naturally aspirated, 830hp",
        msrp_at_launch=Decimal("499000"), msrp_currency="EUR",
        variant_scarcity_multiplier=Decimal("2.50"),
        appreciation_stage="momentum",
    )

    sf_comp_a = AssetModel(
        manufacturer_id=ferrari.id, name="812 Competizione", variant="A",
        production_year_start=2021, production_year_end=2022,
        total_produced=599, estimated_liquid_supply=150,
        is_open_top=True, is_limited_edition=True, is_invitation_only=True,
        engine_type="V12", engine_config="6.5L naturally aspirated, 830hp",
        msrp_at_launch=Decimal("580000"), msrp_currency="EUR",
        variant_scarcity_multiplier=Decimal("3.00"),
        appreciation_stage="momentum",
    )

    pista_coupe = AssetModel(
        manufacturer_id=ferrari.id, name="488 Pista", variant=None,
        production_year_start=2018, production_year_end=2020,
        total_produced=3500, estimated_liquid_supply=1200,
        is_open_top=False, is_limited_edition=False,
        engine_type="V8", engine_config="3.9L twin-turbo",
        msrp_at_launch=Decimal("350000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("1.00"),
        appreciation_stage="early_appreciation",
    )

    pista_spider = AssetModel(
        manufacturer_id=ferrari.id, name="488 Pista", variant="Spider",
        production_year_start=2018, production_year_end=2020,
        total_produced=499, estimated_liquid_supply=200,
        is_open_top=True, is_limited_edition=True,
        engine_type="V8", engine_config="3.9L twin-turbo",
        msrp_at_launch=Decimal("400000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("2.50"),
        appreciation_stage="pre_discovery",
        notes="Under 500 produced. V8 at peak before electrification. Has not yet had headline auction moment. Pre-catalyst opportunity.",
    )

    laferrari = AssetModel(
        manufacturer_id=ferrari.id, name="LaFerrari", variant=None,
        production_year_start=2013, production_year_end=2016,
        total_produced=499, estimated_liquid_supply=100,
        is_open_top=False, is_limited_edition=True, is_invitation_only=True,
        engine_type="V12 Hybrid", engine_config="6.3L V12 + electric",
        msrp_at_launch=Decimal("1420000"), msrp_currency="EUR",
        variant_scarcity_multiplier=Decimal("2.00"),
        appreciation_stage="maturity",
    )

    laferrari_aperta = AssetModel(
        manufacturer_id=ferrari.id, name="LaFerrari", variant="Aperta",
        production_year_start=2016, production_year_end=2018,
        total_produced=210, estimated_liquid_supply=40,
        is_open_top=True, is_limited_edition=True, is_invitation_only=True,
        engine_type="V12 Hybrid", engine_config="6.3L V12 + electric",
        msrp_at_launch=Decimal("2000000"), msrp_currency="EUR",
        variant_scarcity_multiplier=Decimal("4.00"),
        appreciation_stage="maturity",
        notes="Only 210 exist. Any one coming to market is a price-setting event.",
    )

    f40 = AssetModel(
        manufacturer_id=ferrari.id, name="F40", variant=None,
        production_year_start=1987, production_year_end=1992,
        total_produced=1315, estimated_liquid_supply=400,
        is_open_top=False, is_limited_edition=True,
        engine_type="V8", engine_config="2.9L twin-turbo",
        variant_scarcity_multiplier=Decimal("2.00"),
        appreciation_stage="maturity",
    )

    f50 = AssetModel(
        manufacturer_id=ferrari.id, name="F50", variant=None,
        production_year_start=1995, production_year_end=1997,
        total_produced=349, estimated_liquid_supply=200,
        is_open_top=True, is_limited_edition=True, is_invitation_only=True,
        engine_type="V12", engine_config="4.7L naturally aspirated",
        variant_scarcity_multiplier=Decimal("2.50"),
        appreciation_stage="maturity",
    )

    speciale_coupe = AssetModel(
        manufacturer_id=ferrari.id, name="458 Speciale", variant=None,
        production_year_start=2013, production_year_end=2015,
        total_produced=3000, estimated_liquid_supply=1000,
        is_open_top=False,
        engine_type="V8", engine_config="4.5L naturally aspirated",
        variant_scarcity_multiplier=Decimal("1.00"),
        appreciation_stage="momentum",
    )

    speciale_a = AssetModel(
        manufacturer_id=ferrari.id, name="458 Speciale", variant="A",
        production_year_start=2014, production_year_end=2015,
        total_produced=499, estimated_liquid_supply=200,
        is_open_top=True, is_limited_edition=True,
        engine_type="V8", engine_config="4.5L naturally aspirated",
        variant_scarcity_multiplier=Decimal("2.50"),
        appreciation_stage="momentum",
        notes="Historical analogue for Pista Spider trajectory.",
    )

    ferrari_models = [
        sp3_monza, sf_coupe, sf_gts, sf_competizione, sf_comp_a,
        pista_coupe, pista_spider, laferrari, laferrari_aperta,
        f40, f50, speciale_coupe, speciale_a,
    ]

    # -----------------------------------------------------------------------
    # Bugatti Models
    # -----------------------------------------------------------------------
    chiron = AssetModel(
        manufacturer_id=bugatti.id, name="Chiron", variant=None,
        production_year_start=2016, production_year_end=2022,
        total_produced=500, estimated_liquid_supply=150,
        is_open_top=False, is_limited_edition=True,
        engine_type="W16", engine_config="8.0L quad-turbo",
        msrp_at_launch=Decimal("2998000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("1.50"),
        appreciation_stage="early_appreciation",
    )

    chiron_ss = AssetModel(
        manufacturer_id=bugatti.id, name="Chiron", variant="Super Sport",
        production_year_start=2021, production_year_end=2022,
        total_produced=60, estimated_liquid_supply=20,
        is_open_top=False, is_limited_edition=True, is_invitation_only=True,
        engine_type="W16", engine_config="8.0L quad-turbo, 1600hp",
        msrp_at_launch=Decimal("3900000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("3.50"),
        appreciation_stage="early_appreciation",
        notes="Bugatti in ownership transition. Outgoing W16 gen historically reprices upward after next gen launches. Same pattern as Veyron→Chiron.",
    )

    veyron = AssetModel(
        manufacturer_id=bugatti.id, name="Veyron", variant=None,
        production_year_start=2005, production_year_end=2015,
        total_produced=450, estimated_liquid_supply=200,
        is_open_top=False, is_limited_edition=True,
        engine_type="W16", engine_config="8.0L quad-turbo, 1001hp",
        variant_scarcity_multiplier=Decimal("1.50"),
        appreciation_stage="momentum",
        notes="Historical analogue — repriced significantly after Chiron launch.",
    )

    bugatti_models = [chiron, chiron_ss, veyron]

    # -----------------------------------------------------------------------
    # McLaren Models
    # -----------------------------------------------------------------------
    senna_coupe = AssetModel(
        manufacturer_id=mclaren.id, name="Senna", variant=None,
        production_year_start=2018, production_year_end=2020,
        total_produced=500, estimated_liquid_supply=180,
        is_open_top=False, is_limited_edition=True,
        engine_type="V8", engine_config="4.0L twin-turbo",
        msrp_at_launch=Decimal("958966"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("2.00"),
        appreciation_stage="early_appreciation",
        notes="McLaren financial turbulence capped production. Finding floor and beginning to move.",
    )

    speedtail = AssetModel(
        manufacturer_id=mclaren.id, name="Speedtail", variant=None,
        production_year_start=2019, production_year_end=2020,
        total_produced=106, estimated_liquid_supply=40,
        is_open_top=False, is_limited_edition=True, is_invitation_only=True,
        engine_type="V8 Hybrid", engine_config="4.0L twin-turbo + electric",
        msrp_at_launch=Decimal("2250000"), msrp_currency="USD",
        variant_scarcity_multiplier=Decimal("3.50"),
        appreciation_stage="pre_discovery",
        notes="McLaren financial turbulence guarantees no further production. 106 total.",
    )

    mclaren_models = [senna_coupe, speedtail]

    session.add_all(ferrari_models + bugatti_models + mclaren_models)
    session.flush()

    # -----------------------------------------------------------------------
    # Model Relationships (comparable appreciation pairs)
    # -----------------------------------------------------------------------
    relationships = [
        (sf_coupe, sf_gts, "coupe_to_spider", Decimal("0.850")),
        (sf_coupe, sf_competizione, "standard_to_track", Decimal("0.750")),
        (sf_gts, sf_comp_a, "gts_to_track_spider", Decimal("0.700")),
        (pista_coupe, pista_spider, "coupe_to_spider", Decimal("0.800")),
        (laferrari, laferrari_aperta, "coupe_to_spider", Decimal("0.900")),
        (f40, f50, "generational_successor", Decimal("0.650")),
        (speciale_coupe, speciale_a, "coupe_to_spider", Decimal("0.850")),
        (speciale_a, pista_spider, "historical_analogue", Decimal("0.700")),
        (veyron, chiron, "generational_successor", Decimal("0.750")),
        (chiron, chiron_ss, "standard_to_limited", Decimal("0.800")),
    ]
    for src, rel, rtype, corr in relationships:
        session.add(AssetModelRelationship(
            source_model_id=src.id, related_model_id=rel.id,
            relationship_type=rtype, correlation_strength=corr,
        ))

    # -----------------------------------------------------------------------
    # Ferrari Colour Tiers
    # -----------------------------------------------------------------------
    ferrari_colours = [
        ("Rosso Corsa", "322", ColourTier.TIER_1, False, Decimal("0.00")),
        ("Nero", "DS 1250", ColourTier.TIER_1, False, Decimal("0.00")),
        ("Grigio Silverstone", "740", ColourTier.TIER_1, False, Decimal("-2.00")),
        ("Blu Pozzi", "526", ColourTier.TIER_1, False, Decimal("2.00")),
        ("Blu Tour de France", "521", ColourTier.TIER_1, False, Decimal("3.00")),
        ("Argento Nürburgring", "226", ColourTier.TIER_1, False, Decimal("-1.00")),
        ("Bianco Avus", "100", ColourTier.TIER_2, False, Decimal("-3.00")),
        ("Giallo Modena", "4305", ColourTier.TIER_2, False, Decimal("-5.00")),
        ("Verde British Racing", None, ColourTier.TIER_2, False, Decimal("-4.00")),
        ("Rosso Mugello", None, ColourTier.TIER_2, False, Decimal("-1.00")),
        ("Tailor Made - Custom", None, ColourTier.TIER_3, True, Decimal("-10.00")),
    ]
    for cname, ccode, tier, tm, adj in ferrari_colours:
        session.add(ColourSpec(
            manufacturer_id=ferrari.id, colour_name=cname, colour_code=ccode,
            tier=tier, is_tailor_made=tm, liquidity_adjustment_pct=adj,
        ))

    # -----------------------------------------------------------------------
    # Dealers
    # -----------------------------------------------------------------------
    dealers_data = [
        ("Tom Hartley Jnr", DealerTier.SECONDARY_PREMIUM, "United Kingdom", "Europe", "Ferrari, Porsche hypercars", Decimal("8.00"), True),
        ("Romans International", DealerTier.SECONDARY_PREMIUM, "United Kingdom", "Europe", "Ferrari, McLaren, Lamborghini", Decimal("7.00"), False),
        ("Talacrest", DealerTier.SECONDARY_PREMIUM, "United Kingdom", "Europe", "Classic Ferrari specialist", Decimal("10.00"), False),
        ("Girardo & Co", DealerTier.SECONDARY_PREMIUM, "United Kingdom", "Europe", "Blue-chip collector cars", Decimal("8.00"), False),
        ("Joe Macari", DealerTier.SECONDARY_STANDARD, "United Kingdom", "Europe", "Ferrari, Maserati", Decimal("6.00"), False),
        ("Hexagon Classics", DealerTier.SECONDARY_STANDARD, "United Kingdom", "Europe", "Mixed classic and modern", Decimal("7.00"), False),
        ("DK Engineering", DealerTier.SECONDARY_PREMIUM, "United Kingdom", "Europe", "Ferrari specialist, racing provenance", Decimal("8.00"), False),
        ("Al Ain Class Motors", DealerTier.SECONDARY_PREMIUM, "United Arab Emirates", "Middle East", "Hypercar specialist", Decimal("5.00"), False),
        ("Manhattan Motorcars", DealerTier.ALLOCATION_ACCESS, "United States", "North America", "Authorized Ferrari dealer", Decimal("5.00"), True),
    ]
    for dname, tier, country, region, spec, margin, alloc in dealers_data:
        session.add(Dealer(
            name=dname, tier=tier, country=country, region=region,
            specialisation=spec, typical_margin_pct=margin, has_allocation_access=alloc,
        ))

    # -----------------------------------------------------------------------
    # Auction Houses
    # -----------------------------------------------------------------------
    rm = AuctionHouse(
        name="RM Sotheby's", tier=AuctionHouseTier.MAJOR,
        buyer_premium_pct=Decimal("12.500"), seller_commission_pct=Decimal("10.000"),
        catalogue_fee=Decimal("5000.00"),
        specialisation="Premier collector car auctions worldwide",
    )
    gooding = AuctionHouse(
        name="Gooding & Company", tier=AuctionHouseTier.MAJOR,
        buyer_premium_pct=Decimal("12.000"), seller_commission_pct=Decimal("10.000"),
        catalogue_fee=Decimal("4000.00"),
        specialisation="Pebble Beach specialist, high-end collector cars",
    )
    bonhams = AuctionHouse(
        name="Bonhams", tier=AuctionHouseTier.MID,
        buyer_premium_pct=Decimal("15.000"), seller_commission_pct=Decimal("10.000"),
        catalogue_fee=Decimal("3000.00"),
        specialisation="Quail Lodge, international sales",
    )
    bat = AuctionHouse(
        name="Bring a Trailer", tier=AuctionHouseTier.ONLINE,
        buyer_premium_pct=Decimal("5.000"), seller_commission_pct=Decimal("0.000"),
        catalogue_fee=Decimal("99.00"),
        specialisation="Daily online auctions, highest transaction volume, full public data",
    )
    cab = AuctionHouse(
        name="Cars and Bids", tier=AuctionHouseTier.ONLINE,
        buyer_premium_pct=Decimal("4.500"), seller_commission_pct=Decimal("0.000"),
        catalogue_fee=Decimal("99.00"),
        specialisation="Online auctions, modern enthusiast cars",
    )
    session.add_all([rm, gooding, bonhams, bat, cab])

    # -----------------------------------------------------------------------
    # US 25-Year Import Rule
    # -----------------------------------------------------------------------
    us_25y_rule = MarketRule(
        category=RuleCategory.IMPORT_ELIGIBILITY,
        name="US 25-Year Import Exemption",
        description="Vehicles 25+ years old are exempt from FMVSS standards for US import under 49 USC 30112(b)(9). Opens the world's largest collector car buyer pool.",
        jurisdiction="US",
        effective_date=date(1998, 1, 1),
        rule_logic={"type": "age_threshold", "threshold_years": 25, "exemption": "FMVSS"},
        impact_description="Typically adds 15-30% to market value by opening US buyer pool for previously ineligible non-US-spec vehicles.",
    )
    session.add(us_25y_rule)
    session.flush()

    # 25-year calendar entries for key models approaching eligibility
    session.add(ImportEligibilityCalendar(
        asset_model_id=f40.id, jurisdiction="US",
        manufacture_year=1992, eligible_year=2017, eligible_date=date(2017, 1, 1),
        rule_reference_id=us_25y_rule.id,
        estimated_price_impact_pct=Decimal("20.00"),
        notes="Final year F40s became eligible 2017. Already priced in.",
    ))

    # Ferrari Classiche certification rule
    session.add(MarketRule(
        category=RuleCategory.CERTIFICATION,
        name="Ferrari Classiche Certification",
        description="Official Ferrari certification programme verifying originality and provenance. Red Book certification adds quantifiable value, typically 5-15% premium.",
        jurisdiction=None,
        rule_logic={"type": "certification", "provider": "Ferrari Classiche", "premium_pct_range": [5, 15]},
        impact_description="Classiche-certified cars command 5-15% premium over uncertified equivalents. Required for concours eligibility.",
    ))

    # LHD vs RHD rule
    session.add(MarketRule(
        category=RuleCategory.DRIVE_SIDE,
        name="LHD/RHD Market Premium Differential",
        description="Left-hand drive commands premium in US/EU markets. RHD is neutral in UK/Australia/Japan but discounted 5-15% in LHD markets.",
        jurisdiction=None,
        rule_logic={
            "type": "drive_side_differential",
            "lhd_premium_markets": ["US", "EU", "UAE"],
            "rhd_neutral_markets": ["UK", "Australia", "Japan", "Singapore", "Hong Kong"],
            "rhd_discount_in_lhd_market_pct": -10,
        },
        impact_description="A RHD car in the US is worth 5-15% less than LHD equivalent. No discount in RHD markets.",
    ))

    # UK VAT rule
    session.add(MarketRule(
        category=RuleCategory.TAX_TREATMENT,
        name="UK VAT on Margin Scheme",
        description="UK dealers can sell collector cars under VAT margin scheme — VAT charged only on dealer margin, not full price. UAE has no VAT on vehicles.",
        jurisdiction="UK",
        rule_logic={"type": "tax", "vat_rate": 20, "margin_scheme_eligible": True},
        impact_description="Effective VAT cost is lower under margin scheme. UAE purchases avoid VAT entirely.",
    ))

    # -----------------------------------------------------------------------
    # Cost Model Templates
    # -----------------------------------------------------------------------
    session.add(CostModel(
        name="UK Auction Buy / UK Auction Sell",
        geography="UK", acquisition_channel="auction", exit_channel="auction",
        buyer_premium_pct=Decimal("12.500"), seller_commission_pct=Decimal("10.000"),
        insurance_annual_pct=Decimal("1.250"), storage_monthly=Decimal("800.00"),
        transport_estimate=Decimal("2000.00"), preparation_estimate=Decimal("5000.00"),
        vat_pct=Decimal("20.000"),
    ))
    session.add(CostModel(
        name="UK Dealer Buy / US Auction Sell (Monterey)",
        geography="US", acquisition_channel="dealer", exit_channel="auction",
        buyer_premium_pct=Decimal("0.000"), seller_commission_pct=Decimal("10.000"),
        insurance_annual_pct=Decimal("1.500"), storage_monthly=Decimal("1000.00"),
        transport_estimate=Decimal("8000.00"), preparation_estimate=Decimal("7000.00"),
        import_duty_pct=Decimal("2.500"),
    ))
    session.add(CostModel(
        name="UAE Dealer Buy / UAE Private Sell",
        geography="UAE", acquisition_channel="dealer", exit_channel="private_sale",
        buyer_premium_pct=Decimal("0.000"), seller_commission_pct=Decimal("3.000"),
        insurance_annual_pct=Decimal("1.000"), storage_monthly=Decimal("500.00"),
        transport_estimate=Decimal("1500.00"), preparation_estimate=Decimal("3000.00"),
        vat_pct=Decimal("0.000"),
    ))

    session.commit()
    print(f"Seeded: {len(ferrari_models)} Ferrari models, {len(bugatti_models)} Bugatti models, {len(mclaren_models)} McLaren models")
    print("Seeded: dealers, auction houses, colour specs, model relationships, market rules, cost models")


if __name__ == "__main__":
    engine = create_engine(settings.database_url_sync)
    with Session(engine) as session:
        seed(session)
