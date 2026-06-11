from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import json
import logging

LOG = logging.getLogger("dq.profiling.test_data")

_TEST_DATA_REQUEST_TTL_SECONDS = 3600


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _request_key(request_id: str) -> str:
    return f"test-data-request:{request_id}"


def _sample_value_for_attribute(attribute: dict[str, Any], index: int) -> object:
    field_name = str(attribute.get("name") or attribute.get("id") or "").lower()
    field_type = str(attribute.get("type") or "").lower()
    field_format = str(attribute.get("format") or "").lower()

    if "email" in field_name:
        return f"user{index + 1}@example.com"
    if "status" in field_name:
        return "active" if index % 2 == 0 else "inactive"
    if "date" in field_name or field_format in {"date", "date-time", "datetime"}:
        return (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()
    if field_type == "boolean":
        return index % 2 == 0
    if field_type in {"integer", "int", "number", "float", "double", "bigint", "smallint"}:
        return index + 1
    return f"val_{index + 1}"


def generate_test_data_result(payload: dict[str, Any]) -> dict[str, Any]:
    attributes = list(payload.get("attributes") or [])
    sample_count = max(0, int(payload.get("sample_count") or 0))

    samples = []
    if attributes:
        samples = [
            {
                str(attribute.get("name") or attribute.get("id") or ""): _sample_value_for_attribute(attribute, index)
                for attribute in attributes
                if str(attribute.get("name") or attribute.get("id") or "").strip()
            }
            for index in range(sample_count)
        ]

    return {
        "version_id": payload.get("version_id") or payload.get("target_id") or "",
        "version_name": payload.get("version_name"),
        "data_object_id": payload.get("data_object_id"),
        "attribute_count": len(attributes),
        "sample_count": sample_count,
        "samples": samples,
        "attributes": attributes,
        "generated_at": _current_timestamp(),
    }


def _read_request_record(redis_client: Any, request_id: str) -> dict[str, Any] | None:
    raw = redis_client.get(_request_key(request_id))
    return json.loads(raw) if raw else None


def _write_request_record(redis_client: Any, record: dict[str, Any]) -> None:
    redis_client.set(
        _request_key(str(record["request_id"])),
        json.dumps(record),
        ex=_TEST_DATA_REQUEST_TTL_SECONDS,
    )


def handle_test_data_job(data: dict[str, Any], redis_client: Any) -> dict[str, Any]:
    request_id = str(data.get("test_data_request_id") or "").strip()
    if not request_id:
        raise RuntimeError("test_data_request_id is required for test_data_generation jobs")

    record = _read_request_record(redis_client, request_id)
    if record is None:
        raise KeyError(f"test_data_request {request_id} not found")

    record["status"] = "started"
    record["started_at"] = record.get("started_at") or _current_timestamp()
    record["error_message"] = None
    _write_request_record(redis_client, record)

    try:
        result = generate_test_data_result(data.get("payload") if isinstance(data.get("payload"), dict) else {})
    except Exception as exc:
        record["status"] = "failed"
        record["completed_at"] = _current_timestamp()
        record["error_message"] = str(exc)
        _write_request_record(redis_client, record)
        raise

    record["status"] = "completed"
    record["completed_at"] = _current_timestamp()
    record["error_message"] = None
    record["result"] = result
    _write_request_record(redis_client, record)
    LOG.info("completed queued test data request %s", request_id)
    return result
