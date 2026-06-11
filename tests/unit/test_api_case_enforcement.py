from types import SimpleNamespace
import json
from typing import Any

from app.middleware import api_case_enforcement as ace


def _to_camel_key(key: str) -> str:
    parts = str(key or "").split("_")
    if not parts:
        return ""
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _to_camel_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {_to_camel_key(str(k)): _to_camel_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_camel_payload(i) for i in value]
    return value


def test_key_transforms_and_payload_roundtrip():
    assert ace._to_snake_key("dataObjectId") == "data_object_id"
    # convert back using local helper (no compatibility wrappers in production code)
    assert _to_camel_key("data_object_id") == "dataObjectId"

    payload = {"someKey": [{"innerKey": "v"}], "listVal": [1, 2, {"deepKey": 3}]}
    snake = ace._to_snake_payload(payload)
    assert "some_key" in snake and "inner_key" in snake["some_key"][0]

    camel = _to_camel_payload(snake)
    assert "someKey" in camel and "innerKey" in camel["someKey"][0]


def test_is_api_path_and_content_helpers():
    # api paths: either /api/... or /<group>/v<number>/...
    assert ace._is_api_path("/group/v1/foo")
    assert ace._is_api_path("/api/v1/bar")
    assert not ace._is_api_path("/health")

    headers = [(b"X-Other", b"x"), (b"content-type", b"application/json; charset=utf-8")]
    assert ace._header_value(headers, b"content-type") == "application/json; charset=utf-8"
    out = ace._set_header(list(headers), b"content-length", b"123")
    assert any(k.lower() == b"content-length" for k, _ in out)
    removed = ace._remove_header(out, b"content-type")
    assert not any(k.lower() == b"content-type" for k, v in removed)
    assert ace._is_json_content_type("application/json")
    assert not ace._is_json_content_type("text/plain")


class FakeRequest:
    def __init__(self, path: str, headers: dict | None = None, body_bytes: bytes = b""):
        self.scope = {"type": "http", "path": path, "headers": []}
        if headers:
            for k, v in headers.items():
                self.scope["headers"].append((k.encode("ascii"), v.encode("latin-1")))
        self.headers = headers or {}
        self._body = body_bytes
        self.url = SimpleNamespace(path=path)

    async def body(self):
        return self._body


async def _call_dispatch(request, middleware):
    messages: list[dict] = []

    async def send_collector(message: dict) -> None:
        messages.append(message)

    async def receive_builder() -> dict:
        return {"type": "http.request", "body": request._body, "more_body": False}

    await middleware(request.scope, receive_builder, send_collector)

    # collect response body
    body = b"".join([m.get("body", b"") for m in messages if m.get("type") == "http.response.body"])
    # expose the captured scope (middleware should pass original scope to the app)
    return (body.decode("utf-8") if body else None), request


def test_dispatch_non_api_path():
    captured = {}

    async def asgi_app(scope, receive, send):
        # capture the incoming scope so tests can assert on headers/values
        captured["req"] = SimpleNamespace(scope=scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"resp", "more_body": False})

    m = ace.ApiCaseEnforcementMiddleware(asgi_app)
    req = FakeRequest("/health")

    import asyncio

    resp, captured_req = asyncio.get_event_loop().run_until_complete(_call_dispatch(req, m))
    assert resp == "resp"
    assert captured.get("req") is not None


def test_dispatch_api_json_normalization():
    captured = {}

    async def asgi_app(scope, receive, send):
        captured["req"] = SimpleNamespace(scope=scope)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"resp", "more_body": False})

    m = ace.ApiCaseEnforcementMiddleware(asgi_app)
    payload = json.dumps({"snake_key": 1}).encode("utf-8")
    req = FakeRequest("/group/v1/test", headers={"content-type": "application/json"}, body_bytes=payload)

    import asyncio

    resp, _ = asyncio.get_event_loop().run_until_complete(_call_dispatch(req, m))
    assert resp == "resp"
    # The captured_req should be a Request-like object with scope headers updated
    assert captured.get("req") is not None
    # Ensure content-type header present in scope (content-length may not be set)
    hdrs = dict((k.lower(), v) for k, v in captured["req"].scope.get("headers", []))
    assert b"content-type" in hdrs
