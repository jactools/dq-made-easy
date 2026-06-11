"""Live HTTP integration test for version metadata endpoints."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.integration

_GATEWAY_BASE = "http://localhost:9111"
_BACKEND_BASE = "http://localhost:4010"


def _to_snake_case(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return text.replace("-", "_").lower()


def _expected_manifest_versions() -> dict[str, object]:
    manifest_path = Path(__file__).resolve().parents[5] / "VERSION_MANIFEST.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_components = payload.get("components") or {}
    components = {
        _to_snake_case(key): str(value)
        for key, value in raw_components.items()
    } if isinstance(raw_components, dict) else {}
    return {
        "apps": payload.get("apps") or {},
        "components": components,
    }


def _get_json(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urlopen(url, timeout=8) as response:  # nosec B310 - controlled localhost URL in test
            status = int(getattr(response, "status", 0) or 0)
            body = response.read().decode("utf-8")
    except URLError as exc:
        pytest.skip(f"Live HTTP endpoint unreachable for integration test: {url} ({exc})")

    return status, json.loads(body)


def _assert_version_payload(payload: dict[str, object], expected: dict[str, object]) -> None:
    apps = payload["apps"]
    assert isinstance(apps["api"], str)
    assert apps["api"]
    assert apps["api"] == expected["apps"]["api"]
    assert apps["ui"] in {"unknown", expected["apps"]["ui"]}

    components = payload["components"]
    assert isinstance(components, dict)
    assert components in ({}, expected["components"])


def _assert_system_info_payload(payload: dict[str, object], expected: dict[str, object]) -> None:
    api_payload = payload["api"]
    assert isinstance(api_payload["version"], str)
    build_date = api_payload.get("build_date") or api_payload.get("buildDate")
    assert isinstance(build_date, str)

    version_apps = payload["versions"]["apps"]
    assert version_apps["api"] == expected["apps"]["api"]
    assert version_apps["ui"] in {"unknown", expected["apps"]["ui"]}

    version_components = payload["versions"]["components"]
    assert isinstance(version_components, dict)
    assert version_components in ({}, expected["components"])

    assert api_payload["version"] == expected["apps"]["api"]


def test_live_http_version_info_endpoints_return_manifest_values(live_db_url: str) -> None:
    _ = live_db_url
    expected = _expected_manifest_versions()

    gateway_version_status, gateway_version_payload = _get_json(f"{_GATEWAY_BASE}/system/v1/version-catalog")
    gateway_system_status, gateway_system_payload = _get_json(f"{_GATEWAY_BASE}/system/v1/system-info")
    backend_version_status, backend_version_payload = _get_json(f"{_BACKEND_BASE}/system/v1/version-catalog")
    backend_system_status, backend_system_payload = _get_json(f"{_BACKEND_BASE}/system/v1/system-info")

    assert gateway_version_status == 200
    assert gateway_system_status == 200
    assert backend_version_status == 200
    assert backend_system_status == 200

    _assert_version_payload(gateway_version_payload, expected)
    _assert_system_info_payload(gateway_system_payload, expected)
    _assert_version_payload(backend_version_payload, expected)
    _assert_system_info_payload(backend_system_payload, expected)
