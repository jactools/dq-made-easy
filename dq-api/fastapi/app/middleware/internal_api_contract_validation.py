from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.routing import Match

from app.core.errors import _problem_details
from dq_utils.internal_api_contracts import InternalApiContractLookupError
from dq_utils.internal_api_contracts import InternalApiContractRegistry
from dq_utils.internal_api_contracts import InternalApiContractValidationError


def _is_json_content_type(value: str | None) -> bool:
    normalized = str(value or "").lower()
    return "application/json" in normalized or normalized.endswith("+json")


def _restore_request_body(request: Request, body: bytes) -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive


def _resolve_route_path(request: Request) -> str | None:
    route = request.scope.get("route")
    path_format = getattr(route, "path_format", None)
    if isinstance(path_format, str) and path_format:
        return path_format

    for candidate in request.app.router.routes:
        methods = getattr(candidate, "methods", None)
        if methods and request.method.upper() not in methods:
            continue
        match, _ = candidate.matches(request.scope)
        if match is Match.FULL:
            candidate_path = getattr(candidate, "path_format", None)
            if isinstance(candidate_path, str) and candidate_path:
                return candidate_path
    return None


def _problem_response(request: Request, *, status_code: int, detail: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_problem_details(request, status=status_code, title="HTTP Error", detail=detail),
    )


class InternalApiContractValidationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, contracts_root: str | Path) -> None:
        super().__init__(app)
        self._registry = InternalApiContractRegistry(contracts_root)

    async def dispatch(self, request: Request, call_next) -> Response:
        request_path = str(request.url.path or "")
        if not request_path.startswith("/api/"):
            return await call_next(request)

        route_path = _resolve_route_path(request)
        if route_path is None:
            return await call_next(request)

        operation = self._registry.get_operation(request.method, route_path)
        if operation is None:
            return _problem_response(
                request,
                status_code=500,
                detail={
                    "error": "internal_api_contract_missing",
                    "message": "No internal API contract was found for the resolved route.",
                    "method": request.method.upper(),
                    "path": route_path,
                },
            )

        body = await request.body()
        _restore_request_body(request, body)

        if not body:
            if operation.request_body_required:
                return _problem_response(
                    request,
                    status_code=422,
                    detail={
                        "error": "contract_schema_validation_failed",
                        "message": "Request body is required by the internal API contract.",
                        "method": operation.method,
                        "path": operation.path,
                        "operation_id": operation.operation_id,
                        "validation_errors": [
                            {
                                "json_path": "$",
                                "schema_path": "$",
                                "message": "Request body is required.",
                                "validator": "required",
                            }
                        ],
                    },
                )
            return await call_next(request)

        content_type = request.headers.get("content-type")
        if operation.request_body_schema_ref is None:
            if _is_json_content_type(content_type):
                return _problem_response(
                    request,
                    status_code=500,
                    detail={
                        "error": "internal_api_contract_missing_request_schema",
                        "message": "A JSON request body was received, but the internal API contract defines no JSON Schema for this operation.",
                        "method": operation.method,
                        "path": operation.path,
                        "operation_id": operation.operation_id,
                        "content_type": content_type,
                    },
                )
            return await call_next(request)

        if not _is_json_content_type(content_type):
            return _problem_response(
                request,
                status_code=415,
                detail={
                    "error": "unsupported_media_type",
                    "message": "Request body must be sent as JSON for this internal API contract.",
                    "method": operation.method,
                    "path": operation.path,
                    "operation_id": operation.operation_id,
                    "content_type": content_type,
                    "supported_media_types": list(operation.request_content_types),
                },
            )

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            return _problem_response(
                request,
                status_code=400,
                detail={
                    "error": "invalid_json_payload",
                    "message": "Request body is not valid JSON.",
                    "method": operation.method,
                    "path": operation.path,
                    "operation_id": operation.operation_id,
                    "line": exc.lineno,
                    "column": exc.colno,
                },
            )

        try:
            self._registry.validate_request_payload(request.method, route_path, payload)
        except InternalApiContractValidationError as exc:
            return _problem_response(
                request,
                status_code=422,
                detail={
                    "error": "contract_schema_validation_failed",
                    "message": "Request payload does not match the internal API contract schema.",
                    "method": exc.operation.method,
                    "path": exc.operation.path,
                    "operation_id": exc.operation.operation_id,
                    "validation_errors": [issue.as_dict() for issue in exc.issues],
                },
            )
        except InternalApiContractLookupError as exc:
            return _problem_response(
                request,
                status_code=500,
                detail={
                    "error": "internal_api_contract_lookup_failed",
                    "message": str(exc),
                    "method": request.method.upper(),
                    "path": route_path,
                },
            )

        return await call_next(request)