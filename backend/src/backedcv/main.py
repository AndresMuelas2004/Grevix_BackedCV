"""FastAPI app factory: API routes under /api, the built frontend at /."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backedcv import __version__
from backedcv.agents.cv_builder.agent import default_order_model
from backedcv.api.errors import install_error_handlers
from backedcv.api.locks import RunLocks
from backedcv.api.rate_limit import RunLimiter
from backedcv.api.retention import AnalysisLedger, purge_hourly, utc_now
from backedcv.api.routes import analyses, downloads, health, inputs, meta, optimize, samples
from backedcv.graph.builder import build_graph
from backedcv.llm.structured import OpenAIStructuredLLM, StructuredLLM
from backedcv.settings import get_settings


def create_app(llm: StructuredLLM | None = None, checkpointer=None) -> FastAPI:
    """`llm` and `checkpointer` are injectable so tests run without network or disk."""
    settings = get_settings()
    if settings.env == "prod":
        # Traces must not carry the CV or the posting. Set before any model call; values the
        # operator has already set are kept.
        os.environ.setdefault("LANGSMITH_HIDE_INPUTS", "true")
        os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS", "true")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        model = llm or OpenAIStructuredLLM(settings)
        # The ordering agent needs a real chat model; injected test models keep the fallback.
        order_model = (
            default_order_model(settings) if llm is None and settings.openai_api_key else None
        )
        app.state.llm = model
        app.state.locks = RunLocks()
        async with AsyncExitStack() as stack:
            if checkpointer is None:
                settings.data_dir.mkdir(parents=True, exist_ok=True)
                saver = await stack.enter_async_context(
                    AsyncSqliteSaver.from_conn_string(str(settings.data_dir / "checkpoints.sqlite"))
                )
                ledger_path = settings.data_dir / "analyses.sqlite"
            else:
                saver, ledger_path = checkpointer, ":memory:"
            app.state.checkpointer = saver
            app.state.graph = build_graph(model, checkpointer=saver, order_model=order_model)
            app.state.ledger = AnalysisLedger(ledger_path)
            stack.callback(app.state.ledger.close)
            app.state.purge_task = asyncio.create_task(
                purge_hourly(app.state.ledger, saver, app.state.locks, clock=utc_now)
            )
            stack.push_async_callback(_stop, app.state.purge_task)
            yield

    app = FastAPI(title="BackedCV", version=__version__, lifespan=lifespan)
    app.state.limiter = RunLimiter(
        per_hour=settings.rate_limit_per_hour, per_day=settings.daily_model_runs
    )
    install_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(analyses.router, prefix="/api")
    app.include_router(inputs.router, prefix="/api")
    app.include_router(optimize.router, prefix="/api")
    app.include_router(downloads.router, prefix="/api")
    app.include_router(samples.router, prefix="/api")
    app.include_router(meta.router, prefix="/api")

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


async def _stop(task: asyncio.Task) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = create_app()
