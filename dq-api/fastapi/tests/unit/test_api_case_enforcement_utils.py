from app.middleware.api_case_enforcement import (
    _to_snake_key,
    _to_snake_payload,
    _is_api_path,
    _header_value,
    _set_header,
    _remove_header,
    _is_json_content_type,
)


def _to_camel_key(key: str) -> str:
    parts = str(key).split("_")
    if not parts:
        return ""
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _to_camel_payload(value):
    from collections.abc import Mapping, Sequence

    if isinstance(value, Mapping):
        return {_to_camel_key(str(key)): _to_camel_payload(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_to_camel_payload(item) for item in value]
    return value


def test_key_conversions_and_payload_transforms():
    assert _to_snake_key("camelValueX") == "camel_value_x"
    assert _to_camel_key("snake_value_x") == "snakeValueX"

    payload = {"SomeKey": {"NestedField": 1}, "listField": [{"InnerOne": 2}, "str"]}
    snake = _to_snake_payload(payload)
    assert "some_key" in snake and "nested_field" in snake["some_key"]
    assert isinstance(snake["list_field"][0]["inner_one"], int)

    camel = _to_camel_payload({"some_key": {"nested_field": 1}, "list_field": [{"inner_one": 2}]})
    assert "someKey" in camel and "nestedField" in camel["someKey"]


def test_headers_and_content_detection():
    headers = [(b"Content-Type", b"application/json; charset=utf-8"), (b"X-Foo", b"bar")]
    assert _header_value(headers, b"content-type").startswith("application/json")

    new = _set_header(headers, b"content-length", b"123")
    assert any(k.lower() == b"content-length" for k, _ in new)

    removed = _remove_header(new, b"x-foo")
    assert not any(k.lower() == b"x-foo" for k, _ in removed)

    assert _is_json_content_type("application/json; charset=utf-8")
    assert _is_api_path("/system/v1/health")
    assert not _is_api_path("/health")
