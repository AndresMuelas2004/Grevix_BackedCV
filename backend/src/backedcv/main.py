"""FastAPI app factory: API routes under /api, the built frontend at /."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backedcv import __version__
from backedcv.api.errors import install_error_handlers
from backedcv.api.locks import RunLocks
from backedcv.api.routes import analyses, health
from backedcv.graph.builder import build_graph
from backedcv.llm.structured import OpenAIStructuredLLM, StructuredLLM
from backedcv.settings import get_settings


def create_app(llm: StructuredLLM | None = None, checkpointer=None) -> FastAPI:
    """`llm` and `checkpointer` are injectable so tests run without network or disk."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        model = llm or OpenAIStructuredLLM(settings)
        app.state.locks = RunLocks()
        if checkpointer is not None:
            app.state.graph = build_graph(model, checkpointer=checkpointer)
            yield
            return
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(
            str(settings.data_dir / "checkpoints.sqlite")
        ) as saver:
            app.state.graph = build_graph(model, checkpointer=saver)
            yield

    app = FastAPI(title="BackedCV", version=__version__, lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(analyses.router, prefix="/api")

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
