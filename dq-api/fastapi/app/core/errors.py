import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.request_context import get_correlation_id


logger = logging.getLogger(__name__)


def _problem_details(
    request: Request,
    *,
    status: int,
    title: str,
    detail: Any = None,
    type_uri: str = "about:blank",
) -> dict:
    return {
        "type": type_uri,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
        "correlation_id": get_correlation_id(),
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        payload = _problem_details(
            request,
            status=exc.status_code,
            title="HTTP Error",
            detail=exc.detail if isinstance(exc.detail, (dict, list)) else str(exc.detail),
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        payload = _problem_details(
            request,
            status=422,
            title="Validation Error",
            detail=str(exc),
            type_uri="https://datatracker.ietf.org/doc/html/rfc7807",
        )
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        settings = get_settings()
        logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
        payload = _problem_details(
            request,
            status=500,
            title="Internal Server Error",
            detail=(str(exc) if settings.environment != "production" else "An unexpected error occurred"),
        )
        return JSONResponse(status_code=500, content=payload)
