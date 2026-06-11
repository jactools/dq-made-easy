from uuid import uuid4
import logging

from fastapi import Request
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.request_context import set_correlation_id
from app.core.telemetry import current_trace_id


logger = logging.getLogger("app.middleware.correlation_id")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.header_name, str(uuid4()))
        set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("correlation_id", correlation_id)

        trace_id = request.scope.get("otel.trace_id") or current_trace_id()
        if trace_id:
            request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers[self.header_name] = correlation_id
        trace_id = request.scope.get("otel.trace_id") or getattr(request.state, "trace_id", None) or current_trace_id()
        if trace_id:
            response.headers["X-Trace-ID"] = trace_id
        return response
