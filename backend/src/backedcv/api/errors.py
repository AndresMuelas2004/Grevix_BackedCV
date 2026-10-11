"""Errors as {"code", "title", "detail"} with stable codes the frontend can switch on."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.sse import ServerSentEvent

from backedcv.ingestion import IngestionError

NO_DETAIL = "No further detail is available."


class ApiError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str = ""):
        super().__init__(f"{code}: {title}")
        self.status, self.code, self.title, self.detail = status, code, title, detail


def _body(code: str, title: str, detail: str) -> dict:
    return {"code": code, "title": title, "detail": detail}


def error_detail(exc: Exception) -> str:
    """The exception message, cut to 200 characters."""
    return str(exc).strip()[:200] or NO_DETAIL


def stream_error(code: str, title: str, exc: Exception) -> ServerSentEvent:
    """The `error` event that ends a stream which failed after it had started."""
    return ServerSentEvent(event="error", data=_body(code, title, error_detail(exc)))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.title, exc.detail), status_code=exc.status)

    @app.exception_handler(IngestionError)
    async def ingestion_error(_: Request, exc: IngestionError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.title, exc.detail), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        body = _body("invalid_request", "The request is not valid.", f"{where}: {first['msg']}")
        return JSONResponse(body, status_code=422)
