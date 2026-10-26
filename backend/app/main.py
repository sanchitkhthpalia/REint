"""FastAPI application.

Run locally / in Docker:  uvicorn app.main:app --host 0.0.0.0 --port 8000  (from backend/)
On Vercel:                 api/index.py re-exports `app` as a Python serverless function.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import Settings
from app.http_cache import cache_headers
from app.observability import access_log, configure_logging
from app.service import AnalysisService
from app.snapshot import load_snapshot

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    snapshot = load_snapshot(settings.data_dir)

    app = FastAPI(
        title="Wind Forecast Monitor API",
        description="Day-ahead wind forecasts available at decision time, and their error "
        "against actual generation (Elexon BMRS WINDFOR / FUELHH).",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.service = AnalysisService(snapshot, settings.cache_size)

    app.middleware("http")(cache_headers)
    app.middleware("http")(access_log)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    app.include_router(router)

    logger.info(
        "app started",
        extra={
            "fields": {
                "snapshot_id": snapshot.snapshot_id,
                "data_dir": str(settings.data_dir),
                "cors_origins": settings.cors_origins,
                "cache_size": settings.cache_size,
            }
        },
    )
    return app


app = create_app()
