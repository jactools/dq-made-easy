from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.entities.gx_suite import build_gx_suite_entity
from app.domain.entities.gx_suite import build_gx_suite_expectation_entity


@dataclass(slots=True)
class GxSuiteValidationError(Exception):
    suite_id: str
    suite_version: int | None
    reason: str
    message: str

    def __str__(self) -> str:
        return self.message


def _resolved_target_ids(resolved_scope: Any) -> list[str]:
    if isinstance(resolved_scope, dict):
        values = resolved_scope.get("dataObjectVersionIds", [])
    else:
        values = getattr(resolved_scope, "dataObjectVersionIds", []) if resolved_scope is not None else []
    return [str(value).strip() for value in values or [] if str(value).strip()]


def assert_gx_suite_runnable(suite: Any) -> None:
    suite_id = str(getattr(suite, "suiteId", "") or "")
    suite_version = getattr(suite, "suiteVersion", None)

    if getattr(suite, "executionContract", None) is None:
        raise GxSuiteValidationError(
            suite_id=suite_id,
            suite_version=suite_version,
            message=f"GX suite '{suite_id}' is missing an execution_contract",
            reason="missing_execution_contract",
        )

    resolved_scope = getattr(suite, "resolvedExecutionScope", None)
    if not _resolved_target_ids(resolved_scope):
        raise GxSuiteValidationError(
            suite_id=suite_id,
            suite_version=suite_version,
            message=f"GX suite '{suite_id}' is missing resolved execution targets",
            reason="missing_targets",
        )

    gx_suite = build_gx_suite_entity(getattr(suite, "gxSuite", None))
    if gx_suite is None:
        raise GxSuiteValidationError(
            suite_id=suite_id,
            suite_version=suite_version,
            message=f"GX suite '{suite_id}' is missing gx_suite payload",
            reason="missing_gx_suite",
        )

    expectations = gx_suite.expectations
    if len(expectations) == 0:
        raise GxSuiteValidationError(
            suite_id=suite_id,
            suite_version=suite_version,
            message=f"GX suite '{suite_id}' has no executable expectations",
            reason="empty_expectations",
        )

    for index, expectation_payload in enumerate(expectations):
        expectation = build_gx_suite_expectation_entity(expectation_payload)
        if expectation is None:
            raise GxSuiteValidationError(
                suite_id=suite_id,
                suite_version=suite_version,
                message=f"GX suite '{suite_id}' expectation at index {index} is invalid",
                reason="invalid_expectation",
            )
        expectation_type = str(expectation.expectationType or "").strip()
        if not expectation_type:
            raise GxSuiteValidationError(
                suite_id=suite_id,
                suite_version=suite_version,
                message=f"GX suite '{suite_id}' expectation at index {index} is missing expectation_type",
                reason="invalid_expectation",
            )
        kwargs = expectation.kwargs
        if kwargs is None or len(kwargs) == 0:
            raise GxSuiteValidationError(
                suite_id=suite_id,
                suite_version=suite_version,
                message=f"GX suite '{suite_id}' expectation '{expectation_type}' is missing kwargs",
                reason="invalid_expectation",
            )
