"""Errors as {"code", "title", "detail"} with stable codes the frontend can switch on."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backedcv.ingestion import IngestionError


class ApiError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str = ""):
        super().__init__(f"{code}: {title}")
        self.status, self.code, self.title, self.detail = status, code, title, detail


def _body(code: str, title: str, detail: str) -> dict:
    return {"code": code, "title": title, "detail": detail}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.title, exc.detail), status_code=exc.status)

    @app.exception_handler(IngestionError)
    async def ingestion_error(_: Request, exc: IngestionError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.title, exc.detail), status_code=exc.status)
