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

| Module | Status |
|---|---|
| Database Schema | Done |
| Data Collection (BaT, RM Sotheby's) | Done |
| Fair Value Engine | In Progress |
| Signal / Consensus / Risk / Execution / Ledger / Reconciliation / Backtesting | Planned |
