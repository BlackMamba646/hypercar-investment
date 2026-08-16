from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from aatp.api.routes import alerts, backtest, catalog, consensus, ledger, market_data, pipeline, risk, signals, valuation
from aatp.core.logging import get_logger, setup_logging

logger = get_logger("api.app")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("aatp_api_starting", version=app.version)
    yield
    logger.info("aatp_api_shutting_down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AATP API",
        description="Alternative Asset Trading Platform API — hypercar investment analytics, valuation, signals, consensus, risk, and portfolio management.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Include all routers
    app.include_router(catalog.router)
    app.include_router(market_data.router)
    app.include_router(valuation.router)
    app.include_router(signals.router)
    app.include_router(consensus.router)
    app.include_router(risk.router)
    app.include_router(ledger.router)
    app.include_router(alerts.router)
    app.include_router(backtest.router)
    app.include_router(pipeline.router)

    @app.get("/health", tags=["system"])
    async def health_check() -> dict:
        return {"status": "ok"}

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file = STATIC_DIR / full_path
            if file.is_file():
                return FileResponse(file)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
