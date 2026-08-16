# hypercar-investment

Alternative Asset Trading Platform (AATP) — quantitative trading infrastructure for physical alternative assets, starting with luxury hypercars.

See [PLAN.md](PLAN.md) for the full project plan, architecture, and module specifications.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest tests/unit/ -v
```

## Status

| Module | Status | Tests |
|---|---|---|
| Database Schema & Catalog | Done | N/A |
| Data Collection (BaT, RM Sotheby's) | Done | 63 |
| Fair Value Engine | Done | 47 |
| Signal Engine | Done | 53 |
| Consensus Engine | Done | 64 |
| Risk Engine | Done | 71 |
| Execution Engine | Done | 51 |
| Trading Ledger | Done | 33 |
| Reconciliation & Monitoring | Done | 68 |
| Backtesting | Done | 82 |
| API Layer (21 endpoints) | Done | — |
| **Total** | **Complete** | **532** |
