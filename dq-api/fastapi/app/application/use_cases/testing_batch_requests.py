from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _payload_value(payload: Any, name: str) -> Any:
    if isinstance(payload, Mapping):
        if name in payload:
            return payload[name]
        camel_name = _snake_to_camel(name)
        if camel_name in payload:
            return payload[camel_name]
        return None
    if hasattr(payload, name):
        return getattr(payload, name)
    camel_name = _snake_to_camel(name)
    if hasattr(payload, camel_name):
        return getattr(payload, camel_name)
    return None


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _model_dump_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


@dataclass(slots=True)
class RunBatchTestRequestCommand:
    request_id: str


@dataclass(slots=True)
class BatchTestRequestExecutionResult:
    response_payload: dict[str, Any]
    rule_id: str | None = None


@dataclass(slots=True)
class BatchTestRequestExecutionServices:
    get_batch_test_request: GetBatchTestRequest
    build_execution_context: BuildExecutionContext
    run_batch_test_request: RunBatchTestRequest
    build_batch_test_execution_context_payload: BuildBatchTestExecutionContextPayload


GetBatchTestRequest = Callable[[str], Any | None]
BuildExecutionContext = Callable[[str], Awaitable[Any]]
RunBatchTestRequest = Callable[[str], Any]
BuildBatchTestExecutionContextPayload = Callable[[str, Any, str], tuple[dict[str, Any], dict[str, Any]]]


async def execute_batch_test_request(
    command: RunBatchTestRequestCommand,
    services: BatchTestRequestExecutionServices,
) -> BatchTestRequestExecutionResult:
    request_row = services.get_batch_test_request(command.request_id)
    rule_id = _normalize_optional_str(_payload_value(request_row, "rule_id"))
    execution_context = await services.build_execution_context(rule_id) if rule_id is not None else None

    response_payload = _model_dump_payload(services.run_batch_test_request(command.request_id))
    if request_row is None:
        response_payload["executionContext"] = None
        return BatchTestRequestExecutionResult(response_payload=response_payload, rule_id=None)

    correlation_id = _normalize_optional_str(_payload_value(request_row, "execution_correlation_id")) or f"corr-{uuid4().hex[:12]}"
    context_payload, _scheduler_handoff = services.build_batch_test_execution_context_payload(
        command.request_id,
        execution_context,
        correlation_id,
    )
    response_payload["executionContext"] = context_payload
    return BatchTestRequestExecutionResult(response_payload=response_payload, rule_id=rule_id)