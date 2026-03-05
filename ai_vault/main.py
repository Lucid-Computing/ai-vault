"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from ai_vault.db import get_engine, get_session_factory, init_db, reset_engine
from ai_vault.settings import get_settings


def create_app(*, db_session: Optional[AsyncSession] = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        db_session: Optional pre-configured session (for testing).
    """
    settings = get_settings()

    app = FastAPI(
        title="AI Vault",
        description="Local-first AI resource access manager",
        version="0.1.0",
    )

    @app.on_event("startup")
    async def startup():
        if db_session is None:
            reset_engine()
            engine = get_engine(settings.database_url)
            get_session_factory(engine)
            await init_db(engine)

    # Mount API routes
    from ai_vault.api.router import api_router
    app.include_router(api_router, prefix="/api")

    # Mount MCP server
    from ai_vault.mcp_server.server import get_mcp_app
    try:
        mcp_app = get_mcp_app()
        app.mount("/mcp", mcp_app)
    except Exception:
        pass  # MCP mount may fail in test environments

    # Serve static UI if built
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and any(static_dir.iterdir()):
        # Mount static assets (_app/ etc)
        app.mount("/_app", StaticFiles(directory=str(static_dir / "_app")), name="static_app")

        # SPA fallback: serve index.html for all non-API/non-asset routes
        index_html = static_dir / "index.html"

        @app.get("/{path:path}")
        async def spa_fallback(request: Request, path: str):
            # Try to serve the exact static file first
            file_path = static_dir / path
            if file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for SPA routing
            return FileResponse(str(index_html))

    return app
