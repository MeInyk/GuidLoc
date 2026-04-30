"""FastAPI application entry point."""

import logging

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.router import router as auth_router
from guidloc.chats.router import router as chats_router
from guidloc.common.config import Settings, get_settings
from guidloc.common.database import get_session
from guidloc.common.logging import setup_logging
from guidloc.locations.router import router as locations_router
from guidloc.users.router import router as users_router

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
    async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
        """Return basic service health information, including DB connectivity."""
        db_status = "ok"
        try:
            await session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Database health check failed")
            db_status = "error"

        return {"status": "ok", "env": settings.app_env, "database": db_status}

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(chats_router)
    app.include_router(locations_router)
    logger.info("Application initialized (env=%s)", settings.app_env)
    return app


app = create_app()
