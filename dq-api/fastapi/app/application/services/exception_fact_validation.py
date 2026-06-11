from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.application.services.execution_engine_capabilities import ExecutionEngineCapability
from app.application.services.execution_engine_capabilities import ExecutionEngineCapabilityError
from app.application.services.execution_engine_capabilities import require_exception_fact_capability
from app.domain.entities import GxExecutionRunEntity


@dataclass(frozen=True)
class ExceptionFactValidationService:
    def require_exception_fact_collection_support(self, *, execution_context: GxExecutionRunEntity) -> ExecutionEngineCapability:
        try:
            return require_exception_fact_capability(str(execution_context.engineType or ""))
        except ExecutionEngineCapabilityError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "error": "violation_persistence_unavailable",
                    "message": str(exc),
                    "run_id": execution_context.id,
                    "engine_type": exc.engine_type or None,
                    "capability_error": exc.error_code,
                },
            ) from exc

    def validate_exception_fact_persistence_result(
        self,
        *,
        expected_count: int,
        persisted_count: int,
        run_id: str,
    ) -> None:
        if int(expected_count) == int(persisted_count):
            return

        raise HTTPException(
            status_code=503,
            detail={
                "error": "violation_persistence_unavailable",
                "message": "Exception fact persistence did not persist the expected number of rows",
                "run_id": run_id,
                "expected_count": int(expected_count),
                "persisted_count": int(persisted_count),
            },
        )


exception_fact_validation_service = ExceptionFactValidationService()
