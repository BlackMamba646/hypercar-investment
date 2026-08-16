# AATP — Alternative Asset Trading Platform

## Complete Project Plan

A production-grade quantitative hedge fund technology stack applied to physical alternative assets, starting with luxury hypercars/supercars. Asset-class agnostic at schema level — extensible to watches, wine, whisky, art.

---

## Investment Thesis

- **Core edge:** Supply asymmetry in limited-production variants (Spider / GTS / open-top) that structurally appreciate faster than their coupe counterparts
- **Layered scarcity:** Model scarcity + variant scarcity + spec scarcity compounds the appreciation ceiling
- **Target return:** 25%+ net return after brutal transaction costs (buyer premium, seller commission, storage, insurance, transport, preparation)
- **Hold period:** 1–2 years
- **Key models:**
  - Ferrari: SP3 Monza, 812 GTS, 488 Pista Spider, LaFerrari Aperta, 458 Speciale Aperta, F40, F50
  - Bugatti: Chiron Super Sport, Veyron Grand Sport
  - McLaren: Senna, Speedtail
  - Lamborghini: Aventador SVJ, Centenario
  - Porsche: 918 Spyder

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.9+ |
| Web framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async, asyncpg driver) |
| Database | PostgreSQL |
| Migrations | Alembic |
| Cache / broker | Redis |
| Task queue | Celery with Redis broker |
| Scraping | httpx (async), BeautifulSoup, lxml |
| Retry logic | tenacity |
| Data analysis | NumPy, pandas, scipy, scikit-learn |
| Logging | structlog (JSON in prod, console in dev) |
| Config | pydantic-settings (.env) |
| Testing | pytest, pytest-asyncio, respx, factory-boy |
| Linting | ruff |
| Type checking | mypy (strict) |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AATP Architecture                            │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────────┤
│  DATA    │  FAIR    │ SIGNAL   │CONSENSUS │  RISK    │  EXECUTION   │
│COLLECTION│  VALUE   │ ENGINE   │ ENGINE   │ ENGINE   │   ENGINE     │
│ (M2)     │  (M3)    │  (M4)    │  (M5)    │  (M6)    │    (M7)      │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────────┤
│                      TRADING LEDGER (M8)                            │
├─────────────────────────────────────────────────────────────────────┤
│              RECONCILIATION & MONITORING (M9)                       │
├─────────────────────────────────────────────────────────────────────┤
│                    BACKTESTING (M10)                                 │
├─────────────────────────────────────────────────────────────────────┤
│              PostgreSQL SCHEMA (M1) — Foundation                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Build Sequence (Strict Order)

The modules are built in dependency order. Each module depends on the ones above it.

---

### MODULE 1: Database Schema & Asset Catalog — COMPLETED

**Status: DONE**

**What it does:** Defines the entire data model — 30 tables, 16 enum types, covering all 10 modules. Asset-class agnostic: every table that references an asset uses `asset_class` enum (car, watch, wine, whisky, art). UUID primary keys, timezone-aware timestamps, JSONB for extensible metadata.

**Files:**
- `aatp/db/base.py` — `Base`, `TimestampMixin`, `UUIDPrimaryKeyMixin`
- `aatp/db/models.py` — All 30 table models (~1060 lines)
- `aatp/db/session.py` — Async session factory
- `aatp/core/config.py` — Pydantic settings (DB, Redis, Celery, scraper config, alert thresholds)
- `aatp/core/logging.py` — Structlog configuration
- `alembic/versions/001_initial_schema.py` — Full migration with all tables, indexes, constraints
- `scripts/seed_data.py` — Seeds 9 manufacturers, 13 Ferrari models, 3 Bugatti, 2 McLaren, colours, dealers, auction houses, market rules, cost models

**Tables by module:**

| Module | Tables |
|---|---|
| M1 Catalog | manufacturers, asset_models, asset_model_relationships, colour_specs, option_specs |
| M1 Market Data | data_provenance, transactions, currency_rates, news_articles, forum_sentiments, macro_indicators |
| M1 Rules | market_rules, import_eligibility_calendar, rule_model_flags |
| M3 Valuation | fair_values, mileage_curves, cost_models |
| M4 Signals | signals, opportunity_scores |
| M5 Consensus | consensus_scores, consensus_model_scores |
| M6 Risk | risk_assessments, portfolio_risk_snapshots |
| M7 Execution | dealers, auction_houses, auction_events, spec_guides |
| M8 Ledger | positions, cost_entries, ledger_entries, portfolio_snapshots |
| M9 Reconciliation | reconciliation_runs, alerts |
| M10 Backtesting | backtest_runs, backtest_signals, backtest_model_validations |
| System | scraper_runs |

**Key enums:** AssetClass, TransactionSource, TransactionType, ColourTier, ConditionGrade, SignalType, ConsensusModelType, OpportunityStatus, PositionStatus, CostCategory, AlertType, AlertSeverity, RuleCategory, DealerTier, AuctionHouseTier

**Design decisions:**
- `Mapped[Optional[X]]` syntax for Python 3.9 compatibility (not `X | None`)
- `from __future__ import annotations` on all DB files
- Immutable `ledger_entries` — no UPDATE, only correction entries via `corrects_entry_id`
- ConsensusModelScore has `CheckConstraint("score >= -2 AND score <= 2")`
- `normalised_price_usd` stored on transactions with full breakdown of 6 adjustment percentages

---

### MODULE 2: Data Collection & Scrapers — COMPLETED

**Status: DONE** (63/63 tests passing)

**What it does:** Scrapes auction results from Bring a Trailer and RM Sotheby's. Stores raw HTML with full provenance. Parses structured data (title, year, price, mileage, colours, VIN, location). Normalises prices across 6 dimensions to produce comparable values. Fuzzy-matches listings to asset models in the catalog.

**Files:**
- `aatp/collectors/base.py` — Abstract `BaseScraper` with rate limiting (token-bucket), tenacity retry, provenance storage, duplicate detection, semaphore-controlled concurrency
- `aatp/collectors/bat.py` — Bring a Trailer scraper: 18 search terms, listing parser, BaT buyer premium (5% capped at $5k)
- `aatp/collectors/rmsothebys.py` — RM Sotheby's scraper: auction calendar → event pages → lot parser, tiered buyer premium (12.5% on first $250k, 12% on $250k-$1M, 10% above $1M)
- `aatp/collectors/model_matcher.py` — Fuzzy asset model matching with exact name (0.7 confidence), name+variant (0.95), token similarity (0.8*ratio), variant indicator detection, year/manufacturer filtering
- `aatp/collectors/normalisation.py` — 6-dimension normalisation pipeline
- `aatp/collectors/tasks.py` — Celery task wrappers
- `aatp/core/celery_app.py` — Beat schedule: BaT daily 6AM UTC, RM Sotheby's weekly Monday 8AM, normalisation daily 7AM

**Normalisation pipeline (6 adjustments):**

| Dimension | Logic |
|---|---|
| Mileage | 8 bands: delivery miles (+5%) → 50k+ (-15%). Model-specific `mileage_curves` override defaults |
| Colour | Tier 1 (0%), Tier 2 (-3%), Tier 3 (-8%). Lookup from `colour_specs`, heuristic fallback |
| Options | Keyword scoring: racing seats +1.5%, carbon ceramic +1.5%, aftermarket -2%, modified -3%. Capped at +5% total |
| Geography | US baseline. UK -2%, UAE -3%, CH +1%. RHD in LHD market -7% |
| Provenance | Books +2% (missing -3%), service history +2% (missing -4%), single owner +2%, celebrity +5%, Classiche +3%, accident -10% |
| Condition | NLP keyword grading: concours +8%, excellent +3%, good 0%, fair -8%, project -25% |

**Formula:** `normalised_price = total_price_usd / (1 + total_adjustment_pct / 100)`

**Tests (63 total):**
- `tests/unit/test_bat_parser.py` — 18 tests: search URL extraction, listing parsing, BaT premium calculations
- `tests/unit/test_rm_parser.py` — 17 tests: lot parsing, tiered premium, country inference
- `tests/unit/test_normalisation.py` — 18 tests: mileage bands, colour tiers, condition NLP
- `tests/unit/test_model_matcher.py` — 10 tests: exact/fuzzy matching, filtering, no-match

**Test fixtures:**
- `tests/fixtures/bat_listing.html` — Realistic BaT auction listing
- `tests/fixtures/bat_search.html` — BaT search results page
- `tests/fixtures/rm_lot.html` — RM Sotheby's lot page

---

### MODULE 3: Fair Value & Quote Engine — TODO (NEXT)

**Status: NOT STARTED**

**What it does:** Produces point-in-time fair value estimates (low / mid / high) for each asset model, with confidence intervals. Three sub-models feed into the fair value:

#### 3A. Comparable Transaction Model
- Query normalised transactions for the same `asset_model_id` within a configurable lookback window (default 12 months)
- Weight recent transactions higher (exponential decay: half-life ~90 days)
- Compute weighted percentiles: P25 = low, P50 = mid, P75 = high
- Confidence score derived from: comparable count, recency spread, price dispersion (coefficient of variation)
- Minimum 3 comparables required for a valuation; below that, widen window or flag low confidence
- Store comparable transaction IDs in `fair_values.comparable_transaction_ids` for audit

#### 3B. Appreciation Curve Modelling
- Track normalised price over time per model to compute rolling appreciation rates (30d, 90d, 365d)
- Classify appreciation stage: `discovery` → `acceleration` → `plateau` → `correction`
- Stage detection rules:
  - Discovery: appreciation_rate_365d > 5%, fewer than 10 comparables, limited auction frequency
  - Acceleration: appreciation_rate_90d > 15% annualised, increasing volume
  - Plateau: appreciation_rate_90d < 5%, stable volume
  - Correction: negative 90d rate, or single large decline > 10%
- Use related models (`asset_model_relationships`) for cross-model appreciation signals (e.g., if 812 Superfast appreciated 20%, predict GTS will follow)

#### 3C. Cost-Adjusted Return Modelling
- Given a hypothetical acquisition price and a `cost_model`, compute net return after all costs
- Cost stack:
  - Acquisition: buyer premium (from auction house schedule)
  - Holding: insurance (annual % of value), storage (monthly), maintenance estimate
  - Exit: seller commission, transport, preparation/detailing, photography, catalogue fee
  - Tax: import duty, VAT (if applicable)
- IRR calculation over projected hold period
- Break-even hold period: minimum months to achieve target net return
- Monte Carlo simulation for return distribution (optional, stretch)

#### Fair Value Output
- Writes to `fair_values` table with: low/mid/high, confidence_score, comparable_count, appreciation rates, methodology description, model_parameters, warnings
- Warnings examples: "Only 4 comparables in 12 months — widen window", "All comparables from single auction house", "Price dispersion > 30% — consider spec-specific valuation"

**Files to create:**
- `aatp/valuation/comparable.py` — Comparable transaction model
- `aatp/valuation/appreciation.py` — Appreciation curve and stage detection
- `aatp/valuation/cost_return.py` — Cost-adjusted return calculator
- `aatp/valuation/engine.py` — Orchestrator that runs all three sub-models and writes FairValue
- `aatp/valuation/tasks.py` — Celery tasks for scheduled valuation runs
- `tests/unit/test_comparable.py`
- `tests/unit/test_appreciation.py`
- `tests/unit/test_cost_return.py`

---

### MODULE 4: Signal Engine & Opportunity Scanner — TODO

**Status: NOT STARTED**

**What it does:** Generates trading signals from fair value data, market events, and external catalysts. Each signal has type, strength (-1 to +1), direction (-1/0/+1), confidence, and supporting data.

#### Signal Types

| Signal | Logic |
|---|---|
| MOMENTUM | Price moving up/down vs. fair value over 30/90d windows. Trigger: > 5% deviation from expected appreciation |
| DEALER_AUCTION_SPREAD | When dealer asking prices diverge from auction results. Large spread = arbitrage opportunity |
| CATALYST | Upcoming events that could move prices: new model announcement, Monterey/Geneva week, production end, homologation milestone |
| VOLUME_SPIKE | Unusual transaction volume for a model. Could signal market turning point |
| COMPARABLE_APPRECIATION | Related model appreciated significantly. Use `asset_model_relationships` correlation strength |
| PATTERN_MATCH | Historical pattern recognition: "Spider variant typically appreciates 12–18 months after coupe peaks" |

#### Opportunity Scoring
- Composite score = weighted sum of all active signals for a model
- Weights: momentum 0.25, dealer_auction_spread 0.20, catalyst 0.20, volume_spike 0.10, comparable_appreciation 0.15, pattern_match 0.10
- Include liquidity score (based on transaction frequency), cost-adjusted return %, time to next catalyst
- Apply rule flags from `market_rules` (e.g., 25-year import rule for US)
- Write to `opportunity_scores` table
- Status thresholds: `actionable` if composite > 4.0, `watchlist` if > 2.0

**Files to create:**
- `aatp/signals/momentum.py`
- `aatp/signals/spread.py`
- `aatp/signals/catalyst.py`
- `aatp/signals/volume.py`
- `aatp/signals/comparable.py`
- `aatp/signals/pattern.py`
- `aatp/signals/scanner.py` — Orchestrator that runs all signal generators and computes opportunity scores
- `aatp/signals/tasks.py`
- `tests/unit/test_signals_*.py`

---

### MODULE 5: Multi-Model Consensus Engine — TODO

**Status: NOT STARTED**

**What it does:** Six independent models each score an opportunity from -2 to +2. Aggregate score determines action. Veto logic: a -2 from any single model kills the opportunity regardless of aggregate.

#### The Six Models

| Model | What it evaluates | Score logic |
|---|---|---|
| MOMENTUM | Price trend and acceleration | +2 if strong uptrend > 20% annualised, +1 if moderate, 0 if flat, -1 if declining, -2 if crash |
| FUNDAMENTAL_VALUE | Fair value vs. current market price | +2 if >15% undervalued, +1 if 5-15%, 0 if fair, -1 if overvalued, -2 if >15% overvalued |
| LIQUIDITY | Ability to exit within target timeframe | +2 if multiple exit channels, frequent auctions. -2 if no comparables sold in 12 months |
| SENTIMENT | News, forum buzz, dealer sentiment | +2 if overwhelmingly positive + rising interest. -2 if negative press or recall |
| MACRO | Interest rates, collector car index, wealth indicators | +2 if tailwinds. -2 if recession signals |
| RULES | Regulatory/import/tax considerations | +2 if favorable (25-year rule now eligible). -2 if regulatory blocker (import ban, new tax) |

#### Consensus Logic
- Aggregate = sum of 6 model scores (range: -12 to +12)
- Veto check: if any model scores -2, opportunity is KILLED regardless of aggregate
- Actionable threshold: aggregate >= +4 AND no veto
- Watchlist: aggregate >= +2 AND no veto
- Disagreement flag: if spread (max - min) > 3, flag for manual review
- Store individual model scores with rationale and supporting data
- Write to `consensus_scores` and `consensus_model_scores` tables

**Files to create:**
- `aatp/consensus/models/momentum.py`
- `aatp/consensus/models/fundamental.py`
- `aatp/consensus/models/liquidity.py`
- `aatp/consensus/models/sentiment.py`
- `aatp/consensus/models/macro.py`
- `aatp/consensus/models/rules.py`
- `aatp/consensus/engine.py` — Orchestrator: runs all 6 models, aggregates, applies veto
- `aatp/consensus/tasks.py`
- `tests/unit/test_consensus_*.py`

---

### MODULE 6: Risk Engine — TODO

**Status: NOT STARTED**

**What it does:** Assesses risk at position level and portfolio level. Every open position gets a composite risk score. Portfolio snapshots track concentration risk.

#### Position-Level Risk (6 dimensions)

| Risk | What it measures |
|---|---|
| Liquidity risk | Can we sell this within target timeframe? Based on auction frequency, dealer network, model popularity |
| Concentration risk | How much of our portfolio is in this manufacturer/era/type? |
| Physical risk | Storage adequacy, insurance coverage, geographic risk (flooding, theft) |
| Counterparty risk | Dealer/auction house reliability, payment risk |
| Spec risk | Is this spec desirable? Colour tier, options, mileage relative to market |
| Provenance risk | Documentation completeness, ownership history gaps, accident history |

**Composite risk = weighted average of 6 dimensions. Weights configurable.**

#### Portfolio-Level Risk
- Manufacturer concentration: max 40% single manufacturer
- Era concentration: max 60% single decade
- Type concentration: max 70% single type (e.g., all Ferraris)
- Total illiquid exposure: flag if > 30% of positions haven't seen a comparable sale in 90 days
- Scenario analysis:
  - "What if Ferrari market drops 20%?"
  - "What if interest rates rise 200bps?"
  - "What if no Monterey week this year?"
- Write to `risk_assessments` (position) and `portfolio_risk_snapshots` (portfolio)
- Generate alerts for risk threshold breaches

**Files to create:**
- `aatp/risk/position_risk.py`
- `aatp/risk/portfolio_risk.py`
- `aatp/risk/scenarios.py`
- `aatp/risk/engine.py`
- `aatp/risk/tasks.py`
- `tests/unit/test_risk_*.py`

---

### MODULE 7: Execution Engine — TODO

**Status: NOT STARTED**

**What it does:** Decision support for acquisition and exit. Does NOT execute trades automatically — surfaces recommendations with full cost analysis.

#### Acquisition Support
- Given an opportunity, compute optimal acquisition channel:
  - BaT auction (low fees, moderate ceiling)
  - RM Sotheby's / Gooding (high ceiling, high fees)
  - Dealer purchase (negotiable, no public price discovery)
  - Private sale (lowest cost, highest effort)
- Spec guide lookup from `spec_guides`: recommended colours, options, mileage ceiling, certification requirements
- Full cost-of-entry calculation per channel using `cost_models`

#### Exit Strategy
- Optimal exit channel based on: asset value, market timing, upcoming auction events
- Exit cost calculation per channel
- Consignment deadline tracking from `auction_events`
- Preparation checklist: detailing, photography, documentation assembly, Classiche certification
- Net proceeds estimate after all exit costs

#### Dealer & Auction House Management
- Dealer registry with reliability scores, specialisation, allocation access status
- Auction house registry with fee structures, event calendars, geographic reach
- Upcoming auction events calendar with consignment deadlines

**Files to create:**
- `aatp/execution/acquisition.py`
- `aatp/execution/exit_strategy.py`
- `aatp/execution/cost_calculator.py`
- `aatp/execution/spec_guide.py`
- `tests/unit/test_execution_*.py`

---

### MODULE 8: Trading Ledger — TODO

**Status: NOT STARTED**

**What it does:** Immutable financial record of every position, cost, and P&L calculation. The single source of truth for portfolio state.

#### Position Lifecycle
1. **Acquisition:** Create `position` record with all acquisition details. Record `cost_entries` for buyer premium, transport, insurance deposit, etc. Write `ledger_entry` for acquisition.
2. **Holding:** Monthly recurring costs (storage, insurance) auto-generated. Fair value updates from M3 flow into `current_fair_value_usd`. Unrealised P&L recalculated.
3. **Exit:** Record exit price, channel, costs. Write final `ledger_entry`. Calculate realised P&L and IRR. Set status to `exited`.

#### Ledger Rules
- **Immutable:** `ledger_entries` never updated. Corrections create a new entry with `corrects_entry_id` pointing to the original and `is_correction = True`
- **Double-entry inspired:** Every financial event has a matching ledger entry
- **IRR calculation:** Uses actual cash flows (acquisition, holding costs, exit proceeds) with scipy's `irr` function
- **Portfolio snapshots:** Daily aggregation of all open positions into `portfolio_snapshots`

#### P&L Calculation
```
Total Cost Basis = Acquisition Price + Buyer Premium + Transport + Insurance + Storage + Maintenance + ...
Unrealised P&L = Current Fair Value - Total Cost Basis
Realised P&L = Exit Proceeds (net of seller commission) - Total Cost Basis
IRR = internal rate of return over actual holding period
```

**Files to create:**
- `aatp/ledger/position_service.py`
- `aatp/ledger/cost_service.py`
- `aatp/ledger/ledger_service.py`
- `aatp/ledger/pnl.py`
- `aatp/ledger/snapshot.py`
- `tests/unit/test_ledger_*.py`

---

### MODULE 9: Reconciliation & Monitoring — TODO

**Status: NOT STARTED**

**What it does:** Ensures data integrity across all modules. Detects divergences, generates alerts, and produces the daily health report.

#### Reconciliation Checks
- **Price reconciliation:** Compare stored normalised prices against re-running the normalisation pipeline. Flag divergences > 1%
- **Fair value reconciliation:** Compare stored fair values against re-running the valuation engine. Flag divergences > 5%
- **Ledger reconciliation:** Sum of cost entries must equal position's `total_cost_basis`. Sum of ledger entries must balance
- **Position P&L reconciliation:** Recalculate unrealised P&L from current fair values and cost basis. Flag divergences
- **Scraper health:** Check scraper_runs for failures, missed schedules, declining item counts

#### Alert System
- Alert types: price movement, catalyst, auction result, consensus change, holding cost warning, hold period warning, liquidity warning, reconciliation divergence
- Severity: INFO, WARNING, CRITICAL
- Delivery: in-app (stored in `alerts` table), email (SMTP)
- Thresholds from config: price movement > 10%, hold period > 18 months, etc.

#### Monitoring
- Scraper success rates and item counts
- Normalisation coverage (% of transactions normalised)
- Fair value coverage (% of models with current valuation)
- Signal freshness (age of latest signals)
- System health dashboard data

**Files to create:**
- `aatp/reconciliation/price_recon.py`
- `aatp/reconciliation/ledger_recon.py`
- `aatp/reconciliation/health_check.py`
- `aatp/reconciliation/alert_service.py`
- `aatp/reconciliation/tasks.py`
- `tests/unit/test_reconciliation_*.py`

---

### MODULE 10: Backtesting Environment — TODO

**Status: NOT STARTED**

**What it does:** Replays historical data through the signal → consensus → risk pipeline to validate model accuracy before live deployment.

#### Backtest Flow
1. Define parameters: date range, models to test, signal weights, consensus thresholds
2. For each date in range:
   a. Compute fair values using only data available up to that date (no look-ahead bias)
   b. Generate signals using only historical data
   c. Run consensus engine
   d. Record predicted direction and return
3. After simulation, attach actual outcomes:
   - What actually happened to the price 6m, 12m, 24m later?
   - Was the signal correct? Was the consensus correct?
4. Compute aggregate metrics:
   - Signal accuracy rate, false positive rate
   - Average return, median return
   - Sharpe ratio, max drawdown
   - Per-model validation (which of the 6 consensus models was most/least accurate?)
   - Optimal weights for each model

#### Walk-Forward Validation
- Split historical data into train/test windows
- Calibrate model weights on train set
- Validate on test set
- Report stability of weights across windows

**Files to create:**
- `aatp/research/backtest_runner.py`
- `aatp/research/walk_forward.py`
- `aatp/research/metrics.py`
- `tests/unit/test_backtest_*.py`

---

## API Layer (Cross-Cutting)

**Status: NOT STARTED** (built incrementally as modules complete)

FastAPI endpoints exposing each module's functionality. Built after the core engine modules are complete.

**Planned endpoints:**

| Group | Endpoints |
|---|---|
| Catalog | `GET /models`, `GET /models/{id}`, `GET /manufacturers` |
| Market Data | `GET /transactions`, `GET /transactions/{model_id}` |
| Valuation | `GET /fair-values/{model_id}`, `POST /fair-values/refresh` |
| Signals | `GET /signals/{model_id}`, `GET /opportunities` |
| Consensus | `GET /consensus/{model_id}`, `POST /consensus/run` |
| Risk | `GET /risk/positions/{id}`, `GET /risk/portfolio` |
| Ledger | `GET /positions`, `POST /positions`, `PATCH /positions/{id}`, `GET /pnl` |
| Alerts | `GET /alerts`, `PATCH /alerts/{id}/read` |
| Backtest | `POST /backtest`, `GET /backtest/{id}` |

**Files to create:**
- `aatp/api/routes/catalog.py`
- `aatp/api/routes/market_data.py`
- `aatp/api/routes/valuation.py`
- `aatp/api/routes/signals.py`
- `aatp/api/routes/consensus.py`
- `aatp/api/routes/risk.py`
- `aatp/api/routes/ledger.py`
- `aatp/api/routes/alerts.py`
- `aatp/api/routes/backtest.py`
- `aatp/api/schemas/` — Pydantic request/response schemas
- `aatp/api/app.py` — FastAPI app factory

---

## Project Structure

```
hypercar-investment/
├── aatp/
│   ├── __init__.py
│   ├── api/                    # FastAPI endpoints
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes/
│   │   └── schemas/
│   ├── collectors/             # MODULE 2: Data collection
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract scraper with rate limiting
│   │   ├── bat.py              # Bring a Trailer scraper
│   │   ├── rmsothebys.py       # RM Sotheby's scraper
│   │   ├── model_matcher.py    # Fuzzy asset model matching
│   │   ├── normalisation.py    # 6-dimension price normalisation
│   │   └── tasks.py            # Celery tasks
│   ├── consensus/              # MODULE 5: Multi-model consensus
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── models/
│   │   │   ├── momentum.py
│   │   │   ├── fundamental.py
│   │   │   ├── liquidity.py
│   │   │   ├── sentiment.py
│   │   │   ├── macro.py
│   │   │   └── rules.py
│   │   └── tasks.py
│   ├── core/                   # Shared infrastructure
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   ├── config.py
│   │   └── logging.py
│   ├── db/                     # MODULE 1: Database
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── models.py           # 30 tables, 16 enums
│   │   └── session.py
│   ├── execution/              # MODULE 7: Execution engine
│   │   ├── __init__.py
│   │   ├── acquisition.py
│   │   ├── exit_strategy.py
│   │   ├── cost_calculator.py
│   │   └── spec_guide.py
│   ├── ledger/                 # MODULE 8: Trading ledger
│   │   ├── __init__.py
│   │   ├── position_service.py
│   │   ├── cost_service.py
│   │   ├── ledger_service.py
│   │   ├── pnl.py
│   │   └── snapshot.py
│   ├── reconciliation/         # MODULE 9: Reconciliation
│   │   ├── __init__.py
│   │   ├── price_recon.py
│   │   ├── ledger_recon.py
│   │   ├── health_check.py
│   │   ├── alert_service.py
│   │   └── tasks.py
│   ├── research/               # MODULE 10: Backtesting
│   │   ├── __init__.py
│   │   ├── backtest_runner.py
│   │   ├── walk_forward.py
│   │   └── metrics.py
│   ├── risk/                   # MODULE 6: Risk engine
│   │   ├── __init__.py
│   │   ├── position_risk.py
│   │   ├── portfolio_risk.py
│   │   ├── scenarios.py
│   │   └── engine.py
│   ├── rules/                  # Market rules (feeds into consensus)
│   │   └── __init__.py
│   ├── signals/                # MODULE 4: Signal engine
│   │   ├── __init__.py
│   │   ├── momentum.py
│   │   ├── spread.py
│   │   ├── catalyst.py
│   │   ├── volume.py
│   │   ├── comparable.py
│   │   ├── pattern.py
│   │   ├── scanner.py
│   │   └── tasks.py
│   └── valuation/              # MODULE 3: Fair value engine
│       ├── __init__.py
│       ├── comparable.py
│       ├── appreciation.py
│       ├── cost_return.py
│       ├── engine.py
│       └── tasks.py
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── config/
├── notebooks/
├── scripts/
│   └── seed_data.py
├── tests/
│   ├── unit/
│   │   ├── test_bat_parser.py
│   │   ├── test_rm_parser.py
│   │   ├── test_normalisation.py
│   │   └── test_model_matcher.py
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
│       ├── bat_listing.html
│       ├── bat_search.html
│       └── rm_lot.html
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
├── PLAN.md                     # This file
└── README.md
```

---

## Configuration Reference

All configuration via environment variables (`.env` file). Key settings:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://aatp:aatp@localhost:5432/aatp` | Async DB connection |
| `DATABASE_URL_SYNC` | `postgresql://aatp:aatp@localhost:5432/aatp` | Sync DB (Alembic) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery message broker |
| `AATP_ENV` | `development` | Environment (development/staging/production) |
| `SCRAPER_REQUEST_DELAY_SECONDS` | `2.0` | Rate limiting between requests |
| `SCRAPER_MAX_CONCURRENT_REQUESTS` | `3` | Semaphore limit |
| `PRICE_MOVEMENT_ALERT_THRESHOLD_PCT` | `10.0` | Alert on >10% price move |
| `CONSENSUS_ACTIONABLE_THRESHOLD` | `4` | Aggregate score to flag actionable |
| `CONSENSUS_WATCHLIST_THRESHOLD` | `2` | Aggregate score for watchlist |
| `MIN_NET_RETURN_THRESHOLD_PCT` | `25.0` | Minimum acceptable net return |
| `MAX_HOLD_PERIOD_MONTHS` | `24` | Maximum hold period |

---

## Getting Started

```bash
# Clone
git clone git@github.com:BlackMamba646/hypercar-investment.git
cd hypercar-investment

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env

# Start infrastructure
docker compose up -d  # PostgreSQL + Redis

# Run migrations
alembic upgrade head

# Seed reference data
python scripts/seed_data.py

# Run tests
pytest tests/unit/ -v

# Start Celery worker
celery -A aatp.core.celery_app worker -l info

# Start Celery beat (scheduler)
celery -A aatp.core.celery_app beat -l info

# Start API server
uvicorn aatp.api.app:app --reload
```

---

## Progress Tracker

| # | Module | Status | Tests |
|---|---|---|---|
| 1 | Database Schema & Catalog | DONE | N/A (migration tested by Alembic) |
| 2 | Data Collection & Scrapers | DONE | 63/63 passing |
| 3 | Fair Value Engine | TODO | — |
| 4 | Signal Engine | TODO | — |
| 5 | Consensus Engine | TODO | — |
| 6 | Risk Engine | TODO | — |
| 7 | Execution Engine | TODO | — |
| 8 | Trading Ledger | TODO | — |
| 9 | Reconciliation & Monitoring | TODO | — |
| 10 | Backtesting | TODO | — |
| — | API Layer | TODO | — |
