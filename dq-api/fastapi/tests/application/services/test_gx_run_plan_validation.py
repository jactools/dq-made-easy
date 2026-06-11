from app.application.services.gx_run_plan_validation import _validate_execution_contract_snapshot
from app.domain.entities.gx_execution_run import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxExecutionTraceabilityEntity


def test_validate_execution_contract_snapshot_accepts_streaming_and_micro_batch_shapes() -> None:
    for execution_shape in ("streaming", "micro_batch"):
        execution_contract = GxExecutionContractEntity(
            engineTarget="pyspark",
            executionShape=execution_shape,
            traceability=GxExecutionTraceabilityEntity(
                ruleId="rule-1",
                ruleVersionId="rule-version-1",
                gxSuiteId="suite-1",
                gxSuiteVersion=1,
                dataObjectVersionId="dov-1",
            ),
        )
        violations = _validate_execution_contract_snapshot(execution_contract)
        assert violations == []
