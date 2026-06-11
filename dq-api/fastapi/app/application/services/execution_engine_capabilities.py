from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionEngineCapability:
    engine_type: str
    supported_execution_shapes: frozenset[str]
    row_level_exception_facts_supported: bool
    record_identifier_resolution_supported: bool
    normalized_reason_codes_supported: bool
    supported_record_identifier_types: frozenset[str]
    sql_pushdown_supported: bool = False
    required_exception_fact_behavior: str = "fail_fast"


class ExecutionEngineCapabilityError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        engine_type: str,
        status_code: int = 503,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.engine_type = engine_type
        self.status_code = status_code


_CAPABILITIES: dict[str, ExecutionEngineCapability] = {
    "gx": ExecutionEngineCapability(
        engine_type="gx",
        supported_execution_shapes=frozenset({"single_object", "join_pair", "streaming", "micro_batch"}),
        row_level_exception_facts_supported=True,
        record_identifier_resolution_supported=True,
        normalized_reason_codes_supported=True,
        supported_record_identifier_types=frozenset({"primary_key", "business_key"}),
    ),
    "soda": ExecutionEngineCapability(
        engine_type="soda",
        supported_execution_shapes=frozenset({"single_object"}),
        row_level_exception_facts_supported=False,
        record_identifier_resolution_supported=False,
        normalized_reason_codes_supported=True,
        supported_record_identifier_types=frozenset(),
    ),
    "pyspark_native": ExecutionEngineCapability(
        engine_type="pyspark_native",
        supported_execution_shapes=frozenset({"single_object", "join_pair", "streaming", "micro_batch"}),
        row_level_exception_facts_supported=True,
        record_identifier_resolution_supported=True,
        normalized_reason_codes_supported=True,
        supported_record_identifier_types=frozenset({"primary_key", "business_key"}),
        sql_pushdown_supported=True,
    ),
}


def _normalize_engine_type(engine_type: str) -> str:
    normalized = str(engine_type or "").strip().lower()
    if not normalized:
        raise ExecutionEngineCapabilityError(
            "Exception fact persistence requires an explicit engine_type",
            error_code="missing_engine_type",
            engine_type="",
        )
    return normalized


def get_execution_engine_capability(engine_type: str) -> ExecutionEngineCapability:
    normalized_engine_type = _normalize_engine_type(engine_type)
    capability = _CAPABILITIES.get(normalized_engine_type)
    if capability is None:
        raise ExecutionEngineCapabilityError(
            f"Execution engine '{normalized_engine_type}' does not declare exception fact capabilities",
            error_code="unsupported_engine_type",
            engine_type=normalized_engine_type,
        )
    return capability


def require_exception_fact_capability(engine_type: str) -> ExecutionEngineCapability:
    capability = get_execution_engine_capability(engine_type)

    if not capability.row_level_exception_facts_supported:
        raise ExecutionEngineCapabilityError(
            f"Execution engine '{capability.engine_type}' does not support row-level exception facts required for exception persistence",
            error_code="row_level_exception_facts_unsupported",
            engine_type=capability.engine_type,
        )
    if not capability.record_identifier_resolution_supported:
        raise ExecutionEngineCapabilityError(
            f"Execution engine '{capability.engine_type}' does not support record identifier resolution required for exception persistence",
            error_code="record_identifier_resolution_unsupported",
            engine_type=capability.engine_type,
        )
    if not capability.normalized_reason_codes_supported:
        raise ExecutionEngineCapabilityError(
            f"Execution engine '{capability.engine_type}' does not support normalized reason codes required for exception persistence",
            error_code="normalized_reason_codes_unsupported",
            engine_type=capability.engine_type,
        )
    return capability


def require_sql_pushdown_capability(engine_type: str) -> ExecutionEngineCapability:
    capability = get_execution_engine_capability(engine_type)

    if not capability.sql_pushdown_supported:
        raise ExecutionEngineCapabilityError(
            f"Execution engine '{capability.engine_type}' does not support SQL pushdown planning",
            error_code="sql_pushdown_unsupported",
            engine_type=capability.engine_type,
        )
    return capability