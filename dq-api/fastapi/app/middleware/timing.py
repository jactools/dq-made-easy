import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.api_metrics import _SKIP_PATHS, api_metrics_store
from app.core.otel_metrics import record_request_metric


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started_at = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        response.headers["X-Process-Time-MS"] = f"{elapsed_ms:.2f}"

        path = request.url.path
        if path not in _SKIP_PATHS:
            error_detail: str | None = None
            if response.status_code >= 400:
                error_detail = response.headers.get("X-Error-Detail")
            api_metrics_store.record(
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=elapsed_ms,
                error_detail=error_detail,
            )

            route = request.scope.get("route")
            operation = getattr(route, "path", None) or path
            record_request_metric(
                method=request.method,
                path=path,
                operation=str(operation),
                status_code=response.status_code,
                duration_ms=elapsed_ms,
            )

        return response
