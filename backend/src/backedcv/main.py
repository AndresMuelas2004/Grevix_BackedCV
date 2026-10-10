"""FastAPI app factory: API routes under /api, the built frontend at /."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backedcv import __version__
from backedcv.api.routes import health
from backedcv.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="BackedCV", version=__version__)
    app.include_router(health.router, prefix="/api")

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
