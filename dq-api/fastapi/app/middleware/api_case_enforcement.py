from __future__ import annotations

import json
import re
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any, Callable


_GROUP_VERSIONED_API_RE = re.compile(r"^/[a-z][a-z0-9-]*/v\d+(?:/|$)")


_CAMEL_TO_SNAKE_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_TO_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def _to_snake_key(key: str) -> str:
    first_pass = _CAMEL_TO_SNAKE_RE_1.sub(r"\1_\2", key)
    return _CAMEL_TO_SNAKE_RE_2.sub(r"\1_\2", first_pass).lower()


def _to_snake_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {_to_snake_key(str(key)): _to_snake_payload(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_snake_payload(item) for item in value]
    return value


def _normalize_json_response_body(body: bytes) -> bytes:
    if not body:
        return body
    try:
        payload = json.loads(body)
    except Exception:
        return body
    return json.dumps(
        _to_snake_payload(payload),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _is_api_path(path: str) -> bool:
    normalized = str(path or "")
    if normalized == "/api" or normalized.startswith("/api/"):
        return True
    return _GROUP_VERSIONED_API_RE.match(normalized) is not None


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    name_l = name.lower()
    for key, value in headers:
        if key.lower() == name_l:
            try:
                return value.decode("latin-1")
            except Exception:
                return None
    return None


def _set_header(headers: list[tuple[bytes, bytes]], name: bytes, value: bytes) -> list[tuple[bytes, bytes]]:
    name_l = name.lower()
    out = [(k, v) for (k, v) in headers if k.lower() != name_l]
    out.append((name, value))
    return out


def _remove_header(headers: list[tuple[bytes, bytes]], name: bytes) -> list[tuple[bytes, bytes]]:
    name_l = name.lower()
    return [(k, v) for (k, v) in headers if k.lower() != name_l]


def _is_json_content_type(raw: str | None) -> bool:
    return "application/json" in str(raw or "").lower()


class ApiCaseEnforcementMiddleware:
    """ASGI middleware that preserves snake_case API responses.

    Request bodies are left untouched so backend routes can enforce the canonical
    snake_case contract directly. JSON responses are normalized to snake_case.
    """

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        if not _is_api_path(path):
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope.get("headers") or [])
        normalize_response_body = False
        buffered_response_start: dict[str, Any] | None = None
        buffered_response_body: list[bytes] = []

        async def send_wrapped(message: dict[str, Any]) -> None:
            nonlocal buffered_response_start, normalize_response_body

            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                normalize_response_body = _is_json_content_type(_header_value(headers, b"content-type"))
                if normalize_response_body:
                    buffered_response_start = dict(message)
                    buffered_response_start["headers"] = headers
                    return
                await send(message)
                return

            if message.get("type") == "http.response.body" and buffered_response_start is not None:
                buffered_response_body.append(message.get("body", b""))
                if message.get("more_body", False):
                    return

                normalized_body = _normalize_json_response_body(b"".join(buffered_response_body))
                response_start = dict(buffered_response_start)
                response_headers = _remove_header(list(response_start.get("headers") or []), b"content-length")
                response_headers = _set_header(
                    response_headers,
                    b"content-length",
                    str(len(normalized_body)).encode("ascii"),
                )
                response_start["headers"] = response_headers

                await send(response_start)
                await send(
                    {
                        "type": "http.response.body",
                        "body": normalized_body,
                        "more_body": False,
                    }
                )
                buffered_response_start = None
                buffered_response_body.clear()
                normalize_response_body = False
                return

            await send(message)

        await self.app(scope, receive, send_wrapped)
