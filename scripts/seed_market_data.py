"""
Populate the database with realistic market data:
- Transactions (real-world-representative auction results and dealer listings)
- Fair values for all models
- Signals, opportunity scores, consensus scores
- Portfolio positions with costs
- Alerts
- Risk assessments
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aatp.core.config import settings
from aatp.db.models import (
    Alert,
    AlertSeverity,
    AlertType,
    AssetModel,
    CostCategory,
    CostEntry,
    ConsensusModelScore,
    ConsensusModelType,
    ConsensusScore,
    DataProvenance,
    FairValue,
    OpportunityScore,
    OpportunityStatus,
    Position,
    PositionStatus,
    PortfolioRiskSnapshot,
    RiskAssessment,
    Signal,
    SignalType,
    Transaction,
    TransactionSource,
    TransactionType,
)


def now():
    return datetime.now(timezone.utc)


def seed_market_data(session: Session) -> None:
    # Get all models keyed by name+variant
    models = {}
    for m in session.execute(select(AssetModel)).scalars():
        key = f"{m.name}" + (f" {m.variant}" if m.variant else "")
        models[key] = m

    # Create a data provenance record for seeded data
    prov = DataProvenance(
        source=TransactionSource.MANUAL_ENTRY,
        collected_at=now(),
        raw_content_hash="seed_data_hash",
        is_valid=True,
    )
    session.add(prov)
    session.flush()

    # -------------------------------------------------------------------
    # TRANSACTIONS — realistic auction and dealer data
    # -------------------------------------------------------------------
    txn_data = [
        # Ferrari 812 Superfast
        ("812 Superfast", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2025, 11, 15), Decimal("385000"), "USD", 2019, 4200, "Rosso Corsa", "Nero", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("812 Superfast", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2025, 12, 3), Decimal("392000"), "USD", 2020, 3100, "Grigio Silverstone", "Rosso", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("812 Superfast", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2026, 1, 20), Decimal("410000"), "USD", 2020, 2800, "Nero", "Cuoio", "LHD",
         "United States", "North America", "RM Sotheby's", "Arizona 2026"),
        ("812 Superfast", TransactionSource.DEALER_LISTING, TransactionType.DEALER_LISTING,
         date(2026, 3, 10), Decimal("425000"), "USD", 2021, 1900, "Blu Pozzi", "Crema", "LHD",
         "United Kingdom", "Europe", None, None),
        ("812 Superfast", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2026, 5, 22), Decimal("415000"), "USD", 2020, 5100, "Bianco Avus", "Nero", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("812 Superfast", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2026, 7, 5), Decimal("435000"), "USD", 2021, 1500, "Rosso Corsa", "Nero", "LHD",
         "United Kingdom", "Europe", None, "Tom Hartley Jnr"),

        # Ferrari 812 Superfast GTS
        ("812 Superfast GTS", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 18), Decimal("520000"), "USD", 2021, 2100, "Rosso Corsa", "Crema", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("812 Superfast GTS", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2025, 11, 5), Decimal("545000"), "USD", 2022, 1800, "Blu Tour de France", "Cuoio", "LHD",
         "United Kingdom", "Europe", None, "Romans International"),
        ("812 Superfast GTS", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2026, 2, 14), Decimal("560000"), "USD", 2022, 1200, "Nero", "Rosso", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("812 Superfast GTS", TransactionSource.GOODING, TransactionType.AUCTION_SOLD,
         date(2026, 5, 10), Decimal("585000"), "USD", 2022, 900, "Grigio Silverstone", "Nero", "LHD",
         "United States", "North America", "Gooding & Company", "Amelia Island 2026"),
        ("812 Superfast GTS", TransactionSource.DEALER_LISTING, TransactionType.DEALER_LISTING,
         date(2026, 7, 20), Decimal("610000"), "USD", 2022, 650, "Rosso Corsa", "Crema", "LHD",
         "United Arab Emirates", "Middle East", None, "Al Ain Class Motors"),

        # Ferrari 812 Competizione
        ("812 Competizione", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 16), Decimal("780000"), "USD", 2022, 800, "Rosso Corsa", "Nero Alcantara", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("812 Competizione", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2026, 1, 15), Decimal("810000"), "USD", 2022, 600, "Grigio Silverstone", "Nero", "LHD",
         "United Kingdom", "Europe", None, "Tom Hartley Jnr"),
        ("812 Competizione", TransactionSource.GOODING, TransactionType.AUCTION_SOLD,
         date(2026, 3, 8), Decimal("845000"), "USD", 2022, 450, "Blu Pozzi", "Nero Alcantara", "LHD",
         "United States", "North America", "Gooding & Company", None),

        # Ferrari 812 Competizione A
        ("812 Competizione A", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 17), Decimal("1150000"), "USD", 2022, 300, "Rosso Corsa", "Nero", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("812 Competizione A", TransactionSource.PRIVATE_SALE, TransactionType.PRIVATE_SALE,
         date(2026, 4, 1), Decimal("1250000"), "USD", 2022, 200, "Grigio Silverstone", "Rosso", "LHD",
         "United Kingdom", "Europe", None, None),

        # Ferrari 488 Pista
        ("488 Pista", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2025, 9, 20), Decimal("425000"), "USD", 2019, 3800, "Rosso Corsa", "Nero", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("488 Pista", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2026, 1, 8), Decimal("440000"), "USD", 2020, 2900, "Giallo Modena", "Nero", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("488 Pista", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2026, 5, 15), Decimal("460000"), "USD", 2020, 2100, "Bianco Avus", "Rosso", "LHD",
         "United States", "North America", "RM Sotheby's", None),

        # Ferrari 488 Pista Spider
        ("488 Pista Spider", TransactionSource.GOODING, TransactionType.AUCTION_SOLD,
         date(2025, 8, 15), Decimal("620000"), "USD", 2020, 1500, "Rosso Corsa", "Cuoio", "LHD",
         "United States", "North America", "Gooding & Company", "Monterey 2025"),
        ("488 Pista Spider", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2026, 2, 28), Decimal("650000"), "USD", 2020, 1100, "Nero", "Rosso", "LHD",
         "United Kingdom", "Europe", None, "Romans International"),
        ("488 Pista Spider", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2026, 6, 18), Decimal("680000"), "USD", 2020, 800, "Blu Tour de France", "Crema", "LHD",
         "United States", "North America", "Bring a Trailer", None),

        # LaFerrari
        ("LaFerrari", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 17), Decimal("3800000"), "USD", 2015, 1200, "Rosso Corsa", "Nero", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("LaFerrari", TransactionSource.PRIVATE_SALE, TransactionType.PRIVATE_SALE,
         date(2026, 3, 15), Decimal("3950000"), "USD", 2014, 900, "Nero", "Rosso", "LHD",
         "United Kingdom", "Europe", None, None),

        # LaFerrari Aperta
        ("LaFerrari Aperta", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 11, 9), Decimal("6800000"), "USD", 2017, 400, "Rosso Corsa", "Cuoio", "LHD",
         "United States", "North America", "RM Sotheby's", "New York Icons"),
        ("LaFerrari Aperta", TransactionSource.PRIVATE_SALE, TransactionType.PRIVATE_SALE,
         date(2026, 5, 1), Decimal("7200000"), "USD", 2017, 300, "Blu Pozzi", "Crema", "LHD",
         "United Arab Emirates", "Middle East", None, None),

        # F40
        ("F40", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 16), Decimal("2750000"), "USD", 1991, 12000, "Rosso Corsa", "Black", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("F40", TransactionSource.GOODING, TransactionType.AUCTION_SOLD,
         date(2026, 1, 18), Decimal("2850000"), "USD", 1990, 8500, "Rosso Corsa", "Black", "LHD",
         "United States", "North America", "Gooding & Company", "Scottsdale 2026"),

        # F50
        ("F50", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2026, 1, 19), Decimal("4100000"), "USD", 1996, 6200, "Rosso Corsa", "Tan", "LHD",
         "United States", "North America", "RM Sotheby's", "Arizona 2026"),

        # 458 Speciale
        ("458 Speciale", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2025, 10, 5), Decimal("380000"), "USD", 2014, 8900, "Rosso Corsa", "Nero", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("458 Speciale", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2026, 4, 12), Decimal("395000"), "USD", 2015, 6200, "Bianco Avus", "Nero", "LHD",
         "United States", "North America", "Bring a Trailer", None),

        # 458 Speciale A
        ("458 Speciale A", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 17), Decimal("680000"), "USD", 2015, 3200, "Rosso Corsa", "Cuoio", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("458 Speciale A", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2026, 6, 1), Decimal("720000"), "USD", 2015, 2100, "Blu Pozzi", "Crema", "LHD",
         "United Kingdom", "Europe", None, "Girardo & Co"),

        # SP3 Monza
        ("SP3 Monza", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 18), Decimal("4500000"), "USD", 2019, 150, "Argento", "Rosso", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),

        # Bugatti Chiron
        ("Chiron", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 11, 10), Decimal("3200000"), "USD", 2019, 2500, "Nocturne/Silver", "Black", "LHD",
         "United States", "North America", "RM Sotheby's", None),
        ("Chiron", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2026, 4, 20), Decimal("3350000"), "USD", 2020, 1800, "Blue Royal/Atlantic Blue", "Beluga", "LHD",
         "United Arab Emirates", "Middle East", None, "Al Ain Class Motors"),

        # Bugatti Chiron Super Sport
        ("Chiron Super Sport", TransactionSource.PRIVATE_SALE, TransactionType.PRIVATE_SALE,
         date(2026, 3, 1), Decimal("5200000"), "USD", 2022, 500, "Nocturne", "Havana Brown", "LHD",
         "United Arab Emirates", "Middle East", None, None),

        # Bugatti Veyron
        ("Veyron", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 11, 9), Decimal("1850000"), "USD", 2008, 8500, "Blue/Silver", "Tan", "LHD",
         "United States", "North America", "RM Sotheby's", None),
        ("Veyron", TransactionSource.GOODING, TransactionType.AUCTION_SOLD,
         date(2026, 1, 17), Decimal("1950000"), "USD", 2010, 5200, "Black/Red", "Black", "LHD",
         "United States", "North America", "Gooding & Company", "Scottsdale 2026"),

        # McLaren Senna
        ("Senna", TransactionSource.BRING_A_TRAILER, TransactionType.AUCTION_SOLD,
         date(2025, 10, 28), Decimal("850000"), "USD", 2019, 1200, "MSO Aurora Blue", "Black Alcantara", "LHD",
         "United States", "North America", "Bring a Trailer", None),
        ("Senna", TransactionSource.DEALER_LISTING, TransactionType.DEALER_SOLD,
         date(2026, 5, 8), Decimal("920000"), "USD", 2019, 800, "MSO Belize Blue", "Black", "LHD",
         "United Kingdom", "Europe", None, "Romans International"),

        # McLaren Speedtail
        ("Speedtail", TransactionSource.RM_SOTHEBYS, TransactionType.AUCTION_SOLD,
         date(2025, 8, 16), Decimal("2100000"), "USD", 2020, 600, "Heritage Paint", "Saddle Tan", "LHD",
         "United States", "North America", "RM Sotheby's", "Monterey 2025"),
        ("Speedtail", TransactionSource.PRIVATE_SALE, TransactionType.PRIVATE_SALE,
         date(2026, 6, 15), Decimal("2350000"), "USD", 2020, 350, "MSO Bespoke Silver", "Black", "LHD",
         "United Kingdom", "Europe", None, None),
    ]

    ext_counter = 0
    for row in txn_data:
        name, source, txn_type, txn_date, price, currency, year, miles, ext_col, int_col, drive, country, region, ah, dealer = row
        model = models.get(name)
        if not model:
            continue
        ext_counter += 1
        t = Transaction(
            provenance_id=prov.id,
            asset_model_id=model.id,
            source=source,
            external_id=f"SEED-{ext_counter:04d}",
            transaction_type=txn_type,
            transaction_date=txn_date,
            total_price=price,
            total_price_usd=price,
            normalised_price_usd=price,
            currency=currency,
            year=year,
            mileage=miles,
            colour_exterior=ext_col,
            colour_interior=int_col,
            drive_side=drive,
            sale_country=country,
            sale_region=region,
            auction_house=ah,
            dealer_name=dealer,
            has_books=True,
            has_tools=True,
            service_history_complete=True,
        )
        session.add(t)

    session.flush()
    print(f"  Transactions: {ext_counter}")

    # -------------------------------------------------------------------
    # FAIR VALUES — current valuations for all models
    # -------------------------------------------------------------------
    fv_data = {
        "812 Superfast":      (Decimal("380000"), Decimal("420000"), Decimal("460000"), "early_appreciation", Decimal("2.5"), Decimal("8.0"), Decimal("12.0")),
        "812 Superfast GTS":  (Decimal("540000"), Decimal("580000"), Decimal("625000"), "early_appreciation", Decimal("3.2"), Decimal("10.5"), Decimal("18.0")),
        "812 Competizione":   (Decimal("780000"), Decimal("830000"), Decimal("890000"), "momentum", Decimal("4.0"), Decimal("12.0"), Decimal("22.0")),
        "812 Competizione A": (Decimal("1100000"), Decimal("1200000"), Decimal("1350000"), "momentum", Decimal("5.0"), Decimal("15.0"), Decimal("28.0")),
        "488 Pista":          (Decimal("420000"), Decimal("450000"), Decimal("490000"), "early_appreciation", Decimal("2.0"), Decimal("6.5"), Decimal("10.0")),
        "488 Pista Spider":   (Decimal("630000"), Decimal("670000"), Decimal("720000"), "pre_discovery", Decimal("3.5"), Decimal("11.0"), Decimal("16.0")),
        "LaFerrari":          (Decimal("3600000"), Decimal("3900000"), Decimal("4200000"), "maturity", Decimal("1.5"), Decimal("4.0"), Decimal("6.0")),
        "LaFerrari Aperta":   (Decimal("6500000"), Decimal("7000000"), Decimal("7800000"), "maturity", Decimal("2.0"), Decimal("5.5"), Decimal("8.0")),
        "F40":                (Decimal("2600000"), Decimal("2800000"), Decimal("3100000"), "maturity", Decimal("1.0"), Decimal("3.5"), Decimal("5.0")),
        "F50":                (Decimal("3800000"), Decimal("4100000"), Decimal("4500000"), "maturity", Decimal("1.2"), Decimal("4.0"), Decimal("6.5")),
        "458 Speciale":       (Decimal("360000"), Decimal("390000"), Decimal("420000"), "momentum", Decimal("2.0"), Decimal("6.0"), Decimal("9.0")),
        "458 Speciale A":     (Decimal("650000"), Decimal("700000"), Decimal("760000"), "momentum", Decimal("3.0"), Decimal("9.0"), Decimal("14.0")),
        "SP3 Monza":          (Decimal("4000000"), Decimal("4500000"), Decimal("5200000"), "maturity", Decimal("1.5"), Decimal("5.0"), Decimal("8.0")),
        "Chiron":             (Decimal("3000000"), Decimal("3300000"), Decimal("3600000"), "early_appreciation", Decimal("2.5"), Decimal("7.0"), Decimal("11.0")),
        "Chiron Super Sport": (Decimal("4800000"), Decimal("5200000"), Decimal("5800000"), "early_appreciation", Decimal("3.0"), Decimal("9.0"), Decimal("15.0")),
        "Veyron":             (Decimal("1700000"), Decimal("1900000"), Decimal("2100000"), "momentum", Decimal("2.0"), Decimal("6.0"), Decimal("10.0")),
        "Senna":              (Decimal("800000"), Decimal("900000"), Decimal("1000000"), "early_appreciation", Decimal("3.5"), Decimal("10.0"), Decimal("14.0")),
        "Speedtail":          (Decimal("2000000"), Decimal("2250000"), Decimal("2500000"), "pre_discovery", Decimal("4.0"), Decimal("12.0"), Decimal("18.0")),
    }

    fv_count = 0
    for name, (low, mid, high, stage, r30, r90, r365) in fv_data.items():
        model = models.get(name)
        if not model:
            continue
        fv = FairValue(
            asset_model_id=model.id,
            valuation_date=date(2026, 8, 15),
            fair_value_low=low,
            fair_value_mid=mid,
            fair_value_high=high,
            confidence_score=Decimal("0.850"),
            comparable_count=5,
            comparable_window_months=12,
            appreciation_stage=stage,
            appreciation_rate_30d=r30,
            appreciation_rate_90d=r90,
            appreciation_rate_365d=r365,
            methodology="Comparable transaction analysis with mileage/colour/provenance normalisation",
        )
        session.add(fv)
        fv_count += 1
    session.flush()
    print(f"  Fair values: {fv_count}")

    # -------------------------------------------------------------------
    # SIGNALS — active opportunity signals
    # -------------------------------------------------------------------
    signal_data = [
        ("812 Superfast GTS", SignalType.MOMENTUM, Decimal("0.820"), 1, Decimal("0.900"),
         "12-month price trajectory +18%. V12 convertible scarcity driving sustained demand."),
        ("812 Superfast GTS", SignalType.COMPARABLE_APPRECIATION, Decimal("0.750"), 1, Decimal("0.850"),
         "458 Speciale A followed identical trajectory 3 years earlier. GTS is at the same inflection point."),
        ("812 Competizione", SignalType.MOMENTUM, Decimal("0.880"), 1, Decimal("0.920"),
         "Strong upward momentum. 22% appreciation over 12 months. Invitation-only allocation premium widening."),
        ("812 Competizione A", SignalType.MOMENTUM, Decimal("0.900"), 1, Decimal("0.950"),
         "Fastest appreciating 812 variant. 28% 12-month return. Only 599 produced."),
        ("488 Pista Spider", SignalType.CATALYST, Decimal("0.700"), 1, Decimal("0.800"),
         "Pre-catalyst: under 500 produced, V8 at peak before electrification. No headline auction moment yet."),
        ("488 Pista Spider", SignalType.COMPARABLE_APPRECIATION, Decimal("0.720"), 1, Decimal("0.830"),
         "Historical analogue: 458 Speciale A trajectory. Pista Spider is 2 years behind on the appreciation curve."),
        ("Chiron Super Sport", SignalType.CATALYST, Decimal("0.650"), 1, Decimal("0.780"),
         "Bugatti ownership transition catalyst. Outgoing W16 generation historically reprices after successor reveal."),
        ("Chiron Super Sport", SignalType.COMPARABLE_APPRECIATION, Decimal("0.680"), 1, Decimal("0.800"),
         "Veyron repriced 40% over 3 years post-Chiron launch. Same pattern likely for Chiron→next gen."),
        ("Speedtail", SignalType.CATALYST, Decimal("0.600"), 1, Decimal("0.750"),
         "McLaren financial turbulence guarantees no further production. Only 106 exist. Floor finding."),
        ("Senna", SignalType.MOMENTUM, Decimal("0.720"), 1, Decimal("0.840"),
         "Finding floor after McLaren restructuring. Production capped. 14% 12-month appreciation."),
        ("LaFerrari Aperta", SignalType.VOLUME_SPIKE, Decimal("0.500"), 1, Decimal("0.700"),
         "Two market appearances in 6 months after 18-month drought. Each sale set new price floor."),
        ("Veyron", SignalType.MOMENTUM, Decimal("0.650"), 1, Decimal("0.800"),
         "Steady 10% annual appreciation. Now firmly in collector car territory."),
    ]

    sig_count = 0
    for name, sig_type, strength, direction, confidence, desc in signal_data:
        model = models.get(name)
        if not model:
            continue
        sig = Signal(
            asset_model_id=model.id,
            signal_type=sig_type,
            strength=strength,
            direction=direction,
            confidence=confidence,
            description=desc,
            supporting_data={"source": "seed_data"},
            transaction_count=5,
            is_active=True,
        )
        session.add(sig)
        sig_count += 1
    session.flush()
    print(f"  Signals: {sig_count}")

    # -------------------------------------------------------------------
    # OPPORTUNITY SCORES
    # -------------------------------------------------------------------
    opp_data = [
        ("812 Superfast GTS", Decimal("7.850"), 2, OpportunityStatus.ACTIONABLE, Decimal("0.800"), Decimal("25.0"), 90),
        ("812 Competizione A", Decimal("8.500"), 1, OpportunityStatus.ACTIONABLE, Decimal("0.700"), Decimal("35.0"), 60),
        ("488 Pista Spider", Decimal("7.200"), 2, OpportunityStatus.WATCHLIST, Decimal("0.750"), Decimal("22.0"), 180),
        ("Chiron Super Sport", Decimal("6.800"), 2, OpportunityStatus.WATCHLIST, Decimal("0.600"), Decimal("18.0"), 365),
        ("Speedtail", Decimal("6.500"), 1, OpportunityStatus.WATCHLIST, Decimal("0.550"), Decimal("20.0"), 270),
        ("Senna", Decimal("7.100"), 1, OpportunityStatus.WATCHLIST, Decimal("0.700"), Decimal("16.0"), 120),
    ]

    opp_count = 0
    for name, score, sig_ct, status, liq, ret, ttc in opp_data:
        model = models.get(name)
        if not model:
            continue
        opp = OpportunityScore(
            asset_model_id=model.id,
            composite_score=score,
            signal_count=sig_ct,
            signal_breakdown={"momentum": 1, "catalyst": 1},
            liquidity_score=liq,
            cost_adjusted_return_pct=ret,
            time_to_catalyst_days=ttc,
            status=status,
        )
        session.add(opp)
        opp_count += 1
    session.flush()
    print(f"  Opportunity scores: {opp_count}")

    # -------------------------------------------------------------------
    # CONSENSUS SCORES — 6-model consensus for key models
    # -------------------------------------------------------------------
    consensus_configs = [
        ("812 Superfast GTS", 8, False, OpportunityStatus.ACTIONABLE, True),
        ("812 Competizione A", 10, False, OpportunityStatus.ACTIONABLE, True),
        ("488 Pista Spider", 6, False, OpportunityStatus.WATCHLIST, False),
        ("Chiron Super Sport", 5, False, OpportunityStatus.WATCHLIST, False),
        ("Speedtail", 4, False, OpportunityStatus.WATCHLIST, False),
        ("Senna", 6, False, OpportunityStatus.WATCHLIST, False),
        ("812 Competizione", 9, False, OpportunityStatus.ACTIONABLE, True),
        ("LaFerrari", 3, False, OpportunityStatus.PASSED, False),
    ]

    model_score_templates = [
        (ConsensusModelType.MOMENTUM, "Strong upward price trajectory supported by declining inventory"),
        (ConsensusModelType.FUNDAMENTAL_VALUE, "Trading below replacement cost with production confirmed ended"),
        (ConsensusModelType.LIQUIDITY, "Adequate market depth with 3-6 month typical time to sale"),
        (ConsensusModelType.SENTIMENT, "Positive collector sentiment; featured in major publications"),
        (ConsensusModelType.MACRO, "Alternative asset allocation increasing in UHNW portfolios"),
        (ConsensusModelType.RULES, "No regulatory headwinds; import eligible in major markets"),
    ]

    con_count = 0
    for name, agg, veto, status, actionable in consensus_configs:
        model = models.get(name)
        if not model:
            continue
        cs = ConsensusScore(
            asset_model_id=model.id,
            aggregate_score=agg,
            has_veto=veto,
            status=status,
            actionable=actionable,
        )
        session.add(cs)
        session.flush()

        for i, (mtype, rationale) in enumerate(model_score_templates):
            score = min(2, max(-2, (agg - 3) // 2 + (1 if i < 2 else 0)))
            cms = ConsensusModelScore(
                consensus_score_id=cs.id,
                model_type=mtype,
                score=score,
                confidence=Decimal("0.800") + Decimal(str(i * 0.02)),
                rationale=rationale,
                supporting_data={"source": "seed_data"},
            )
            session.add(cms)
        con_count += 1
    session.flush()
    print(f"  Consensus scores: {con_count}")

    # -------------------------------------------------------------------
    # POSITIONS — portfolio holdings
    # -------------------------------------------------------------------
    positions_data = [
        ("812 Superfast GTS", "2022 Ferrari 812 GTS — Rosso Corsa / Crema, 1,200 miles",
         2022, "Rosso Corsa", "Crema", 1200,
         date(2025, 6, 15), Decimal("495000"), "Tom Hartley Jnr",
         Decimal("580000"), Decimal("52500"), Decimal("18500"), Decimal("566000"),
         Decimal("14000"), Decimal("0.168")),
        ("812 Competizione", "2022 Ferrari 812 Competizione — Grigio Silverstone / Nero, 450 miles",
         2022, "Grigio Silverstone", "Nero Alcantara", 450,
         date(2025, 9, 1), Decimal("750000"), "Private sale",
         Decimal("830000"), Decimal("37500"), Decimal("12000"), Decimal("799500"),
         Decimal("30500"), Decimal("0.042")),
        ("488 Pista Spider", "2020 Ferrari 488 Pista Spider — Blu TdF / Crema, 800 miles",
         2020, "Blu Tour de France", "Crema", 800,
         date(2026, 1, 10), Decimal("610000"), "Romans International",
         Decimal("670000"), Decimal("30500"), Decimal("8500"), Decimal("649000"),
         Decimal("21000"), Decimal("0.055")),
        ("Senna", "2019 McLaren Senna — MSO Volcano Orange / Carbon, 650 miles",
         2019, "MSO Volcano Orange", "Carbon Black", 650,
         date(2025, 12, 1), Decimal("830000"), "Private sale",
         Decimal("900000"), Decimal("41500"), Decimal("14000"), Decimal("885500"),
         Decimal("14500"), Decimal("0.024")),
    ]

    pos_ids = []
    for name, desc, year, ext_c, int_c, miles, acq_date, acq_price, channel, fv, acq_costs, hold_costs, cost_basis, pnl, irr in positions_data:
        model = models.get(name)
        if not model:
            continue
        pos = Position(
            asset_model_id=model.id,
            status=PositionStatus.OPEN,
            year=year,
            description=desc,
            colour_exterior=ext_c,
            colour_interior=int_c,
            mileage_at_acquisition=miles,
            acquisition_date=acq_date,
            acquisition_price=acq_price,
            acquisition_currency="USD",
            acquisition_price_usd=acq_price,
            acquisition_channel=channel,
            current_fair_value_usd=fv,
            fair_value_date=date(2026, 8, 15),
            total_acquisition_costs=acq_costs,
            total_holding_costs=hold_costs,
            total_cost_basis=cost_basis,
            unrealised_pnl=pnl,
            irr=irr,
            storage_location="Windrush Car Storage, London",
            insurance_provider="Hagerty",
        )
        session.add(pos)
        session.flush()
        pos_ids.append(pos.id)

        # Add cost entries
        for cat, amt, cdesc in [
            (CostCategory.TRANSPORT, Decimal("3500"), "UK collection and delivery to storage"),
            (CostCategory.INSURANCE, Decimal("6000"), "Annual Hagerty agreed-value policy"),
            (CostCategory.STORAGE, Decimal("9600"), "Windrush dehumidified storage 12 months"),
            (CostCategory.INSPECTION, Decimal("2500"), "Pre-purchase inspection"),
            (CostCategory.DETAILING, Decimal("1500"), "Full paint correction and ceramic coating"),
        ]:
            session.add(CostEntry(
                position_id=pos.id,
                cost_category=cat,
                cost_date=acq_date,
                amount=amt,
                currency="USD",
                amount_usd=amt,
                description=cdesc,
            ))

    session.flush()
    print(f"  Positions: {len(pos_ids)}")

    # -------------------------------------------------------------------
    # RISK ASSESSMENTS
    # -------------------------------------------------------------------
    for pid in pos_ids:
        session.add(RiskAssessment(
            position_id=pid,
            liquidity_risk_score=Decimal("0.400"),
            concentration_risk_score=Decimal("0.250"),
            physical_risk_score=Decimal("0.150"),
            counterparty_risk_score=Decimal("0.100"),
            spec_risk_score=Decimal("0.200"),
            provenance_risk_score=Decimal("0.120"),
            composite_risk_score=Decimal("0.330"),
            risk_explanation="Moderate overall risk. Liquidity is the primary concern given niche market. Concentration in Ferrari mitigated by different model segments.",
            risk_factors={
                "volatility_30d": 3.2,
                "volatility_90d": 5.1,
                "beta_to_market": 0.85,
                "time_to_liquidity_days": 90,
            },
        ))

    # Portfolio-level risk
    session.add(PortfolioRiskSnapshot(
        snapshot_date=date(2026, 8, 15),
        manufacturer_concentration={"Ferrari": 0.72, "McLaren": 0.28},
        era_concentration={"2018-2022": 0.85, "2013-2017": 0.15},
        type_concentration={"V12": 0.48, "V8": 0.28, "V8 twin-turbo": 0.24},
        max_manufacturer_exposure_pct=Decimal("72.00"),
        total_illiquid_90d_pct=Decimal("15.00"),
        scenario_analysis={
            "market_downturn_20pct": {"portfolio_impact_pct": -18.5, "worst_position": "Senna"},
            "ferrari_brand_event": {"portfolio_impact_pct": -12.0, "affected_positions": 3},
            "interest_rate_hike_200bps": {"portfolio_impact_pct": -8.0},
        },
        narrative="Portfolio is concentrated in Ferrari (72%) with moderate liquidity risk. Diversification into McLaren provides some hedging. All positions are in the modern collector car segment (2018-2022 production). Key risk: a broad market correction would impact all positions simultaneously due to high correlation within the hypercar segment.",
    ))
    session.flush()
    print(f"  Risk assessments: {len(pos_ids)} + 1 portfolio snapshot")

    # -------------------------------------------------------------------
    # ALERTS
    # -------------------------------------------------------------------
    alert_data = [
        (AlertType.PRICE_MOVEMENT, AlertSeverity.INFO,
         "812 GTS: +3.2% in 30 days",
         "Ferrari 812 Superfast GTS fair value increased from $562K to $580K over the past 30 days, driven by Amelia Island auction result."),
        (AlertType.AUCTION_RESULT, AlertSeverity.INFO,
         "812 Competizione: $845K at Gooding",
         "Ferrari 812 Competizione sold for $845,000 at Gooding & Company, 2% above previous comparable."),
        (AlertType.CONSENSUS_CHANGE, AlertSeverity.WARNING,
         "812 Competizione A: consensus upgraded to ACTIONABLE",
         "Consensus engine upgraded 812 Competizione A from WATCHLIST to ACTIONABLE. 5 of 6 models bullish, aggregate score 10/12."),
        (AlertType.CATALYST, AlertSeverity.WARNING,
         "Bugatti successor announcement expected Q4 2026",
         "Industry sources indicate Bugatti Tourbillon (Chiron successor) production start Q1 2027. Historical pattern: outgoing generation reprices 15-30% in the 12 months following successor reveal."),
        (AlertType.HOLDING_COST_WARNING, AlertSeverity.INFO,
         "Senna: holding costs approaching 5% of acquisition",
         "McLaren Senna position holding costs are $14,000 (1.7% of $830K acquisition). Annual run rate of $19,600 if held 12 months."),
        (AlertType.LIQUIDITY_WARNING, AlertSeverity.WARNING,
         "Speedtail: low market liquidity",
         "Only 2 McLaren Speedtail transactions observed in the past 12 months across all tracked sources. Estimated time to sale: 6-9 months."),
        (AlertType.PRICE_MOVEMENT, AlertSeverity.CRITICAL,
         "LaFerrari Aperta: private sale at $7.2M",
         "LaFerrari Aperta private sale reported at $7,200,000 in UAE — new market high. Previous comparable was $6.8M at RM Sotheby's in November 2025."),
        (AlertType.AUCTION_RESULT, AlertSeverity.INFO,
         "488 Pista Spider: $680K on BaT",
         "Ferrari 488 Pista Spider sold for $680,000 on Bring a Trailer, a 4.6% increase over the February dealer sale. Colour premium for Blu Tour de France."),
    ]

    alert_count = 0
    for atype, severity, title, message in alert_data:
        session.add(Alert(
            alert_type=atype,
            severity=severity,
            title=title,
            message=message,
            is_read=False,
        ))
        alert_count += 1
    session.flush()
    print(f"  Alerts: {alert_count}")

    session.commit()
    print("\nAll market data seeded successfully.")


if __name__ == "__main__":
    engine = create_engine(settings.database_url_sync)
    with Session(engine) as session:
        seed_market_data(session)
