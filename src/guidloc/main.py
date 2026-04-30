"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from guidloc.common.config import Settings, get_settings
from guidloc.common.logging import setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings: Settings = get_settings()
    setup_logging(settings.app_log_level)

    app = FastAPI(
        title="GuidLoc API",
        version="0.1.0",
        debug=settings.app_debug,
    )

    @app.get("/health", tags=["health"], summary="Service health check")
    async def health() -> dict[str, str]:
        """Return basic service health information."""
        return {"status": "ok", "env": settings.app_env}

    logger.info("Application initialized (env=%s)", settings.app_env)
    return app


app = create_app()
