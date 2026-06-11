from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import re


_GROUP_VERSIONED_API_RE = re.compile(r"^/[a-z][a-z0-9-]*/v\d+(?:/|$)")


def _is_api_path(path: str) -> bool:
    normalized = str(path or "")
    if normalized == "/api" or normalized.startswith("/api/"):
        return True
    return _GROUP_VERSIONED_API_RE.match(normalized) is not None


class RequireKongGatewayMiddleware(BaseHTTPMiddleware):
    """Reject requests that bypass Kong.

    Policy: all API requests MUST go through Kong.
    We treat the presence of Kong forwarding headers as the signal.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not _is_api_path(request.url.path):
            return await call_next(request)

        # Kong adds X-Kong-Request-Id by default.
        # X-Forwarded-Host is also present for proxied requests.
        if request.headers.get("x-kong-request-id") or request.headers.get("x-forwarded-host"):
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={"detail": "Requests bypassing Kong are not allowed."},
        )
