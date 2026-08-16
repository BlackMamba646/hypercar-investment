# AATP Setup Guide

Get the Alternative Asset Trading Platform dashboard running with real data.

## Prerequisites

- **Python 3.11+** — backend API
- **Node.js 18+** — frontend dev server
- **Docker & Docker Compose** — PostgreSQL 16 and Redis 7
- **Git** — clone the repo

## 1. Clone the Repository

```bash
git clone https://github.com/BlackMamba646/hypercar-investment.git
cd hypercar-investment
```

## 2. Start the Database and Cache

Docker Compose spins up PostgreSQL 16 and Redis 7:

```bash
docker-compose up -d
```

Verify both are healthy:

```bash
docker-compose ps
```

You should see `postgres` and `redis` with status `healthy`.

**Connection defaults** (from `.env.example`):

| Service    | Host      | Port | User | Password | Database |
|------------|-----------|------|------|----------|----------|
| PostgreSQL | localhost | 5432 | aatp | aatp     | aatp     |
| Redis      | localhost | 6379 | —    | —        | 0        |

## 3. Configure Environment Variables

```bash
cp .env.example .env
```

The defaults work for local development. Edit `.env` if you need custom database credentials, alert thresholds, or SMTP settings for email alerts.

## 4. Install Python Dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

## 5. Run Database Migrations

Apply the schema (30 tables, 16 enums):

```bash
alembic upgrade head
```

## 6. Start the Backend API

```bash
uvicorn aatp.api.app:app --reload --port 8000
```

Verify it's running:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

## 7. Start the Celery Worker (Optional)

The Celery worker handles background tasks like scheduled data collection and valuation refreshes:

```bash
celery -A aatp.workers.celery_app worker --loglevel=info
```

This is optional for browsing the dashboard but required for automated scraping and scheduled jobs.

## 8. Install and Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard opens at [http://localhost:3000](http://localhost:3000).

The Vite dev server proxies `/api` requests to the backend at `localhost:8000`, so both servers need to be running.

## 9. Populate Data

The dashboard will show empty states until data exists. To populate:

**API Docs** — Use the interactive Swagger UI at `http://localhost:8000/docs` to create manufacturers, asset models, and transactions manually.

**Collectors** — Start the Celery worker (step 7) and trigger collection tasks to scrape market data from configured sources.

**Seed Script** — If a seed script exists in the repo, run it to load sample data:

```bash
python -m aatp.scripts.seed  # check if available
```

## Quick Start (All Commands)

```bash
# Terminal 1 — infrastructure
docker-compose up -d

# Terminal 2 — backend
cp .env.example .env
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e ".[dev]"
alembic upgrade head
uvicorn aatp.api.app:app --reload --port 8000

# Terminal 3 — frontend
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Dashboard Pages

| Page | Route | What It Shows |
|------|-------|---------------|
| Dashboard | `/` | Portfolio snapshot, top opportunities, recent alerts, open positions |
| Catalog | `/catalog` | Manufacturers, asset models with all specs and flags |
| Model Detail | `/catalog/:id` | Full model info, fair value, signals, consensus, transactions |
| Market Data | `/market` | All transactions with 24 columns, filters, pagination |
| Valuations | `/valuations` | Per-model fair values (low/mid/high), appreciation rates |
| Signals | `/signals` | Opportunity scanner with composite scores |
| Consensus | `/consensus` | Per-model consensus with 6 model score breakdowns |
| Risk | `/risk` | Portfolio risk snapshot, concentration analysis, radar charts |
| Portfolio | `/portfolio` | Positions table, P&L snapshot, status filters |
| Position Detail | `/portfolio/:id` | Full position with acquisition, exit, valuation, risk radar |
| Alerts | `/alerts` | Alerts with type/severity/read filters, mark-as-read |
| Backtest | `/backtest` | Create and monitor backtests with full metrics |

## Troubleshooting

**"Backend not connected" on all pages**
The backend API is not running. Start it with `uvicorn aatp.api.app:app --reload --port 8000`.

**Database connection refused**
Run `docker-compose up -d` and wait for the health checks to pass.

**Alembic migration fails**
Make sure PostgreSQL is running and the `DATABASE_URL_SYNC` in `.env` is correct.

**Frontend shows empty data**
The API is running but the database has no data yet. Use the Swagger UI at `/docs` to create records or run the collectors.

**Port conflicts**
- PostgreSQL default: 5432
- Redis default: 6379
- Backend API: 8000
- Frontend dev server: 3000

Edit `docker-compose.yml` or pass `--port` flags to change them.
