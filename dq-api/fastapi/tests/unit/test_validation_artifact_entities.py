from app.domain.entities import GxArtifactAssignmentScopeEntity
from app.domain.entities import GxArtifactCompiledFromEntity
from app.domain.entities import GxArtifactEnvelopeEntity
from app.domain.entities import GxArtifactExecutionHintsEntity
from app.domain.entities import GxArtifactResolvedExecutionScopeEntity
from app.domain.entities import GxExecutionContractEntity
from app.domain.entities.gx_execution_run import GxExecutionIncrementalSelectionEntity
from app.domain.entities import GxExecutionSourceMaterializationEntity
from app.domain.entities import GxExecutionSourceTargetEntity
from app.domain.entities import GxExecutionTraceabilityEntity
from app.domain.entities import ValidationArtifactAssignmentScopeEntity
from app.domain.entities import ValidationArtifactCompiledFromEntity
from app.domain.entities import ValidationArtifactEngineArtifactEntity
from app.domain.entities import ValidationArtifactEnvelopeEntity
from app.domain.entities import ValidationArtifactExecutionHintsEntity
from app.domain.entities import ValidationArtifactResolvedExecutionScopeEntity
from app.domain.entities import ValidationArtifactRunPlanningEntity
from app.domain.entities import ValidationArtifactRunPlanningTraceabilityEntity
from app.domain.entities import build_gx_artifact_envelope_from_validation_artifact
from app.domain.entities import build_validation_artifact_envelope_entity
from app.domain.entities import build_validation_artifact_envelope_from_gx_artifact
from app.domain.entities.gx_suite import GxArtifactEvidencePolicyEntity
from app.domain.entities.gx_suite import GxArtifactFailedRowsPolicyEntity


def test_validation_artifact_aliasing() -> None:
    envelope = ValidationArtifactEnvelopeEntity(
        validationArtifactId="va_1",
        validationArtifactVersion=1,
        engineType="gx",
        engineArtifact=ValidationArtifactEngineArtifactEntity(
            engineType="gx",
            artifactKind="gx_expectation_suite",
            artifactSchemaVersion="gx-artifact-envelope/v1",
            payload={"suiteId": "gx_1"},
        ),
    )

    payload = envelope.model_dump(by_alias=True, exclude_none=True)
    assert payload["validation_artifact_id"] == "va_1"
    assert payload["engine_type"] == "gx"
    assert payload["engine_artifact"]["artifact_schema_version"] == "gx-artifact-envelope/v1"


def test_build_validation_artifact_from_gx_artifact_projects_gx_envelope() -> None:
    gx_envelope = GxArtifactEnvelopeEntity(
        suiteId="gx_suite_1",
        suiteVersion=2,
        artifactVersion="v1",
        assignmentScope=GxArtifactAssignmentScopeEntity(dataObjectId="do_1", datasetId="ds_1"),
        resolvedExecutionScope=GxArtifactResolvedExecutionScopeEntity(dataObjectVersionIds=["dov_1"]),
        gxSuite={"expectation_suite_name": "dq_suite"},
        compiledFrom=GxArtifactCompiledFromEntity(
            ruleIds=["rule_1"],
            compilerVersion="dq-compiler-7.3",
            generatedAt="2026-04-26T10:30:00Z",
        ),
        executionHints=GxArtifactExecutionHintsEntity(
            recommendedEngine="pyspark",
            primaryKeyFields=["id"],
            businessKeyFields=["business_id"],
            incrementalSelection=GxExecutionIncrementalSelectionEntity(
                selectionMode="new_partitions",
                selectedDataObjectVersionIds=["dov_1"],
            ),
            evidence=GxArtifactEvidencePolicyEntity(
                failedRows=GxArtifactFailedRowsPolicyEntity(
                    mode="sample",
                    limit=25,
                    includeRowIdentifier=True,
                    includePrimaryKey=True,
                ),
                emitCompiledArtifact=True,
                emitGeneratedSql=False,
            ),
        ),
        executionContract=GxExecutionContractEntity(
            engineTarget="pyspark",
            executionShape="join_pair",
            traceability=GxExecutionTraceabilityEntity(
                ruleId="rule_1",
                ruleVersionId="rv_1",
                gxSuiteId="gx_suite_1",
                gxSuiteVersion=2,
                dataObjectVersionId="dov_1",
            ),
            sourceMaterialization=GxExecutionSourceMaterializationEntity(
                landingZoneArtifactId="lz_1",
                landingZoneVersionId="lzv_1",
                outputLocation="s3://dq-landing-zone/output",
                joinType="inner",
                joinKeys=["customer_id"],
                leftSource=GxExecutionSourceTargetEntity(
                    dataObjectId="do_left",
                    dataObjectVersionId="dov_left",
                ),
                rightSource=GxExecutionSourceTargetEntity(
                    dataObjectId="do_right",
                    dataObjectVersionId="dov_right",
                ),
            ),
        ),
        savedBy="rule-compiler",
        sourcePipeline="rule-compiler",
        status="active",
    )

    validation_artifact = build_validation_artifact_envelope_from_gx_artifact(gx_envelope)

    assert validation_artifact.validationArtifactId == "gx_suite_1"
    assert validation_artifact.engineType == "gx"
    assert validation_artifact.executionHints.recommendedEngineTarget == "pyspark"
    assert validation_artifact.runPlanning.groupingKey == "data_object_version_id"
    assert validation_artifact.runPlanning.traceability is not None
    assert validation_artifact.runPlanning.traceability.validationArtifactVersion == 2
    assert validation_artifact.executionHints.evidence is not None
    assert validation_artifact.executionHints.evidence.failedRows is not None
    assert validation_artifact.executionHints.evidence.failedRows.mode == "sample"
    assert validation_artifact.executionHints.evidence.failedRows.limit == 25
    assert validation_artifact.executionHints.incrementalSelection is not None
    assert validation_artifact.executionHints.incrementalSelection.selectionMode == "new_partitions"
    assert validation_artifact.executionHints.incrementalSelection.selectedDataObjectVersionIds == ["dov_1"]
    assert validation_artifact.engineArtifact.artifactKind == "gx_expectation_suite"
    assert validation_artifact.engineArtifact.payload["suiteId"] == "gx_suite_1"


def test_build_gx_artifact_envelope_from_validation_artifact_projects_pyspark_native_payload() -> None:
    validation_artifact = ValidationArtifactEnvelopeEntity(
        validationArtifactId="psa_sales_order_quality",
        validationArtifactVersion=1,
        artifactContractVersion="v1",
        engineType="pyspark_native",
        assignmentScope=ValidationArtifactAssignmentScopeEntity(
            dataObjectId="do_sales_order",
            datasetId="ds_sales",
            dataProductId="odcs.dp.sales-001",
        ),
        resolvedExecutionScope=ValidationArtifactResolvedExecutionScopeEntity(
            dataObjectVersionIds=["dov_sales_order_v3"],
        ),
        compiledFrom=ValidationArtifactCompiledFromEntity(
            ruleIds=["rule_sales_order_not_null"],
            compilerVersion="dq-compiler-7.3",
            generatedAt="2026-04-26T16:30:00Z",
        ),
        executionHints=ValidationArtifactExecutionHintsEntity(
            recommendedEngineTarget="pyspark",
            primaryKeyFields=["order_id"],
            businessKeyFields=["sales_order_number"],
            incrementalSelection=GxExecutionIncrementalSelectionEntity(
                selectionMode="changed_slices",
                selectedDataObjectVersionIds=["dov_sales_order_v3"],
            ),
            supportedExecutionShapes=["single_object"],
        ),
        runPlanning=ValidationArtifactRunPlanningEntity(
            engineTarget="pyspark",
            executionShape="single_object",
            groupingKey="data_object_version_id",
            groupingValues=["dov_sales_order_v3"],
            traceability=ValidationArtifactRunPlanningTraceabilityEntity(
                ruleId="rule_sales_order_not_null",
                ruleVersionId="rv_sales_order_not_null_v4",
                validationArtifactId="psa_sales_order_quality",
                validationArtifactVersion=1,
                dataObjectVersionId="dov_sales_order_v3",
            ),
        ),
        engineArtifact=ValidationArtifactEngineArtifactEntity(
            engineType="pyspark_native",
            artifactKind="pyspark_native_plan",
            artifactSchemaVersion="pyspark-native-artifact-envelope/v1",
            payload={
                "artifact_id": "psa_sales_order_quality",
                "artifact_revision": 1,
                "artifact_version": "v1",
                "engine_type": "pyspark_native",
                "engine_target": "pyspark",
                "assignment_scope": {
                    "data_object_id": "do_sales_order",
                    "dataset_id": "ds_sales",
                    "data_product_id": "odcs.dp.sales-001",
                },
                "resolved_execution_scope": {
                    "data_object_version_ids": ["dov_sales_order_v3"],
                },
                "compiled_from": {
                    "rule_ids": ["rule_sales_order_not_null"],
                    "compiler_version": "dq-compiler-7.3",
                    "generated_at": "2026-04-26T16:30:00Z",
                },
                "execution_hints": {
                    "primary_key_fields": ["order_id"],
                    "business_key_fields": ["sales_order_number"],
                    "supported_execution_shapes": ["single_object"],
                },
                "traceability": {
                    "rule_id": "rule_sales_order_not_null",
                    "rule_version_id": "rv_sales_order_not_null_v4",
                    "artifact_id": "psa_sales_order_quality",
                    "artifact_revision": 1,
                    "data_object_version_id": "dov_sales_order_v3",
                },
                "pyspark_plan": {
                    "execution_shape": "single_object",
                    "input_mode": "spark_dataframe",
                    "checks": [
                        {
                            "check_id": "check_not_null_order_id",
                            "check_kind": "not_null",
                            "column_refs": ["order_id"],
                            "assertion": {"predicate_sql": "order_id IS NOT NULL"},
                            "severity": "error",
                        }
                    ],
                },
            },
        ),
    )

    gx_envelope = build_gx_artifact_envelope_from_validation_artifact(validation_artifact)

    assert gx_envelope.suiteId == "psa_sales_order_quality"
    assert gx_envelope.suiteVersion == 1
    assert gx_envelope.executionContract is not None
    assert gx_envelope.executionContract.engineType == "pyspark_native"
    assert gx_envelope.executionContract.executionShape == "single_object"
    assert gx_envelope.executionHints.recommendedEngine == "pyspark"
    assert gx_envelope.executionHints.incrementalSelection is not None
    assert gx_envelope.executionHints.incrementalSelection.selectionMode == "changed_slices"
    assert gx_envelope.gxSuite["pysparkPlan"]["execution_shape"] == "single_object"


def test_build_validation_artifact_envelope_accepts_snake_case_payload() -> None:
    envelope = build_validation_artifact_envelope_entity(
        {
            "validation_artifact_id": "va_2",
            "validation_artifact_version": 2,
            "artifact_contract_version": "v1",
            "engine_type": "gx",
            "assignment_scope": {"data_object_id": "do_2"},
            "resolved_execution_scope": {"data_object_version_ids": ["dov_2"]},
            "compiled_from": {
                "rule_ids": ["rule_2"],
                "compiler_version": "dq-compiler-7.3",
                "generated_at": "2026-04-26T10:30:00Z",
            },
            "execution_hints": {
                "recommended_engine_target": "pyspark",
                "primary_key_fields": ["id"],
                "evidence": {
                    "failed_rows": {
                        "mode": "sample",
                        "limit": 12,
                        "include_row_identifier": True,
                        "include_primary_key": False,
                    },
                    "emit_compiled_artifact": True,
                    "emit_generated_sql": False,
                },
            },
            "run_planning": {
                "engine_target": "pyspark",
                "execution_shape": "single_object",
                "grouping_key": "data_object_version_id",
                "traceability": {
                    "rule_id": "rule_2",
                    "rule_version_id": "rv_2",
                    "validation_artifact_id": "va_2",
                    "validation_artifact_version": 2,
                },
            },
            "engine_artifact": {
                "engine_type": "gx",
                "artifact_kind": "gx_expectation_suite",
                "artifact_schema_version": "gx-artifact-envelope/v1",
                "payload": {"suiteId": "gx_suite_2"},
            },
        }
    )

    assert envelope.validationArtifactId == "va_2"
    assert envelope.assignmentScope.dataObjectId == "do_2"
    assert envelope.runPlanning.executionShape == "single_object"
    assert envelope.executionHints.evidence is not None
    assert envelope.executionHints.evidence.failedRows is not None
    assert envelope.executionHints.evidence.failedRows.limit == 12